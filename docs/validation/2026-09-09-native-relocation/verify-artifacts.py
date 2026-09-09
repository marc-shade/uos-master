#!/usr/bin/env python3
"""Verify this checkpoint's saved evidence; no emulator or hardware access."""
import hashlib
import json
from pathlib import Path
import sys

ARCHIVE=Path(__file__).resolve().parent
sys.path.insert(0,str(ARCHIVE.parents[2]))
from native_files_check import exact_d64_files


def read(name):return json.loads((ARCHIVE/name).read_text())
def digest(data):return hashlib.sha256(data).hexdigest()


images=read('images.json');layout=read('layout.json');package=read('package/report.json')
assert package['passed'] and package['images']==images and package['layout']==layout
assert package['reproducible_images']==5 and package['legacy_images_unchanged']==18
build=package['legacy_images']|{'target/native/'+name:record['sha256'] for name,record in images.items()}
for name,record in images.items():
    data=(ARCHIVE/'package/clean/target/native'/name).read_bytes()
    assert len(data)==record['bytes'] and digest(data)==record['sha256'],name
for name in ('layout.json','uos128.sym'):
    assert (ARCHIVE/name).read_bytes()==(ARCHIVE/'package/clean/target/native'/name).read_bytes(),name
kernel=(ARCHIVE/'package/clean/target/native/uos128.prg').read_bytes()
origin=int.from_bytes(kernel[:2],'little')
start=layout['staging_start']-origin+2;size=layout['low_padded_end']-layout['low_start']
resident=kernel[start:start+size]
assert len(resident)==1280 and layout['load_end']==origin+len(kernel)-2

cpu_names=('relocation','heap','apps','files','directory','calc','browser','capture')
for name in cpu_names:
    report=read('cpu-'+name+'.json');assert report['passed'],name
    for key in ('kernel_sha256','image_sha256'):
        if key in report:assert report[key]==images['uos128.prg']['sha256'],name
    if 'calc_sha256' in report:assert report['calc_sha256']==images['calc.prg']['sha256']
    if 'images' in report:
        assert all(value==images[key]['sha256'] for key,value in report['images'].items())
assert len(read('cpu-relocation.json')['cases'])==9
assert len(read('cpu-capture.json')['cases'])==32
probe_hash=read('cpu-capture.json')['probe_sha256']
for folder,count in (('regressions-all',7),('regressions-boot-bytes',2)):
    report=read(folder+'/report.json')
    assert report['build']==build and len(report['suites'])==count
    assert all(suite['exit_code']==0 for suite in report['suites'].values())

emulators=('emulator-workspace-initial','emulator-d64-initial','emulator-d71','emulator-d81',
           'emulator-files-d64','emulator-files-d71','emulator-files-d81','emulator-workspace','emulator-d64')
for folder in (*emulators,'hardware'):
    report=read(folder+'/report.json');assert report['passed'],folder
    if 'build' in report:assert report['build']==(build if folder=='hardware' else images),folder
    if 'kernel_sha256' in report:assert report['kernel_sha256']==images['uos128.prg']['sha256']
    if 'disk_sha256' in report:assert report['disk_sha256']==images['uos128.d64']['sha256']
    if 'native_copy_bytes' in report:
        assert report['native_copy_bytes']==66053 and report['c1541_copy_matches']
    if 'captures' in report:
        assert digest((ARCHIVE/folder/'native-read.prg').read_bytes())==probe_hash
    for capture in report.get('captures',[]):
        assert capture['restored'] and capture['probe_sha256']==probe_hash
        assert capture['output_address']==0x3a00 and capture['chunk_limit']==512
        assert len((ARCHIVE/folder/(capture['label']+'.bin')).read_bytes())==capture['count']
        offset=0
        for chunk in capture['chunks']:
            assert chunk['code']==1 and 1<=chunk['count']<=512
            assert chunk['address']==capture['address']+offset
            assert not chunk['mode_register']&0x40 and chunk['common_register']&15==4
            assert chunk['foreground_mmu']==0x0e
            offset+=chunk['count']
        assert offset==capture['count']
    if folder in ('emulator-workspace','emulator-d64','hardware'):
        boot=report['resident_boot']
        assert boot['cpu_capture_matches_image'] and boot['layout']==layout
        assert boot['bytes']==size and boot['sha256']==digest(resident)
        assert (ARCHIVE/folder/'resident-initial-0000.bin').read_bytes()==resident
    if 'frames' in report:
        assert len(report['frames'])==12 and report['all_owned_memory_and_files_released']
        assert report['heap_observations'][-1]['free']==[191,251,32]
        for bank in (0,1):
            expected=bytes((i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(2000))
            assert (ARCHIVE/folder/f'workspace-bank-{bank}.bin').read_bytes()==expected

hardware=read('hardware/report.json')
assert hardware['legacy_desktop_restored'] and hardware['dos_paths_restored'] and hardware['images_unchanged']
assert hardware['workspace_allocations']==[dict(bank=0,page=64,bytes=8192),dict(bank=1,page=4,bytes=8192)]
assert len(hardware['captures'])==15
chunks=sum(len(capture['chunks']) for capture in hardware['captures']);assert chunks==59
for label in hardware['frames']:
    for display,count in (('vic',1000),('vdc',2000)):
        name=label+'-'+display+'.bin';actual=(ARCHIVE/'hardware'/name).read_bytes()
        assert len(actual)==count and actual==(ARCHIVE/'emulator-d64'/name).read_bytes(),name
original=(ARCHIVE/'hardware/native.d64').read_bytes()
assert digest(original)==hardware['native_disk_sha256']
expected=exact_d64_files(original)
for name,image in ((b'U','uos128.prg'),(b'BROWSE','browse.prg'),(b'NUMBER','calc.prg')):
    assert digest(expected[name][1])==images[image]['sha256']
expected[b'BROWSAVE']=(1,b'42\r')
disk=(ARCHIVE/'hardware/browser-readback.d64').read_bytes();actual=exact_d64_files(disk)
assert actual==expected and disk[:256]==original[:256]
comparisons=0
for name,(_,data) in actual.items():
    if data:
        assert (ARCHIVE/'hardware'/('readback-'+name.decode()+'.bin')).read_bytes()==data
        comparisons+=1
readback=dict(bytes=len(disk),sha256=digest(disk),exact_files=len(actual),
              c1541_nonempty_files=comparisons,empty_stored_bytes=len(actual[b'EMPTY'][1]),boot_block_unchanged=True)
assert hardware['independent_readback']==readback and len(actual)==20 and comparisons==19
before=read('hardware/drives-before.json');after=read('hardware/drives-restored.json')
assert not before['errors'] and not after['errors']
before={key:value for drive in before['drives'] for key,value in drive.items()}
after={key:value for drive in after['drives'] for key,value in drive.items()}
assert {key:value for key,value in before.items() if key!='a'}=={key:value for key,value in after.items() if key!='a'}
assert {key:value for key,value in before['a'].items() if key!='image_file'}=={key:value for key,value in after['a'].items() if key!='image_file'}

report=dict(passed=True,images=images,layout=layout,cpu_reports=len(cpu_names),emulator_suites=len(emulators),
            explicit_boot_comparisons=3,resident_bytes=size,resident_sha256=digest(resident),
            physical_frame_pairs=len(hardware['frames']),physical_captures=len(hardware['captures']),
            physical_irq_chunks=chunks,physical_readback=readback,reproducible_images=5,
            legacy_images_unchanged=18,full_os_complete=False)
(ARCHIVE/'artifact-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: eight CPU reports, nine emulator suites, three exact boot comparisons, physical screens and 20 disk files')
