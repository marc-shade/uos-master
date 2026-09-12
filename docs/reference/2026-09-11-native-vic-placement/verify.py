#!/usr/bin/env python3
"""Rebuild and audit the retained native VIC experiment without machine I/O."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import native_image

def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

meta=read(HERE/'observations.json')
assert not meta['physical_hardware_io'] and not meta['kernel_display_lease']
reports={name:read(HERE/name/'report.json') for name in meta['runs']}
assert reports['probe']['passed'] and not reports['probe']['graphics_mode_tested']
assert reports['probe']['vic_interrupt_masks']==[1]*3
assert reports['probe']['common_and_vic_bank_registers']==[4]*3
assert reports['initial-client']['passed']
assert not reports['first-canvas-parser-failure']['passed']
assert not reports['canvas-length-diagnostic']['passed']
assert reports['corrected']['passed'] and not reports['negative-control']['passed']

for name in ('initial-client','corrected'):
    folder=HERE/name
    with tempfile.TemporaryDirectory(prefix='uos-vic-rebuild-') as scratch:
        output=Path(scratch)/'display.prg'
        subprocess.run(['64tass','-a','-I',str(folder),'-o',str(output),str(folder/'display.asm')],
                       check=True,capture_output=True)
        assert native_image.seal(output.read_bytes())==(folder/'DISPLAY.PRG').read_bytes()
assert native_image.validate((HERE/'initial-client/DISPLAY.PRG').read_bytes())['bytes']==432
assert native_image.validate((HERE/'corrected/DISPLAY.PRG').read_bytes())['bytes']==468
assert (HERE/'negative-control/DISPLAY.PRG').read_bytes()==(HERE/'initial-client/DISPLAY.PRG').read_bytes()
for name,report in reports.items():
    assert report['source_disk_sha256']==meta['source_disk_sha256']
    if name=='probe':continue
    assert not report['physical_hardware_io'] and not report['kernel_display_lease']
    assert sha(HERE/name/'DISPLAY.PRG')==report['prototype_sha256']
    assert sha(HERE/name/'native.d64')==report['private_disk_start_sha256']
    for observation in report['observations']:
        for field,value in observation.items():
            if field!='label':
                assert (HERE/name/(observation['label']+'-'+field+'.bin')).read_bytes().hex()==value

def canvas(folder,label,expected_rows):
    raw=(HERE/folder/(label+'-display-get.bin')).read_bytes()
    fields,width,height,x,y,iw,ih,bpp=struct.unpack_from('<I6HB',raw)
    (declared,)=struct.unpack_from('<I',raw,4+fields);pixels=raw[8+fields:]
    assert (fields,width,height,bpp,declared,len(pixels))==(13,384,272,8,104448,104444)
    pattern=bytes([14,6])*160
    matches=[(y,pixels[y*width:(y+1)*width].find(pattern)) for y in range(height)]
    matches=[(y,x) for y,x in matches if x>=0]
    assert len(matches)==expected_rows
    if expected_rows==200:
        assert matches==[(y,32) for y in range(35,235)]
        record=next(c for c in reports[folder]['canvases'] if c['label']==label)
        assert record['passed'] and record['rectangle']==[32,35,320,200]
        assert record['matching_pixels']==64000 and record['missing_tail_bytes']==4

for label in ('explicit-exit','normal-return'):
    canvas('corrected',label,200)
    assert (HERE/'corrected'/(label+'-surface.bin')).read_bytes()==b'\xaa'*8192+b'\xe6'*1024
canvas('negative-control','explicit-exit',96)
assert not reports['negative-control']['canvases'][0]['passed']
assert 'rendered VIC bitmap differs' in (HERE/'negative-control/workflow.log').read_text()

corrected=reports['corrected'];observed={r['label']:r for r in corrected['observations']}
assert corrected['successful_presentations']==2 and corrected['surface_bytes_per_success']==9216
assert corrected['source_disk_unchanged'] and corrected['private_disk_unchanged']
assert corrected['refused_reservation_preserved_existing_bytes']
assert [e['key'] for e in corrected['events']]==[67,27,67,13,65,67,27,70]
for label in ('explicit-exit','normal-return'):
    samples=[observed[f'{label}-active-{n}'] for n in range(3)]
    assert len({r['jiffy'] for r in samples})==3
    for sample in samples:
        assert sample['port']=='2f75' and sample['irq_vector']=='65fa'
        assert sample['mmu']==observed['boot']['mmu']
        assert bytes.fromhex(sample['text_mode'])[1]==255
        vic=bytes.fromhex(sample['vic'])
        assert vic[0x11]&0x7f==0x3b and vic[0x16]&0x3f==8 and vic[0x18]&0xfe==0x80
        assert vic[0x1a]&15==1
        heap=bytes.fromhex(sample['heap']);tag=heap[0xc0]
        assert 1<=tag<=32 and heap[0xc0:0xe4]==bytes([tag])*36
        assert heap[0x400+(tag-1)*8:0x404+(tag-1)*8]==bytes([32,0,0xc0,36])
        assert heap[:256].count(0)==135 and heap[256:512].count(0)==251
    restored=observed[label+'-restored']
    assert restored['port']=='2f73' and bytes.fromhex(restored['text_mode'])[1]==0
    assert restored['irq_vector']=='65fa' and restored['mmu']==observed['boot']['mmu']
    heap=bytes.fromhex(restored['heap'])
    assert heap[0xc0:0xe4]==bytes(36)
    assert heap[:256].count(0)==175 and heap[256:512].count(0)==251
    assert bytes.fromhex(restored['app'])[0]==0 and bytes.fromhex(restored['app'])[3]==0

before=bytes.fromhex(observed['before-refused-reservation']['heap'])
failed=bytes.fromhex(observed['refused-reservation']['heap'])
assert before[0xdf:0xff]==failed[0xdf:0xff] and len(set(before[0xdf:0xff]))==1
assert before[0xdf]!=0 and observed['refused-reservation']['port']=='2f73'
assert bytes.fromhex(observed['refused-reservation']['prototype'])[:3]==bytes([1,2,0])

def workspace(columns,free,slots,handle,result):
    lines=['UOS 128 - NATIVE MEMORY WORKSPACE','', 'SELECTED BANK: 0',
           f'FREE 256-BYTE PAGES (HEX) 0/1: {free[0]:02X}/{free[1]:02X}',
           f'FREE HANDLES (HEX): {slots:02X}',f'SELECTED HANDLE: {int.from_bytes(handle,"little"):08X}',
           f'LAST RESULT: {result:02X}','','1/2 SELECT BANK  A ALLOCATE 8K',
           'W FILL  V VERIFY  F RELEASE','C CALCULATOR  B FILES AND APPS',
           '00 OK  04 INVALID HANDLE  0A MISMATCH','','NATIVE DESKTOP MIGRATION IN PROGRESS']
    lines+=['']*(25-len(lines))
    return bytes(ord(c)-64 if 'A'<=c<='Z' else ord(c) for line in lines for c in line.ljust(columns))

assert len(corrected['screens'])==6
for screen in corrected['screens']:
    allocated=screen['label'] in ('workspace-allocation','refused-restored')
    assert screen['free']==([143,251] if allocated else [175,251])
    assert screen['slots']==(31 if allocated else 32)
    assert screen['result']==(2 if screen['label']=='refused-restored' else 0)
    for columns in (40,80):
        actual=(HERE/'corrected'/f'{screen["label"]}-{columns}.bin').read_bytes()
        assert actual==workspace(columns,screen['free'],screen['slots'],bytes.fromhex(screen['handle']),screen['result'])
print('PASS: two rebuilt clients, two complete surfaces/64000-pixel frames, IRQ/ownership/restoration, six text-screen pairs and rejected ROM-overlay control')
