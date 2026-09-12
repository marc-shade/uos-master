#!/usr/bin/env python3
"""Audit integrated sources, harness corrections and reuse of prior host checks."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from archive_base import read_base, MANIFEST_SHA256

ARCHIVE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--record',action='store_true')
args = parser.parse_args()
read = lambda name: json.loads((ARCHIVE/name).read_text())
digest = lambda data: hashlib.sha256(data).hexdigest()
frozen,live = read('frozen.json'),read('frozen-live.json')
assert len(frozen)==len(live)==47 and frozen.keys()==live.keys()
metadata=[]
for name in frozen:
    old=(ARCHIVE/'frozen'/name).read_bytes()
    current=(ARCHIVE/'frozen-live'/name).read_bytes()
    for data,record in ((old,frozen[name]),(current,live[name])):
        assert len(data)==record['bytes'] and digest(data)==record['sha256'],name
    if old!=current:
        assert name.endswith('.lst'),name
        rows=lambda data:[line for line in data.decode().splitlines()
                          if line.strip() and not line.startswith(';')]
        assert rows(old)==rows(current),name
        metadata.append(name)
assert len(metadata)==5
harness={}
counts={}
for folder in ('harness','harness-sdk-correction','harness-physical'):
    contents=read(folder+'/SHA256.json')
    counts[folder]=len(contents)
    for name,expected in contents.items():
        assert digest((ARCHIVE/folder/name).read_bytes())==expected,(folder,name)
    harness.update(contents)
assert counts=={'harness':130,'harness-sdk-correction':3,'harness-physical':4}
assert len(harness)==132
previous=read_base('harness/SHA256.json')|read_base('harness-after-usb-failure/SHA256.json')
assert len(previous)==125
assert all(harness[name]==expected for name,expected in previous.items())
software_harness_files=len(harness)
current=read('harness-current/SHA256.json')
assert len(current)==3
for name,expected in current.items():
    assert digest((ARCHIVE/'harness-current'/name).read_bytes())==expected,name
harness.update(current)
assert len(harness)==133
changed_prior=sorted(name for name,expected in previous.items() if harness[name]!=expected)
assert changed_prior==['hw_native_usb_recovery.py','hw_ultimate_check.py']
reports={
    'host-transport.json':8,'host-uploads.json':11,'host-editor-restore.json':5,
    'host-usb-restore.json':13,'host-usb-cleanup.json':14}
for name,count in reports.items():
    report=read(name)
    assert report==read_base(name) and report['passed'] and not report['hardware_io']
    assert len(report['cases'])==count
assert sum(reports.values())==51
current_reports={}
for name,count in [('transport',8),('uploads',11),('editor_restore',5),('usb_restore',13),('usb_cleanup',14),('usb_reopen_cleanup',36)]:
    report=read('host-current/'+name+'.json')
    assert report['passed'] and not report['hardware_io'] and len(report['cases'])==count
    assert all(value.get('passed') if isinstance(value,dict) else value for value in report['cases'].values())
    if name!='usb_reopen_cleanup':
        assert report['cases'].keys()==read('host-'+name.replace('_','-')+'.json')['cases'].keys()
    current_reports[name]=count
assert sum(current_reports.values())==87
reopen=read('host-current/usb_reopen_cleanup.json')
assert reopen['source_report_sha256']==digest((ARCHIVE/'hardware-usb-reopen-failure/report.json').read_bytes())
assert len(reopen['expected_files'])==12 and sum(item['bytes'] for item in reopen['expected_files'])==332431
repeat='host-usb-restore-after-diagnostics.json'
assert read(repeat)==read_base(repeat)
assert read(repeat)['passed'] and len(read(repeat)['cases'])==13
sdk=read('sdk-example/source/SHA256.json')
assert len(sdk)==6 and all(harness[name]==sha for name,sha in sdk.items())
images=read('images.json')
for name,record in images.items():
    assert record==live['target/native/'+name]
package=read('package/report.json')
assert package['passed'] and package['extra_resident_bytes']==15
assert package['additional_reserved_pages']==0
assert package['images']==images
result=dict(passed=True,hardware_io=False,
    base_commit='2bde88b41e7227c2d8fc3fe2e185a20ae6e2df73',
    base_manifest_sha256=MANIFEST_SHA256,frozen_files=47,live_frozen_files=47,
    listing_metadata_only_differences=metadata,images_identical_to_software_qualification=True,
    original_harness_files=130,sdk_corrections=3,physical_harness_overrides_and_additions=4,
    software_harness_files=software_harness_files,current_harness_files=133,baseline_harness_files_reused=123,
    changed_prior_harness_files=changed_prior,current_harness_overrides_and_additions=3,
    distinct_host_cases_reused=0,existing_host_cases_rerun=51,new_host_reopen_cases=36,
    repeated_prior_restoration_cases=13,current_host_reports=current_reports,
    host_reports=reports,host_checks_rerun_for_this_checkpoint=True,
    native_source_change='src/native/ultimate.inc',resident_code_growth_bytes=15)
destination=ARCHIVE/'integration-verification.json'
if args.record:destination.write_text(json.dumps(result,indent=2)+'\n')
else:assert read('integration-verification.json')==result
print('PASS: 47 integrated files; 133 final harness files; 51 existing and 36 new host checks pass on current recovery code')
