#!/usr/bin/env python3
"""Execute the modal loader, selector, file service and UCI register driver.

KERNAL LOAD and input are adapters. Optional full graphics execute on the
VIC/VDC memory model. Directory and file contents live in the DOS model.
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import posixpath

from py65.devices.mpu6502 import MPU
from ci_file_copy import PathFiles, symbols
from ci_ultimate import Browser, petscii
from profile_browser import DisplayBus
from uci_bus import ROOT, load_driver


class PickerFilesystem(PathFiles):
    def __init__(self, folders, files):
        super().__init__(files)
        self.folders = folders
        self.paths = {1: b'/shell', 2: b'/'}
        self.before = None

    def respond(self, command):
        if self.before:
            override = self.before(command)
            if override is not None:
                return override
        ctx, op = command[:2]
        path = self.paths[ctx]
        if op == 0x12:
            return [(path if path.endswith(b'/') else path+b'/', b'00,OK')]
        if op == 0x11:
            assert command[2:] and b'\0' not in command[2:]
            dest = posixpath.normpath(posixpath.join(path, command[2:]))
            if dest not in self.folders:
                return [(b'', b'83,NO SUCH DIRECTORY')]
            self.paths[ctx] = dest
            return [(b'', b'00,OK')]
        if op == 0x13:
            return [(b'', b'00,OK' if self.folders[path] else b'01,DIRECTORY EMPTY')]
        if op == 0x14:
            entries = self.folders[path]
            return [(e, b'00,OK' if i == len(entries)-1 else b'') for i, e in enumerate(entries)]
        return super().respond(command)


class Picker(Browser):
    def __init__(self, folders=None, files=None, real_display=False):
        self.bus = PickerFilesystem(folders or {b'/': [], b'/shell': []}, files or {})
        self.fs = self.bus
        self.real_display = real_display
        if real_display:
            self.bus = DisplayBus(self.bus)
        load_driver(self.bus)
        self.cpu = MPU(memory=self.bus)
        self.keys = deque()
        self.button = 0x10
        self.cancel_after = None
        self.vic, self.vdc = [], {}
        self.sym = symbols('uos-picker')
        self.gsym = symbols('uos-files')
        self.loads = []
        self.load_failure = False
        self.ticks = 0
        self.steps = 0
        for name in ('uos', 'uos-files'):
            self.load(name)
        ram = self.bus.ram
        ram[0x5000:0x6200] = bytes((i*7+61)&255 for i in range(0x1200))
        ram[0x7350:0x7400] = bytes([0xb6])*0xb0
        ram[0x9000:0x9100] = bytes([0xd8])*256
        ram[0xba] = 8
        if real_display:
            for name in ('uos-gfx', 'uos-vdc'):
                self.load(name)
            ram[0xcc24] = 1
            self.cpu.pc = 0xc000
            self.cpu.stPushWord(0x02ff)
            while self.cpu.pc != 0x0300:
                self.cpu.step()

    def load(self, name):
        prg = (ROOT/'target'/f'{name}.prg').read_bytes()
        origin = int.from_bytes(prg[:2], 'little')
        self.bus.ram[origin:origin+len(prg)-2] = prg[2:]

    def start(self, mode=1, context=2, default=b'new.txt'):
        self.context = context
        ram = self.bus.ram
        ram[0x6000:0x6000+len(default)+1] = default+b'\0'
        ram[2:4] = b'\x00\x60'
        self.document = bytes(ram[0x5000:0x6200])
        self.cpu.pc, self.cpu.a, self.cpu.x = 0x4c80, mode, context
        self.cpu.stPushWord(0x02ff)

    def stub(self):
        c, ram = self.cpu, self.bus.ram
        if c.pc in (0xffd2, 0xffbd, 0xffba, 0xffd5):
            if c.pc == 0xffbd:
                self.load_name = petscii(bytes(ram[c.x+c.y*256:c.x+c.y*256+c.a]))
            if c.pc == 0xffba:
                assert (c.a, c.x, c.y) == (1, 8, 1)
            if c.pc == 0xffd5:
                self.loads.append(self.load_name)
                assert self.load_name == 'uos-picker'
                if self.load_failure:
                    c.p |= c.CARRY
                    c.a = 4
                else:
                    self.load(self.load_name)
                    c.p &= ~c.CARRY
            c.pc = c.stPopWord()+1
            return True
        if c.pc == 0x083b:
            self.ticks += 1
        if not self.real_display or c.pc in (0x082c, 0x083b, 0x083e):
            return super().stub()
        return False

    def run(self, key=None, returned=False):
        if key is not None:
            self.keys.append(key)
        for steps in range(15000000):
            if self.cpu.pc == 0x0300:
                assert returned, ('unexpected return', hex(self.cpu.a))
                self.guards()
                self.steps += steps
                return self.cpu.a, bool(self.cpu.p & self.cpu.CARRY)
            if self.cpu.pc == self.sym['input_loop'] and steps and not self.keys:
                assert not returned, ('selector still open', self.value('error'))
                self.guards()
                self.steps += steps
                return
            if not self.stub():
                pc = self.cpu.pc
                assert (0x0801 <= pc < 0x1000 or 0x4100 <= pc < 0x5000 or
                        0x6200 <= pc < 0x7200 or 0x8a00 <= pc < 0x9b00 or
                        0xc000 <= pc < 0xd000), hex(pc)
                self.cpu.step()
        raise AssertionError(('picker did not finish', hex(self.cpu.pc)))

    def names(self):
        result = []
        for i in range(self.value('count')):
            p = self.bus.ram[self.sym['ptrsL']+i] + 256*self.bus.ram[self.sym['ptrsH']+i]
            n = self.bus.ram[self.sym['lensL']+i] + 256*self.bus.ram[self.sym['lensH']+i]
            result.append(bytes(self.bus.ram[p:p+n]))
            assert self.bus.ram[p+n] == 0
        return result

    def guards(self):
        ram = self.bus.ram
        assert bytes(ram[0x5000:0x6200]) == self.document, 'caller document/code changed'
        assert ram[0x7350:0x7359] == bytes([0xb6])*9, 'settings changed'
        assert ram[0x9000:0x9100] == bytes([0xd8])*256, 'controls changed'
        assert not self.bus.discarded, 'unread UCI data discarded'

    def close(self, entry=0x4103):
        self.cpu.pc, self.cpu.x = entry, self.context
        self.cpu.stPushWord(0x02ff)
        return self.run(returned=True)

    def filename(self, name):
        self.run(0x15)
        for c in name:
            self.run(c-32 if 97 <= c <= 122 else c+128 if 65 <= c <= 90 else c)
        assert self.cstring(0x7200) == name

    def click(self, x, y, returned=False):
        sx = x+24
        self.bus.ram[0xd000], self.bus.ram[0xd010], self.bus.ram[0xd001] = sx&255,sx>>8,y+50
        self.button = 0
        self.run()
        self.button = 0x10
        return self.run(returned=returned)


def selection_and_lease():
    b = Picker({b'/': [b'\x10folder'], b'/folder': [b'\x20hello.txt'], b'/shell': []},
               {b'/folder/hello.txt': b'hello\n'})
    b.start(); b.run(); b.run(13)
    assert b.names() == [b'hello.txt']
    assert b.run(13, returned=True) == (0, False)
    assert b.cstring(0x7800) == b'/folder/hello.txt'
    assert b.fs.paths == {1: b'/shell', 2: b'/folder'}
    assert b.bus.ram[0x4c88] == 1 and b.bus.ram[0x4123] == 1
    assert b.close() == (0, False)
    assert b.fs.paths == {1: b'/shell', 2: b'/'}
    assert b.bus.ram[0x4c88] == 0 and b.fs.handles == {1: None, 2: None}
    return dict(path=b.cstring(0x7800).decode(), instructions=b.steps)


def variable_pages():
    names = [(f'{i:04d}-'.encode()+b'x'*(506 if i%3 else 17)) for i in range(24)]
    entries = [b'\x20'+name for name in names]
    b = Picker({b'/': entries, b'/shell': []})
    b.start(); b.run()
    pages = []
    for _ in range(25):
        pages.append((b.value('base', 2), b.names()))
        assert pages[-1][1], ('empty page with more flag', b.value('error'))
        if not b.value('more'):
            break
        b.run(ord('N'))
    else:
        raise AssertionError('next page did not advance')
    assert [n for _, page in pages for n in page] == names
    for base, page in reversed(pages[:-1]):
        b.run(ord('B'))
        assert (b.value('base', 2), b.names()) == (base, page)
    assert b.run(27, returned=True) == (0xe9, True)
    assert b.fs.paths[2] == b'/' and b.bus.ram[0x4c88] == 0
    short = [f'item-{i:04d}'.encode() for i in range(272)]
    b = Picker({b'/': [b'\x20'+n for n in short], b'/shell': []})
    b.start(); b.run()
    for page in range(1, 34):
        b.run(ord('N'))
        assert b.value('base', 2) == page*8
        assert b.names() == short[page*8:page*8+8]
    b.run(ord('B'))
    assert b.value('base', 2) == 256 and b.names() == short[256:264]
    b.run(27, returned=True)
    return dict(entries=len(names), pages=len(pages), longest_name=max(map(len,names)))


def creation_and_collision():
    b = Picker({b'/': [b'\x10folder'], b'/folder': [], b'/shell': []},
               {b'/folder/existing.txt': b'keep'})
    b.start(7); b.run(); b.run(13); b.run(0x85)
    b.filename(b'existing.txt'); b.run(13)
    assert b.value('error') == 0xff and b.fs.files[b'/folder/existing.txt'] == b'keep'
    assert 'FILE EXISTS' in b.vdc[3]
    assert b.fs.paths[2] == b'/folder' and b.bus.ram[0x4123] == 0
    b.filename(b'Case sensitive Name.txt')
    assert b.run(13, returned=True) == (0, False)
    assert b.cstring(0x7800) == b'/folder/Case sensitive Name.txt'
    assert b.close() == (0, False)
    assert b.fs.paths[2] == b'/'
    return dict(existing_preserved=True, full_case_path=b.cstring(0x7800).decode())


def recovery_faults():
    reports = []
    for fault in ('close', 'restore'):
        b = Picker({b'/': [b'\x10folder'], b'/folder': [b'\x20a'], b'/shell': []},
                   {b'/folder/a': b'abc'})
        b.start(); b.run(); b.run(13); b.run(13, returned=True)
        def fail(cmd):
            if cmd[1] == (3 if fault == 'close' else 0x11):
                return [(b'', b'87,INTERNAL ERROR')]
        b.fs.before = fail
        assert b.close()[1]
        assert b.fs.paths[2] == b'/folder' and b.bus.ram[0x4c88] != 0
        if fault == 'restore':
            assert b.bus.ram[0x4c88] == 2 and b.bus.ram[0x4123] == 0
            commands = len(b.fs.commands)
            b.cpu.pc, b.cpu.a, b.cpu.x = 0x4100, 1, 2
            b.cpu.stPushWord(0x02ff)
            assert b.run(returned=True) == (0xe8, True)
            assert len(b.fs.commands) == commands
        # The caller can overwrite every modal workspace byte before retry.
        b.bus.ram[0x6200:0x7350] = bytes([0xaa])*0x1150
        b.bus.ram[0x7359:0x8000] = bytes([0xaa])*0xca7
        b.fs.before = None
        assert b.close() == (0, False)
        assert b.fs.paths[2] == b'/' and b.bus.ram[0x4c88] == 0
        reports.append(fault)
    b = Picker()
    b.start(); b.load_failure = True
    assert b.run(returned=True) == (0xea, True) and not b.fs.commands
    b = Picker(files={b'foreign': b'do not close'})
    b.fs.handles[2] = dict(name=b'foreign', mode=1, pos=0)
    b.start()
    assert b.run(returned=True) == (0xe2, True)
    assert b.fs.commands == [b'\x02\x07'] and b.fs.handles[2]['name'] == b'foreign'
    return dict(recovered=reports, missing_library=True, foreign_handle_preserved=True)


def bounds_and_input():
    deep = b'/'+b'/'.join([b'a'*127]+[b'b'*126]*3)
    name = b'z'*511
    b = Picker({b'/': [], deep: [b'\x20'+name], b'/shell': []}, {deep+b'/'+name: b'ok'})
    b.fs.paths[2] = deep
    b.start(); b.run()
    assert b.run(13,returned=True) == (0,False)
    assert b.cstring(0x7800) == deep+b'/'+name
    assert int.from_bytes(b.bus.ram[0x4c8c:0x4c8e],'little') == 1021
    assert b.close() == (0,False)
    b = Picker({b'/': [], deep: [], b'/shell': []})
    b.fs.paths[2] = deep
    leaf = b'z'*127
    b.start(7,default=leaf); b.run(); b.run(0x85)
    assert b.run(13,returned=True) == (0,False)
    assert b'\x02\x02\x07'+deep+b'/'+leaf in b.fs.commands
    assert b.close() == (0,False)
    # Absolute creation must retain the service's guard for parent components.
    unsafe = b'/'+b'a'*128
    b = Picker({b'/': [], unsafe: [], b'/shell': []})
    b.fs.paths[2] = unsafe
    b.start(7); b.run(); b.run(0x85); b.run(13)
    assert b.value('error') == 0xe0 and not any(c[1] == 2 for c in b.fs.commands)
    b.run(27); b.run(27,returned=True)
    # Right-side mouse hits, shifted shortcut, root and cancellation.
    b = Picker({b'/': [b'\x10one', b'\x10two'], b'/one': [], b'/two': [], b'/shell': []})
    b.start(); b.run(); b.click(290,49)
    assert b.value('selected') == 1
    b.click(40,180)
    assert b.fs.paths[2] == b'/two'
    b.run(ord('/'))
    assert b.fs.paths[2] == b'/'
    assert b.click(290,180,returned=True) == (0xe9,True)
    for packet in (b'\x20bad\0tail', b'\x10bad/name', b'\x20'+b'z'*512):
        b = Picker({b'/': [packet], b'/shell': []})
        b.start(); b.run()
        assert b.value('error') == 0xe4 and not b.names()
        b.run(27,returned=True)
    b = Picker({b'/': [b'\x20a'], b'/shell': []})
    b.start(); b.cancel_after = 3; b.run()
    assert b.value('error') == 0xe9 and not b.names()
    b.run(ord('R')); assert b.names() == [b'a']
    b.run(27,returned=True)
    return dict(read_path_bytes=1021, create_leaf_bytes=127, parent_guard=True,
                right_edge_mouse=True, malformed_packets=3, scan_cancel_retry=True)


def contexts_and_guards():
    b = Picker(); b.start(7,context=1); b.run(); b.run(0x85)
    assert b.run(13,returned=True) == (0,False)
    assert b.fs.files[b'/shell/new.txt'] == b''
    assert b.close() == (0,False) and b.fs.paths == {1:b'/shell',2:b'/'}
    for mode,ctx in [(0,1),(2,2),(7,0),(1,3),(1,255)]:
        b = Picker(); b.start(mode,ctx)
        assert b.run(returned=True) == (0xe0,True) and not b.fs.commands
    b = Picker(); b.start(); b.bus.ram[0x4c8e] = 1
    assert b.run(returned=True) == (0xe2,True) and not b.fs.commands
    b = Picker()
    b.fs.before = lambda cmd: [(b'/'+b'x'*509+b'/',b'00,OK')] if cmd[1] == 0x12 else None
    b.start(); assert b.run(returned=True) == (0xe4,True)
    assert b.bus.ram[0x4c88] == 0 and not any(c[1] == 0x11 for c in b.fs.commands)
    b = Picker(); b.start(7); b.bus.ram[2:4] = b'\0\x48'
    assert b.run(returned=True) == (0xe0,True) and not b.fs.commands
    return dict(context_one=True, invalid_arguments=6, nested_rejected=True,
                oversized_cwd_rejected_before_change=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--json')
    args = p.parse_args()
    report = {'build': {n: hashlib.sha256((ROOT/'target'/f'{n}.prg').read_bytes()).hexdigest()
                        for n in ('uos', 'uos-files', 'uos-picker')}}
    for name, check in [('selection', selection_and_lease), ('pages', variable_pages),
                        ('creation', creation_and_collision), ('recovery', recovery_faults),
                        ('bounds_input', bounds_and_input), ('contexts', contexts_and_guards)]:
        report[name] = check()
        print(f'PASS: picker {name}', flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
