#!/usr/bin/env python3
"""Audit archived bytes, CPU observations and screen oracles; no hardware I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import statistics
import sys

ARCHIVE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ARCHIVE/'oracle'))
from native_editor_check import editor_screen
from native_files_check import exact_d64_files
from native_browser_check import disk_records,browser_screen,preview_screen
from native_capture import expected_screen,calculator_screen

parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()

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
assert package['reproducible_images']==6 and package['legacy_images_unchanged']==18 and package['extracted_files']==4
assert package['preceding_native_prgs_unchanged']==['boot.prg','editor.prg']
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
cpu_reports=sorted(ARCHIVE.glob('cpu-*.json'));assert len(cpu_reports)==15
cpu_run=read('cpu-run/report.json');assert cpu_run['passed'] and len(cpu_run['suites'])==15
assert all(result['exit_code']==0 for result in cpu_run['suites'].values())
for path in cpu_reports:
    report=json.loads(path.read_text());assert report['passed'],path.name
    source_name=path.name[4:].replace('-','_')
    assert report==read('cpu-run/'+source_name)
    for key in ('kernel_sha256','image_sha256'):
        if key in report:assert report[key]==images['uos128.prg']['sha256'],path.name
    if 'calc_sha256' in report:assert report['calc_sha256']==images['calc.prg']['sha256']
    if 'images' in report:assert all(value==images[name]['sha256'] for name,value in report['images'].items())
for name,count in (('apps',52),('files',93),('capture',32),('relocation',9),('directory',18),
                   ('ultimate',6),('browser',8),('document',4),('editor',9),('editor-ultimate',3),
                   ('loader-ultimate',54),('usb-apps',4)):
    assert len(read('cpu-'+name+'.json')['cases'])==count,name
assert not read('cpu-editor.json')['quick']
assert read('cpu-ultimate.json')['cases']['protocol_edges']['extent_bytes']==16777217
assert read('cpu-editor-ultimate.json')['saved']['bytes']==66056
redraw=read('cpu-editor-redraw.json');assert redraw['checked_frames']==1086 and redraw['field_events']==516
for label in ('small-field-ten-characters','large-field-ten-characters'):
    event=redraw['measurements'][label]
    assert event['document_reads']==event['locate_calls']==0 and event['screen_clears']==[0,0]
    assert event['chrout_calls']==[390,790] and event['written_rows']==[[6],[6]]
usb=read('cpu-usb-apps.json');assert usb['checked_frames']==1002
assert usb['cases']['bounded-path-field']['no_directory_or_file_io']
assert usb['cases']['calculator-error-recovery']['no_new_open_until_checked_close']
regressions=read('regressions/report.json');initial=read('initial-regressions/report.json')
assert initial['build']==regressions['build']==build
assert initial['suites']=={'native':{'exit_code':0},'nativefiles':{'exit_code':1}}
assert len(regressions['suites'])==9 and all(value['exit_code']==0 for value in regressions['suites'].values())
failed=read('initial-fixture-disk-full/report.json');assert not failed['passed']
assert failed['kernel_sha256']==images['uos128.prg']['sha256']
assert failed['file_events'][-1]['key']==ord('W') and failed['file_events'][-1]['result']==0x11
failed_disk=(ARCHIVE/'initial-fixture-disk-full/files.d64').read_bytes()
assert sum(failed_disk[357*256+track*4] for track in range(1,36) if track!=18)==0
closed=exact_d64_files(failed_disk)
assert closed[b'SOURCE'][1]==(ARCHIVE/'initial-fixture-disk-full/source.bin').read_bytes()
assert b'COPY' not in closed and all(name in closed for name in (b'BROWSE',b'EDITOR'))
closed_blocks=sum(max(1,(len(data)+253)//254) for kind,data in closed.values())
capacity=664-1-closed_blocks
assert capacity<(len(closed[b'SOURCE'][1])+253)//254
preflight=read('fixture-capacity-preflight.json')
assert preflight['passed'] and preflight['final_guard_excludes_directory_track']
assert preflight['regression_fixture_bytes_unchanged'] and preflight['free_data_blocks']==324
assert preflight['needed_copy_blocks']==261
assert preflight['test_disk_sha256']==read('emulator-files-d64/report.json')['test_disk_sha256']
assert preflight['helper_sha256']==digest((ARCHIVE/'oracle/native_files_check.py').read_bytes())

listings={app:(ARCHIVE/'package/clean/target/native'/(app+'.lst')).read_text()
          for app in ('editor','calc','browse')}
def app_address(app,name):
    match=re.search(r'^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?'+re.escape(name)+r':',listings[app],re.M)
    assert match,(app,name)
    return int(match[1],16)
def address(name):return app_address('editor',name)

first_directory=ARCHIVE/'initial-hardware-field-oracle'
first=read('initial-hardware-field-oracle/report.json')
assert not first['passed'] and first['legacy_desktop_restored'] and first['images_unchanged']
assert first['build']==build and first['error']=="('usb-corrupt-path', 'VIC complete screen')"
analysis=read('initial-hardware-field-oracle/screen-oracle-analysis.json');assert analysis['passed']
first_records=disk_records((first_directory/'native.d64').read_bytes())
assert analysis['path']==first['private_directory']+'/BAD APP.PRG'
assert analysis['expected_previous_error']=='DISK I/O ERROR'
frames_equal(first_directory,'usb-corrupt-path',lambda cols:browser_screen(cols,first_records,
    error=analysis['expected_previous_error'],usb_prompt=analysis['path']))
for display,columns in (('vic',40),('vdc',80)):
    raw=(first_directory/('usb-corrupt-path-'+display+'.bin')).read_bytes()
    wrong=browser_screen(columns,first_records,usb_prompt=analysis['path'])
    assert sorted({i//columns for i,(a,b) in enumerate(zip(raw,wrong)) if a!=b})==[19]
    assert digest(raw)==analysis['frames'][display]['sha256']
field=(first_directory/'usb-corrupt-path-field-state.bin').read_bytes()
at=app_address('browse','b_usb_path')-app_address('browse','b_usb_length')
assert field[0]==len(analysis['path'].encode()) and field[at:at+field[0]]==analysis['path'].encode()
assert (first_directory/'usb-corrupt-path-mode.bin').read_bytes()==bytes([2])
first_rom=read('initial-hardware-field-oracle/rom-observations.json')
assert first_rom['passed'] and first_rom['all_disagreements_match_rom']
first_disagreements=[]
for observed in first['ram_observations']:
    cpu=(first_directory/(observed['label']+'.bin')).read_bytes()
    direct=(first_directory/(observed['label']+'-dma.bin')).read_bytes()
    assert len(cpu)==len(direct)==observed['count']
    assert digest(cpu)==observed['cpu_sha256'] and digest(direct)==observed['direct_sha256']
    assert observed['direct_matches_cpu']==(cpu==direct)
    if cpu!=direct:first_disagreements.append(observed)
assert len(first_disagreements)==len(first_rom['observations'])==1
assert first_disagreements[0]['label']=='usb-missing-path-mode' and first_disagreements[0]['count']==1
assert all(first_disagreements[0][key]==first_rom['observations'][0][key]
           for key in ('label','address','count','direct_sha256','cpu_sha256'))
cleanup=read('initial-hardware-field-oracle/failed-workflow-cleanup.json')
assert cleanup['passed'] and cleanup['private_files_removed'] and cleanup['dos_paths_restored']
assert cleanup['settings_unchanged'] and cleanup['desktop_live'] and cleanup['images_unchanged']
assert cleanup['private_directory']==first['private_directory']
assert set(cleanup['readbacks'])==set(first['fixture_readbacks'])|{'HISTORY'}
for name,record in cleanup['readbacks'].items():
    raw=(first_directory/('cleanup-readback-'+name+'.bin')).read_bytes()
    expected=b'42\r' if name=='HISTORY' else (first_directory/('fixture-'+name+'.bin')).read_bytes()
    assert raw==expected and len(raw)==record['bytes'] and digest(raw)==record['sha256']

timeout_directory=ARCHIVE/'initial-hardware-host-timeout'
timeout=read('initial-hardware-host-timeout/report.json')
assert not timeout['passed'] and timeout['legacy_desktop_restored'] and timeout['images_unchanged']
assert timeout['error']=='1' and timeout['build']==build and timeout['usb_apps']['passed']
assert timeout['editor_states'][-1]['label']=='ultimate-large-open' and not timeout.get('large_save_seconds')
failure=(timeout_directory/'failure-context.bin').read_bytes()
assert failure[0x12]==1 and failure[0x15]==ord('8') and failure[0x23]==2
timeout_records=disk_records((timeout_directory/'native.d64').read_bytes())
for field in timeout['usb_apps']['fields']:
    frames_equal(timeout_directory,field['label'],lambda cols:browser_screen(cols,timeout_records,
        error=field['browser_error'],usb_prompt=field['path'],usb_device=field['device']))
for item in timeout['usb_apps']['browser_returns']:
    frames_equal(timeout_directory,item['label'],lambda cols:browser_screen(cols,timeout_records,error=item['error']))
for app,label in (('calc','usb-calculator-source'),('editor','usb-editor-source')):
    assert (timeout_directory/(label+'-app-header.bin')).read_bytes()==(ARCHIVE/'package/clean/target/native'/(app+'.prg')).read_bytes()[2:34]
timeout_note=(timeout_directory/'fixture-NOTE.TXT.bin').read_bytes()
timeout_large=(timeout_directory/'fixture-LARGE.TXT.bin').read_bytes()
timeout_documents={'ultimate-editor-new':b'','ultimate-open-mixed':timeout_note,
    'ultimate-edited-quote':timeout_note[:5]+b'!'+timeout_note[5:],
    'ultimate-saved-long-path':timeout_note[:5]+b'!'+timeout_note[5:],
    'ultimate-open-failure-keeps-document':timeout_note[:5]+b'!'+timeout_note[5:],
    'ultimate-open-empty':b'','ultimate-large-open':timeout_large}
assert {state['label'] for state in timeout['editor_states']}==set(timeout_documents)
for state in timeout['editor_states']:
    label=state['label'];data=timeout_documents[label]
    raw=(timeout_directory/(label+'-app-state.bin')).read_bytes()
    context=(timeout_directory/(label+'-document-state.bin')).read_bytes()
    def timeout_value(name,size=1):
        at=address('ed_'+name)-address('ed_active');return int.from_bytes(raw[at:at+size],'little')
    def timeout_string(name):
        at=address('ed_'+name)-address('ed_active');return raw[at:at+256].split(bytes([0]))[0].decode()
    for name,size in (('cursor',3),('view',3),('horizontal',3),('status',1),('mode',1),('device',1)):
        assert state[name]==timeout_value(name,size)
    assert state['fmt']==timeout_value('format') and state['name']==timeout_string('name')
    assert state['length']==len(data)==int.from_bytes(context[:3],'little') and not state['fault']
    assert (context[12],context[13],context[14])==(state['dirty'],state['chunks'],state['fault'])
    frames_equal(timeout_directory,label,lambda cols:editor_screen(cols,data,state['cursor'],name=state['name'],
        dirty=bool(state['dirty']),device=state['device'],fmt=state['fmt'],view=state['view'],
        horizontal=state['horizontal'],mode=state['mode'],status=state['status'],field=timeout_string('field')))
timeout_rom=read('initial-hardware-host-timeout/rom-observations.json')
assert timeout_rom['passed'] and timeout_rom['all_disagreements_match_rom']
timeout_disagreements=[]
for observed in timeout['ram_observations']:
    cpu=(timeout_directory/(observed['label']+'.bin')).read_bytes()
    direct=(timeout_directory/(observed['label']+'-dma.bin')).read_bytes()
    assert len(cpu)==len(direct)==observed['count']
    assert digest(cpu)==observed['cpu_sha256'] and digest(direct)==observed['direct_sha256']
    assert observed['direct_matches_cpu']==(cpu==direct)
    if cpu!=direct:timeout_disagreements.append(observed)
assert len(timeout_disagreements)==len(timeout_rom['observations'])==3
for observed,reference in zip(timeout_disagreements,timeout_rom['observations']):
    assert all(observed[key]==reference[key] for key in ('label','address','count','direct_sha256','cpu_sha256'))

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
assert hardware['host_request_timeout_seconds']==60 and not hardware['uncertain_host_writes']
reuse=hardware['fixture_reuse']
assert hardware['private_directory_reused'] and hardware['private_directory']==timeout['private_directory']
assert reuse['source_report_sha256']==digest((timeout_directory/'report.json').read_bytes())
assert reuse['complete_workflow_restarted'] and reuse['prior_outputs_removed']
assert set(reuse['prior_outputs_readbacks'])=={'HISTORY','A LONG SAVED DOCUMENT NAME.TXT'}
for name,record in reuse['prior_outputs_readbacks'].items():
    raw=(directory/('prior-output-'+name+'.bin')).read_bytes()
    expected=b'42\r' if name=='HISTORY' else timeout_note[:5]+b'!'+timeout_note[5:]
    assert raw==expected and len(raw)==record['bytes'] and digest(raw)==record['sha256']
assert hardware['independent_workspace_bytes']==16384
for bank in (0,1):
    data=(directory/f'workspace-{bank}-all.bin').read_bytes()
    assert data==bytes((i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(8192))
fixtures={'NOTE.TXT','EMPTY.TXT','LARGE.TXT','USB CALCULATOR LONG NAME.PRG','TEXT EDITOR.PRG','BAD APP.PRG'}
assert set(hardware['fixture_readbacks'])==fixtures
for name,record in hardware['fixture_readbacks'].items():
    data=(directory/('fixture-readback-'+name+'.bin')).read_bytes()
    assert data==(directory/('fixture-'+name+'.bin')).read_bytes() and digest(data)==record['sha256'] and len(data)==record['bytes']
assert set(hardware['output_readbacks'])==fixtures|{'A LONG SAVED DOCUMENT NAME.TXT','LARGE COPY.TXT','HISTORY'}
for name,record in hardware['output_readbacks'].items():
    data=(directory/('final-readback-'+name+'.bin')).read_bytes()
    expected=b'42\r' if name=='HISTORY' else (directory/'saved-expected.bin').read_bytes() if name=='LARGE COPY.TXT' else (
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

usb=hardware['usb_apps'];assert usb['passed']
assert len(usb['fields'])==7 and len(usb['calculator_states'])==5 and len(usb['browser_returns'])==4
def context(label,app,device,fmt):
    data=(directory/(label+'-app-context.bin')).read_bytes()
    assert len(data)==14 and (data[0],data[1],data[3],data[12],data[13])==(32,device,2,fmt,8)
    header=(directory/(label+'-app-header.bin')).read_bytes()
    assert header==(ARCHIVE/'package/clean/target/native'/(app+'.prg')).read_bytes()[2:34]
    return digest(header)
frames_equal(directory,'usb-browser-initial',lambda cols:browser_screen(cols,records))
for field in usb['fields']:
    label=field['label'];data=(directory/(label+'-field-state.bin')).read_bytes()
    start=app_address('browse','b_usb_length');at=app_address('browse','b_usb_path')-start
    assert data[0]==field['bytes']==len(field['path'].encode())
    assert data[app_address('browse','b_usb_device')-start]==field['device']
    assert data[at:at+field['bytes']]==field['path'].encode()
    assert (directory/(label+'-mode.bin')).read_bytes()==bytes([2])
    frames_equal(directory,label,lambda cols:browser_screen(cols,records,error=field['browser_error'],usb_prompt=field['path'],usb_device=field['device']))
assert usb['fields'][0]['bytes']==255 and usb['fields'][1]['bytes']==254 and usb['fields'][2]['bytes']==0
for item in usb['browser_returns']:
    assert context(item['label'],'browse',8,0)==item['header_sha256']
    frames_equal(directory,item['label'],lambda cols:browser_screen(cols,records,error=item['error']))
for label,app,device in (('usb-calculator','calc',2),('usb-editor','editor',1)):
    record=usb['calculator_source' if app=='calc' else 'editor_source']
    assert record['device']==device and record['format']==3 and record['boot_device']==8
    assert context(label+'-source',app,device,3)==record['header_sha256']
for state in usb['calculator_states']:
    label=state['label'];data=(directory/(label+'-calculator-state.bin')).read_bytes()
    start=app_address('calc','owner')
    def calc_byte(name):return data[app_address('calc',name)-start]
    at=app_address('calc','dispbuf')-start
    assert data[at:at+8].split(bytes([0]))[0]==state['result'].encode()
    assert calc_byte('owner')==32 and calc_byte('history_count')==calc_byte('history_head')==len(state['history'])
    assert calc_byte('history_view')==0
    at=app_address('calc','history_handle')-start;handle=data[at:at+4]
    descriptor=(directory/(label+'-history-descriptor.bin')).read_bytes()
    assert descriptor[:4]==bytes([32,1,state['history_page'],2]) and descriptor[4:7]==handle[1:]
    history=(directory/(label+'-history.bin')).read_bytes()
    assert history==b''.join(word.encode().ljust(16,b' ') for word in reversed(state['history']))
    assert digest(history)==state['history_sha256']
    frames_equal(directory,label,lambda cols:calculator_screen(cols,state['result'],state['history'],
        save_prompt=state['prompt'],save_status=state['status'],usb=True))
assert (directory/'fixture-USB CALCULATOR LONG NAME.PRG.bin').read_bytes()==(ARCHIVE/'package/clean/target/native/calc.prg').read_bytes()
assert (directory/'fixture-TEXT EDITOR.PRG.bin').read_bytes()==(ARCHIVE/'package/clean/target/native/editor.prg').read_bytes()
from native_image import validate
try:validate((directory/'fixture-BAD APP.PRG.bin').read_bytes())
except ValueError as error:assert 'CRC' in str(error)
else:raise AssertionError('bad application fixture was valid')

rom=read('rom-observations.json');assert rom['passed'] and rom['all_disagreements_match_rom']
physical_disagreements=[observation for observation in hardware['ram_observations'] if not observation['direct_matches_cpu']]
assert len(rom['observations'])==len(physical_disagreements)==disagreements
for observed,reference in zip(physical_disagreements,rom['observations']):
    assert all(observed[key]==reference[key] for key in ('label','address','count','direct_sha256','cpu_sha256'))
    direct=(directory/(observed['label']+'-dma.bin')).read_bytes()
    cpu=(directory/(observed['label']+'.bin')).read_bytes()
    assert reference['different_bytes']==sum(a!=b for a,b in zip(direct,cpu))

launches={}
for label,elapsed in usb['launch_seconds'].items():
    matches=[i for i,event in enumerate(hardware['events']) if event.get('key')==13 and event['elapsed_seconds']==elapsed]
    assert matches,label
    launches[label]=dict(elapsed_seconds=elapsed,event_indices=matches)
performance=dict(physical_launches=launches,
    physical_file_seconds={name:hardware[name+'_seconds'] for name in ('large_open','large_save','large_reopen')},
    quiet_seconds=hardware['quiet_seconds'],
    host_request_timeout_seconds=hardware['host_request_timeout_seconds'],
    qualification='Observed workflow times include quiet intervals and host monitoring. Successful USB launches use a 1-second initial quiet interval. Missing/corrupt launch times include reloading and scanning the boot IEC browser. File-operation times exclude typing the path; these are not isolated throughput or keyboard benchmarks.')
record_or_compare('performance.json',performance)
report=dict(passed=True,images=images,layout=layout,cpu_reports=15,usb_field_frames=1002,editor_redraw_frames=1086,
    emulator_suites=10,explicit_boot_comparisons=8,captures=capture_count,irq_chunks=irq_chunks,frame_pairs=frame_pairs,
    ram_observations=observations,direct_dma_disagreements=disagreements,
    physical_frame_pairs=len(hardware['frames']),physical_captures=len(hardware['captures']),
    physical_irq_chunks=sum(len(c['chunks']) for c in hardware['captures']),physical_readbacks=hardware['output_readbacks'],
    physical_disagreements_matching_rom=len(rom['observations']),stream_copy_bytes=stream_bytes,saved_bytes=66056,
    reproducible_images=6,legacy_images_unchanged=18,preceding_native_prgs_unchanged=2,full_os_complete=False,
    retained_initial_hardware=dict(frame_pairs=len(first['frames']),captures=len(first['captures']),
        ram_observations=len(first['ram_observations']),dma_disagreements=len(first_disagreements),
        corrected_screen_frames=2,verified_cleanup_files=len(cleanup['readbacks'])),
    retained_host_timeout=dict(frame_pairs=len(timeout['frames']),captures=len(timeout['captures']),
        ram_observations=len(timeout['ram_observations']),dma_disagreements=len(timeout_disagreements),
        complete_workflow_restarted=reuse['complete_workflow_restarted'],prior_outputs_verified=2),
    initial_fixture_capacity_blocks=capacity,initial_fixture_copy_blocks=(len(closed[b'SOURCE'][1])+253)//254)
record_or_compare('artifact-verification.json',report)
print('PASS: 15 CPU reports, ten emulator suites, physical USB apps, screens, banked RAM and nine closed files')
