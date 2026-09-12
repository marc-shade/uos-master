#!/usr/bin/env python3
"""Keep a real large document, surface and picker cache in base C128 RAM."""
import hashlib
import json
from pathlib import Path
from py65.devices.mpu6502 import MPU
import ci_native_heap as heap
from native_display_bus import DisplayBus
heap.Bus=DisplayBus
from ci_native_file_dialog import DialogEditor,ROOT

MODULE=(ROOT/'module/GRAPHICS.PRG').read_bytes()
EXPECTED=(ROOT/'client/expected-surface.bin').read_bytes()
raw=(b'0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n'*1800)[:66053]
want=raw[:65537]+b'C12'+raw[65537:]
entries=[b'\x20'+f'FILE {i:04d}'.encode() for i in range(300)]
report=dict(passed=False,hardware_io=False,kernel_sha256=hashlib.sha256((ROOT/'target/native/uos128.prg').read_bytes()).hexdigest(),
            editor_sha256=hashlib.sha256((ROOT/'target/native/editor.prg').read_bytes()).hexdigest(),
            module_sha256=hashlib.sha256(MODULE).hexdigest(),snapshots=[],calls=[])


def call(e,entry,expected=0):
    # Model a foreground call from the retained app core. Preserve the suspended
    # editor's hardware stack while running the actual public service entry.
    stack=bytes(e.ram[0x100:0x200]);caller=e.symbol('cloop');cpu=MPU(memory=e.m.bus,pc=entry)
    cpu.sp=0xd0;cpu.p=0x20;cpu.stPushWord(caller-1)
    try:
        for steps in range(15000000):
            if cpu.pc==caller and cpu.sp==0xd0:break
            if not e.io.stub(cpu):cpu.step()
        else:raise AssertionError(('service did not return',hex(cpu.pc)))
        assert (cpu.a,cpu.p&1)==(expected,int(bool(expected))),(hex(entry),cpu.a,cpu.p)
        assert e.m.bus.config==0x0e and cpu.p&12==0
        report['calls'].append(dict(entry=entry,error=expected,instructions=steps))
    finally:e.ram[0x100:0x200]=stack


def snapshot(e,label,data):
    assert e.contents()==data
    records=[]
    for index in range(32):
        r=bytes(e.ram[0x3c00+index*8:0x3c08+index*8])
        if r[0]:records.append(dict(handle=index+1,owner=r[0],bank=r[1],page=r[2],pages=r[3],generation=int.from_bytes(r[4:7],'little')))
    report['snapshots'].append(dict(label=label,free=e.m.stats(),records=records,
        document_bytes=len(data),document_sha256=hashlib.sha256(data).hexdigest(),
        document_state=e.state()|{'handles':e.state()['handles'].hex()}))


def editor():
    e=DialogEditor(usb={b'/Usb0/LARGE':raw},directories={b'/':[b'\x10Usb0'],b'/Usb0':entries})
    e.io.files[8,b'GRAPHICS.PRG',b'P']=MODULE
    for _ in range(3):e.key(0x8b)
    return e


def graphics(e,surface):
    e.ram[0x3d86]=12;e.ram[0x3da0:0x3dac]=b'GRAPHICS.PRG'
    call(e,0x1c5f)
    assert e.ram[0x3d1b]==2
    token=bytes(e.ram[0x3d17:0x3d1a])
    e.m.select(surface,32);call(e,0x1c62)
    assert e.ram[heap.symbol('v_tag')]==surface[0] and e.ram[0xd8]==255
    assert bytes(e.m.bus.ram[0][0xc000:0xe400])==EXPECTED
    assert e.m.bus.video[0xd011]==0x3b and e.m.bus.video[0xd018]==0x80
    return token


try:
    e=editor();video=dict(e.m.bus.video),e.ram[1],e.ram[0xd8],e.m.bus.compare
    surface=e.heap_call('alloc',36,0,32,page=0xc0)
    e.m.select(surface,32)
    for offset in range(0,9216,512):
        e.m.set(heap.VALUE,0xaa if offset<8192 else 0xe6)
        e.heap_call('transfer','fill',offset,512)
    e.prompt(0x85,'/Usb0/LARGE');e.check(raw,0,False,name='/Usb0/LARGE')
    e.prompt(0x88,'010001');e.type('C128');e.key(20);e.check(want,65540,True)
    snapshot(e,'large-document-with-reserved-surface',want)
    token=graphics(e,surface);snapshot(e,'graphics-module-visible',want)
    call(e,0x1c6b)
    assert not e.ram[heap.symbol('v_tag')]
    assert (e.m.bus.video,e.ram[1],e.ram[0xd8],e.m.bus.compare)==video
    e.begin(mode=2,name='/Usb0/LARGE COPY')
    for base in range(8,264,8):e.type('N')
    e.check_picker(path=b'/Usb0/',entries=entries[256:264],base=256,device=1,more=True)
    snapshot(e,'picker-ordinal-256-with-document-and-surface',want)
    assert sum(e.m.stats()[:2])==31,e.m.stats()
    assert bytes(e.m.bus.ram[0][0xc000:0xe400])==EXPECTED
    e.key(27);e.intact(returned=True);e.check(want,65540,True,mode=2)
    current_token=bytes(e.ram[0x3d17:0x3d1a]);assert current_token!=token
    e.ram[0x3d17:0x3d1a]=token;call(e,0x1c62,4)
    e.ram[0x3d17:0x3d1a]=current_token
    e.key(13);e.check(want,65540,False,status=1,name='/Usb0/LARGE COPY')
    assert e.ultimate.files[b'/Usb0/LARGE COPY']==want
    snapshot(e,'verified-save-with-surface-retained',want)
    newer=graphics(e,surface);assert newer!=token
    snapshot(e,'graphics-reloaded-after-picker-and-save',want)
    e.m.select(surface,32);e.heap_call('invoke','free')
    assert not e.ram[heap.symbol('v_tag')]
    assert (e.m.bus.video,e.ram[1],e.ram[0xd8],e.m.bus.compare)==video
    e.check(want);e.exit();assert e.m.stats()==(175,251,32)
    report['complete_lifecycle_passed']=True
    print('PASS: 79-page editor, 36-page surface, full 66056-byte document and eight picker-cache pages; 31 pages remain',flush=True)

    e=editor();e.prompt(0x85,'/Usb0/LARGE');e.check(raw,0,False)
    before=e.m.metadata();e.heap_call('alloc',36,0,32,page=0xc0,expected=2)
    assert e.m.metadata()==before and not e.ram[heap.symbol('v_tag')]
    e.check(raw);snapshot(e,'late-surface-reservation-rejected-with-document-intact',raw)
    e.exit();report['late_reservation_rejection_passed']=True
    report['passed']=True
    print('PASS: late aligned-surface reservation fails without changing the document or existing allocations',flush=True)
except BaseException as error:report['error']=str(error);raise
finally:(ROOT/'graphics/layout-report.json').write_text(json.dumps(report,indent=2)+'\n')
