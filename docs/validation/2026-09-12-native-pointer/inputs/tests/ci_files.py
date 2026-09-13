#!/usr/bin/env python3
"""Run the assembled shared file service and UCI transport against a DOS model.

The model stores actual bytes/positions for both contexts, including short
successful writes and malformed replies. No service routine is stubbed.
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path

from py65.devices.mpu6502 import MPU
from uci_bus import UCIBus, load_driver
from ci_desktop import symbol

ROOT = Path(__file__).resolve().parents[1]
OPEN, CLOSE, READ, WRITE, SEEK, TELL, CLOSEALL = range(0x4100, 0x4115, 3)
COUNT, SIZE, POS, EOF, MODES, STATUS = 0x4117, 0x4119, 0x411d, 0x4121, 0x4122, 0x4124


class Files(UCIBus):
    def __init__(self, files=None):
        super().__init__([])
        self.ram[:] = bytes((i*17+91) & 255 for i in range(65536))
        self.files = {name: bytearray(data) for name, data in (files or {}).items()}
        self.handles = {1: None, 2: None}
        self.paths = {1: b'/shell', 2: b'/browser'}
        self.write_limit = None
        self.read_limit = None
        self.fragment = None
        self.read_status = b''
        self.direct_write_corruption = False
        self.inject = {}

    def __setitem__(self, address, value):
        if address == 0xdf1c and value == 1:
            command = bytes(self.command)
            assert command[0] in (1, 2), command
            reply = self.respond(command)
            override = self.inject.get(command[1])
            if override:
                reply = override(command, reply)
            self.packets = deque(reply)
        super().__setitem__(address, value)

    def respond(self, command):
        target, op = command[:2]
        handle = self.handles[target]
        if op == 7:
            if handle is None:
                return [(b'', b'85,NO FILE OPEN')]
            name = handle['name']
            metadata = len(self.files[name]).to_bytes(4, 'little') + bytes(7) + b'\x20'
            return [(metadata + name[:63], b'00,OK')]
        if op == 2:
            assert handle is None, 'OPEN overwrote an existing handle'
            mode, name = command[2], command[3:]
            if mode == 7:
                if name in self.files:
                    return [(b'', b'FILE EXISTS')]
                self.files[name] = bytearray()
            elif name not in self.files:
                return [(b'', b"FILE DOESN'T EXIST")]
            assert mode in (1, 7)
            self.handles[target] = dict(name=name, mode=mode, pos=0)
            return [(b'', b'00,OK')]
        if op == 3:
            self.handles[target] = None
            return [(b'', b'00,OK' if handle else b'84,NO FILE TO CLOSE')]
        assert handle is not None, ('operation without a handle', command)
        data = self.files[handle['name']]
        if op == 6:
            handle['pos'] = int.from_bytes(command[2:6], 'little')
            return [(b'', b'00,OK')]
        if op == 4:
            length = int.from_bytes(command[2:4], 'little')
            if self.read_limit is not None:
                length = min(length, self.read_limit)
            payload = bytes(data[handle['pos']:handle['pos']+length])
            handle['pos'] += len(payload)
            parts = [payload]
            if self.fragment:
                parts = [payload[i:i+self.fragment] for i in range(0, len(payload), self.fragment)] or [b'']
            return [(part, self.read_status if i == len(parts)-1 else b'')
                    for i, part in enumerate(parts)]
        if op == 5:
            assert handle['mode'] == 7 and command[2:4] == b'\0\0'
            payload = command[4:]
            if self.write_limit is not None:
                limit = (self.write_limit.get(len(payload),len(payload))
                         if isinstance(self.write_limit,dict) else self.write_limit)
                payload = payload[:limit]
            start = handle['pos']
            if self.direct_write_corruption and start % 512 == 0 and len(payload) >= 512:
                # Reference USB firmware's direct-sector DMA cannot reach the
                # command FIFO mapping. It reports OK but saves other bytes.
                payload = bytes(byte ^ 0xa5 for byte in payload)
            data[start:start+len(payload)] = payload
            handle['pos'] += len(payload)
            return [(b'', b'00,OK')]
        raise AssertionError(command)


class Client:
    def __init__(self, bus=None):
        self.bus = bus or Files()
        load_driver(self.bus)
        image = (ROOT/'target/uos-files.prg').read_bytes()
        self.origin = int.from_bytes(image[:2], 'little')
        self.end = self.origin + len(image)-2
        self.bus.ram[self.origin:self.end] = image[2:]
        self.steps = 0

    def call(self, entry, target=2, mode=1, name=None, buffer=0x6000, data=None, length=512, offset=None):
        ram = self.bus.ram
        if name is not None:
            buffer = 0x6800
            ram[buffer:buffer+len(name)+1] = name + b'\0'
        if data is not None:
            length = len(data)
            ram[buffer:buffer+length] = data
        ram[2:4] = buffer.to_bytes(2, 'little')
        ram[4:6] = length.to_bytes(2, 'little')
        if offset is not None:
            ram[2:6] = offset.to_bytes(4, 'little')
        cpu = MPU(memory=self.bus, pc=entry)
        cpu.a, cpu.x, cpu.y = mode, target, 0xa5
        cpu.sp = 0xf1
        cpu.stPushWord(0x02ff)
        self.bus.writes.clear()
        for step in range(20000000):
            if cpu.pc == 0x0300:
                assert cpu.sp == 0xf1, 'unbalanced service stack'
                self.steps += step
                return cpu.a, bool(cpu.p & cpu.CARRY)
            assert self.origin <= cpu.pc < self.end or 0x8a00 <= cpu.pc < 0x9b00, hex(cpu.pc)
            cpu.step()
        raise AssertionError('file service did not return')

    def ok(self, *args, **kwargs):
        result = self.call(*args, **kwargs)
        assert result == (0, False), (result, bytes(self.bus.ram[STATUS:STATUS+32]))
        return self.value(COUNT, 2)

    def value(self, address, size=1):
        return int.from_bytes(self.bus.ram[address:address+size], 'little')


def binary_reads():
    payload = bytes(range(256))*259 + b'\0\xfflast'
    c = Client(Files({b'long.bin': payload, b'empty': b''}))
    c.ok(OPEN, name=b'long.bin')
    result = bytearray()
    while not c.value(EOF):
        count = c.ok(READ)
        result.extend(c.bus.ram[0x6000:0x6000+count])
    assert bytes(result) == payload and c.value(POS, 4) == len(payload)
    before = len(c.bus.commands)
    assert c.ok(READ) == 0 and len(c.bus.commands) == before
    for offset in (0, 255, 256, 65535, 65536, len(payload)):
        c.ok(SEEK, offset=offset)
        c.bus.fragment = 73
        count = c.ok(READ, length=511)
        assert bytes(c.bus.ram[0x6000:0x6000+count]) == payload[offset:offset+511]
    c.ok(CLOSE)
    c.ok(OPEN, name=b'empty')
    assert c.value(EOF) == 1 and c.ok(READ) == 0
    c.ok(CLOSEALL)
    assert c.bus.paths == {1: b'/shell', 2: b'/browser'}
    return dict(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), steps=c.steps)


def creation_and_copy():
    payload = bytes((i*73+11) & 255 for i in range(66053))
    c = Client(Files({b'source': payload}))
    c.ok(OPEN, target=1, name=b'source')
    c.ok(OPEN, target=2, mode=7, name=b'destination')
    for start in range(0, len(payload), 512):
        count = c.ok(READ, target=1)
        assert c.ok(WRITE, target=2, length=count) == count
    assert bytes(c.bus.files[b'destination']) == payload
    assert c.value(POS, 4) == len(payload) and c.value(SIZE, 4) == len(payload)
    assert c.call(SEEK, offset=len(payload)+1) == (0xe7, True)
    c.ok(SEEK, offset=65534)
    patch = b'\0checked\xff'
    c.ok(WRITE, data=patch)
    assert c.value(SIZE, 4) == len(payload)
    c.ok(CLOSEALL)
    assert c.bus.handles == {1: None, 2: None}
    c.ok(OPEN, name=b'destination')
    c.ok(SEEK, offset=65534)
    assert c.ok(READ, length=len(patch)) == len(patch)
    assert c.bus.ram[0x6000:0x6000+len(patch)] == patch
    before = bytes(c.bus.files[b'destination'])
    c.ok(CLOSE)
    assert c.call(OPEN, mode=7, name=b'destination') == (255, True)
    assert bytes(c.bus.files[b'destination']) == before
    assert c.value(MODES+1) == 255  # plain-text failure cannot prove ownership
    assert bytes(c.bus.ram[STATUS:STATUS+12]) == b'FILE EXISTS\0'
    c.ok(CLOSE)  # firmware says 84; no handle was actually opened
    assert c.value(MODES+1) == 0
    return dict(bytes=len(payload), writes=sum(cmd[1] == 5 for cmd in c.bus.commands), steps=c.steps)


def names_and_buffers():
    # These read-only cases prove lossless transport bounds. Real firmware may
    # be unable to resolve long components; creation must prevent that case.
    names = [b'a'*511, b'/'+b'p'*380+b'/'+b'n'*511]
    c = Client(Files({name: b'x'*512 for name in names}))
    for name in names:
        c.ok(OPEN, name=name)
        assert c.bus.commands[-2] == b'\x02\x02\x01'+name
        c.ok(CLOSE)
    for name in (b'', b'n'*894):
        before = len(c.bus.commands)
        assert c.call(OPEN, name=name) == (0xe0, True)
        assert len(c.bus.commands) == before
    c.ok(OPEN, name=names[0])
    for buffer, length in ((0x4fff, 1), (0x7fff, 2), (0x8000, 1), (0x734f, 2),
                           (0x7350, 1), (0x7358, 1), (0x6000, 0), (0x6000, 513)):
        before = len(c.bus.commands)
        assert c.call(READ, buffer=buffer, length=length) == (0xe0, True), (buffer, length)
        assert len(c.bus.commands) == before
    for buffer, length in ((0x5000, 512), (0x7150, 512), (0x7359, 512), (0x7e00, 512), (0x734f, 1)):
        c.ok(SEEK, offset=0)
        before = bytes(c.bus.ram)
        c.ok(READ, buffer=buffer, length=length)
        assert c.bus.ram[buffer:buffer+length] == b'x'*length
        assert c.bus.ram[0x7350:0x7359] == before[0x7350:0x7359]
        assert c.bus.ram[0x8000:0x8080] == before[0x8000:0x8080]
        assert c.bus.ram[0x8400:0x8800] == before[0x8400:0x8800]
    return dict(max_name=893, max_command=896, invalid_buffers=8, valid_buffers=5)


def creation_names():
    c = Client()
    valid = (b'n'*127, b'/'+b'a'*127+b'/'+b'b'*127+b'/file',
             b'\\'+b'a'*127+b'\\'+b'b'*127+b'\\file',
             b'/'.join([bytes([65+i])*127 for i in range(6)]+[b'Z'*125]))
    for name in valid:
        c.ok(OPEN, mode=7, name=name)
        assert c.bus.commands[-2] == b'\x02\x02\x07'+name
        c.ok(CLOSE)
    invalid = (b'n'*128, b'n'*255, b'/'+b'a'*128+b'/file',
               b'\\'+b'a'*128+b'\\file', b'/ok/'+b'b'*128)
    for name in invalid:
        before = len(c.bus.commands)
        assert c.call(OPEN, mode=7, name=name) == (0xe0, True), name
        assert len(c.bus.commands) == before and name not in c.bus.files
        assert c.value(MODES+1) == 0
    assert len(valid[-1]) == 893
    return dict(max_component=127, max_name=893, valid=len(valid), rejected_before_io=len(invalid))


def usb_sector_workaround():
    c = Client()
    c.bus.direct_write_corruption = True
    c.ok(OPEN, mode=7, name=b'usb.bin')
    payload = bytes((i*73+i//256*17+11)&255 for i in range(1536))
    for start in range(0,len(payload),512):
        assert c.ok(WRITE,data=payload[start:start+512]) == 512
    assert c.value(POS,4) == len(payload) and c.value(SIZE,4) == len(payload)
    c.ok(CLOSE)
    c.ok(OPEN,name=b'usb.bin')
    actual = bytearray()
    for _ in range(3):
        n=c.ok(READ)
        actual.extend(c.bus.ram[0x6000:0x6000+n])
    assert bytes(actual) == payload
    c.ok(CLOSE)
    assert all(len(cmd)<516 for cmd in c.bus.commands if cmd[1]==5)
    return dict(bytes=len(payload),sector_dma_corruption_avoided=True,closed_reopen_match=True)


def ownership():
    c = Client(Files({b'foreign': b'abc', b'ours': b'xyz'}))
    c.bus.handles[1] = dict(name=b'foreign', mode=1, pos=2)
    assert c.call(OPEN, target=1, name=b'ours') == (0xe2, True)
    c.ok(CLOSE, target=1)
    assert c.bus.handles[1]['pos'] == 2
    c.ok(OPEN, name=b'ours')
    before = len(c.bus.commands)
    assert c.call(OPEN, name=b'foreign') == (0xe2, True)
    assert c.call(WRITE, data=b'no') == (0xe3, True)
    assert len(c.bus.commands) == before
    c.ok(CLOSEALL)
    assert c.bus.handles[1] is not None and c.bus.handles[2] is None
    assert c.call(READ) == (0xe1, True)
    for target in (0, 3, 255):
        assert c.call(OPEN, target=target, name=b'ours') == (0xe0, True)
    for mode in (0, 2, 6, 8, 14, 255):
        assert c.call(OPEN, mode=mode, name=b'ours') == (0xe0, True)
    c.bus.inject[7] = lambda cmd, reply: [(b'', b'84,NO FILE TO CLOSE')]
    before = len(c.bus.commands)
    assert c.call(OPEN, name=b'ours') == (84, True)
    assert len(c.bus.commands) == before+1 and c.bus.commands[-1][1] == 7
    return dict(foreign_preserved=True, invalid_modes=6, invalid_contexts=3)


def launch_cleanup():
    """Actual core launch reaches its loader with its prefilled name intact.

    Only the unrelated graphics clear is stubbed. Core FILLFILE, launch,
    resident CLOSEALL and the UCI transport execute their assembled code.
    """
    for close_failure in (False, True):
        c = Client(Files({b'foreign': b'abc'}))
        c.bus.handles[1] = dict(name=b'foreign', mode=1, pos=2)
        c.ok(OPEN, mode=7, name=b'owned')
        if close_failure:
            c.bus.inject[3] = lambda cmd, reply: [(b'', b'87,INTERNAL ERROR')]
        image = (ROOT/'target/uos.prg').read_bytes()
        origin = int.from_bytes(image[:2], 'little')
        c.bus.ram[origin:origin+len(image)-2] = image[2:]
        name = b'UOS-ULTIMATE'
        c.bus.ram[0x6000:0x6000+len(name)+1] = name+b'\0'
        c.bus.ram[2:4] = b'\0\x60'
        c.bus.ram[0xc006] = 0x60
        cpu = MPU(memory=c.bus, pc=0x0829)
        cpu.sp = 0xf0
        cpu.stPushWord(0x02ff)
        for _ in range(1000):
            if cpu.pc == 0x0300:
                break
            cpu.step()
        else:
            raise AssertionError('FILLFILE did not return')
        cpu.pc = 0x0832
        loader = symbol('uos', 'LOADER')
        for _ in range(100000):
            if cpu.pc == loader:
                break
            cpu.step()
        else:
            raise AssertionError('LAUNCH_APP did not reach LOADER')
        address = symbol('uos', 'file')
        assert bytes(c.bus.ram[address:address+len(name)+1]) == name+b'\0'
        assert c.bus.ram[symbol('uos', 'ftmp')] == len(name)
        assert c.value(MODES+1) == (255 if close_failure else 0)
        assert c.bus.handles[1]['pos'] == 2
        assert c.bus.commands[-1] == b'\x02\x03'
        assert cpu.sp == 0xee, 'launch cleanup unbalanced stack'
    return dict(loader_name_preserved=True, foreign_handle_preserved=True,
                successful_close_released=True, failed_close_retained=True)


def failures():
    scenarios = []
    for failure in ('short', 'extra', 'clipped', 'nondigit', 'numeric', 'absent'):
        c = Client(Files({b'data': bytes(range(256))*2}))
        c.ok(OPEN, name=b'data')
        if failure == 'short':
            c.bus.read_limit = 511
            expected = 0xe5
        elif failure in ('extra', 'clipped'):
            c.bus.inject[4] = lambda cmd, reply: [(bytes(513), b'')]
            expected = 0xe4
            if failure == 'extra':
                c.bus.inject[4] = lambda cmd, reply: [(bytes(512), b''), (b'x', b'')]
        elif failure == 'nondigit':
            c.bus.read_status = b'NO STATUS CODE'
            expected = 0xe4
        elif failure == 'numeric':
            c.bus.read_status = b'74,DRIVE NOT READY'
            expected = 74
        else:
            c.bus.present = False
            expected = 0xfe
        assert c.call(READ) == (expected, True), failure
        assert c.value(MODES+1) == 255
        before = len(c.bus.commands)
        assert c.call(READ) == (0xe8, True)
        assert len(c.bus.commands) == before
        c.bus.present = True
        c.ok(CLOSE)
        assert c.value(MODES+1) == 0
        scenarios.append(failure)
    for failure in ('short_write', 'short_tail', 'wrong_write', 'error_write', 'text_write', 'tail_write', 'lost_open', 'short_info', 'missing_info', 'close_retry'):
        c = Client()
        if failure == 'lost_open':
            c.bus.inject[2] = lambda cmd, reply: [(b'', b'UNKNOWN')]
            assert c.call(OPEN, mode=7, name=b'new') == (255, True)
        elif failure == 'short_info':
            c.bus.inject[7] = lambda cmd, reply: [(b'\0'*11, b'00,OK')] if c.bus.handles[2] else reply
            assert c.call(OPEN, mode=7, name=b'new') == (0xe4, True)
        elif failure == 'missing_info':
            c.bus.inject[7] = lambda cmd, reply: [(b'', b'82,FILE NOT FOUND')] if c.bus.handles[2] else reply
            assert c.call(OPEN, mode=7, name=b'new') == (82, True)
        else:
            c.ok(OPEN, mode=7, name=b'new')
            if failure == 'short_write':
                c.bus.write_limit = 510
                expected = 0xe6  # final byte lands early after the short prefix
            elif failure == 'short_tail':
                c.bus.write_limit = {1:0}
                expected = 0xe5
            elif failure == 'wrong_write':
                c.bus.inject[4] = lambda cmd, reply: [(b'\xff'*512, b'')]
                expected = 0xe6
            elif failure == 'error_write':
                c.bus.inject[5] = lambda cmd, reply: [(b'', b'72,DISK FULL')]
                expected = 72
            elif failure == 'text_write':
                c.bus.inject[5] = lambda cmd, reply: [(b'', b'DISK IS FULL')]
                expected = 255
            elif failure == 'tail_write':
                c.bus.inject[5] = lambda cmd, reply: [(b'', b'DISK IS FULL')] if len(cmd)==5 else reply
                expected = 255
            else:
                c.bus.inject[3] = lambda cmd, reply: [(b'', b'74,NOT READY')]
                assert c.call(CLOSE) == (74, True)
            if failure != 'close_retry':
                assert c.call(WRITE, data=bytes(range(256))*2) == (expected, True), failure
        assert c.value(MODES+1) == 255, failure
        c.bus.inject.clear()
        c.ok(CLOSE)
        assert c.bus.handles[2] is None
        scenarios.append(failure)
    return dict(scenarios=scenarios, silent_short_write_detected=True, no_automatic_write_replay=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'images': {n: hashlib.sha256((ROOT/'target'/n).read_bytes()).hexdigest()
                         for n in ('uos-files.prg', 'uos-net.prg', 'uos.prg')}, 'checks': {}}
    for check in (binary_reads, creation_and_copy, names_and_buffers, creation_names, usb_sector_workaround, ownership, launch_cleanup, failures):
        report['checks'][check.__name__] = check()
        print('PASS:', check.__name__, report['checks'][check.__name__], flush=True)
    report['passed'] = True
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
