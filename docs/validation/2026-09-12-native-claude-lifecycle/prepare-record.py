#!/usr/bin/env python3
"""Freeze the selected source and rebuild in a directory without target images."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
root = Path('/home/marc/geos128/uos')
work = Path(__file__).resolve().parent
source = work/'inputs'
clean = work/'clean-rebuild'
source.mkdir()
clean.mkdir()
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
names = sorted(name for name in tracked if name and (
    ('/' not in name and name.endswith('.py')) or
    name.startswith(('src/', 'probes/', 'apps/claude/', 'tests/'))))
manifest = {}
for name in names:
    path = root/name
    if not path.is_file():
        continue
    data = path.read_bytes()
    manifest[name] = hashlib.sha256(data).hexdigest()
    for base in (source, clean):
        out = base/name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
(work/'inputs.json').write_text(json.dumps(manifest, indent=2)+'\n')
with (work/'clean-rebuild.log').open('w') as log:
    subprocess.run([sys.executable, '-B', 'build-native-desktop.py'], cwd=clean,
                   stdout=log, stderr=subprocess.STDOUT, check=True)
report = dict(passed=False, initially_empty_target=True, images={}, source_files=len(manifest))
for prefix in ('native', 'native-desktop'):
    for path in sorted((clean/'target'/prefix).iterdir()):
        if path.suffix not in ('.prg', '.d64'):
            continue
        relative = path.relative_to(clean)
        observed, expected = path.read_bytes(), (root/relative).read_bytes()
        assert observed == expected, relative
        report['images'][str(relative)] = dict(bytes=len(observed), sha256=hashlib.sha256(observed).hexdigest())
assert len(report['images']) == 19
for name, digest in manifest.items():
    assert hashlib.sha256((clean/name).read_bytes()).hexdigest() == digest, name
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest, name
report['passed'] = True
(work/'clean-rebuild.json').write_text(json.dumps(report, indent=2)+'\n')
print(f"PASS: {len(report['images'])} identical images from {len(manifest)} frozen source files")

# Preserve the compiler's load map and all suite outputs separately from the
# unseeded rebuild, so the verifier need not invoke any build tool.
for prefix in ('native', 'native-desktop'):
    for path in sorted((root/'target'/prefix).iterdir()):
        if path.is_file() and path.suffix in ('.prg', '.d64', '.lbl', '.map', '.lst', '.sym', '.json'):
            out = source/path.relative_to(root)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out)
