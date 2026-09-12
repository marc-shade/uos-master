#!/usr/bin/env python3
"""Check the frozen uninstrumented physical-run inputs and exact native images."""
import argparse
import hashlib
import json
from pathlib import Path

ARCHIVE=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
parser=argparse.ArgumentParser();parser.add_argument('--usb-only',action='store_true')
parser.add_argument('--record',action='store_true');args=parser.parse_args()
inputs=ARCHIVE/'hardware-inputs';manifest=read(inputs/'frozen-inputs.json')
assert len(manifest)==255
for name,digest in manifest.items():assert sha(inputs/name)==digest,name
for name,record in read(ARCHIVE/'frozen-live.json').items():
    assert manifest[name]==record['sha256'],name
current={}
for folder in ('harness','harness-sdk-correction','harness-physical','harness-current'):
    current.update(read(ARCHIVE/folder/'SHA256.json'))
shared=sorted(set(current)&set(manifest))
assert all(current[name]==manifest[name] for name in shared)
assert 'rollback_probe' not in (inputs/'hw_native_ultimate_check.py').read_text()
context=read(inputs/'RUN-CONTEXT.json')
assert context['input_files']==255 and context['instrumentation'] is False
assert context['kernel_sha256']==manifest['target/native/uos128.prg']
assert context['command']==['python3','-u','hw_ultimate_check.py','--native-usb-browser']
images=read(ARCHIVE/'images.json')
expected=read(ARCHIVE/'package/report.json')['legacy_images']|{'target/native/'+name:row['sha256'] for name,row in images.items()}
folders=['hardware'] if args.usb_only else ['hardware','hardware-iec']
for folder in folders:
    report=read(ARCHIVE/folder/'report.json')
    assert report['passed'] and report['native_checks_passed'] and report['legacy_desktop_restored']
    assert report['images_unchanged'] and report['build']==expected
    assert report['dos_paths_restored'] and not report['uncertain_host_writes']
    assert sha(ARCHIVE/folder/'native.d64')==images['uos128.d64']['sha256']
    assert all(manifest[name]==digest for name,digest in report['build'].items())
result=dict(passed=True,hardware_io=False,uninstrumented_frozen_inputs=255,
            shared_current_harness_inputs=len(shared),physical_workflows=folders,
            kernel_sha256=images['uos128.prg']['sha256'],disk_sha256=images['uos128.d64']['sha256'],
            input_manifest_sha256=sha(inputs/'frozen-inputs.json'))
output=ARCHIVE/('physical-usb-input-verification.json' if args.usb_only else 'physical-input-verification.json')
if args.record:output.write_text(json.dumps(result,indent=2)+'\n')
else:assert result==read(output)
print(f'PASS: 255 frozen uninstrumented inputs; {len(folders)} physical workflows use the qualified kernel and exact app images')
