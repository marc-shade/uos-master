#!/usr/bin/env python3
"""Rebuild a separate source tree and compare every native PRG/D64 byte hash."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--report',type=Path,required=True)
parser.add_argument('--log',type=Path,required=True)
args=parser.parse_args()
record=Path(__file__).resolve().parent
assert not (record/'SHA256SUMS').exists(),'sealed record is immutable'
inputs=json.loads((record/'inputs-files.json').read_text())
with args.log.open('wb') as log:
    result=subprocess.run(['python3','-B','build-native-desktop.py'],cwd=args.source,stdout=log,stderr=subprocess.STDOUT)
images={str(p.relative_to(args.source)):hashlib.sha256(p.read_bytes()).hexdigest()
    for folder in ('target/native','target/native-desktop') for p in (args.source/folder).iterdir()
    if p.suffix in ('.prg','.d64')}
differences={name:dict(expected=inputs.get(name,{}).get('sha256'),actual=digest)
    for name,digest in images.items() if inputs.get(name,{}).get('sha256')!=digest}
report=dict(passed=result.returncode==0 and len(images)==22 and not differences,
    source=str(args.source),build_exit_code=result.returncode,images=images,differences=differences)
args.report.write_text(json.dumps(report,indent=2)+'\n')
assert report['passed'],report
print('PASS: all 22 native PRG/D64 images reproduce exactly',flush=True)
