#!/usr/bin/env python3
"""Disk-loaded desktop: complete surfaces, controls, fallback and handoffs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--desktop-boot', action='store_true')
parser.add_argument('--report', type=Path, default=ROOT/'target/native-desktop/cpu-report.json')
args = parser.parse_args()
import ci_native_heap as heap
heap.IMAGE = ROOT/('target/native-desktop/uos128.prg' if args.desktop_boot else 'target/native/uos128.prg')
from native_display_bus import DisplayBus
heap.Bus = DisplayBus
import ci_native_calc as calc
from launcher_scene import surface, console
ROOT = Path(__file__).resolve().parents[1]
report = dict(passed=False, hardware_io=False, cases=[])


class Desktop(calc.Calculator):
    instruction_limit = 12000000

    def __init__(self):
        super().__init__('desktop', loader_name=b'BROWSE', image_prefix='native-desktop')

    def heap_call(self, method, *args, **kwargs):
        saved=bytes(self.ram[0x100:0x200])
        try:return getattr(self.m,method)(*args,**kwargs)
        finally:self.ram[0x100:0x200]=saved

    def check(self, selected=0, error=0, fallback=False):
        assert self.value('gd_selected') == selected
        assert self.ram[0x3d2f] == selected
        assert self.value('gd_launch_error') == error
        assert self.value('gd_bitmap') == int(not fallback)
        assert self.screens[1] == console(80, selected, error, fallback), ('VDC text mismatch', selected, error, fallback)
        if fallback:
            assert self.screens[0] == console(40, selected, error, fallback)
            assert self.value('gd_handle') == 0
            assert not self.ram[heap.symbol('v_tag')]
        else:
            actual = bytes(self.ram[0xc000:0xe400])
            wanted = surface(selected, error)
            assert actual == wanted, ('surface mismatch', next((i for i,(a,b) in enumerate(zip(actual,wanted)) if a != b), None))
            assert self.heap_call('stats') == (175-self.image[12]-36, 251, 30)
            assert self.ram[heap.symbol('v_tag')] == self.value('gd_handle')
            assert self.m.bus.video[0xd011] == 0x3b
            assert self.ram[0xd7] & 0x80


def done(name, d):
    report['cases'].append(dict(name=name, events=d.events, instructions=d.instructions))
    print('PASS:', name, flush=True)


original_machine = calc.Machine
try:
    d = Desktop();d.check()
    for key, selected in [(9,1),(0x11,2),(0x1d,0),(0x91,2),(0x9d,1),(0x13,0),(ord('?'),0)]:
        d.key(key);d.check(selected)
    d.key(27, exited=True)
    assert d.ram[0x3d28] == 2 and not d.ram[heap.symbol('v_tag')]
    assert d.m.bus.video[0xd011] == 0x1b and d.ram[1] == 0x73 and d.ram[0xd8] == 0
    done('complete surfaces, navigation wrap, home, ignored input, workspace cleanup', d)
    for saved in (0,1,2,3,127,255):
        class SelectedMachine(original_machine):
            def __init__(self):
                super().__init__();self.ram[0x3d2f]=saved
        calc.Machine=SelectedMachine
        d=Desktop();d.check(saved if saved<3 else 0);d.key(27,exited=True)
        done('restore or repair saved desktop selection '+str(saved),d)
    calc.Machine=original_machine
    for selected in (0,1,2):
        d=Desktop()
        for _ in range(selected):d.key(9)
        d.check(selected);d.key(27,exited=True)
        machine=d.m
        calc.Machine=lambda:machine
        d=Desktop();d.check(selected);d.key(27,exited=True)
        done('desktop reload retains selection and releases both allocations '+str(selected),d)
        calc.Machine=original_machine
    for key, name in [(13,b'CALC'),(ord('c'),b'CALC'),(ord('E'),b'EDITOR'),(ord('f'),b'FILES')]:
        d = Desktop();d.key(key, exited=True)
        assert d.ram[0x3d28] == 1 and d.ram[0x3d21:0x3d23] == bytes([8,len(name)])
        assert d.ram[0x3d2c] == 0 and bytes(d.ram[0x3d40:0x3d40+len(name)]) == name
        assert not d.ram[heap.symbol('v_tag')] and d.m.bus.video[0xd011] == 0x1b
        assert d.ram[0x3d2f] == {b'CALC':0,b'EDITOR':1,b'FILES':2}[name]
        done('owned app handoff '+name.decode()+' key '+str(key), d)
    class ErrorMachine(original_machine):
        def __init__(self):
            super().__init__();self.ram[0x3d2b]=0x11
    calc.Machine = ErrorMachine
    d = Desktop();d.check(error=0x11);assert d.ram[0x3d2b] == 0
    d.key(9);d.check(1,error=0x11);d.key(27,exited=True)
    done('dispatcher failure visible in complete graphics and VDC text', d)
    class FragmentedMachine(original_machine):
        def __init__(self):
            super().__init__();self.obstacle=self.alloc(1,0,77,page=0xd0)
    calc.Machine = FragmentedMachine
    d=Desktop();d.check(fallback=True);assert d.value('gd_error') == 2
    d.key(9);d.check(1,fallback=True)
    d.m.select(d.m.obstacle,77);d.heap_call('invoke','free')
    d.key(13,exited=True);assert bytes(d.ram[0x3d40:0x3d46]) == b'EDITOR'
    done('fragmented surface refusal retains unrelated owner and text app controls',d)
    class UnsupportedMachine(original_machine):
        def __init__(self):
            super().__init__();self.bus.video[0xd015]=1
    calc.Machine=UnsupportedMachine
    d=Desktop();d.check(fallback=True);assert d.value('gd_error') == 8
    assert d.heap_call('stats') == (175-d.image[12],251,31)
    assert d.m.bus.video[0xd015] == 1
    d.key(27,exited=True)
    done('unsupported display releases surface and retains usable text consoles',d)
    calc.Machine=original_machine
    files=calc.Calculator('files',loader_name=b'FILES',image_prefix='native-desktop')
    files.key(27,exited=True)
    assert files.ram[0x3d28] == 0
    done('Files exits to dispatcher desktop without workspace request',files)
    report['passed']=True
except BaseException as error:
    report['error']=str(error)
    raise
finally:
    calc.Machine=original_machine
    report['images']={name:hashlib.sha256((ROOT/'target/native-desktop'/name).read_bytes()).hexdigest() for name in ('desktop.prg','files.prg')}
    report['images']['uos128.prg']=hashlib.sha256(heap.IMAGE.read_bytes()).hexdigest()
    report['kernel_path']=str(heap.IMAGE.relative_to(ROOT))
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
