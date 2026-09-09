#!/usr/bin/env python3
"""Audit the saved editor qualification without touching hardware or a build."""
import hashlib
import json
from pathlib import Path
import re
import sys

ARCHIVE=Path(__file__).resolve().parent
sys.path.insert(0,str(ARCHIVE.parents[2]))
from native_files_check import exact_d64_files
from native_editor_check import editor_screen


def read(name):return json.loads((ARCHIVE/name).read_text())
def digest(data):return hashlib.sha256(data).hexdigest()


images=read('images.json');layout=read('layout.json');package=read('package/report.json')
assert package['passed'] and package['images']==images and package['layout']==layout
assert package['reproducible_images']==6 and package['legacy_images_unchanged']==18 and package['extracted_files']==4
assert len(package['preceding_native_prgs_unchanged'])==4
build=package['legacy_images']|{'target/native/'+name:record['sha256'] for name,record in images.items()}
for name,record in images.items():
    data=(ARCHIVE/'package/clean/target/native'/name).read_bytes()
    assert len(data)==record['bytes'] and digest(data)==record['sha256'],name
for name in ('layout.json','uos128.sym'):
    assert (ARCHIVE/name).read_bytes()==(ARCHIVE/'package/clean/target/native'/name).read_bytes(),name
kernel=(ARCHIVE/'package/clean/target/native/uos128.prg').read_bytes()
origin=int.from_bytes(kernel[:2],'little');start=layout['staging_start']-origin+2
size=layout['low_padded_end']-layout['low_start'];resident=kernel[start:start+size]
assert len(resident)==1280 and layout['load_end']==origin+len(kernel)-2

cpu_names=('document','editor','calc','browser')
for name in cpu_names:
    report=read('cpu-'+name+'.json');assert report['passed'],name
    for key in ('kernel_sha256','image_sha256'):
        if key in report:assert report[key]==images['uos128.prg']['sha256'],name
    if 'calc_sha256' in report:assert report['calc_sha256']==images['calc.prg']['sha256']
    if 'images' in report:assert all(value==images[key]['sha256'] for key,value in report['images'].items())
assert len(read('cpu-document.json')['cases'])==4
assert len(read('cpu-editor.json')['cases'])==9 and not read('cpu-editor.json')['quick']
probe=ARCHIVE/'document.prg';document=read('cpu-document.json')
assert len(probe.read_bytes())==document['document_bytes'] and digest(probe.read_bytes())==document['document_sha256']
failed_cpu=read('cpu-initial-harness-failure/report.json');assert not failed_cpu['passed']
assert digest((ARCHIVE/'cpu-initial-harness-failure/editor.prg').read_bytes())==failed_cpu['images']['editor.prg']
listing=(ARCHIVE/'package/clean/target/native/editor.lst').read_text()
def address(name):
    match=re.search(r'^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?'+re.escape(name)+r':',listing,re.M)
    assert match,name
    return int(match[1],16)
for folder,count in (('regressions-editor-d64',1),('regressions-followup',6),('regressions-cpu-observation',3)):
    report=read(folder+'/report.json')
    assert report['build']==build and len(report['suites'])==count
    assert all(suite['exit_code']==0 for suite in report['suites'].values())

editors=('emulator-editor-d64','emulator-editor-d71','emulator-editor-d81','hardware')
initial_editors=('emulator-editor-d64-initial','emulator-editor-d71-initial','emulator-editor-d81-initial')
other_emulators=('emulator-workspace','emulator-browser-d64','emulator-browser-d71','emulator-browser-d81')
probe_hash=digest((ARCHIVE/'emulator-editor-d64/native-read.prg').read_bytes())
boot_comparisons=0
for folder in (*editors,*initial_editors,*other_emulators):
    report=read(folder+'/report.json');assert report['passed'],folder
    if 'build' in report:assert report['build']==(build if folder=='hardware' else images),folder
    if 'disk_sha256' in report:assert report['disk_sha256']==images['uos128.d64']['sha256']
    assert digest((ARCHIVE/folder/'native-read.prg').read_bytes())==probe_hash
    for capture in report['captures']:
        assert capture['restored'] and capture['probe_sha256']==probe_hash
        assert capture['output_address']==0x3a00 and capture['chunk_limit']==512
        assert len((ARCHIVE/folder/(capture['label']+'.bin')).read_bytes())==capture['count']
        offset=0
        for chunk in capture['chunks']:
            assert chunk['code']==1 and 1<=chunk['count']<=512
            assert chunk['address']==capture['address']+offset
            assert not chunk['mode_register']&0x40 and chunk['common_register']&15==4 and chunk['foreground_mmu']==0x0e
            offset+=chunk['count']
        assert offset==capture['count']
    boot=report['resident_boot'];boot_comparisons+=1
    assert boot['cpu_capture_matches_image'] and boot['layout']==layout
    assert boot['bytes']==size and boot['sha256']==digest(resident)
    assert (ARCHIVE/folder/'resident-initial-0000.bin').read_bytes()==resident
    if 'frames' in report:
        assert report['all_owned_memory_and_files_released'] and report['heap_observations'][-1]['free']==[191,251,32]
        for bank in (0,1):
            expected=bytes((i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(2000))
            assert (ARCHIVE/folder/f'workspace-bank-{bank}.bin').read_bytes()==expected
    if folder not in (*editors,*initial_editors):continue
    assert len(report['frames'])==18 and len(report['editor_states'])==16
    assert len(report['captures'])==(54 if folder in editors else 21)
    if folder in editors:
        assert len(report['ram_observations'])==33
        for observation in report['ram_observations']:
            cpu=(ARCHIVE/folder/(observation['label']+'.bin')).read_bytes()
            dma=(ARCHIVE/folder/(observation['label']+'-dma.bin')).read_bytes()
            assert len(cpu)==len(dma)==observation['count']
            assert digest(cpu)==observation['cpu_sha256'] and digest(dma)==observation['direct_sha256']
            assert observation['direct_matches_cpu']==(cpu==dma)
    assert report['large_input_bytes']==66053 and report['saved_bytes']==66056 and report['edit_offset']==65537
    assert report['rom_getin_expansion_verified'] and report['function_key_bytes_restored']==256
    assert (ARCHIVE/folder/'function-keys-before.bin').read_bytes()==(ARCHIVE/folder/'function-keys-after.bin').read_bytes()
    if folder in editors:
        assert (ARCHIVE/folder/'editor-saved-function-keys.bin').read_bytes()==(ARCHIVE/folder/'function-keys-before.bin').read_bytes()
    saved=(ARCHIVE/folder/'saved-expected.seq').read_bytes();raw=(ARCHIVE/folder/'large.seq').read_bytes()
    assert saved==raw[:65537]+b'C12'+raw[65537:] and len(saved)==report['saved_bytes']
    assert digest(saved)==report['saved_sha256']==read('cpu-editor.json')['large_saved_sha256']
    assert sum(event['rom_expansion'] for event in report['events'])>=12
    if folder!='hardware':
        for name in ('note','large','saved'):
            expected=saved if name=='saved' else (ARCHIVE/folder/(name+'.seq')).read_bytes()
            assert (ARCHIVE/folder/(name+'-c1541.seq')).read_bytes()==expected
    note=(ARCHIVE/folder/'note.seq').read_bytes();edited_note=note[:5]+b'!'+note[5:]
    documents={
        'editor-new':b'','editor-open-mixed-quotes':note,'editor-caret-inside-quote':note,
        'editor-insert':edited_note,'editor-discard-prompt':edited_note,'editor-declined-discard':edited_note,
        'editor-failed-open-retains':edited_note,'editor-empty-file':b'','editor-large-open':raw,
        'editor-cursor-over-64k':raw,'editor-large-edited':saved,'editor-saved-verified':saved,
        'editor-existing-file-rejected':saved,'editor-new-after-save':b'',
        'editor-reopened-saved':saved,'editor-reopened-edit-position':saved}
    for state in report['editor_states']:
        label=state['label'];data=documents[label]
        assert state['length']==len(data) and not state['fault']
        if folder in editors:
            raw=(ARCHIVE/folder/(label+'-app-state.bin')).read_bytes()
            context=(ARCHIVE/folder/(label+'-document-state.bin')).read_bytes()
            def value(name,count=1):
                offset=address('ed_'+name)-address('ed_active')
                return int.from_bytes(raw[offset:offset+count],'little')
            for name,count in (('cursor',3),('view',3),('horizontal',3),('status',1),('mode',1),('device',1)):
                assert state[name]==value(name,count),(folder,label,name)
            assert state['fmt']==value('format')
            offset=address('ed_name')-address('ed_active')
            assert raw[offset:offset+17].split(b'\0')[0].decode()==state['name']
            assert (int.from_bytes(context[:3],'little'),context[12],context[13],context[14])==(
                state['length'],state['dirty'],state['chunks'],state['fault'])
        for display,columns in (('vic',40),('vdc',80)):
            expected=editor_screen(columns,data,state['cursor'],name=state['name'],dirty=bool(state['dirty']),
                                   device=state['device'],fmt=state['fmt'],view=state['view'],horizontal=state['horizontal'],
                                   mode=state['mode'],status=state['status'])
            assert (ARCHIVE/folder/(label+'-'+display+'.bin')).read_bytes()==expected,(folder,label,display)

hardware=read('hardware/report.json')
assert hardware['legacy_desktop_restored'] and hardware['dos_paths_restored'] and hardware['images_unchanged']
chunks=sum(len(capture['chunks']) for capture in hardware['captures']);assert chunks==116
for label in hardware['frames']:
    for display,count in (('vic',1000),('vdc',2000)):
        name=label+'-'+display+'.bin';actual=(ARCHIVE/'hardware'/name).read_bytes()
        assert len(actual)==count and actual==(ARCHIVE/'emulator-editor-d64'/name).read_bytes(),name
original=(ARCHIVE/'hardware/native.d64').read_bytes()
assert digest(original)==hardware['native_disk_sha256']
expected=exact_d64_files(original)
for name,image in ((b'U','uos128.prg'),(b'CALC','calc.prg'),(b'BROWSE','browse.prg'),(b'EDITOR','editor.prg')):
    assert digest(expected[name][1])==images[image]['sha256']
saved=(ARCHIVE/'hardware/saved-expected.seq').read_bytes();expected[b'SAVED']=(1,saved)
disk=(ARCHIVE/'hardware/editor-readback.d64').read_bytes();actual=exact_d64_files(disk)
assert actual==expected and disk[:256]==original[:256]
comparisons=0
for name,(_,data) in actual.items():
    if data:
        assert (ARCHIVE/'hardware'/('readback-'+name.decode()+'.bin')).read_bytes()==data
        comparisons+=1
readback=dict(bytes=len(disk),sha256=digest(disk),exact_files=len(actual),c1541_nonempty_files=comparisons,
              empty_stored_bytes=len(actual[b'EMPTY'][1]),boot_block_unchanged=True,saved_bytes=len(saved),saved_sha256=digest(saved))
assert hardware['independent_readback']==readback and len(actual)==8 and comparisons==7
before=read('hardware/drives-before.json');after=read('hardware/drives-restored.json')
assert not before['errors'] and not after['errors']
before={key:value for drive in before['drives'] for key,value in drive.items()}
after={key:value for drive in after['drives'] for key,value in drive.items()}
assert {key:value for key,value in before.items() if key!='a'}=={key:value for key,value in after.items() if key!='a'}
assert {key:value for key,value in before['a'].items() if key!='image_file'}=={key:value for key,value in after['a'].items() if key!='image_file'}
settings=(ARCHIVE/'hardware/settings-before.bin').read_bytes()
assert bytes.fromhex(hardware['legacy_boot_settings_hex'])[2:7]==settings[2:7]
failed=read('hardware-initial-failed/report.json');assert not failed['passed'] and failed['build']==build
assert read('hardware-initial-failed/diagnostic-screen.json')['failure_vic_matches_intended_goto']
assert read('hardware-initial-failed/settings-recovery.json')['passed']
rom=read('rom-observations.json');assert rom['passed'] and rom['all_disagreements_match_rom']
disagreements=[r for r in hardware['ram_observations'] if not r['direct_matches_cpu']]
assert len(rom['observations'])==len(disagreements)==1
for observed,reference in zip(disagreements,rom['observations']):
    assert all(observed[key]==reference[key] for key in ('label','address','count','direct_sha256','cpu_sha256'))
    assert reference['matching_rom_bases']==[0x8000]

report=dict(passed=True,images=images,layout=layout,cpu_reports=4,emulator_suites=10,
            explicit_boot_comparisons=boot_comparisons,resident_bytes=size,resident_sha256=digest(resident),
            physical_frame_pairs=18,physical_captures=54,physical_irq_chunks=chunks,physical_readback=readback,
            physical_direct_dma_disagreements=sum(not r['direct_matches_cpu'] for r in hardware['ram_observations']),
            reproducible_images=6,preceding_native_prgs_unchanged=4,legacy_images_unchanged=18,full_os_complete=False)
(ARCHIVE/'artifact-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: four CPU reports, ten emulator suites, physical screens and all eight disk files')
