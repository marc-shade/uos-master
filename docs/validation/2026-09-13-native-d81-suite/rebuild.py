#!/usr/bin/env python3
"""Rebuild the suite and compare every native PRG, D64 and D81 image."""
import argparse,hashlib,json,subprocess
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--report',type=Path,required=True);parser.add_argument('--log',type=Path,required=True)
args=parser.parse_args();record=Path(__file__).resolve().parent
assert not (record/'SHA256SUMS').exists(),'sealed record is immutable'
expected=json.loads((record/'images.json').read_text())
with args.log.open('wb') as log:
 result=subprocess.run(['python3','-B','build-native-desktop.py'],cwd=args.source,stdout=log,stderr=subprocess.STDOUT)
images={str(p.relative_to(args.source)):hashlib.sha256(p.read_bytes()).hexdigest()
 for folder in ('target/native','target/native-desktop') for p in (args.source/folder).rglob('*') if p.suffix in ('.prg','.d64','.d81')}
report=dict(passed=result.returncode==0 and images==expected,source=str(args.source),build_exit_code=result.returncode,images=images)
args.report.write_text(json.dumps(report,indent=2)+'\n');assert report['passed'],report
print('PASS: all 29 native PRG/D64/D81 images reproduce exactly')
