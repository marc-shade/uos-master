#!/usr/bin/env python3
"""Audit archived bytes, CPU observations and screen oracles; no hardware I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import re
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
assert package['preceding_native_prgs_unchanged']==['uos128.prg','boot.prg','calc.prg','browse.prg']
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
cpu_reports=sorted(ARCHIVE.glob('cpu-*.json'));assert len(cpu_reports)==3
for path in cpu_reports:
    report=json.loads(path.read_text());assert report['passed'],path.name
    for key in ('kernel_sha256','image_sha256'):
        if key in report:assert report[key]==images['uos128.prg']['sha256'],path.name
    if 'calc_sha256' in report:assert report['calc_sha256']==images['calc.prg']['sha256']
    if 'images' in report:assert all(value==images[name]['sha256'] for name,value in report['images'].items())
assert len(read('cpu-editor-iec.json')['cases'])==9 and not read('cpu-editor-iec.json')['quick']
assert len(read('cpu-editor-ultimate.json')['cases'])==3
redraw=read('cpu-redraw.json')
assert redraw['checked_frames']==1086 and redraw['field_events']==516
for name in ('small-field-ten-characters','large-field-ten-characters'):
    event=redraw['measurements'][name]
    assert event['document_reads']==event['locate_calls']==0 and event['screen_clears']==[0,0]
    assert event['chrout_calls']==[390,790] and event['written_rows']==[[6],[6]]
assert redraw['measurements']['large-cursor-right']['document_reads']==0
for name in ('large-insert-character','large-backspace-character'):
    assert redraw['measurements'][name]['document_reads']<=2
for name in ('line-offset-carry','down-after-offset-carry','up-before-offset-borrow','line-offset-borrow','down-after-offset-borrow'):
    assert redraw['measurements'][name]['screen_clears']==[0,0]
profiles={name:read('profile-'+name+'.json') for name in ('before','after')}
preceding=read('preceding-hardware.json');assert preceding['passed']
for name,profile in profiles.items():
    assert profile['passed'] and profile['images']['uos128.prg']==images['uos128.prg']['sha256']
    assert profile['images']['editor.prg']==(images['editor.prg']['sha256'] if name=='after' else preceding['build']['target/native/editor.prg'])
for name in ('small-field-ten-characters','large-field-ten-characters'):
    assert sum(profiles['before']['measurements'][name]['chrout_calls'])==23250
    assert sum(profiles['after']['measurements'][name]['chrout_calls'])==1180
assert profiles['after']['measurements']['large-cursor-right']['cpu_instructions']*20<profiles['before']['measurements']['large-cursor-right']['cpu_instructions']
regressions=read('regressions/report.json')
assert regressions['build']==build and len(regressions['suites'])==3
assert all(value['exit_code']==0 for value in regressions['suites'].values())

listing=(ARCHIVE/'package/clean/target/native/editor.lst').read_text()
def address(name):
    match=re.search(r'^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?'+re.escape(name)+r':',listing,re.M)
    assert match,name
    return int(match[1],16)

folders=[f'emulator-editor-{fmt}' for fmt in ('d64','d71','d81')]+['hardware']
capture_count=irq_chunks=frame_pairs=observations=disagreements=0
probe_hash=digest((ARCHIVE/'emulator-editor-d64/native-read.prg').read_bytes())
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
    if folder.startswith('emulator-editor-'):
        fmt=report['format'];device=report['data_device']
        disk=directory/('documents.'+('d64','d71','d81')[fmt] if fmt else 'native.d64')
        records=disk_records(disk.read_bytes(),fmt)
        frames_equal(directory,'workspace-restored',lambda cols:expected_screen(cols,1))
        frames_equal(directory,'browser-after-editor',lambda cols:browser_screen(cols,records,0,device,fmt))
        for bank in (0,1):
            assert (directory/f'workspace-bank-{bank}.bin').read_bytes()==bytes(
                (i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(2000))
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
        documents.update({name:note for name in ('redraw-small-field','redraw-small-shortened','redraw-small-cancelled')})
        documents.update({name:large for name in ('redraw-large-cursor','redraw-large-right','redraw-large-left','redraw-large-field','redraw-large-shortened','redraw-large-cancelled')})
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
        if label.startswith('redraw-'):
            expected_cursor=0 if label.startswith('redraw-small-') else 65538 if label=='redraw-large-right' else 65537
            assert state['cursor']==expected_cursor and state['dirty']==0
            assert state['mode']==(2 if label.endswith(('-field','-shortened')) else 0)
            if label.endswith('-field'):assert string('field')=='/Usb0/Note'
            if label.endswith('-shortened'):assert string('field')=='/Usb0/Not'
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
assert len(hardware['frames'])==24 and len(hardware['editor_states'])==22
assert hardware['saved_sha256']==preceding['saved_sha256']
rom=read('rom-observations.json');assert rom['passed'] and rom['all_disagreements_match_rom']
physical_disagreements=[observed for observed in hardware['ram_observations'] if not observed['direct_matches_cpu']]
assert len(rom['observations'])==len(physical_disagreements)==disagreements==2
assert [observed['label'] for observed in physical_disagreements]==[
    'redraw-small-field-document-state','ultimate-edited-quote-app-state']
for observed,reference in zip(physical_disagreements,rom['observations']):
    assert all(observed[key]==reference[key] for key in ('label','address','count','direct_sha256','cpu_sha256'))
    assert reference['matching_rom_bases']==[0x4000 if observed['address']<0x8000 else 0x8000]
    direct=(directory/(observed['label']+'-dma.bin')).read_bytes()
    cpu=(directory/(observed['label']+'.bin')).read_bytes()
    assert reference['different_bytes']==sum(a!=b for a,b in zip(direct,cpu))
timed=hardware['redraw_timings']
assert set(timed)=={'redraw-small-ten-characters','redraw-large-ten-characters','large-cursor-right','large-cursor-left','large-insert-queue','large-backspace'}
for name,record in timed.items():
    event=hardware['events'][record['event_index']]
    assert record['elapsed_seconds']==event['elapsed_seconds']
    if name.endswith('ten-characters'):
        assert event['literal_hex']==b'/Usb0/Note'.hex() and event['quiet_seconds']==record['quiet_seconds']==.1
    elif name=='large-insert-queue':
        assert event['literal_hex']==b'C128'.hex() and event['quiet_seconds']==record['quiet_seconds']==4
    else:
        assert event['key']=={'large-cursor-right':0x1d,'large-cursor-left':0x9d,'large-backspace':20}[name]
        assert record['quiet_seconds']==.1
queues={}
for label,report_source in (('preceding',preceding),('current',hardware)):
    samples=[dict(event_index=index,elapsed_seconds=event['elapsed_seconds'])
             for index,event in enumerate(report_source['events']) if event.get('native_getin_queue') and
             len(bytes.fromhex(event['literal_hex']))==10 and event.get('quiet_seconds',4)==4]
    values=[sample['elapsed_seconds'] for sample in samples]
    queues[label]=dict(count=len(values),minimum_seconds=min(values),maximum_seconds=max(values),
                       median_seconds=statistics.median(values),samples=samples,quiet_seconds=4)
performance=dict(cpu_before=profiles['before']['measurements'],cpu_after=profiles['after']['measurements'],
                 physical_fast_checks=timed,physical_ten_character_queues=queues,
                 physical_file_seconds={name:hardware[name+'_seconds'] for name in ('large_open','large_save','large_reopen')},
                 qualification='CPU instruction counts omit ROM execution and cartridge timing. Physical elapsed times include the specified quiet interval and host monitoring; they are not isolated throughput or keyboard benchmarks.')
record_or_compare('performance.json',performance)
report=dict(passed=True,images=images,layout=layout,cpu_reports=3,cpu_checked_frames=1086,cpu_field_events_without_document_reads=516,
            emulator_suites=3,explicit_boot_comparisons=4,captures=capture_count,irq_chunks=irq_chunks,
            frame_pairs=frame_pairs,ram_observations=observations,direct_dma_disagreements=disagreements,
            physical_direct_dma_disagreements=len(physical_disagreements),
            physical_disagreements_matching_rom=len(rom['observations']),
            physical_frame_pairs=len(hardware['frames']),physical_captures=len(hardware['captures']),
            physical_irq_chunks=sum(len(c['chunks']) for c in hardware['captures']),
            physical_readbacks=hardware['output_readbacks'],saved_bytes=66056,
            reproducible_images=6,legacy_images_unchanged=18,preceding_native_prgs_unchanged=4,full_os_complete=False)
record_or_compare('artifact-verification.json',report)
print('PASS: three CPU reports and emulator suites; physical redraws, banked RAM, five USB files and timings')
