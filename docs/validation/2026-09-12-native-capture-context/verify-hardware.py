#!/usr/bin/env python3
"""Audit the retained failed attempt and completed restoration without device I/O."""
import hashlib
import json
from pathlib import Path
import sys

A = Path(__file__).resolve().parent
H = A/'hardware'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
sys.path.insert(0, str(A/'inputs'))
from launcher_scene import surface, console

r = read(H/'report.json')
attempt = read(A/'physical-attempt.json')
assert attempt['process_finished'] and not attempt['passed']
assert attempt['manifest_sha256'] == sha(A/'frozen-inputs.json')
assert not attempt['full_desktop_qualification']
assert r['physical_hardware_io'] and not r['passed'] and not r['full_desktop_workflow']
assert not r.get('native_checks_passed') and r['events'] == []
assert r['native_error'] == 'native heap changed during observation'
for key in ('legacy_desktop_restored', 'cleanup_complete', 'images_unchanged',
            'dos_paths_restored', 'controls_restored', 'preflight_controls_restored'):
    assert r[key], key
assert r['uncertain_host_writes'] == []
assert r['host_connect_failures'] == [dict(method='PUT', endpoint='/v1/machine:writemem',
    attempt=1, request_sent=False, error='timed out')]
assert 'no request sent' in (A/'hardware-stdout.txt').read_text()

rows = r['captures'] + r['mode_captures']
assert len(rows) == 16 and sum(row['restored'] for row in rows) == 15
chunks = [chunk for row in rows for chunk in row['chunks']]
assert len(chunks) == 53 and sum(c['count'] for c in chunks) == 24783
assert sum(c['foreground_mmu'] == 0 for c in chunks) == 1
assert sum(c['foreground_mmu'] == 14 for c in chunks) == 52
status_bytes = payload_bytes = borrower_bytes = completed_pairs = 0
differences = []
missing_after = []
for row in rows:
    result = bytearray()
    for chunk in row['chunks']:
        status = H/chunk['status_file']; payload = H/chunk['payload_file']
        assert sha(status) == chunk['status_sha256']
        assert sha(payload) == chunk['payload_sha256']
        raw = status.read_bytes(); data = payload.read_bytes()
        assert len(raw) == 12 and len(data) == chunk['count'] == chunk['payload_bytes']
        assert raw[0] == chunk['code'] == 1 and raw[9] == chunk['mode_register']
        assert raw[10] == chunk['common_register'] and raw[11] == chunk['foreground_mmu']
        assert not raw[9] & 0x40 and raw[10] & 15 == 4 and raw[11] in (0, 14)
        assert int.from_bytes(raw[7:9], 'little') == chunk['address_resyncs']
        result.extend(data); status_bytes += len(raw); payload_bytes += len(data)
    assert len(result) == row['count'] and result == (H/(row['label']+'.bin')).read_bytes()
    for name, check in row['borrower_checks'].items():
        before_path = H/check['before_file']; before = before_path.read_bytes()
        assert sha(before_path) == check['before_sha256'] and len(before) == check['bytes']
        borrower_bytes += len(before)
        if 'after_file' not in check:
            missing_after.append((row['label'], name)); continue
        after_path = H/check['after_file']; after = after_path.read_bytes()
        assert sha(after_path) == check['after_sha256']
        assert len(after) == check['observed_bytes'] == len(before)
        changed = [i for i, (x, y) in enumerate(zip(before, after)) if x != y]
        assert changed == check['different_offsets'] and check['matches'] == (before == after)
        differences.extend((row['label'], name, check['address']+i, before[i], after[i]) for i in changed)
        borrower_bytes += len(after); completed_pairs += 1
assert (status_bytes, payload_bytes, borrower_bytes, completed_pairs) == (636, 24783, 153344, 63)
assert missing_after == [('boot-vdc', 'resident')]
assert differences == [('boot-vdc', 'metadata', 0x3d0c, 27, 7),
                       ('boot-vdc', 'metadata', 0x3d13, 0, 2),
                       ('boot-vdc', 'metadata', 0x3d15, 0, 17)]
last = r['captures'][-1]
assert last['label'] == 'boot-vdc' and not last['restored']
before = (H/'boot-vdc-borrower-metadata-before.bin').read_bytes()
after = (H/'boot-vdc-borrower-metadata-after.bin').read_bytes()
assert before[:0x500] == after[:0x500]
assert before[0x511:0x513] == after[0x511:0x513] == bytes([0, 1])
assert int.from_bytes(before[0x513:0x515], 'little') == 0
assert int.from_bytes(after[0x513:0x515], 'little') == 2
assert len(r['transport_samples']) == 6
for sample in r['transport_samples']:
    expected = console(80) if sample['mode'] else surface()[sample['address']-0xc000:][:sample['bytes']]
    assert (H/(sample['label']+'-expected.bin')).read_bytes() == expected
    assert (H/(sample['label']+'.bin')).read_bytes() == expected
    assert sample['matches'] and not sample['different_offsets']
    assert sample['capture_returned'] == (sample['label'] != 'boot-vdc')
assert len(r['paused_capture_batches']) == 154
assert all(b['pause_acknowledged'] and b['resume_attempted'] and b['resume_acknowledged']
           for b in r['paused_capture_batches'])
for control in r['host_control_requests']:
    assert control['request_started'] and control['response_received'] and not control['replayed']
    assert control['status'] == 200 and json.loads(bytes.fromhex(control['body_hex']))['errors'] == []
assert len(r['ram_write_receipts']) == 940
for receipt in r['ram_write_receipts']:
    expected = f'{receipt["address"]:04x}-{receipt["address"]+receipt["bytes"]-1:04x}'
    reply = json.loads(bytes.fromhex(receipt['body_hex']))
    assert receipt['range_acknowledged'] and receipt['response_received'] and receipt['status'] == 200
    assert receipt['expected_range'] == reply['address'].lower() == expected and reply['errors'] == []
    assert not receipt['replayed'] and 1 <= receipt['bytes'] <= 128
resident = r['resident_boot']
assert resident['passed'] and not resident['unexpected_changes']
assert resident['immutable_bytes'] == 11971 and resident['mutable_bytes'] == 1581
assert read(H/'drives-before.json') == read(H/'drives-restored.json') == read(H/'drives-final.json')
assert (H/'settings-before.bin').read_bytes() == bytes.fromhex('507302f0a502030000')
assert r['dos_paths_before_hex'] == {'1': '2f', '2': '2f557362302f6336342f232d612f'}
files = {r['native_disk_upload_path']: H/'native.d64', r['restore_prg_path']: A/'inputs/target/uos.prg'}
assert set(r['temporary_readbacks']) == set(files) and len(files) == 2
assert r['restore_prg_owned'] and r['restore_prg_verified_before_mounts']
for path, expected in files.items():
    saved = r['temporary_readbacks'][path]
    assert saved['sha256'] == sha(expected) and saved['bytes'] == expected.stat().st_size
    assert (H/('readback-'+Path(path).name+'.bin')).read_bytes() == expected.read_bytes()
assert sum(x['bytes'] for x in r['temporary_readbacks'].values()) == 176884
assert {x['path'] for x in r['temporary_deletions'] if x['started'] and x['confirmed']} == set(files)
print('PASS archive audit: failed physical observation retained; 24,783 payload bytes, three ABI differences, 940 acknowledged writes, original deployment and two-file cleanup verified')
