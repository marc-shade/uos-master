#!/usr/bin/env python3
"""Verify the controlled input explanation while retaining the physical uncertainty."""
import hashlib
import json
from pathlib import Path
import sys

A = Path(__file__).resolve().parent
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
baseline = read(A/'frozen-inputs.json')
manifest = read(A/'input-control-manifest.json')
assert len(manifest) == 346 and set(manifest)-set(baseline) == {'native_input_capture_vice.py'}
assert {n for n, h in baseline.items() if manifest[n] != h} == {'tests/ci_native_desktop_iec.py'}
for name, digest in manifest.items():
    path = A/'input-control-overlays'/name
    if not path.exists(): path = A/'inputs'/name
    assert sha(path) == digest, name
sys.path.insert(0, str(A/'inputs'))
from launcher_scene import console

E = A/'emulator-input'; report = read(E/'report.json')
assert report['passed'] and not report['physical_hardware_io']
assert report['options']['input_during_capture']
assert [e['key'] for e in report['events']] == [17, 17]
control = report['input_control']
assert control['passed'] and control['activity_rejected']
assert not control['physical_failure_cause_proven']
assert control['original_vdc_payload_matches'] and control['independent_resident_immutable_bytes_match']
assert report['expected_capture_error'] == 'native heap changed during observation'
assert len(report['desktops']) == 2 and [d['selected'] for d in report['desktops']] == [0, 2]
assert sum(d['pixels'] for d in report['desktops']) == 128000
assert (E/'input-vdc.bin').read_bytes() == console(80)
row, = report['captures']
assert row['label'] == 'input-vdc' and not row['restored'] and len(row['chunks']) == 4
payload = bytearray()
for chunk in row['chunks']:
    status = E/chunk['status_file']; data = E/chunk['payload_file']
    assert sha(status) == chunk['status_sha256'] and sha(data) == chunk['payload_sha256']
    assert len(status.read_bytes()) == 12 and status.read_bytes()[0] == 1
    assert data.stat().st_size == chunk['count'] == chunk['payload_bytes']
    payload.extend(data.read_bytes())
assert payload == console(80)
changes = []
for name, check in row['borrower_checks'].items():
    before = E/check['before_file']; assert sha(before) == check['before_sha256']
    if name == 'resident':
        assert 'after_file' not in check
        after = E/'input-vdc-independent-resident-after.bin'
    else:
        after = E/check['after_file']; assert sha(after) == check['after_sha256']
    a, b = before.read_bytes(), after.read_bytes(); assert len(a) == len(b) == check['bytes']
    different = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if name == 'resident':
        assert different == [0x17d0-0x1300] and a[different[0]] == 27 and b[different[0]] == 7
    else:
        assert different == check['different_offsets'] and check['matches'] == (a == b)
        changes.extend(dict(address=check['address']+i, before=a[i], after=b[i]) for i in different)
assert changes == control['exact_physical_difference_pattern'] == [
    dict(address=0x3d0c, before=27, after=7), dict(address=0x3d13, before=0, after=2),
    dict(address=0x3d15, before=0, after=17)]
assert all(b['pause_acknowledged'] and b['resume_acknowledged'] for b in report['paused_capture_batches'])
history = read(A/'input-control-history/xpeawv_i/report.json')
assert not history['passed'] and history['options']['input_during_capture']
assert history['error'] == ''
print('PASS: two controlled cursor-down events reproduce all three physical ABI differences; strict capture rejected activity, immutable resident bytes and both rendered desktop states verified')
