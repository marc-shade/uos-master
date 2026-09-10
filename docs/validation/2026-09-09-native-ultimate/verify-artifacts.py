#!/usr/bin/env python3
"""Audit archived bytes, CPU observations and screen oracles; no hardware I/O."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import statistics
import sys

ARCHIVE=Path(__file__).resolve().parent
sys.path.insert(0,str(ARCHIVE/'oracle'))
from native_editor_check import editor_screen
from native_files_check import exact_d64_files
from native_browser_check import disk_records,browser_screen,preview_screen
from native_capture import expected_screen,calculator_screen

def read(name):return json.loads((ARCHIVE/name).read_text())
def digest(data):return hashlib.sha256(data).hexdigest()
def frames_equal(directory,label,expected):
    for display,columns in (('vic',40),('vdc',80)):
        assert (directory/(label+'-'+display+'.bin')).read_bytes()==expected(columns),(directory.name,label,display)

images=read('images.json');layout=read('layout.json');package=read('package/report.json')
assert package['passed'] and package['images']==images and package['layout']==layout
rebuilt=read('post-hardware-rebuild.json')
assert rebuilt['passed'] and rebuilt['tested_images_unchanged'] and rebuilt['images']==images
assert package['reproducible_images']==6 and package['legacy_images_unchanged']==18 and package['extracted_files']==4
assert package['preceding_native_prgs_unchanged']==['boot.prg','calc.prg','browse.prg']
build=package['legacy_images']|{'target/native/'+name:record['sha256'] for name,record in images.items()}
for name,record in images.items():
    data=(ARCHIVE/'package/clean/target/native'/name).read_bytes()
    assert len(data)==record['bytes'] and digest(data)==record['sha256'],name
kernel=(ARCHIVE/'package/clean/target/native/uos128.prg').read_bytes()
origin=int.from_bytes(kernel[:2],'little')
def kernel_bytes(start,length):return kernel[start-origin+2:start-origin+2+length]
resident=kernel_bytes(layout['staging_start'],layout['low_padded_end']-layout['low_start'])
service=kernel_bytes(layout['service_start'],layout['service_end']-layout['service_start'])
assert len(resident)==1280 and len(service)==3872 and layout['managed_pages']==426
cpu_reports=sorted(ARCHIVE.glob('cpu-*.json'));assert len(cpu_reports)==12
for path in cpu_reports:
    report=json.loads(path.read_text());assert report['passed'],path.name
    for key in ('kernel_sha256','image_sha256'):
        if key in report:assert report[key]==images['uos128.prg']['sha256'],path.name
    if 'calc_sha256' in report:assert report['calc_sha256']==images['calc.prg']['sha256']
    if 'images' in report:assert all(value==images[name]['sha256'] for name,value in report['images'].items())
assert len(read('cpu-files.json')['cases'])==6
assert read('cpu-files.json')['cases']['protocol_edges']['extent_bytes']==16777217
assert len(read('cpu-editor.json')['cases'])==3 and read('cpu-editor.json')['saved']['bytes']==66056
assert len(read('cpu-editor-iec.json')['cases'])==9 and not read('cpu-editor-iec.json')['quick']
assert len(read('cpu-document.json')['cases'])==4
regressions=read('regressions/report.json')
assert regressions['build']==build and len(regressions['suites'])==7
assert all(value['exit_code']==0 for value in regressions['suites'].values())
assert read('initial-regressions/report.json')['suites']['native']['exit_code']!=0
assert not read('initial-emulator-harness-failure/report.json')['passed']
assert not read('initial-hardware-connection-timeout/report.json')['passed']

listing=(ARCHIVE/'package/clean/target/native/editor.lst').read_text()
def address(name):
    match=re.search(r'^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?'+re.escape(name)+r':',listing,re.M)
    assert match,name
    return int(match[1],16)

folders=['emulator-workspace']+[f'emulator-{app}-{fmt}' for app in ('editor','browser') for fmt in ('d64','d71','d81')]+['hardware']
capture_count=irq_chunks=frame_pairs=observations=disagreements=0
probe_hash=digest((ARCHIVE/'emulator-workspace/native-read.prg').read_bytes())
for folder in folders:
    directory=ARCHIVE/folder;report=read(folder+'/report.json');assert report['passed'],folder
    if 'build' in report:assert report['build']==(build if folder=='hardware' else images),folder
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
    assert (directory/'resident-initial-0000.bin').read_bytes()==resident
    assert (directory/'service-initial-0000.bin').read_bytes()+(directory/'service-initial-07d0.bin').read_bytes()==service
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
    if folder.startswith(('emulator-browser-','emulator-editor-')):
        fmt=report['format'];device=report['data_device']
        prefix='documents.' if folder.startswith('emulator-editor-') else 'data.'
        disk=directory/(prefix+('d64','d71','d81')[fmt] if fmt else 'native.d64')
        records=disk_records(disk.read_bytes(),fmt)
        frames_equal(directory,'workspace-restored',lambda cols:expected_screen(cols,1))
        for bank in (0,1):
            assert (directory/f'workspace-bank-{bank}.bin').read_bytes()==bytes(
                (i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(2000))
        if folder.startswith('emulator-editor-'):
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
            'ultimate-large-save-verified':saved,'ultimate-existing-file-rejected':saved,'ultimate-new-after-save':b'',
            'ultimate-reopen-second-context':saved,'ultimate-reopened-edit':saved}
    else:
        note=(directory/'note.seq').read_bytes();large=(directory/'large.seq').read_bytes();saved=(directory/'saved-expected.seq').read_bytes()
        changed=note[:5]+b'!'+note[5:]
        documents={'editor-new':b'','editor-open-mixed-quotes':note,'editor-caret-inside-quote':note,'editor-insert':changed,
            'editor-discard-prompt':changed,'editor-declined-discard':changed,'editor-failed-open-retains':changed,
            'editor-empty-file':b'','editor-large-open':large,'editor-cursor-over-64k':large,'editor-large-edited':saved,
            'editor-saved-verified':saved,'editor-existing-file-rejected':saved,'editor-new-after-save':b'',
            'editor-reopened-saved':saved,'editor-reopened-edit-position':saved}
        for name in ('note','large','saved'):
            assert (directory/(name+'-c1541.seq')).read_bytes()==(saved if name=='saved' else (directory/(name+'.seq')).read_bytes())
    assert len(large)==66053 and saved==large[:65537]+b'C12'+large[65537:]
    assert digest(saved)==report['saved_sha256']==read('cpu-editor.json')['saved']['sha256']
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
        assert state['length']==len(data) and not state['fault']
        assert (int.from_bytes(context[:3],'little'),context[12],context[13],context[14])==(
            state['length'],state['dirty'],state['chunks'],state['fault'])
        for display,columns in (('vic',40),('vdc',80)):
            expected=editor_screen(columns,data,state['cursor'],name=state['name'],dirty=bool(state['dirty']),
                device=state['device'],fmt=state['fmt'],view=state['view'],horizontal=state['horizontal'],
                mode=state['mode'],status=state['status'],field=string('field'))
            assert (directory/(label+'-'+display+'.bin')).read_bytes()==expected,(folder,label,display)

hardware=read('hardware/report.json');directory=ARCHIVE/'hardware'
assert hardware['build']==build and hardware['native_checks_passed'] and hardware['legacy_desktop_restored']
assert hardware['images_unchanged'] and hardware['dos_paths_restored'] and hardware['private_files_removed']
assert hardware['dos_paths_after_hex']==hardware['dos_paths_before_hex']
assert hardware['independent_workspace_bytes']==16384
for bank in (0,1):
    data=(directory/f'workspace-{bank}-all.bin').read_bytes()
    assert data==bytes((i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(8192))
assert set(hardware['fixture_readbacks'])=={'NOTE.TXT','EMPTY.TXT','LARGE.TXT'}
for name,record in hardware['fixture_readbacks'].items():
    data=(directory/('fixture-readback-'+name+'.bin')).read_bytes()
    assert data==(directory/('fixture-'+name+'.bin')).read_bytes() and digest(data)==record['sha256'] and len(data)==record['bytes']
assert set(hardware['output_readbacks'])=={'NOTE.TXT','EMPTY.TXT','LARGE.TXT','A LONG SAVED DOCUMENT NAME.TXT','LARGE COPY.TXT'}
for name,record in hardware['output_readbacks'].items():
    data=(directory/('final-readback-'+name+'.bin')).read_bytes()
    expected=(directory/'saved-expected.bin').read_bytes() if name=='LARGE COPY.TXT' else (
        (directory/'fixture-NOTE.TXT.bin').read_bytes()[:5]+b'!'+(directory/'fixture-NOTE.TXT.bin').read_bytes()[5:]
        if name=='A LONG SAVED DOCUMENT NAME.TXT' else (directory/('fixture-'+name+'.bin')).read_bytes())
    assert data==expected and len(data)==record['bytes'] and digest(data)==record['sha256'],name
assert digest((directory/'native.d64').read_bytes())==images['uos128.d64']['sha256']
records=disk_records((directory/'native.d64').read_bytes())
for display,columns in (('vic',40),('vdc',80)):
    assert (directory/('browser-after-ultimate-editor-'+display+'.bin')).read_bytes()==browser_screen(columns,records)
    assert (directory/('workspace-restored-'+display+'.bin')).read_bytes()==expected_screen(columns,1)
flatten=lambda report:{key:value for entry in report['drives'] for key,value in entry.items()}
before=flatten(read('hardware/drives-before.json'));after=flatten(read('hardware/drives-restored.json'))
assert {k:v for k,v in before.items() if k!='a'}=={k:v for k,v in after.items() if k!='a'}
assert {k:v for k,v in before['a'].items() if k!='image_file'}=={k:v for k,v in after['a'].items() if k!='image_file'}
assert bytes.fromhex(hardware['legacy_boot_settings_hex'])[2:7]==(directory/'settings-before.bin').read_bytes()[2:7]
cleanup=read('initial-hardware-connection-timeout/timeout-fixture-cleanup.json')
assert cleanup['passed'] and cleanup['private_files_removed'] and cleanup['dos_path_restored']
assert cleanup['settings_unchanged'] and cleanup['desktop_live']
assert not read('initial-hardware-connection-timeout/outcome.json')['fixture_cleanup_pending']
if 'readback' in cleanup:
    first=ARCHIVE/'initial-hardware-connection-timeout'
    data=(first/'timeout-fixture-readback.bin').read_bytes();record=cleanup['readback']
    assert data==(first/'fixture-NOTE.TXT.bin').read_bytes()[:record['bytes']]
    assert len(data)==record['bytes'] and digest(data)==record['sha256']
preceding=read('preceding-iec-workflow.json')
assert preceding['passed'] and preceding['saved_bytes']==66056 and preceding['saved_sha256']==hardware['saved_sha256']
old_report=(ARCHIVE/preceding['archived_report']).read_bytes()
assert digest(old_report)==preceding['source_report_sha256']
old_report=json.loads(old_report)
assert old_report['passed'] and old_report['saved_sha256']==preceding['saved_sha256']
timings={}
for name in ('large_open','large_save','large_reopen'):
    old=preceding['measurements'][name]['event'];assert old['key']==13
    assert old==old_report['events'][preceding['measurements'][name]['event_index']]
    elapsed=hardware[name+'_seconds']
    matching=[index for index,event in enumerate(hardware['events']) if event.get('key')==13 and event['elapsed_seconds']==elapsed]
    assert len(matching)==1
    timings[name]=dict(ultimate_seconds=elapsed,ultimate_event_index=matching[0],iec_seconds=old['elapsed_seconds'],
                      preceding_iec_event_index=preceding['measurements'][name]['event_index'])
queues=[dict(event_index=index,characters=len(bytes.fromhex(event['literal_hex'])),elapsed_seconds=event['elapsed_seconds'])
        for index,event in enumerate(hardware['events']) if event.get('native_getin_queue')]
full=[queue['elapsed_seconds'] for queue in queues if queue['characters']==10]
performance=dict(physical_report='hardware/report.json',preceding_iec_evidence='preceding-iec-workflow.json',
                 timings=timings,quiet_seconds=hardware['quiet_seconds'],literal_queues=queues,
                 ten_character_queues=dict(count=len(full),minimum_seconds=min(full),maximum_seconds=max(full),
                                           median_seconds=statistics.median(full)),
                 qualification='Observed workflow elapsed times include quiet intervals and host monitoring. File-operation times exclude typing the path. These are not isolated throughput or keyboard benchmarks.')
(ARCHIVE/'performance.json').write_text(json.dumps(performance,indent=2)+'\n')
report=dict(passed=True,images=images,layout=layout,cpu_reports=12,emulator_suites=7,explicit_boot_comparisons=8,
            captures=capture_count,irq_chunks=irq_chunks,frame_pairs=frame_pairs,ram_observations=observations,
            direct_dma_disagreements=disagreements,physical_frame_pairs=len(hardware['frames']),
            physical_captures=len(hardware['captures']),physical_irq_chunks=sum(len(c['chunks']) for c in hardware['captures']),
            physical_readbacks=hardware['output_readbacks'],saved_bytes=66056,
            reproducible_images=6,legacy_images_unchanged=18,preceding_native_prgs_unchanged=3,full_os_complete=False)
(ARCHIVE/'artifact-verification.json').write_text(json.dumps(report,indent=2)+'\n')
cache=ARCHIVE/'oracle/__pycache__'
if cache.exists():shutil.rmtree(cache)
print('PASS: 12 CPU reports, seven emulator suites, physical screens, banked RAM and five USB files')
