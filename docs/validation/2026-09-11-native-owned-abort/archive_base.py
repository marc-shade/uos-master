"""Read provenance anchored to the preceding signed module archive."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / '2026-09-11-native-modules'
MANIFEST_SHA256 = 'f8709c6e23f18685b3ba9aef749dc747e7c1fbd9af6a522ef09002a392f027d5'
manifest = (BASE / 'SHA256SUMS').read_bytes()
assert hashlib.sha256(manifest).hexdigest() == MANIFEST_SHA256
checksums = {name:sha for sha,name in
             (line.split('  ',1) for line in manifest.decode().splitlines())}

def read_base(name):
    data = (BASE / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == checksums[name], name
    return json.loads(data)

