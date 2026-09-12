#!/usr/bin/env python3
"""Rebuild the pinned desktop qualification disk without any hardware access."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for script in ('build-native.py', 'build-launcher.py'):
    subprocess.run([sys.executable, '-B', str(ROOT/script)], cwd=ROOT, check=True)
assert sha(ROOT/'target/native/uos128.prg') == 'e612e81d89b365d9a2f5836c9e89643ec21c1a92463ec7a0fe51a00206e2e54e'
assert sha(ROOT/'launcher/desktop-boot.d64') == 'e301b7d407fd8d6222c660b691f80608b5f601f54e38800e9024e1fa485b3097'
shutil.copyfile(ROOT/'launcher/desktop-boot.d64', ROOT/'target/native/uos128.d64')
images = json.loads((ROOT/'target/native/images.json').read_text())
images['uos128.d64'] = dict(bytes=(ROOT/'target/native/uos128.d64').stat().st_size,
                           sha256=sha(ROOT/'target/native/uos128.d64'))
(ROOT/'target/native/images.json').write_text(json.dumps(images, indent=2)+'\n')
assert json.loads((ROOT/'target/native/layout.json').read_text())['main_end'] == 0x37f8
print('PASS: rebuilt exact sealed desktop boot disk and matching full kernel layout; no physical I/O')
