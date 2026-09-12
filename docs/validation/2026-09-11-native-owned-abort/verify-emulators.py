#!/usr/bin/env python3
"""Audit the isolated candidate's complete emulator captures and file bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ARCHIVE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ARCHIVE/'oracle'))
from native_editor_check import editor_screen
from native_files_check import exact_d64_files
from native_browser_check import disk_records,browser_screen,preview_screen
from native_capture import expected_screen,calculator_screen

parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
args.emulator_only=True
def read(name):return json.loads((ARCHIVE/name).read_text())
def digest(data):return hashlib.sha256(data).hexdigest()
def record_or_compare(name,value):
    if args.record:(ARCHIVE/name).write_text(json.dumps(value,indent=2)+'\n')
    else:assert read(name)==value,name
def frames_equal(directory,label,expected):
    for display,columns in (('vic',40),('vdc',80)):
        assert (directory/(label+'-'+display+'.bin')).read_bytes()==expected(columns),(directory.name,label,display)

images=read('images.json');layout=read('layout.json');package=read('package/report.json')
assert package['passed'] and package['images']==images and package['layout']==layout
assert package['reproducible_images']==7 and package['extracted_files']==5
assert package['extra_resident_bytes']==15 and package['additional_reserved_pages']==0
for name,record in images.items():
    data=(ARCHIVE/'package/clean/target/native'/name).read_bytes()
    assert len(data)==record['bytes'] and digest(data)==record['sha256'],name
kernel=(ARCHIVE/'package/clean/target/native/uos128.prg').read_bytes()
origin=int.from_bytes(kernel[:2],'little')
def kernel_bytes(start,length):return kernel[start-origin+2:start-origin+2+length]
resident=kernel_bytes(layout['staging_start'],layout['low_padded_end']-layout['low_start'])
service=kernel_bytes(layout['service_start'],layout['service_end']-layout['service_start'])
assert len(resident)==2304 and len(service)==4024 and layout['managed_pages']==426
cpu=read('cpu/report.json');assert cpu['passed'] and len(cpu['suites'])==24
assert cpu['images']=={name:row['sha256'] for name,row in images.items()}
for name,result in cpu['suites'].items():
    assert result['exit_code']==0
    saved=read('cpu/'+result['source']);assert saved['passed'],name
    for key in ('kernel_sha256','image_sha256'):
        if key in saved:assert saved[key]==images['uos128.prg']['sha256'],name
    for filename,sha in saved.get('images',{}).items():assert sha==images[filename]['sha256'],name
assert len(read('cpu/native_owned_abort.json')['cases'])==14
assert len(read('cpu/native_sdk_module.json')['cases'])==15
legacy=read('legacy-images.json');assert len(legacy)==18
build=legacy|{'target/native/'+name:row['sha256'] for name,row in images.items()}
regressions=read('regressions/report.json');assert regressions['build']==build
assert len(regressions['suites'])==10 and all(row['exit_code']==0 for row in regressions['suites'].values())

listings={app:(ARCHIVE/'package/clean/target/native'/(app+'.lst')).read_text()
          for app in ('editor','calc','browse')}
def app_address(app,name):
    match=re.search(r'^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?'+re.escape(name)+r':',listings[app],re.M)
    assert match,(app,name)
    return int(match[1],16)
def address(name):return app_address('editor',name)

folders=['emulator-workspace']+[f'emulator-{app}-{fmt}' for app in ('editor','browser') for fmt in ('d64','d71','d81')]+['hardware','hardware-iec']
if args.emulator_only:folders=[folder for folder in folders if not folder.startswith('hardware')]
capture_count=irq_chunks=frame_pairs=observations=disagreements=field_retentions=0
probe_hash=digest((ARCHIVE/'emulator-workspace/native-read.prg').read_bytes())
for folder in folders:
    directory=ARCHIVE/folder;report=read(folder+'/report.json');assert report['passed'],folder
    if 'build' in report:assert report['build']==(build if folder.startswith('hardware') else images),folder
    if 'disk_sha256' in report:assert report['disk_sha256']==images['uos128.d64']['sha256']
    assert digest((directory/'native-read.prg').read_bytes())==probe_hash
    for capture in report['captures']:
        capture_count+=1;assert capture['restored'] and capture['probe_sha256']==probe_hash
        assert capture['output_address']==0x3a00 and capture['chunk_limit']==512
        assert len((directory/(capture['label']+'.bin')).read_bytes())==capture['count']
        offset=0
        for chunk in capture['chunks']:
            irq_chunks+=1
            assert chunk['code']==1 and 1<=chunk['count']<=512 and chunk['address']==capture['address']+offset
            assert not chunk['mode_register']&0x40 and chunk['common_register']&15==4 and chunk['foreground_mmu']==0x0e
            offset+=chunk['count']
        assert offset==capture['count']
    boot=report['resident_boot'];assert boot['layout']==layout and boot['cpu_capture_matches_image'] and boot['service_matches_image']
    assert boot['sha256']==digest(resident) and boot['service_sha256']==digest(service)
    assert b''.join((directory/f'resident-initial-{offset:04x}.bin').read_bytes() for offset in range(0,len(resident),2000))==resident
    assert b''.join((directory/f'service-initial-{offset:04x}.bin').read_bytes() for offset in range(0,len(service),2000))==service
    for observed in report.get('ram_observations',[]):
        observations+=1
        cpu=(directory/(observed['label']+'.bin')).read_bytes();dma=(directory/(observed['label']+'-dma.bin')).read_bytes()
        assert len(cpu)==len(dma)==observed['count'] and digest(cpu)==observed['cpu_sha256'] and digest(dma)==observed['direct_sha256']
        assert observed['direct_matches_cpu']==(cpu==dma)
        disagreements+=cpu!=dma
    if 'heap_observations' in report:
        assert report['all_owned_memory_and_files_released'] and report['heap_observations'][-1]['free']==[175,251,32]
        for observation in report['heap_observations']:
            pages=bytes.fromhex(observation['pages']);handles=bytes.fromhex(observation['handles'])
            assert pages[:0x50]==b'\xff'*0x50 and pages[255]==255 and pages[256:260]==b'\xff'*4 and pages[-1]==255
            assert observation['free']==[pages[:256].count(0),pages[256:].count(0),
                sum(handles[i]==0 and handles[i+4:i+7]!=b'\xff'*3 for i in range(0,256,8))]
    frame_pairs+=len(report.get('frames',[]))
    if folder=='emulator-workspace':
        for bank in (0,1):
            expected=bytes((i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(8192))
            assert (directory/f'bank-{bank}-data.bin').read_bytes()==expected
            assert (directory/f'probe-bank-{bank}.bin').read_bytes()==expected[:2000]
        for display,columns in (('vic',40),('vdc',80)):
            assert (directory/(display+'-final.bin')).read_bytes()==expected_screen(columns,1)
        assert (directory/'probe-vdc.bin').read_bytes()==expected_screen(80,1)
        frames_equal(directory,'calculator',lambda cols:calculator_screen(cols,'42',['42']))
        frames_equal(directory,'calculator-saved',lambda cols:calculator_screen(cols,'42',['42'],save_status='HISTORY SAVED AND VERIFIED'))
        assert (directory/'history.seq').read_bytes()==b'42\r'
        assert exact_d64_files((directory/'saved-history.d64').read_bytes())[b'HISTORY']==(1,b'42\r')
        frame_pairs+=3
    if folder.startswith(('emulator-browser-','emulator-editor-')) or folder=='hardware-iec':
        fmt=report['format'];device=report['data_device']
        iec_editor=folder.startswith('emulator-editor-') or folder=='hardware-iec'
        prefix='documents.' if iec_editor else 'data.'
        disk=directory/('editor-readback.d64' if folder=='hardware-iec' else prefix+('d64','d71','d81')[fmt] if fmt or iec_editor else 'native.d64')
        records=disk_records(disk.read_bytes(),fmt)
        frames_equal(directory,'workspace-restored',lambda cols:expected_screen(cols,1))
        for bank in (0,1):
            assert (directory/f'workspace-bank-{bank}.bin').read_bytes()==bytes(
                (i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(2000))
        if iec_editor:
            frames_equal(directory,'browser-after-editor',lambda cols:browser_screen(cols,records,0,device,fmt))
        else:
            assert (directory/'browsave.seq').read_bytes()==b'42\r'
            frames_equal(directory,'browser-after-app-return',lambda cols:browser_screen(cols,records,0,device,fmt))
            initial=[record for record in records if record['name']!=b'BROWSAVE']
            assert len(initial)==len(records)-1
            frames_equal(directory,'browser-initial',lambda cols:browser_screen(cols,initial,0,device,fmt))
            frames_equal(directory,'browser-last-page',lambda cols:browser_screen(cols,initial,len(initial)-1,device,fmt))
            frames_equal(directory,'bad-app-rejected',lambda cols:browser_screen(cols,initial,0,device,fmt,error='APPLICATION CHECKSUM FAILED'))
            frames_equal(directory,'discovered-calculator',lambda cols:calculator_screen(cols,'42',['42']))
            frames_equal(directory,'calculator-saved',lambda cols:calculator_screen(cols,'42',['42'],save_status='HISTORY SAVED AND VERIFIED'))
            for name in ('hexdata','zero','empty'):
                data=(directory/(name+'.seq')).read_bytes()
                if data:assert (directory/(name+'-c1541.seq')).read_bytes()==data
                for offset in range(0,max(1,len(data)),128):
                    part=data[offset:offset+128]
                    frames_equal(directory,f'preview-{name}-{offset}',lambda cols:preview_screen(
                        cols,name.upper().encode(),part,offset,offset+len(part)==len(data)))
            for number in range(12):
                assert (directory/f'file{number:02}.seq').read_bytes()==(directory/f'file{number:02}-c1541.seq').read_bytes()
    if 'editor_states' not in report:continue
    keys=(directory/'function-keys-before.bin').read_bytes()
    assert len(keys)==256 and keys==(directory/'function-keys-after.bin').read_bytes()==(directory/'editor-saved-function-keys.bin').read_bytes()
    if folder=='hardware':
        note=(directory/'fixture-NOTE.TXT.bin').read_bytes();large=(directory/'fixture-LARGE.TXT.bin').read_bytes()
        saved=(directory/'saved-expected.bin').read_bytes()
        documents={'ultimate-editor-new':b'','ultimate-open-mixed':note,'ultimate-edited-quote':note[:5]+b'!'+note[5:],
            'ultimate-saved-long-path':note[:5]+b'!'+note[5:],'ultimate-open-failure-keeps-document':note[:5]+b'!'+note[5:],
            'ultimate-open-empty':b'','ultimate-large-open':large,'ultimate-large-edited':saved,
            'ultimate-save-field-middle':saved,'ultimate-large-save-verified':saved,'ultimate-existing-file-rejected':saved,'ultimate-new-after-save':b'',
            'ultimate-reopen-second-context':saved,'ultimate-reopened-edit':saved,
            'ultimate-picker-note-returned':b'','ultimate-picker-cancel-keeps-document':saved,'ultimate-picker-folder-returned':saved}
    else:
        note=(directory/'note.seq').read_bytes();large=(directory/'large.seq').read_bytes();saved=(directory/'saved-expected.seq').read_bytes()
        changed=note[:5]+b'!'+note[5:]
        documents={'editor-new':b'','editor-open-mixed-quotes':note,'editor-caret-inside-quote':note,'editor-insert':changed,
            'editor-discard-prompt':changed,'editor-declined-discard':changed,'editor-failed-open-retains':changed,
            'editor-empty-file':b'','editor-large-open':large,'editor-cursor-over-64k':large,'editor-large-edited':saved,
            'editor-save-field-middle':saved,'editor-saved-verified':saved,'editor-existing-file-rejected':saved,'editor-new-after-save':b'',
            'editor-reopened-saved':saved,'editor-reopened-edit-position':saved,
            'editor-open-file-selected':b'','editor-picker-cancel-keeps-document':saved,'editor-save-folder-selected':saved}
        for name in ('note','large','saved'):
            export=('readback-'+name.upper()+'.bin') if folder=='hardware-iec' else name+'-c1541.seq'
            assert (directory/export).read_bytes()==(saved if name=='saved' else (directory/(name+'.seq')).read_bytes())
    assert len(large)==66053 and saved==large[:65537]+b'C12'+large[65537:]
    assert digest(saved)==report['saved_sha256']==read('cpu-editor-ultimate.json')['saved']['sha256']
    assert set(documents)=={state['label'] for state in report['editor_states']}
    for state in report['editor_states']:
        label=state['label'];data=documents[label];raw=(directory/(label+'-app-state.bin')).read_bytes()
        context=(directory/(label+'-document-state.bin')).read_bytes()
        def value(name,size=1):
            at=address('ed_'+name)-address('ed_active');return int.from_bytes(raw[at:at+size],'little')
        def string(name):
            at=address('ed_'+name)-address('ed_active');return raw[at:at+256].split(b'\0')[0].decode()
        for key,size in (('cursor',3),('view',3),('horizontal',3),('status',1),('mode',1),('device',1)):
            assert state[key]==value(key,size),(folder,label,key)
        assert state['fmt']==value('format') and state['name']==string('name')
        assert state['field']==string('field') and state['field_caret']==value('field_cursor')
        assert state['field_views']==list(raw[address('ed_field_views')-address('ed_active'):address('ed_field_views')-address('ed_active')+2])
        assert state['length']==len(data) and not state['fault']
        assert (int.from_bytes(context[:3],'little'),context[12],context[13],context[14])==(
            state['length'],state['dirty'],state['chunks'],state['fault'])
        for display,columns in (('vic',40),('vdc',80)):
            expected=editor_screen(columns,data,state['cursor'],name=state['name'],dirty=bool(state['dirty']),
                device=state['device'],fmt=state['fmt'],view=state['view'],horizontal=state['horizontal'],
                mode=state['mode'],status=state['status'],field=string('field'),
                field_caret=value('field_cursor'),field_view=raw[address('ed_field_views')-address('ed_active')+int(columns==80)])
            assert (directory/(label+'-'+display+'.bin')).read_bytes()==expected,(folder,label,display)
    field=report['field_dialog_retention'];prefix='ultimate' if folder=='hardware' else 'editor'
    before=(directory/(prefix+'-field-before-picker.bin')).read_bytes()
    after=(directory/(prefix+'-field-after-picker.bin')).read_bytes()
    assert len(before)==8 and before==after==bytes.fromhex(field['before_hex'])==bytes.fromhex(field['after_hex'])
    assert field['identical'] and before[0]==len(field['text']) and before[1]==field['caret']<before[0]
    if folder!='hardware':assert (field['text'],field['caret'])==('SAVED',4)
    field_retentions+=1

# Audit all three stream suites separately: these use direct emulator RAM
# observations and independent final disk extraction, not the IRQ observer.
stream_bytes=0
for fmt in ('d64','d71','d81'):
    folder=ARCHIVE/('emulator-files-'+fmt);stream=read(folder.name+'/report.json')
    assert stream['passed'] and stream['format']==fmt and stream['kernel_sha256']==images['uos128.prg']['sha256']
    original=(folder/'source.bin').read_bytes()
    assert len(original)==66053 and stream['native_copy_bytes']==len(original)
    assert stream['native_copy_sha256']==digest(original)
    assert original==(folder/'copied-native-readback.bin').read_bytes()==(folder/'copied-c1541.seq').read_bytes()
    assert stream['c1541_copy_matches'] and stream['app_exit_closed_streams_and_released_memory']
    for name,result in stream['small_files'].items():
        assert result['result']==0 and result['eof']==1
        assert bytes.fromhex(result['data'])==(folder/(name+'.bin')).read_bytes()
    if fmt=='d64':
        assert stream['disk_full_detected_and_existing_file_preserved']
        assert any(event['code']==0x11 for event in stream['disk_full_outcomes'])
        assert (folder/'filler-c1541.seq').read_bytes()==(folder/'filler.seq').read_bytes()
        files=exact_d64_files((folder/'files.d64').read_bytes())
        assert b'BROWSE' not in files and b'EDITOR' not in files
        assert files[b'COPY']==(1,original)
    stream_bytes+=len(original)

result=dict(passed=True,images=images,emulator_suites=10,cpu_suites=24,
    captures=capture_count,irq_chunks=irq_chunks,frame_pairs=frame_pairs,
    ram_observations=observations,direct_dma_disagreements=disagreements,
    stream_copy_bytes=stream_bytes,editor_saved_bytes=66056,field_retentions=field_retentions,
    hardware_io=False,physical_qualification=False)
assert field_retentions==3
record_or_compare('emulator-verification.json',result)
print('PASS: ten emulator workflows; frozen kernel captures, complete screens/fields and independent saved files')
