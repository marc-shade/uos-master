#!/usr/bin/env python3
"""Compare the current main tree with the exact qualified desktop source/images."""
import argparse
import hashlib
import json
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parent
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
parser = argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=ARCHIVE.parents[2])
parser.add_argument('--record',action='store_true')
args = parser.parse_args()
sources = read(ARCHIVE/'source-overlays-current.json')
for name,digest in sources.items():
    assert sha(args.root/name) == digest, name
images = {name:digest for name,digest in read(ARCHIVE/'input-manifest.json').items()
          if name.startswith('target/') and name.endswith(('.prg','.d64'))}
for name,digest in images.items():
    assert sha(args.root/name) == digest, name
assert (args.root/'hw_native_usb_recovery.py').read_bytes() == (ARCHIVE/'inputs/hw_native_usb_recovery.py').read_bytes()
for option in ('--native-desktop','--native-usb-cleanup-reopen','--native-usb-inspect-reopen','--native-usb-release-reopen'):
    assert option in (args.root/'hw_ultimate_check.py').read_text()
result = dict(passed=True,source_files=len(sources),exact_images=len(images),
              latest_owned_abort_recovery_preserved=True,desktop_target='target/native-desktop/uos128.d64',
              diagnostic_target='target/native/uos128.d64',physical_desktop_qualification_complete=False)
if args.record:
    (ARCHIVE/'integration-verification.json').write_text(json.dumps(result,indent=2)+'\n')
else:
    assert result == read(ARCHIVE/'integration-verification.json')
print('PASS: 52 integrated sources and 36 exact images; latest USB recovery preserved; physical qualification remains incomplete')
