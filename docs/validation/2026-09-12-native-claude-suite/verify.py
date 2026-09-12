#!/usr/bin/env python3
"""Audit retained suite images, CPU reports and complete emulator screen data."""
import hashlib
import json
import struct
from pathlib import Path
import sys

sys.dont_write_bytecode = True
A = Path(__file__).resolve().parent
I = A/'inputs'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
inputs = read(A/'inputs.json')
for name,digest in inputs.items(): assert sha(I/name)==digest,name
sys.path[:0] = [str(I),str(I/'apps/claude/host')]
from launcher_scene import surface, console
from native_claude_check import landing_screen
from native_image import validate
import font
import petscii

deployment = read(I/'target/native-desktop/deployment.json')
assert deployment['abi']=='1.10' and deployment['free_pages_at_desktop']==371
assert deployment['desktop']['pages']==19 and deployment['claude']['pages']==49
assert deployment['controls']['pages']==11 and deployment['surface_pages']==36
for kind in ('claude','controls','desktop'):
    info=validate((I/f'target/native-desktop/{kind}.prg').read_bytes())
    assert info==deployment[kind]
assert read(I/'target/native-desktop/layout.json')['nmi_gate_start']==0x1bf0
assert read(I/'target/native-desktop/layout.json')['nmi_gate_end']==0x1bf8
rebuild=read(A/'clean-rebuild.json'); assert rebuild['passed'] and len(rebuild['images'])==19
for name,meta in rebuild['images'].items():
    assert sha(I/name)==meta['sha256'] and (I/name).stat().st_size==meta['bytes']
extract=read(A/'package-extraction.json');assert extract['passed'] and len(extract['entries'])==4
for row in extract['entries']:
    name=row['disk']+'-'+row['entry']+'.prg'
    data=(A/'package-extractions'/name).read_bytes()
    expected=I/'target/native-desktop'/('claude.prg' if row['entry']=='claude' else 'controls.prg')
    assert data==expected.read_bytes() and sha(expected)==row['sha256']
cpu=read(A/'cpu-regressions/report.json')
assert cpu['passed'] and cpu['images_unchanged'] and len(cpu['results'])==30
assert all(code==0 for code in cpu['results'].values())
for name in cpu['results']:
    report=read(A/'cpu-regressions'/(name+'.json'))
    assert report.get('passed'),name
for name,digest in read(A/'cpu-regressions/images-before.json').items():assert sha(I/name)==digest,name
assert len(read(A/'cpu-regressions/claude.json')['cases'])==7
assert len(read(A/'desktop-cpu.json')['cases'])==24 and read(A/'desktop-cpu.json')['passed']
assert '30/30 passed' in (A/'host-final-tests.log').read_text()
assert read(A/'bridge-controls.json')['passed'] and len(read(A/'bridge-controls.json')['cases'])==4

total_pixels=0
for name in ('desktop40','desktop80'):
    w=A/'emulators'/name;r=read(w/'report.json')
    assert r['passed'] and not r['physical_hardware_io']
    assert r['disk_sha256']==sha(I/'target/native-desktop/uos128.d64')
    assert r['kernel_sha256']==sha(I/'target/native-desktop/uos128.prg')
    assert (w/'desktop.d64').read_bytes()==(I/'target/native-desktop/uos128.d64').read_bytes()
    assert r['resident_boot']['passed'] and r['resident_return']['passed']
    for row in r['desktops']:
        label,selected,error,fallback=row['label'],row['selected'],row['error'],row['fallback']
        assert (w/(label+'-80.bin')).read_bytes()==console(80,selected,error,fallback)
        if fallback:
            assert (w/(label+'-40.bin')).read_bytes()==console(40,selected,error,True)
        else:
            bitmap=surface(selected,error)
            assert (w/(label+'-surface.bin')).read_bytes()==bitmap
            assert row['pixels']==64000
            raw=(w/(label+'-display-get.bin')).read_bytes()
            fields,=struct.unpack_from('<I',raw)
            width,height,xoff,yoff,innerw,innerh,bpp=struct.unpack_from('<6HB',raw,4)
            length,=struct.unpack_from('<I',raw,4+fields)
            pixels=raw[8+fields:]
            assert bpp==8 and length==width*height and length-len(pixels) in (0,4)
            left,top,cols,rows=row['rectangle'];assert (cols,rows)==(320,200)
            for y in range(200):
                expected=bytearray()
                for x in range(320):
                    color=bitmap[8192+y//8*40+x//8]
                    ink=bitmap[y//8*320+x//8*8+y%8]&(128>>(x%8))
                    expected.append(color>>4 if ink else color&15)
                assert pixels[(top+y)*width+left:(top+y)*width+left+320]==expected
            total_pixels+=row['pixels']
    for columns in (40,80):
        assert (w/f'claude-launch-page-{columns}.bin').read_bytes()==landing_screen(columns)

for name in ('claude-f8','claude-host-exit80'):
    w=A/'emulators'/name;r=read(w/'report.json')
    assert r['passed'] and not r['physical_hardware_io'] and r['host_exit_code']==0
    for item,digest in r['images'].items():assert sha(I/'target/native-desktop'/item)==digest
    assert (w/'suite.d64').read_bytes()==(I/'target/native-desktop/uos128.d64').read_bytes()
    for label,selection in (('boot-desktop',0),('returned-desktop',4)):
        assert (w/(label+'-surface.bin')).read_bytes()==surface(selection)
        assert (w/(label+'-vdc.bin')).read_bytes()==console(80,selection)
    assert (w/'font-before.bin').read_bytes()==(w/'font-after.bin').read_bytes()
    during=(w/'font-during.bin').read_bytes();code=font.CODES['❯']
    assert during[code*16:code*16+16]==bytes(font.BITMAPS[code])+bytes(8)
    expected=bytearray(b' '*2000)
    for row,text in enumerate(['UOS CLAUDE LINK READY','❯ ✳ ⏺','Keyboard, glyphs and return test',
                               'KEY RECEIVED: p','ESCAPE RECEIVED']):
        data=bytes(petscii.to_screen_code(c) for c in text)
        expected[row*80:row*80+len(data)]=data
    assert (w/'session-vdc.bin').read_bytes()==expected
    count=r['serial_counters']
    assert count['_rxCount']==count['_nmiCount'] and count['_rxDropped']==count['_rxOverruns']==0
    heap=(w/'final-heap.bin').read_bytes()
    assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251)
    assert r['events']==[65,13,80,27,132,81 if r['options']['host_exit'] else 140,27]
    assert (w/'bridge.log').read_text().count('client asked for a resync')>=2

for w in (A/'history').iterdir(): assert not read(w/'report.json')['passed']
print('PASS: 401 frozen inputs, 19 reproduced images, 30 native CPU suites, 34 host checks, four VICE workflows')
print('Retained full desktop rendered-pixel checks:',total_pixels)
