#!/usr/bin/env python3
"""Verify the failed USB record and complete, separately journaled recovery."""
import ast
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
read=lambda name:json.loads((HERE/name).read_text())
sha=lambda data:hashlib.sha256(data).hexdigest()
source=read('report.json');recovery=read('failed-usb-reopen-cleanup.json')
assert not source['passed'] and source['legacy_desktop_restored'] and source['images_unchanged']
assert not source['uncertain_host_writes'] and not source['output_readbacks']
last=source['editor_states'][-1]
assert ast.literal_eval(source['error'])==(last['label'],{k:v for k,v in last.items() if k!='label'})
assert (last['label'],last['status'],last['length'],last['device'])==('ultimate-reopen-second-context',9,0,2)
assert source['editor_states'][-4]['label']=='ultimate-large-save-verified'
assert source['editor_states'][-4]['status']==1
for folder,count in (('run-harness',132),('recovery-harness',4)):
    manifest=read(folder+'/SHA256.json');assert len(manifest)==count
    for name,digest in manifest.items():assert sha((HERE/folder/name).read_bytes())==digest,name
kernel=(HERE/'native-build/target/native/uos128.prg').read_bytes()
assert sha(kernel)==source['build']['target/native/uos128.prg']=='45281b86a55f93c6402a7b0159075148d0f19086471c504bf859332c0b25e63d'
assert (HERE/'native.d64').read_bytes()==(HERE/'native-build/target/native/uos128.d64').read_bytes()
assert sha((HERE/'native.d64').read_bytes())==source['native_disk_sha256']
assert read('drives-before.json')==read('drives-restored.json')
directory=source['private_directory'];expected={}
for name,record in source['fixture_readbacks'].items():
    data=(HERE/('fixture-'+name+'.bin')).read_bytes()
    assert data==(HERE/('fixture-readback-'+name+'.bin')).read_bytes()
    assert record==dict(bytes=len(data),sha256=sha(data),path=directory+'/'+name)
    expected[record['path']]=data
assert len(expected)==7
raw=expected[directory+'/NOTE.TXT'];assert len(raw)==37
expected[directory+'/A LONG SAVED DOCUMENT NAME.TXT']=raw[:5]+b'!'+raw[5:]
raw=expected[directory+'/LARGE.TXT'];assert len(raw)==66053
saved=raw[:65537]+b'C12'+raw[65537:]
assert saved==(HERE/'saved-expected.bin').read_bytes() and len(saved)==66056
expected[directory+'/LARGE COPY.TXT']=saved;expected[directory+'/HISTORY']=b'42\r'
expected[source['native_disk_upload_path']]=(HERE/'native.d64').read_bytes()
expected[source['restore_prg_path']]=(HERE/'restore-loader-readback.bin').read_bytes()
assert len(expected)==12 and sum(map(len,expected.values()))==332431
assert sha(expected[source['restore_prg_path']])==source['build']['target/uos.prg']
prior=read('failed-usb-cleanup.json');assert not prior['passed'] and not prior['readbacks'] and not prior['deletions']
inspection=read('reopen-inspection/report.json')
assert inspection['passed'] and inspection['controls_restored']
assert inspection['paths_hex']==source['dos_paths_before_hex']
assert inspection['files']['1']['code']==85 and inspection['files']['2']['code']==0
info=bytes.fromhex(inspection['files']['2']['records'][0]['data_hex'])
assert int.from_bytes(info[:4],'little')==len(saved) and info[12:]==b'LARGE COPY.TXT'
for report in (prior,inspection,recovery):assert report['source_report_sha256']==sha((HERE/'report.json').read_bytes())
assert recovery['passed'] and recovery['controls_restored'] and recovery['dos_paths_restored']
assert not recovery['uncertain_host_writes'] and not recovery['host_connect_failures']
handle=recovery['retained_read_handle']
assert handle['context']==2 and handle['file_info_hex']==info.hex()
assert all(handle[key] for key in ('seek_started','seek_acknowledged','all_bytes_verified',
    'close_started','close_acknowledged','close_confirmed'))
assert (HERE/'retained-context-two-readback.bin').read_bytes()==saved
assert handle['bytes']==len(saved) and handle['sha256']==sha(saved)
assert len(recovery['planned_files'])==12 and set(recovery['readbacks'])==set(expected)
for index,plan in enumerate(recovery['planned_files']):
    path=plan['path'];data=expected[path]
    assert plan==dict(path=path,bytes=len(data),sha256=sha(data))
    assert recovery['readbacks'][path]==plan
    assert (HERE/f'cleanup-readback-{index:02}.bin').read_bytes()==data
paths=set(expected)|{directory,directory+'/EMPTY FOLDER'}
assert len(recovery['deletions'])==14 and {item['path'] for item in recovery['deletions']}==paths
for deletion in recovery['deletions']:
    assert all(deletion[key] for key in ('started','acknowledged','confirmed'))
    assert deletion['file_info_after']['status']==404 and deletion['file_info_after']['response']['errors']
for name,count in (('recovery-original-host-final.json',14),('recovery-retained-host-final.json',36)):
    report=read(name);assert report['passed'] and not report['hardware_io']
    assert len(report['cases'])==count and all(report['cases'].values())
assert read('recovery-retained-host-final.json')['expected_files']==recovery['planned_files']
print('PASS: failed run preserved; retained 66056-byte file and all 332431 private input/output bytes match; 14 exact removals confirmed')
