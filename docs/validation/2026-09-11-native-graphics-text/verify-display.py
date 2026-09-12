#!/usr/bin/env python3
"""Rebuild the graphics client and audit complete surfaces, pixels and lifetime."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ARCHIVE=Path(__file__).resolve().parent;FOLDER=ARCHIVE/'display-emulator'
BASE=ARCHIVE.parent/'2026-09-11-native-display-lifetime'
SOURCE=ARCHIVE/'source'
sys.dont_write_bytecode=True;sys.path[:0]=[str(SOURCE),str(BASE/'frozen')]
from graphics_oracle import surface
from graphics.font import font
from native_image import seal
from native_files_check import exact_d64_files
from native_browser_check import disk_records,browser_screen
from native_capture import expected_screen,calculator_screen

parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
read=lambda name:json.loads((ARCHIVE/name).read_text())
sha=lambda data:hashlib.sha256(data).hexdigest()
report=read('display-emulator/report.json');images=json.loads((BASE/'images.json').read_text())
expected=surface()
assert (FOLDER/'expected-surface.bin').read_bytes()==expected
assert sha(expected)==report['surface_oracle_sha256']
assert (FOLDER/'font8.bin').read_bytes()==font()
assert report['passed'] and not report['physical_hardware_io'] and report['kernel_display_lease']
assert report['source_disk_sha256']==images['uos128.d64']['sha256']
assert report['source_disk_unchanged'] and report['private_disk_unchanged']
client=(FOLDER/'DISPLAY.PRG').read_bytes();disk=(FOLDER/'native.d64').read_bytes()
assert sha(client)==report['prototype_sha256'] and sha(disk)==report['private_disk_start_sha256']
with tempfile.TemporaryDirectory(prefix='uos-display-client-rebuild-') as temporary:
    output=Path(temporary)/'display.prg'
    subprocess.run(['64tass','-a','-B','-I',str(FOLDER),str(FOLDER/'display.asm'),'-o',str(output)],check=True,capture_output=True)
    assert seal(output.read_bytes())==client
files=exact_d64_files(disk);assert len(files)==7 and files[b'CALC']==(2,client)
for name,image in ((b'U','uos128.prg'),(b'BROWSE','browse.prg'),(b'EDITOR','editor.prg'),
                   (b'EDPICK.PRG','edpick.prg'),(b'TEXTAPP','calc.prg')):
    assert files[name]==(2,(BASE/'frozen/target/native'/image).read_bytes())
assert files[b'GRAPHCHK']==(1,b'\xa5'*513)
observed={row['label']:row for row in report['observations']};assert len(observed)==23
for label,row in observed.items():
    for name,value in row.items():
        if name!='label':assert (FOLDER/(label+'-'+name+'.bin')).read_bytes().hex()==value
boot=observed['boot'];assert boot['port']=='2f73' and boot['irq_vector']=='65fa'
assert bytes.fromhex(boot['text_mode'])[1]==0
def active(row):
    assert row['mmu']==boot['mmu'] and row['irq_vector']==boot['irq_vector']
    assert row['port']=='2f75' and bytes.fromhex(row['text_mode'])[1]==255
    vic=bytes.fromhex(row['vic']);cia=bytes.fromhex(row['cia2'])
    assert vic[0x11]&0x7f==0x3b and vic[0x16]&0x3f==8 and vic[0x18]&0xfe==0x80
    assert vic[0x1a]&15==1 and cia[0]&3==0 and cia[2]&3==3
    heap=bytes.fromhex(row['heap']);assert len(heap)==1536
    tag=heap[0xc0];assert tag and heap[0xc0:0xe4]==bytes([tag])*36
    assert int(row['kernel_display_tag'],16)==tag
    assert heap[0x400+(tag-1)*8:0x404+(tag-1)*8]==bytes([32,0,0xc0,36])
def restored(row):
    assert row['kernel_display_tag']=='00' and row['port']==boot['port']
    assert row['mmu']==boot['mmu'] and row['irq_vector']==boot['irq_vector']
    assert bytes.fromhex(row['text_mode'])[1]==0
    before=bytes.fromhex(boot['vic']);after=bytes.fromhex(row['vic'])
    assert after[0x11]&0x7f==before[0x11]&0x7f and after[0x16:0x19]==before[0x16:0x19]
    assert bytes.fromhex(row['cia2'])[0]&3==bytes.fromhex(boot['cia2'])[0]&3
    assert bytes.fromhex(row['heap'])[0xc0:0xe4]==bytes(36)
for label in ('explicit-exit','normal-return','surface-free'):
    samples=[observed[f'{label}-active-{index}'] for index in range(3)]
    assert len({row['jiffy'] for row in samples})==3
    for row in samples:active(row)
    assert (FOLDER/(label+'-surface.bin')).read_bytes()==expected
    row=observed[label+'-restored'];restored(row)
    heap=bytes.fromhex(row['heap']);app=bytes.fromhex(row['app'])
    assert heap[:256].count(0)==175 and heap[256:512].count(0)==251 and app[0]==app[3]==0
released=observed['surface-free-before-exit'];restored(released)
assert bytes.fromhex(released['app'])[0]==32 and bytes.fromhex(released['prototype'])[:3]==bytes([3,0,0])
for record in report['canvases']:
    label=record['label'];raw=(FOLDER/(label+'-display-get.bin')).read_bytes()
    fields,width,height,x,y,iw,ih,bpp=struct.unpack_from('<I6HB',raw)
    (declared,)=struct.unpack_from('<I',raw,4+fields);pixels=raw[8+fields:]
    assert (fields,width,height,bpp,declared,len(pixels))==(13,384,272,8,104448,104444)
    want=[]
    for py in range(200):
        row=bytearray()
        for px in range(320):
            bits=expected[(py//8)*320+(px//8)*8+py%8]
            colors=expected[8192+(py//8)*40+px//8]
            row.append(colors>>4 if bits&(128>>(px%8)) else colors&15)
        want.append(bytes(row))
    assert all(pixels[(py+35)*width+32:(py+35)*width+352]==want[py] for py in range(200))
    assert record['passed'] and record['rectangle']==[32,35,320,200]
    assert record['matching_pixels']==64000 and record['missing_tail_bytes']==4
assert len(report['canvases'])==5
before=bytes.fromhex(observed['before-refused-reservation']['heap'])
failed=observed['refused-reservation'];after=bytes.fromhex(failed['heap'])
assert before[0xdf:0xff]==after[0xdf:0xff] and before[0xdf]
assert failed['port']=='2f73' and bytes.fromhex(failed['prototype'])[:3]==bytes([1,2,0])
assert report['refused_reservation_preserved_existing_bytes']
for row in report['screens']:
    for columns in (40,80):
        actual=(FOLDER/f'{row["label"]}-{columns}.bin').read_bytes()
        assert actual==expected_screen(columns,0,tuple(row['free']),row['slots'],bytes.fromhex(row['handle']),row['result'])
assert len(report['screens'])==9
records=disk_records(disk);selected=next(index for index,row in enumerate(records) if row['name']==b'CALC')
def screens(label,expected):
    for columns in (40,80):assert (FOLDER/f'{label}-{columns}.bin').read_bytes()==expected(columns)
for row in report['lifecycle']:
    label=row['label'];before=observed[label+'-before-io'];after=observed[label+'-after-io']
    active(before);active(after)
    assert bytes.fromhex(before['prototype'])[:3]==bytes([2,0,1])
    assert bytes.fromhex(after['prototype'])[:3]==bytes([5,0,1]) and before['jiffy']!=after['jiffy']
    heap=bytes.fromhex(after['heap']);assert heap[0x5c0]==heap[0x5d0]==0 and heap[0x5e0:0x5e4]==bytes(4)
    restored(observed[label+'-returned-browser'])
    assert row['read_and_verified_bytes']==513 and row['bitmap_pixels_after_io']==64000
    assert all(row[key] for key in ('file_closed_before_replace','irq_jiffy_advanced',
        'display_restored_before_replacement','both_text_screens_matched'))
    screens(label+'-browser',lambda cols:browser_screen(cols,records))
    screens(label+'-selected',lambda cols:browser_screen(cols,records,selected))
    missing=label=='missing-replacement'
    assert row['missing_file_recovered']==missing and row['calculator_launched']!=missing
    screens(label+'-returned-browser',lambda cols:browser_screen(cols,records,error='DISK I/O ERROR' if missing else None))
    if not missing:screens(label+'-calculator',lambda cols:calculator_screen(cols,'0',[]))
assert len(report['lifecycle'])==2
result=dict(passed=True,hardware_io=False,client_bytes=len(client),client_sha256=sha(client),
    complete_surfaces=3,surface_bytes=3*9216,complete_pixel_frames=5,matching_pixels=5*64000,
    observations=23,workspace_screen_pairs=9,lifecycle_screen_pairs=7,iec_bytes_verified_under_graphics=2*513,
    vice_canvas_missing_tail_bytes=4)
destination=ARCHIVE/'display-verification.json'
if args.record:destination.write_text(json.dumps(result,indent=2)+'\n')
else:assert result==read('display-verification.json')
print('PASS: rebuilt client; three full surfaces; five 64000-pixel frames; exit/free/replacement ownership and text restoration')
