#!/usr/bin/env python3
"""Run the assembled browser and UCI transport with a cartridge filesystem model.

Graphics, keyboard and button calls are host adapters; browser navigation,
packet parsing, command construction and the register transport execute as 6502
code. VICE and physical C128 checks cover the real display and input drivers.
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import posixpath
import re
import subprocess
import tempfile

from py65.devices.mpu6502 import MPU
from uci_bus import ROOT, UCIBus, load_driver


def symbols():
    text = (ROOT / 'target/uos-ultimate.lst').read_text(encoding='latin-1')
    return {m.group(2): int(m.group(1), 16) for m in re.finditer(
        r'^[.>]([0-9a-fA-F]+)\s+.*?\b([a-zA-Z_][a-zA-Z_0-9]*):', text, re.M)}


def petscii(value):
    return bytes(c & 0x7f if 0xc1 <= c <= 0xda else c + 32 if 0x41 <= c <= 0x5a
                 else c for c in value).decode('ascii', 'replace')


class FileSystem(UCIBus):
    def __init__(self, folders, present=True):
        super().__init__(present=present)
        self.folders = folders
        self.paths = {1: b'/shell-place', 2: b'/'}
        self.reject_open = False

    def __setitem__(self, address, value):
        if address == 0xdf1c and value == 1:
            command = bytes(self.command)
            assert command[0] == 2, f'Browser changed another DOS context: {command!r}'
            op, path = command[1], self.paths[2]
            status, data = b'00,OK', b''
            if op == 0x12:
                data = path if path.endswith(b'/') else path + b'/'
            elif op == 0x11:
                component = command[2:]
                assert component and b'\0' not in component
                dest = posixpath.normpath(posixpath.join(path, component))
                if dest not in self.folders:
                    status = b'83,NO SUCH DIRECTORY'
                else:
                    self.paths[2] = dest
            elif op == 0x13:
                status = b'86,CANNOT READ DIRECTORY' if self.reject_open else (
                    b'00,OK' if self.folders[path] else b'01,DIRECTORY EMPTY')
            elif op == 0x14:
                entries = self.folders[path]
                self.packets = deque((name, b'00,OK' if i == len(entries)-1 else b'')
                                     for i, name in enumerate(entries))
            else:
                raise AssertionError(f'Unexpected/mutating browser command: {command.hex()}')
            if op != 0x14:
                self.packets = deque([(data, status)])
        super().__setitem__(address, value)


class Browser:
    def __init__(self, folders, present=True):
        self.bus = FileSystem(folders, present)
        load_driver(self.bus)
        self.sym = symbols()
        self.prg = (ROOT / 'target/uos-ultimate.prg').read_bytes()
        assert int.from_bytes(self.prg[:2], 'little') == 0x5000
        assert 0x5000 + len(self.prg) - 2 <= 0x6000
        self.bus.ram[0x5000:0x5000 + len(self.prg)-2] = self.prg[2:]
        self.bus.ram[0x7350:0x7400] = bytes([0xb6]) * 0xb0
        self.bus.ram[0x7800:0x8000] = bytes([0xc7]) * 0x800
        self.bus.ram[0x9000:0x9100] = bytes([0xd8]) * 0x100
        self.bus.ram[0xba] = 8
        self.cpu = MPU(memory=self.bus, pc=0x5000)
        self.keys = deque()
        self.button = 0x10
        self.vdc, self.vic = {}, []
        self.cancel_after = None

    def value(self, name, size=1):
        a = self.sym[name]
        return int.from_bytes(self.bus.ram[a:a+size], 'little')

    def names(self):
        return [bytes(self.bus.ram[0x6000+i*512:0x6200+i*512]).split(b'\0')[0]
                for i in range(self.value('count'))]

    def cstring(self, address):
        result = bytes(self.bus.ram[address:address+1024]).split(b'\0')[0]
        assert len(result) < 1024, f'Unterminated display string at {address:#x}'
        return result

    def stub(self):
        c = self.cpu
        pc = c.pc
        if pc not in (0x0820, 0x082c, 0x0835, 0x0838, 0x083b, 0x083e,
                      0xc00c, 0xc015, 0xc01e):
            return False
        if pc == 0xc01e:
            self.vic.append((self.bus.ram[2] | self.bus.ram[3] << 8,
                             self.bus.ram[4], petscii(self.cstring(
                                 self.bus.ram[0x14] | self.bus.ram[0x15] << 8))))
        if pc == 0x0835:
            text = petscii(self.cstring(self.bus.ram[0x14] | self.bus.ram[0x15] << 8))
            assert c.a < 25 and c.x + len(text) <= 80, (c.a, c.x, text)
            row = self.vdc.get(c.a, ' ' * 80)
            self.vdc[c.a] = row[:c.x] + text + row[c.x+len(text):]
        if pc == 0x0838:
            self.vdc[c.a] = ' ' * 80
        if pc == 0x082c:
            if self.cancel_after is not None and self.bus.accepted >= self.cancel_after:
                c.a, self.cancel_after = 0x1b, None
            else:
                c.a = self.keys.popleft() if self.keys else 0
        elif pc == 0x083e:
            c.a = self.button
        else:
            # Deliberately destroy caller scratch, as the public drawing and
            # tick contracts permit. Browser-owned pointers live elsewhere.
            self.bus.ram[2:34] = bytes([0xe7]) * 32
            c.a = 0xe7
        c.x = c.y = 0xe7
        c.p = (c.p & ~(c.ZERO | c.NEGATIVE)) | (c.ZERO if c.a == 0 else c.a & 0x80)
        c.pc = c.stPopWord() + 1
        return True

    def run(self, key=None, leave=False):
        if key is not None:
            self.keys.append(key)
        left_loop = False
        for _ in range(5000000):
            if self.cpu.pc == 0x1000:
                assert leave, 'Browser unexpectedly exited'
                assert self.bus.ram[0xba] == 8
                return
            if self.cpu.pc == self.sym['input_loop'] and left_loop and not self.keys:
                assert not leave, 'Browser did not exit'
                self.guards()
                return
            left_loop = True
            if not self.stub():
                assert (0x5000 <= self.cpu.pc < 0x6000 or 0x8a00 <= self.cpu.pc < 0x9b00), hex(self.cpu.pc)
                self.cpu.step()
        raise AssertionError('Browser did not reach its input loop')

    def guards(self):
        assert self.bus.ram[0x7350:0x7400] == bytes([0xb6])*0xb0, 'Settings overwritten'
        assert self.bus.ram[0x7800:0x8000] == bytes([0xc7])*0x800, 'Command buffer overflow'
        assert self.bus.ram[0x9000:0x9100] == bytes([0xd8])*0x100, 'Controls overwritten'
        assert self.bus.paths[1] == b'/shell-place'
        assert not self.bus.discarded, 'ACK discarded an unread packet'

    def click(self, x, y, leave=False):
        sx = x + 24
        self.bus.ram[0xd000] = sx & 255
        self.bus.ram[0xd010] = sx >> 8
        self.bus.ram[0xd001] = y + 50
        self.button = 0
        self.run()
        self.button = 0x10
        self.run(leave=leave)


def check_navigation():
    entries = [b'\x10' + f'folder-{i:04d}'.encode() for i in range(1100)]
    b = Browser({b'/': entries, b'/folder-0256': [], b'/folder-0000': []})
    b.run()
    assert b.names() == [e[1:] for e in entries[:8]] and b.value('more') == 1
    assert 'items 1-8 +' in b.vdc[22]
    for _ in range(8):
        b.run(0x11)
    assert b.value('base', 2) == 8 and b.names()[0] == entries[8][1:]
    b.run(0x91)
    assert b.value('base', 2) == 0 and b.value('selected') == 7
    for i in range(32):
        b.run(0xce if i & 1 else ord('N'))  # shifted and unshifted PETSCII
    assert b.value('base', 2) == 256 and b.names()[0] == entries[256][1:]
    assert 'items 257-264 +' in b.vdc[22]
    b.run(13)
    assert b.bus.paths[2] == b'/folder-0256' and not b.names()
    b.run(ord('U'))
    assert b.bus.paths[2] == b'/' and b.names()[0] == entries[0][1:]
    b.click(90, 176)  # Open, within the third toolbar region
    assert b.bus.paths[2] == b'/folder-0000'
    b.click(170, 176)  # Root
    assert b.bus.paths[2] == b'/'
    b.click(245, 176)  # Next, crosses the VIC low-byte boundary
    assert b.value('base', 2) == 8
    b.click(275, 65)  # full-width row hit in the right half
    assert b.value('selected') == 2
    b.click(288, 176, leave=True)  # Exit
    assert b.cpu.pc == 0x1000


def check_long_names():
    name = b'long-' + b'x' * 290 + b'-END'
    full = b'z' * 511
    b = Browser({b'/': [b'\x10'+name, b'\x20'+full], b'/'+name: []})
    b.run()
    assert b.names() == [name, full]
    for _ in range(7):
        b.run(0x1d)
    assert b.value('nameoff', 2) == 224
    assert '-END' in ''.join(b.vdc.get(i, '') for i in range(14, 21))
    b.run(13)
    assert any(c == b'\x02\x11'+name for c in b.bus.commands)
    assert b.bus.paths[2] == b'/'+name
    b.run(ord('P'))
    b.run(0x1d)
    assert b.value('nameoff', 2) == 32
    b.run(ord('/'))
    b.run(0x11)
    assert b.names()[1] == full
    b.run(13)  # regular file is not an enterable filesystem
    assert '83,' in b.vdc[22] and b.value('count') == 2


def check_failures():
    b = Browser({b'/': []}, present=False)
    b.run()
    assert not b.names() and 'unavailable' in b.vdc[22]
    b.run(27, leave=True)
    for packet in (b'\x10', b'\x10bad\0tail', b'\x10bad/path', b'\x10'+b'z'*600):
        b = Browser({b'/': [packet]})
        b.run()
        assert b.value('count') == 0 and 'invalid' in b.vdc[22], (packet[:10], b.vdc)
        b.bus.folders[b'/'] = [b'\x10ok']
        b.run(ord('R'))
        assert b.names() == [b'ok']
    b = Browser({b'/': [b'\x10one']})
    b.bus.reject_open = True
    b.run()
    assert '86,' in b.vdc[22]
    b.bus.reject_open = False
    b.run(ord('R'))
    b.cancel_after = b.bus.accepted + 2
    b.run(ord('R'))
    assert 'cancelled' in b.vdc[22] and not b.names()
    b.run(ord('R'))
    assert b.names() == [b'one']


def check_bounds():
    names = [bytes([0x61+i])*511 for i in range(8)]
    b = Browser({b'/': [b'\0'+name for name in names]})
    b.run()
    assert b.names() == names and b.value('more') == 0
    assert b.bus.ram[0x6fff] == 0 and b.bus.ram[0x7000:0x7002] == b'/\0'
    b.run(ord('N'))
    assert b.value('base', 2) == 0
    b = Browser({b'/': [b'\0'+f'file-{i}'.encode() for i in range(10)]})
    b.run()
    b.run(ord('N'))
    assert b.names() == [b'file-8', b'file-9'] and b.value('more') == 0
    assert 'items 9-10 .' in b.vdc[22]
    for _ in range(3):
        b.run(0x11)
    assert b.value('selected') == 1 and b.value('base', 2) == 8
    b.run(0x91)
    b.run(0x91)
    assert b.value('selected') == 7 and b.value('base', 2) == 0
    b = Browser({b'/': []})
    b.bus.paths[2] = b'/'+b'path'*128
    b.run()
    assert not b.names() and 'invalid' in b.vdc[22]
    b.run(ord('/'))
    assert b.bus.paths[2] == b'/' and 'empty' in b.vdc[22]


def check_capture_probe():
    with tempfile.TemporaryDirectory(prefix='uos-capture-probe-') as directory:
        prg = Path(directory)/'probe.prg'
        subprocess.run(['64tass', '-a', str(ROOT/'probes/uci-stream.asm'), '-o', str(prg)],
                       check=True, capture_output=True)
        code = prg.read_bytes()[2:]
    for skip in (0, 256):
        packets = [b'\x20'+f'entry-{i:04d}'.encode() for i in range(1100)]
        bus = UCIBus([(p, b'00,OK' if i == 1099 else b'') for i, p in enumerate(packets)])
        load_driver(bus)
        bus.ram[0x5000:0x5000+len(code)] = code
        bus.ram[0x5500:0x5502] = b'\x02\x14'
        bus.ram[0x5f00:0x5f0f] = b'\x34\x12\x02\0'+bytes(9)+skip.to_bytes(2, 'little')
        bus.ram[0x7350:0x7400] = bytes([0xb6])*0xb0
        cpu = MPU(memory=bus, pc=0x5000)
        cpu.stPushWord(0x02ff)
        for _ in range(3000000):
            if cpu.pc == 0x0300:
                break
            cpu.step()
        else:
            raise AssertionError('Capture probe did not finish')
        assert bus.ram[0x5f04:0x5f07] == b'\x01\0\0'
        assert int.from_bytes(bus.ram[0x5f07:0x5f09], 'little') == 1100
        assert bus.ram[0x5f09] == 1  # bounded host capture fills; transaction still completes
        end = int.from_bytes(bus.ram[0x5f0a:0x5f0c], 'little')
        offset, i = 0x6000, skip
        while offset < end:
            length = int.from_bytes(bus.ram[offset:offset+2], 'little')
            assert bus.ram[offset+2] == 0
            assert bus.ram[offset+3:offset+3+length] == packets[i]
            offset += 3+length
            i += 1
        assert offset == end <= 0x7300
        assert bus.ram[0x7350:0x7400] == bytes([0xb6])*0xb0
        assert bus.ram[0x033c:0x033e] == b'\x34\x12'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'build': {n: hashlib.sha256((ROOT/'target'/n).read_bytes()).hexdigest()
                        for n in ('uos.prg', 'uos-net.prg', 'uos-ultimate.prg')}, 'checks': []}
    for fn in (check_navigation, check_long_names, check_failures, check_bounds, check_capture_probe):
        fn()
        report['checks'].append(fn.__name__)
        print(f'PASS: {fn.__name__}', flush=True)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
