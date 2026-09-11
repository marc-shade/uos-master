#!/usr/bin/env python3
"""Audit the failed USB observations and exact private-file reclamation offline."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ARCHIVE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
read=lambda path:json.loads(path.read_text())
digest=lambda data:hashlib.sha256(data).hexdigest()
directory=ARCHIVE/'hardware-usb-initial-failure'
report=read(directory/'report.json');cleanup=read(directory/'failed-usb-cleanup.json')
build=read(ARCHIVE/'build.json')
assert not report['passed'] and report['error']=='' and report['legacy_desktop_restored'] and report['images_unchanged']
assert report['build']==build and not report['editor_states'] and not report['modules']
assert not report['uncertain_host_writes'] and not report['host_connect_failures']
assert report['frames'][-1]=='usb-missing-path' and report['usb_apps']['browser_returns'][-1]['label']=='usb-browser-after-calculator'
assert len(report['host_upload_checks'])==1
upload=report['host_upload_checks'][0]
assert upload['size_verified'] and upload['expected_bytes']==upload['stored_bytes']==174848
assert upload['path']==report['native_disk_upload_path']
for name in ('before','restored'):
    assert read(directory/('drives-'+name+'.json'))==read(directory/'drives-before.json')
core=(ARCHIVE/'package/clean/target/native/browse.prg').read_bytes()
assert (directory/'usb-browser-after-missing-app-header.bin').read_bytes()==core[2:34]
mailbox=(directory/'usb-browser-after-missing-browser-mailbox.bin').read_bytes()
assert mailbox[0]==32 and mailbox[9:11]==bytes([2,3]) and int.from_bytes(mailbox[16:20],'little')==8
retained=(directory/'usb-browser-after-missing-retained-name-direct.bin').read_bytes()
assert retained==b'USB CALCULATOR LONG NAME.PRG' and len(retained)==mailbox[20]
state=(directory/'usb-browser-after-missing-browser-state.bin').read_bytes()
listing=(ARCHIVE/'package/clean/target/native/browse.lst').read_text()
def address(name):
    match=re.search(r'^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?'+name+r':',listing,re.M)
    assert match,name
    return int(match[1],16)
for name in ('bu_count','bu_row','bu_base'):
    assert state[address(name)-address('bu_cursor')]==0
assert state[address('bu_failure')-address('bu_cursor')]==0x11
failure=(directory/'failure-context.bin').read_bytes()
assert failure[0x90]==0xe2 and failure[0xc0:0xc4]==bytes([32,2,2,4]) and failure[0xc7]==0x15
assert 'AssertionError' in (directory/'workflow.log').read_text()
assert 'usb-browser-after-missing' in (directory/'workflow.log').read_text()
model=read(directory/'cpu-sequence-report.json')
assert model['passed'] and model['final_base']==8 and model['final_page']==[(b' '+retained).hex()]
hypothesis=read(directory/'abort-hypothesis.json')
assert hypothesis['passed'] and not hypothesis['hardware_io']
assert hypothesis['kernel_sha256']==build['target/native/uos128.prg']
assert not hypothesis['initiating_physical_failure_proven'] and not hypothesis['native_images_changed']
assert hypothesis['after_open']['status']==0xff and hypothesis['after_open']['abort_pending']==100
assert hypothesis['after_cleanup_attempt']['status']==0xe2 and hypothesis['after_cleanup_attempt']['abort_pending']==99
for stage,error in (('after_open',0x11),('after_cleanup_attempt',0x15)):
    entry=hypothesis[stage]
    descriptor=bytes.fromhex(entry['descriptor'])
    assert descriptor[:4]==bytes([32,2,2,4]) and descriptor[7]==error
    assert entry['timer']=='000000' and entry['active']==0
assert hypothesis['explicit_close_after_abort_completion_passed'] and not hypothesis['implicit_command_replay']

assert cleanup['passed'] and cleanup['hardware_io'] and cleanup['dos_paths_restored']
assert cleanup['source_report_sha256']==digest((directory/'report.json').read_bytes())
private=report['private_directory'];expected={}
for name,record in report['fixture_readbacks'].items():
    data=(directory/('fixture-'+name+'.bin')).read_bytes()
    assert data==(directory/('fixture-readback-'+name+'.bin')).read_bytes()
    assert record['bytes']==len(data) and record['sha256']==digest(data) and record['path']==private+'/'+name
    expected[record['path']]=data
expected[private+'/HISTORY']=b'42\r'
expected[report['native_disk_upload_path']]=(directory/'native.d64').read_bytes()
expected[report['restore_prg_path']]=(directory/'restore-loader-readback.bin').read_bytes()
assert digest(expected[report['native_disk_upload_path']])==build['target/native/uos128.d64']
assert digest(expected[report['restore_prg_path']])==build['target/uos.prg']
assert len(expected)==10 and set(cleanup['readbacks'])==set(expected)
for index,(path,record) in enumerate(cleanup['readbacks'].items()):
    data=(directory/f'cleanup-readback-{index:02}.bin').read_bytes()
    assert data==expected[path] and record['bytes']==len(data) and record['sha256']==digest(data) and record['path']==path
oracle=cleanup['directory_oracles']['private'];entries=[bytes.fromhex(raw) for raw in oracle['pages']['0']['entries_hex']]
names={path.rsplit('/',1)[1].encode() for path in expected if path.startswith(private+'/')}|{b'EMPTY FOLDER'}
assert oracle['count']==len(entries)==9 and {entry[1:] for entry in entries}==names
assert not oracle['pages']['0']['full'] and not oracle['pages']['0']['clipped']
assert cleanup['directory_oracles']['empty']['count']==0
for page in report['usb_browser']['pages']:
    if 'stage_names_hex' not in page:continue
    stage_names={bytes.fromhex(name) for name in page['stage_names_hex']}
    stage=[entry for entry in entries if entry[1:] in stage_names]
    assert len(stage)==len(stage_names)
    assert page['entries_hex']==[entry.hex() for entry in stage[page['base']:page['base']+8]]
    assert stage[page['ordinal']][1:].hex()==page['expected_selection_hex']
removed=cleanup['deletions']
assert len(removed)==12 and len({item['path'] for item in removed})==12
assert {item['path'] for item in removed}==set(expected)|{private,private+'/EMPTY FOLDER'}
assert all(item['started'] and item['acknowledged'] and item['confirmed'] and
    item['file_info_after']['status']==404 and item['file_info_after']['response'].get('errors') for item in removed)
assert 'PASS:' in (directory/'cleanup-workflow.log').read_text()

delta=read(ARCHIVE/'harness-after-usb-failure/SHA256.json');assert len(delta)==4
for name,sha in delta.items():assert digest((ARCHIVE/'harness-after-usb-failure'/name).read_bytes())==sha
guards=read(ARCHIVE/'host-usb-cleanup.json')
assert guards['passed'] and not guards['hardware_io'] and len(guards['cases'])==14 and all(guards['cases'].values())
assert guards['source_report_sha256']==digest((directory/'report.json').read_bytes())
restore=read(ARCHIVE/'host-usb-restore-after-diagnostics.json')
assert restore['passed'] and not restore['hardware_io'] and len(restore['cases'])==13
assert all(case['passed'] for case in restore['cases'].values())
result=dict(passed=True,initial_native_workflow_passed=False,initiating_failure_resolved=False,
    failure_stage='boot-browser directory rescan after missing USB app launch',
    native_images_changed=False,cpu_sequence_passed=True,delayed_abort_hypothesis_passed=True,source_files_verified=10,
    stored_bytes_verified=sum(map(len,expected.values())),deleted_paths=12,
    temporary_input_bytes=sum(len(data) for path,data in expected.items() if path.startswith('/Temp/')),
    cleanup_guard_cases=14,restore_guard_cases=13,harness_delta_files=4,full_os_complete=False)
destination=ARCHIVE/'usb-recovery-verification.json'
if args.record:destination.write_text(json.dumps(result,indent=2)+'\n')
else:assert result==read(destination)
print('PASS: original failed USB observations retained; ten complete inputs verified, twelve exact paths removed')
