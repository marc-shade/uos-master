#!/usr/bin/env python3
"""Shared viewer through the real browser, with byte and full-frame oracles."""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import re

from ci_files import Files
from ci_ultimate import Browser, FileSystem, ROOT
from profile_browser import DisplayBus
from uci_bus import UCIBus


def file_symbols():
    listing = (ROOT/'target/uos-files.lst').read_text(encoding='latin-1')
    return {m.group(2): int(m.group(1), 16) for m in re.finditer(
        r'^[.>]([0-9a-fA-F]+)\s+.*?\b([a-zA-Z_][a-zA-Z_0-9]*):', listing, re.M)}


class FileBrowser(FileSystem):
    def __init__(self, folders, files):
        super().__init__(folders)
        self.files = Files(files)

    def __setitem__(self, address, value):
        if address == 0xdf1c and value == 1 and self.command[0] == 2 and self.command[1] in range(2, 8):
            command = bytes(self.command)
            reply = self.files.respond(command)
            if command[1] in self.files.inject:
                reply = self.files.inject[command[1]](command, reply)
            self.packets = deque(reply)
            UCIBus.__setitem__(self, address, value)
        else:
            super().__setitem__(address, value)


class Viewer(Browser):
    def __init__(self, files, real_display=False, folders=None):
        folders = folders or {b'/': [b'\x20'+name for name in files]}
        super().__init__(folders)
        bus = FileBrowser(folders, files)
        bus.ram = self.bus.ram
        self.fs = bus.files
        self.bus = DisplayBus(bus) if real_display else bus
        self.cpu.memory = self.bus
        self.fsym = file_symbols()
        self.real_display = real_display
        for name in (('uos-files', 'uos', 'uos-gfx', 'uos-vdc') if real_display else ('uos-files',)):
            image = (ROOT/'target'/f'{name}.prg').read_bytes()
            origin = int.from_bytes(image[:2], 'little')
            self.bus.ram[origin:origin+len(image)-2] = image[2:]
        if real_display:
            self.bus.ram[0xcc24] = 1
            self.cpu.pc = 0xc000
            self.cpu.stPushWord(0x02ff)
            while self.cpu.pc != 0x0300:
                self.cpu.step()
            self.cpu.pc = 0x5000

    def fvalue(self, name, size=1):
        address = self.fsym[name]
        return int.from_bytes(self.bus.ram[address:address+size], 'little')

    def stub(self):
        if not self.real_display or self.cpu.pc in (0x082c, 0x083b, 0x083e):
            return super().stub()
        return False

    def run(self, key=None, viewer=False, leave=False):
        if key is not None:
            self.keys.append(key)
        idle = self.fsym['view_loop'] if viewer else self.sym['input_loop']
        for step in range(10000000):
            if self.cpu.pc == idle and step and not self.keys:
                self.guards()
                return
            if not self.stub():
                pc = self.cpu.pc
                assert 0x0801 <= pc < 0x1000 or 0x4100 <= pc < 0x6900 or 0x8a00 <= pc < 0x9b00 or 0xc000 <= pc < 0xd000, hex(pc)
                self.cpu.step()
        raise AssertionError('viewer did not reach expected idle loop')

    def click_view(self, x, y, viewer=True):
        sx = x+24
        self.bus.ram[0xd000] = sx & 255
        self.bus.ram[0xd010] = sx >> 8
        self.bus.ram[0xd001] = y+50
        self.button = 0
        self.run(viewer=self.cpu.pc == self.fsym['view_loop'])
        self.button = 0x10
        self.run(viewer=viewer)

    def frame(self):
        assert self.real_display
        return bytes(self.bus.ram[0xa000:0xbf40]), bytes(self.bus.vdc.video[:0x1000])


def check_rows(view, payload):
    page, count = view.fvalue('view_page', 4), view.fvalue('view_count')
    assert count == len(payload[page:page+96])
    assert bytes(view.bus.ram[0x7c00:0x7c00+count]) == payload[page:page+count]
    for row in range(12):
        data = payload[page+row*8:min(page+row*8+8, page+count)]
        text = view.vdc[6+row]
        if data:
            assert text[:26] == (f'{page+row*8:08x}: '+data.hex()).ljust(26), repr(text)
        else:
            assert not text.strip(), repr(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'build': {n: hashlib.sha256((ROOT/'target'/n).read_bytes()).hexdigest()
                        for n in ('uos-files.prg', 'uos-ultimate.prg', 'uos.prg')}, 'checks': []}
    name = b'long-'+b'x'*500+b'.bin'
    payload = bytes((i*29+7) & 255 for i in range(66053))
    v = Viewer({name: payload, b'empty': b''})
    v.run()
    names = v.names()
    v.click_view(200, 17)
    check_rows(v, payload)
    pages = 0
    while v.fvalue('view_page', 4) < 65536:
        v.run(0xce if pages & 1 else ord('N'), viewer=True)
        pages += 1
    check_rows(v, payload)
    while not v.fvalue('view_eof'):
        v.run(ord('N'), viewer=True)
    check_rows(v, payload)
    before = len(v.bus.commands)
    v.run(ord('N'), viewer=True)
    assert len(v.bus.commands) == before, 'Next at EOF sent an extra command'
    v.click_view(50, 179)
    check_rows(v, payload)
    v.click_view(280, 179, viewer=False)
    assert v.names() == names and v.value('selected') == 0
    assert v.fs.handles[2] is None and v.bus.paths[2] == b'/'
    v.run(0x11)
    v.run(ord('V'), viewer=True)
    assert v.fvalue('view_count') == 0 and v.fvalue('view_eof')
    v.run(27)
    assert v.value('selected') == 1 and v.names() == names
    report['checks'].append({'binary_pages_across_64k': pages, 'long_name_bytes': len(name),
                             'mouse_open_prev_close': True, 'EOF_empty_cache_and_path': True})
    for failure in ('absent', 'read_error', 'close_error'):
        v = Viewer({b'file': b'hello'})
        v.run()
        if failure == 'absent':
            v.bus.present = False
        elif failure == 'read_error':
            v.fs.inject[4] = lambda cmd, reply: [(b'h', b'')]
        v.run(ord('V'), viewer=True)
        if failure != 'close_error':
            assert v.fvalue('view_error') and 'Error $' in v.vdc[21]
        else:
            v.fs.inject[3] = lambda cmd, reply: [(b'', b'74,CLOSE FAILED')]
        v.run(27)
        assert 'file view failed' in v.vdc[22]
        assert v.names() == [b'file']
        report['checks'].append({'failure': failure, 'browser_recovered': True})
    v = Viewer({b'file': bytes(range(129))}, real_display=True)
    v.run()
    original = v.frame()
    v.run(ord('V'), viewer=True)
    first = v.frame()
    v.run(ord('N'), viewer=True)
    last = v.frame()
    assert first != last
    v.run(ord('B'), viewer=True)
    assert v.frame() == first, 'Previous did not reproduce the complete first frame'
    v.run(27)
    assert v.frame() == original, 'browser frame differs after viewer return'
    report['checks'].append({'real_VIC_VDC_frame_roundtrips': 2,
                             'first_VIC_sha256': hashlib.sha256(first[0]).hexdigest(),
                             'first_VDC_sha256': hashlib.sha256(first[1]).hexdigest()})
    report['passed'] = True
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print('PASS: browser file viewer', report['checks'], flush=True)


if __name__ == '__main__':
    main()
