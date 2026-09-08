#!/usr/bin/env python3
"""Measure browser instruction cycles with the assembled VIC and VDC drivers.

Uses the UCI filesystem model and real graphics code. VDC readiness is immediate
after a required poll; VIC bad lines, IRQs, DMA pauses and host latency are not
modeled. Compare this report with physical timings before claiming performance.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path

from ci_ultimate import Browser, ROOT
from ci_vdc_protocol import VDC


class DisplayBus:
    def __init__(self, filesystem):
        self.filesystem = filesystem
        self.vdc = VDC()
        self.vdc.ram = filesystem.ram

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, 'filesystem'), name)

    def __getitem__(self, address):
        if address in (0xd600,0xd601):
            value = self.vdc[address]
            self.vdc.busy = 0
            return value
        if 0xdf1c <= address <= 0xdf1f:
            return self.filesystem[address]
        return self.ram[address]

    def __setitem__(self, address, value):
        if address in (0xd600,0xd601):
            self.vdc[address] = value
            self.vdc.busy = 0
        elif address == 0xdf1c or address == 0xdf1d:
            self.filesystem[address] = value
        else:
            self.ram[address] = value


class RenderBrowser(Browser):
    def __init__(self, folders):
        super().__init__(folders)
        self.bus = DisplayBus(self.bus)
        self.cpu.memory = self.bus
        for name in ('uos','uos-gfx','uos-vdc'):
            image = (ROOT/'target'/f'{name}.prg').read_bytes()
            origin = int.from_bytes(image[:2],'little')
            self.bus.ram[origin:origin+len(image)-2] = image[2:]
        self.bus.ram[0xcc24] = 1
        self.cpu.pc = 0xc000
        self.cpu.stPushWord(0x02ff)
        while self.cpu.pc != 0x0300:
            self.cpu.step()
        self.cpu.pc = 0x5000

    def stub(self):
        if self.cpu.pc in (0x082c,0x083b,0x083e):
            return super().stub()
        return False

    def measure(self, key=None):
        if key is not None:
            self.keys.append(key)
        counts = Counter()
        for steps in range(30000000):
            pc = self.cpu.pc
            if pc == self.sym['input_loop'] and steps and not self.keys:
                self.guards()
                return {'cycles':sum(counts.values()),'by_module':dict(counts),'instructions':steps}
            before = self.cpu.processorCycles
            if not self.stub():
                assert (0x0801 <= pc < 0x1000 or 0x5000 <= pc < 0x6000
                        or 0x8a00 <= pc < 0x9b00 or 0xc000 <= pc < 0xd000),hex(pc)
                self.cpu.step()
            module = ('core' if pc < 0x1000 else 'browser' if pc < 0x6000
                      else 'uci' if pc < 0xc000 else 'vic' if pc < 0xcc00 else 'vdc')
            counts[module] += self.cpu.processorCycles-before
        raise AssertionError('Renderer did not return to input')

    def call(self, name):
        self.cpu.pc = self.sym[name]
        self.cpu.stPushWord(0x02ff)
        for _ in range(30000000):
            if self.cpu.pc == 0x0300:
                return
            self.cpu.step()
        raise AssertionError(f'Renderer {name} did not return')

    def check_fresh(self):
        """Incremental results must equal a fresh frame from the same state."""
        fresh = copy.deepcopy(self)
        fresh.bus.ram[0xa000:0xbf40] = bytes(8000)
        fresh.bus.vdc.video[:0x1000] = bytes([0xa5])*0x1000
        fresh.call('frame')
        fresh.bus.ram[fresh.sym['dirty']] = 31
        fresh.call('paint')
        for name,a,b in [('VIC',self.bus.ram[0xa000:0xbf40],fresh.bus.ram[0xa000:0xbf40]),
                         ('VDC',self.bus.vdc.video[:0x1000],fresh.bus.vdc.video[:0x1000])]:
            if a != b:
                differences = [i for i in range(len(a)) if a[i] != b[i]]
                raise AssertionError(f'{name} differs from fresh rendering at {differences[:16]}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--check-fresh',action='store_true')
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    names = [b'long-'+b'x'*290+b'-END']+[f'folder-{i:04d}'.encode() for i in range(1,18)]
    b = RenderBrowser({b'/':[b'\x10'+name for name in names]})
    def build_hashes():
        return {n:hashlib.sha256((ROOT/'target'/n).read_bytes()).hexdigest()
                for n in ('uos.prg','uos-ultimate.prg','uos-gfx.prg','uos-vdc.prg','uos-net.prg')}

    report={'model':__doc__,'build':build_hashes(),'actions':{},'passed':False}

    def record(name, key=None):
        result = b.measure(key)
        report['actions'][name] = result
        (args.out/f'{name}.vic.bin').write_bytes(b.bus.ram[0xa000:0xbf40])
        (args.out/f'{name}.vdc.bin').write_bytes(b.bus.vdc.video[:0x1000])
        try:
            if args.check_fresh:
                b.check_fresh()
                result['matches_fresh_frame'] = True
        except AssertionError as error:
            result['error'] = str(error)
            raise
        finally:
            (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(name,json.dumps(result),flush=True)

    actions = [('initial',None),('down',0x11),('next',ord('N')),('previous',ord('B'))]
    if args.check_fresh:
        actions += [('name-right',0x1d),('name-left',0x9d),('path',ord('P')),
                    ('select-after-path',0x11),('last-page',ord('N')),
                    ('short-page',ord('N')),('end-bound',ord('N'))]
    for name,key in actions:
        record(name, key)
    if args.check_fresh:
        b.bus.filesystem.reject_open = True
        record('directory-error', ord('R'))
        b.bus.filesystem.reject_open = False
        record('retry', ord('R'))
        b.bus.filesystem.folders[b'/'] = []
        record('empty-directory', ord('R'))
        # Exercise the font's full vertical extent, maximum-width glyphs,
        # and all printable filename bytes (slash is not a valid component).
        wide = b'$gpjqy' + b'mw'*145 + b'-END'
        printable = bytes(c for c in range(0x20,0x7f) if c != ord('/'))
        b.bus.filesystem.folders[b'/'] = [b'\x10'+wide, b'\x10s', b'\x10'+printable]
        for name,key in [('wide-glyphs',ord('/')),('wide-to-short',0x11),
                         ('printable-glyphs',0x11),('printable-to-short',0x91),
                         ('short-to-wide',0x91),('invalid-open',13),
                         ('clear-error',ord('R'))]:
            record(name,key)
    assert report['build'] == build_hashes(), 'Build changed during profiling'
    report['passed'] = True
    (args.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
