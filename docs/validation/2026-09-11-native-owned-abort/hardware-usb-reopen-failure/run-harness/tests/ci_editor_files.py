#!/usr/bin/env python3
"""Editor -> modal picker -> verified file service, running assembled code."""
import argparse
import hashlib
import json
from pathlib import Path

from ci_picker import Picker
from ci_file_copy import symbols
from uci_bus import ROOT


class Editor(Picker):
    def __init__(self, *args, legacy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.esym = symbols('uos-edit')
        self.load('uos-edit')
        self.cpu.pc = 0x5000
        self.bus.ram[0x9b00] = 0
        self.context = 2
        self.legacy = legacy
        self.serial_bytes = b''
        self.serial_index = 0
        self.serial_status = 0
        self.serial_writes = []

    def ev(self, name, length=1):
        a = self.esym[name]
        return int.from_bytes(self.bus.ram[a:a+length], 'little')

    def doc(self):
        return bytes(self.bus.ram[0x5f00:0x5f00+self.ev('edlen',2)])

    def stub(self):
        c = self.cpu
        if c.pc == 0xffba:
            self.logical_file = c.a
            if c.a == 3:
                assert c.x == 8 and c.y in (0, 3)
                c.pc = c.stPopWord()+1
                return True
        if c.pc in (0xffc0, 0xffc3, 0xffc6, 0xffcc, 0xffcf, 0xffb7):
            if c.pc == 0xffc0:
                assert self.logical_file == 3 and ',w' not in self.load_name
                if self.legacy is None:
                    c.p |= c.CARRY
                    c.a = 5
                else:
                    c.p &= ~c.CARRY
                    self.serial_bytes = (b'\x01\x08"title"\0"notes.t"\0' if self.load_name.startswith('$')
                                         else self.legacy)
                    self.serial_index = self.serial_status = 0
            elif c.pc == 0xffc6:
                c.p &= ~c.CARRY
            elif c.pc == 0xffcf:
                c.a = self.serial_bytes[self.serial_index] if self.serial_index < len(self.serial_bytes) else 0
                self.serial_index += 1
                self.serial_status = 64 if self.serial_index >= len(self.serial_bytes) else 0
            elif c.pc == 0xffb7:
                c.a = self.serial_status
            c.pc = c.stPopWord()+1
            return True
        return super().stub()

    def guards(self):
        ram = self.bus.ram
        assert ram[0x7350:0x7359] == bytes([0xb6])*9
        assert ram[0x9000:0x9100] == bytes([0xd8])*256
        assert self.ev('edlen', 2) <= 768
        assert not self.bus.discarded

    def run(self, key=None, picker=False, left=False, confirm=False):
        if key is not None:
            self.keys.append(key)
        idle = self.esym['confirm_loop'] if confirm else self.sym['input_loop'] if picker else self.esym['edloop']
        for steps in range(18000000):
            if self.cpu.pc == 0x1000:
                assert left
                assert self.bus.ram[0x9b00] == 0 and self.cpu.sp == 255
                return
            if self.cpu.pc == idle and steps and not self.keys:
                assert not left
                self.steps += steps
                self.guards()
                return
            if not self.stub():
                pc = self.cpu.pc
                assert (0x0801 <= pc < 0x1000 or 0x4100 <= pc < 0x7200 or
                        0x8a00 <= pc < 0x9b00 or 0xc000 <= pc < 0xd000), hex(pc)
                self.cpu.step()
        raise AssertionError(('editor failed to reach input', hex(self.cpu.pc), self.ev('ed_result')))

    def type(self, text, picker=False):
        for c in text:
            self.run(c-32 if 97 <= c <= 122 else c+128 if 65 <= c <= 90 else c, picker=picker)

    def choose_save(self, name):
        self.run(0x85, picker=True)
        self.run(0x85, picker=True)
        self.run(0x15, picker=True)
        self.type(name, picker=True)
        self.run(13)


def save_and_open():
    b = Editor()
    b.run(); b.type(b'Hello world'); b.run(13); b.type(b'New note')
    expected = b'Hello world\nNew note'
    assert b.doc() == expected and b.ev('dirty') == 1
    b.choose_save(b'first.txt')
    assert b.doc() == expected and b.ev('dirty') == 0 and b.ev('ed_result') == 0
    assert b.fs.files[b'/first.txt'] == expected
    assert b.fs.handles == {1: None, 2: None} and b.bus.ram[0x4c88] == 0
    assert [c for c in b.fs.commands if c[1] == 2] == [b'\x02\x02\x07/first.txt', b'\x02\x02\x01/first.txt']
    # Open executes a >512-byte read into staging while the old note survives.
    payload = (b'ASCII Mixed Case 123\r\n'*40)[:768]
    b.fs.files[b'/long.txt'] = bytearray(payload)
    b.fs.folders[b'/'] = [b'\x20long.txt']
    b.run(0x86, picker=True)
    assert b.doc() == expected
    b.run(13)
    assert b.doc() == payload and b.ev('dirty') == 0
    b.choose_save(b'long-copy.txt')
    assert b.fs.files[b'/long-copy.txt'] == payload and b.ev('ed_result') == 0
    b.run(27, left=True)
    return dict(bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), instructions=b.steps)


def preserve_on_failure():
    cases = []
    for name, payload in [('oversize', b'x'*769), ('binary', b'abc\x00def'), ('short', b'a'*700)]:
        b = Editor(files={b'/incoming.txt': payload}, folders={b'/': [b'\x20incoming.txt'], b'/shell': []})
        b.run(); b.type(b'Keep me')
        if name == 'short':
            b.fs.read_limit = 100
        b.keys.extend([0x86, ord('Y')]); b.run(picker=True)
        b.run(13)
        assert b.doc() == b'Keep me' and b.ev('dirty') == 1
        assert b.ev('ed_result') == {'oversize':0xe7, 'binary':0xeb, 'short':0xe5}[name]
        assert b.fs.handles == {1: None, 2: None} and b.bus.ram[0x4c88] == 0
        cases.append(name)
    for name in ('short-write', 'post-close-corruption', 'final-close'):
        b = Editor(); b.run(); b.type(b'Keep this note')
        if name == 'short-write':
            b.fs.write_limit = 3
        if name == 'post-close-corruption':
            def corrupt(cmd):
                if cmd == b'\x02\x03' and b.fs.handles[2] and b.fs.handles[2]['mode'] == 7:
                    b.fs.files[b'/failed.txt'][0] ^= 1
            b.fs.before = corrupt
        if name == 'final-close':
            def final_close(cmd):
                if cmd == b'\x02\x03' and b.fs.handles[2] and b.fs.handles[2]['mode'] == 1:
                    return [(b'', b'87,INTERNAL ERROR')]
            b.fs.before = final_close
        b.choose_save(b'failed.txt')
        assert b.doc() == b'Keep this note' and b.ev('dirty') == 1 and b.ev('ed_result') != 0
        assert b'/failed.txt' in b.fs.files
        assert len([c for c in b.fs.commands if c[1] == 5]) == 1
        cases.append(name)
    return dict(cases=cases, no_write_replay=True)


def editing_and_import():
    b = Editor(legacy=b'OLD NOTES\rLINE TWO\r'); b.run()
    assert b.doc() == b'old notes\nline two\n' and b.ev('dirty') == 0
    b.run(0x14); b.type(b'!')
    assert b.doc().endswith(b'two!')
    # Reject discard: all actions and the document stay usable.
    for key in (0x86, 0x87, 27):
        old = b.doc()
        b.keys.extend([key, ord('N')]); b.run()
        assert b.doc() == old and b.ev('dirty') == 1
    b.keys.extend([0x87, ord('Y')]); b.run()
    assert b.doc() == b'' and b.ev('dirty') == 0
    b.type(b'first')
    for _ in range(20):
        b.run(13)
    b.type(b'last')
    assert any('last' in line for line in b.vdc.values())
    assert not any('first' in b.vdc.get(i, '') for i in range(4,19))
    b.keys.extend([27, ord('Y')]); b.run(left=True)
    return dict(legacy_read_only=True, visible_tail=True, dirty_actions=3)


def empty_and_unavailable():
    b = Editor(); b.run(); b.choose_save(b'empty.txt')
    assert b.doc() == b'' and b.ev('ed_result') == 0 and b.ev('dirty') == 0
    assert b.fs.files[b'/empty.txt'] == b'' and b.fs.handles == {1:None,2:None}
    assert not any(c[1] in (4,5) for c in b.fs.commands)
    b = Editor(); b.run(); b.type(b'keep'); b.load_failure = True; b.run(0x85)
    assert b.doc() == b'keep' and b.ev('dirty') == 1 and b.ev('ed_result') == 0xea
    assert not b.fs.commands
    b = Editor(files={b'foreign':b'leave alone'})
    b.fs.handles[2] = dict(name=b'foreign',mode=1,pos=0)
    b.run(); b.type(b'keep'); b.keys.extend([0x86,ord('Y')]); b.run()
    assert b.doc() == b'keep' and b.ev('dirty') == 1 and b.ev('ed_result') == 0xe2
    assert b.fs.commands == [b'\x02\x07'] and b.fs.handles[2]['name'] == b'foreign'
    b = Editor(); b.run(); b.type(b'keep')
    b.run(27,confirm=True); assert b.ev('ready') == 2
    b.run(ord('N')); assert b.doc() == b'keep' and b.ev('dirty') == 1
    b.run(27,confirm=True); assert b.ev('ready') == 2
    b.run(ord('Y'),left=True)
    return dict(empty_verified=True, missing_library_preserves_note=True,
                foreign_file_preserved_through_editor_cleanup=True, staged_discard_confirmation=True)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--json'); args = p.parse_args()
    report = {'build': {n: hashlib.sha256((ROOT/'target'/f'{n}.prg').read_bytes()).hexdigest()
                        for n in ('uos', 'uos-files', 'uos-picker', 'uos-edit')}}
    for name, check in [('save_open',save_and_open), ('failures',preserve_on_failure),
                        ('editing',editing_and_import), ('empty_unavailable',empty_and_unavailable)]:
        report[name] = check()
        print(f'PASS: editor files {name}', flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
