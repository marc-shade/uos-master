#!/usr/bin/env python3
"""Browser -> disk-loaded copy dialog -> browser, executing the file service.

Only KERNAL disk LOAD, input/clock and optional graphics are host adapters.
The copy client, core launch path, UCI register transport and full comparisons
execute as 6502 code. Faults include corruption only after CLOSE.
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import posixpath
import re

from ci_files import Files
from ci_ultimate import Browser, FileSystem, ROOT, petscii
from profile_browser import DisplayBus
from uci_bus import UCIBus


def symbols(module):
    listing = (ROOT/'target'/f'{module}.lst').read_text(encoding='latin-1')
    return {m.group(2): int(m.group(1), 16) for m in re.finditer(
        r'^[.>]([0-9a-fA-F]+)\s+.*?\b([a-zA-Z_][a-zA-Z_0-9]*):', listing, re.M)}


class PathFiles(Files):
    def respond(self, command):
        if command[1] == 2:
            name = posixpath.normpath(posixpath.join(self.paths[command[0]], command[3:]))
            command = command[:3]+name
        return super().respond(command)


class CopyFilesystem(FileSystem):
    def __init__(self, folders, files):
        super().__init__(folders)
        self.files = PathFiles(files)
        self.before = None

    def __setitem__(self, address, value):
        if address == 0xdf1c and value == 1 and self.command[0] in (1, 2) and self.command[1] in range(2, 8):
            command = bytes(self.command)
            self.files.paths = self.paths.copy()
            if self.before:
                self.before(command)
            reply = self.files.respond(command)
            if command[1] in self.files.inject:
                reply = self.files.inject[command[1]](command, reply)
            self.packets = deque(reply)
            UCIBus.__setitem__(self, address, value)
        else:
            super().__setitem__(address, value)


class CopyBrowser(Browser):
    def __init__(self, payload=b'hello\0\xff', name=b'source.bin', real_display=False, entries=None):
        self.source = b'/'+name
        folders = {b'/': entries or [b'\x20'+name]}
        super().__init__(folders)
        bus = CopyFilesystem(folders, {self.source: payload})
        bus.ram = self.bus.ram
        self.fs = bus.files
        self.bus = DisplayBus(bus) if real_display else bus
        self.cpu.memory = self.bus
        self.csym = symbols('uos-copy')
        self.core = symbols('uos')
        self.real_display = real_display
        self.module = 'uos-ultimate'
        self.loads = []
        self.load_failure = None
        self.cancel_when = None
        self.ticks = 0
        self.steps = 0
        self.bus.ram[0x9b00] = 0
        for module in (('uos', 'uos-files', 'uos-gfx', 'uos-vdc') if real_display else ('uos', 'uos-files')):
            self.load(module)
        if real_display:
            self.bus.ram[0xcc24] = 1
            self.cpu.pc = 0xc000
            self.cpu.stPushWord(0x02ff)
            while self.cpu.pc != 0x0300:
                self.cpu.step()
            self.cpu.pc = 0x5000

    def load(self, module):
        prg = (ROOT/'target'/f'{module}.prg').read_bytes()
        origin = int.from_bytes(prg[:2], 'little')
        self.bus.ram[origin:origin+len(prg)-2] = prg[2:]

    def cv(self, name, size=1):
        address = self.csym[name]
        return int.from_bytes(self.bus.ram[address:address+size], 'little')

    def stub(self):
        c, ram = self.cpu, self.bus.ram
        if c.pc in (0xffd2, 0xffbd, 0xffba, 0xffd5):
            if c.pc == 0xffbd:
                self.load_name = petscii(bytes(ram[c.x+c.y*256:c.x+c.y*256+c.a]))
            if c.pc == 0xffba:
                assert (c.a, c.x, c.y) == (1, 8, 1), 'overlay loaded from wrong IEC device'
            if c.pc == 0xffd5:
                self.loads.append(self.load_name)
                if self.load_failure == self.load_name:
                    c.a = 4
                    c.p |= c.CARRY
                else:
                    assert self.load_name in ('uos-copy', 'uos-ultimate'), self.load_name
                    self.load(self.load_name)
                    self.module = self.load_name
                    c.p &= ~c.CARRY
            c.pc = c.stPopWord()+1
            return True
        if c.pc == 0x083b:
            self.ticks += 1
        if c.pc == 0x082c and self.module == 'uos-copy' and self.cancel_when and self.cancel_when(self):
            self.keys.appendleft(27)
            self.cancel_when = None
        if not self.real_display and c.pc == 0xc006:  # GFX_ON
            ram[2:34] = bytes([0xe7])*32
            c.a = c.x = c.y = 0xe7
            c.pc = c.stPopWord()+1
            return True
        if not self.real_display or c.pc in (0x082c, 0x083b, 0x083e):
            return super().stub()
        return False

    def guards(self):
        ram = self.bus.ram
        assert ram[0x7350:0x7400] == bytes([0xb6])*0xb0, 'settings/adjacent RAM changed'
        for lo, hi in ((0x7e02, 0x7e10), (0x7e18, 0x8000)):
            assert ram[lo:hi] == bytes([0xc7])*(hi-lo), f'handoff overflow at {lo:04x}'
        assert ram[0x9000:0x9100] == bytes([0xd8])*256, 'controls changed'
        assert self.bus.paths == {1: b'/shell-place', 2: b'/'}, self.bus.paths
        assert not self.bus.discarded, 'ACK discarded unread packet'
        assert self.cpu.sp == 255 and ram[0x9b00] == 1, 'overlay leaked stack/app registrations'

    def run(self, key=None, copy=None, leave=False):
        if key is not None:
            self.keys.append(key)
        if copy is None:
            copy = self.module == 'uos-copy'
        module = 'uos-copy' if copy else 'uos-ultimate'
        idle = self.csym['input_loop'] if copy else self.sym['input_loop']
        for steps in range(60000000):
            if self.cpu.pc == 0x1000:
                assert leave, 'unexpected desktop fallback'
                return
            if self.module == module and self.cpu.pc == idle and steps and not self.keys:
                self.steps += steps
                self.guards()
                return
            if not self.stub():
                pc = self.cpu.pc
                assert (0x0801 <= pc < 0x1000 or 0x4100 <= pc < 0x6900 or
                        0x8a00 <= pc < 0x9b00 or 0xc000 <= pc < 0xd000), hex(pc)
                self.cpu.step()
        raise AssertionError('copy/browser failed to reach expected input loop')

    def destination(self, path):
        self.run(0x15)
        for byte in path:
            # Real GETIN: unshifted a-z = $41-$5a, shifted A-Z = $c1-$da.
            self.run(byte-32 if 97 <= byte <= 122 else byte+128 if 65 <= byte <= 90 else byte)
        assert bytes(self.bus.ram[0x6900:0x6900+len(path)+1]) == path+b'\0'

    def finished(self, result=0, size=None):
        assert self.cv('phase') == 3 and self.cv('result') == result, (
            self.cv('phase'), self.cv('result'), self.vdc.get(18))
        if result == 0:
            assert self.cv('copied', 4) == size and self.cv('checked', 4) == size
            assert 'Copy verified' in self.vdc[16] if not self.real_display else True
        assert self.fs.handles == {1: None, 2: None}
        assert bytes(self.bus.ram[0x4122:0x4124]) == b'\0\0'

    def frame(self):
        return bytes(self.bus.ram[0xa000:0xbf40]), bytes(self.bus.vdc.video[:0x1000])


def success_and_return():
    payload = bytes((i*73+i//256*17+i//65536*29+11)&255 for i in range(66053))
    name = b'source-'+b'n'*500+b'.bin'
    b = CopyBrowser(payload, name)
    b.run()
    b.run(ord('C'), copy=True)
    assert b.csym['copy_end'] < 0x6900
    assert bytes(b.bus.ram[0x7c00:0x7e00]) == name+b'\0'
    b.run(13)
    b.finished(size=len(payload))
    assert b.fs.files[b'/copy.bin'] == payload and b.fs.files[b.source] == payload
    opens = [cmd for cmd in b.bus.commands if cmd[1] == 2]
    assert opens == [b'\x02\x02\x01'+name, b'\x01\x02\x07/copy.bin',
                     b'\x02\x02\x01'+name, b'\x01\x02\x01/copy.bin']
    assert b.ticks >= 260
    b.run(27, copy=False)
    assert b.names() == [name]
    for _ in range(32):
        b.run(0xc3, copy=True)
        b.run(27, copy=False)
    assert b.loads == ['uos-copy', 'uos-ultimate']*33
    return dict(bytes=len(payload), source_name_bytes=len(name), stack_roundtrips=33,
                bytes_sha256=hashlib.sha256(payload).hexdigest(), instructions=b.steps)


def editor_and_mouse():
    b = CopyBrowser()
    b.run()
    # Browser release-edge Copy button, followed by dialog release-edge Copy.
    for button in (0, 0x10):
        b.button = button
        b.bus.ram[0xd000], b.bus.ram[0xd010], b.bus.ram[0xd001] = 174, 0, 67
        b.run(copy=button == 0x10)
    path = b'/'+b'/'.join([b'a'*127]*6)+b'/'+b'Z'*120+b'.bin'
    assert len(path) == 893
    b.destination(path)
    b.run(ord('x'))
    assert b.cv('length', 2) == 893
    b.run(0x13)
    b.run(0x1d)
    b.run(0x14)  # delete leading slash, shift a tail crossing three pages
    assert b.cv('length', 2) == 892 and b.bus.ram[0x6900] == ord('a')
    b.run(ord('/'))
    assert bytes(b.bus.ram[0x6900:0x6900+894]) == path+b'\0'
    b.run(13)
    b.finished(size=7)
    assert b.fs.files[path] == b'hello\0\xff'
    assert b'\x01\x02\x07'+path in b.bus.commands
    b.run(ord('E'))
    b.destination(b'/Case-sensitive File.bin')
    for button in (0, 0x10):
        b.button = button
        b.bus.ram[0xd000], b.bus.ram[0xd010], b.bus.ram[0xd001] = 74, 0, 229
        b.run()
    b.finished(size=7)
    assert b.fs.files[b'/Case-sensitive File.bin'] == b'hello\0\xff'
    return dict(max_destination=893, max_path_copy_verified=True,
                insertion_delete_across_pages=True, mouse_copy=True)


def faults():
    results = []
    for case, expected in (('exists', 255), ('short_write', 0xe6), ('short_read', 0xe5),
                           ('disk_full', 255), ('reopen_corruption', 0xe6),
                           ('source_size_change', 0xe6), ('reopen_tail_corruption', 0xe6),
                           ('close_error', 74), ('final_close_error', 74),
                           ('cancel_copy', 0xe9), ('cancel_verify', 0xe9),
                           ('foreign_handle', 0xe2), ('relative_path', 0xe0),
                           ('long_component', 0xe0)):
        payload = bytes(range(256))*5+b'last'
        b = CopyBrowser(payload)
        b.run()
        b.run(ord('C'), copy=True)
        if case == 'exists':
            b.fs.files[b'/copy.bin'] = bytearray(b'keep me')
        elif case == 'short_write':
            b.fs.write_limit = 10
        elif case == 'short_read':
            b.fs.read_limit = 10
        elif case == 'disk_full':
            b.fs.inject[5] = lambda cmd, reply: [(b'', b'DISK IS FULL')]
        elif case in ('reopen_corruption', 'source_size_change', 'reopen_tail_corruption'):
            def corrupt(cmd, case=case):
                if cmd == b'\x01\x02\x01/copy.bin':
                    b.fs.files[b'/copy.bin'][-1 if case == 'reopen_tail_corruption' else 700] ^= 1
                if case == 'source_size_change' and cmd == b'\x02\x02\x01source.bin' and b.cv('phase') == 2:
                    b.fs.files[b.source].append(3)
            b.bus.before = corrupt
        elif case in ('close_error', 'final_close_error'):
            b.fs.inject[3] = lambda cmd, reply: ([(b'', b'74,CLOSE FAILED')]
                if case == 'close_error' or b.cv('phase') == 2 else reply)
        elif case.startswith('cancel_'):
            phase = 1 if case == 'cancel_copy' else 2
            counter = 'copied' if phase == 1 else 'checked'
            b.cancel_when = lambda b, phase=phase, counter=counter: b.cv('phase') == phase and b.cv(counter, 4) >= 512
        elif case == 'foreign_handle':
            b.fs.handles[2] = dict(name=b.source, mode=1, pos=9)
        elif case == 'relative_path':
            b.destination(b'relative.bin')
        elif case == 'long_component':
            b.destination(b'/'+b'x'*128)
        b.run(13)
        assert b.cv('phase') == 3 and b.cv('result') == expected, (case, b.cv('result'))
        assert 'Copy verified' not in b.vdc[16], (case, b.vdc)
        assert not any(cmd[1] in (9, 10, 11, 0x11) for cmd in b.bus.commands), 'copy deleted/moved/chdir'
        before = len(b.bus.commands)
        b.run()
        b.run()
        assert len(b.bus.commands) == before, 'idle dialog retried a failed operation'
        if case == 'disk_full':
            assert sum(cmd[1] == 5 for cmd in b.bus.commands) == 1
        if case == 'exists':
            assert b.fs.files[b'/copy.bin'] == b'keep me'
        if case == 'foreign_handle':
            assert b.fs.handles[2]['pos'] == 9
        elif case in ('close_error', 'final_close_error'):
            assert bytes(b.bus.ram[0x4122:0x4124]) == b'\xff\xff'
            b.run(ord('E'))
            assert b.cv('phase') == 3
            del b.fs.inject[3]
            b.run(ord('R'))
            assert bytes(b.bus.ram[0x4122:0x4124]) == b'\0\0'
        else:
            b.finished(expected)
        if case == 'cancel_copy':
            assert b.fs.files[b'/copy.bin'] == payload[:512] and b.cv('copied', 4) == 512
        if case == 'cancel_verify':
            assert b.fs.files[b'/copy.bin'] == payload and b.cv('checked', 4) == 512
        results.append(case)
    return dict(failures=results, no_overwrite_delete_or_write_retry=True)


def empty_and_load_failure():
    b = CopyBrowser(b'')
    b.run()
    b.run(ord('C'), copy=True)
    b.run(13)
    b.finished(size=0)
    assert b.fs.files[b'/copy.bin'] == b''
    b = CopyBrowser()
    b.run()
    b.load_failure = 'uos-copy'
    b.run(ord('C'), copy=True, leave=True)
    assert not b.fs.files.get(b'/copy.bin') and b.fs.handles == {1: None, 2: None}
    b = CopyBrowser()
    b.load('uos-copy')
    b.module = 'uos-copy'
    b.run(copy=True)
    assert b.cv('valid') == 0 and b.cv('result') == 0xe0
    assert not b.bus.commands
    return dict(empty_verified=True, load_failure_to_desktop=True, invalid_handoff_no_io=True)


def saved_page():
    entries = [b'\x20'+f'entry-{i:04d}'.encode() for i in range(270)]
    entries[258] = b'\x20source.bin'
    b = CopyBrowser(entries=entries)
    b.run()
    # Arrive beyond ordinal 255 through the real directory parser.
    for _ in range(32):
        b.run(ord('N'))
    b.run(0x11)
    b.run(0x11)
    assert b.value('base', 2) == 256 and b.value('selected') == 2
    b.run(ord('C'), copy=True)
    b.run(13)
    b.finished(size=7)
    b.run(27, copy=False)
    assert b.value('base', 2) == 256 and b.value('selected') == 2
    assert b.names()[2] == b'source.bin'
    return dict(base=256, selected=2, full_selected_name=True)


def display(report_dir):
    b = CopyBrowser(bytes(range(256))*3, real_display=True)
    b.run()
    original = b.frame()
    b.run(ord('C'), copy=True)
    first = b.frame()
    b.run(ord('x'))
    b.run(0x14)
    assert b.frame() == first, 'editor failed whole VIC/VDC erase roundtrip'
    b.run(13)
    b.finished(size=768)
    final = b.frame()
    assert first != final
    b.run(27, copy=False)
    assert b.frame() == original, 'browser return failed complete frame restoration'
    b.run(ord('C'), copy=True)
    b.destination(b'/Wi.im.Wi-im-0123456789.WWWWWWWWWWWW.end')
    caret_positions = []
    for key in (0, 0x9d, 0x9d, 0x13, 0x1d):
        b.run(key or None)
        bitmap = b.frame()[0]
        # '^' is the only glyph on the caret row. Check actual pixels against
        # the editor byte position, including scrolling and nine-bit VIC X.
        xs = [x for y in range(84, 94) for x in range(24, 304)
              if bitmap[(y//8)*320+(x//8)*8+y%8] & (0x80 >> (x%8))]
        expected_x = 24+8*(b.cv('cursor', 2)-b.cv('scroll', 2))
        assert min(xs) == expected_x and max(xs) == expected_x+4, (key, min(xs), max(xs), expected_x)
        caret_positions.append(expected_x)
    if report_dir:
        for label, frame in (('edit', first), ('verified', final), ('browser', original)):
            for suffix, data in zip(('vic', 'vdc'), frame):
                (report_dir/f'{label}.{suffix}.bin').write_bytes(data)
    return dict(editor_and_browser_full_frames=True, caret_pixel_positions=caret_positions,
                verified_VIC_sha256=hashlib.sha256(final[0]).hexdigest())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'build': {n: hashlib.sha256((ROOT/'target'/n).read_bytes()).hexdigest()
                        for n in ('uos-copy.prg', 'uos-files.prg', 'uos-ultimate.prg', 'uos.prg')}, 'checks': {}}
    for check in (success_and_return, editor_and_mouse, faults, empty_and_load_failure, saved_page, display):
        result = check(args.report.parent if args.report else None) if check == display else check()
        report['checks'][check.__name__] = result
        print('PASS:', check.__name__, result, flush=True)
        if args.report:
            args.report.write_text(json.dumps(report, indent=2)+'\n')
    report['passed'] = True
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
