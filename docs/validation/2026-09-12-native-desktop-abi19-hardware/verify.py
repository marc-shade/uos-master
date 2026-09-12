#!/usr/bin/env python3
"""Audit the full physical workflow and restoration using retained bytes only."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
A = Path(__file__).resolve().parent
H = A/'hardware'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
inputs = read(A/'frozen-inputs.json')
assert len(inputs) == 348
for name, digest in inputs.items():
    assert sha(A/'inputs'/name) == digest, name
assert sha(A/'frozen-inputs.json') == 'da468070c73d9842e0157e23279fde4a8d4978f6f8d4339401e10cd0183f1c48'
attempt = read(A/'physical-attempt.json')
assert attempt['passed'] and attempt['process_finished'] and attempt['full_desktop_qualification']
assert attempt['manifest_sha256'] == sha(A/'frozen-inputs.json') and 'error' not in attempt
assert 'HW-NATIVE-DESKTOP PASS' in (A/'physical-stdout.log').read_text()

sys.path.insert(0, str(A/'inputs'))
from launcher_scene import surface, console
from native_capture import expected_screen, calculator_screen
from native_editor_check import editor_screen
from native_browser_check import disk_records, browser_screen
from native_running_layout import RunningLayout
from native_mode_capture import FIELDS

r = read(H/'report.json')
for key in ('passed', 'physical_hardware_io', 'full_desktop_workflow', 'native_checks_passed',
            'legacy_desktop_restored', 'cleanup_complete', 'images_unchanged',
            'dos_paths_restored', 'controls_restored', 'preflight_controls_restored'):
    assert r[key], key
assert not any(key.endswith('_error') for key in r)
assert r['uncertain_host_writes'] == r['host_connect_failures'] == []
for name, digest in r['build'].items(): assert sha(A/'inputs'/name) == digest, name
assert (H/'native.d64').read_bytes() == (A/'inputs/target/native-desktop/uos128.d64').read_bytes()

rows = r['captures']+r['mode_captures']
assert len(r['captures']) == 60 and len(r['mode_captures']) == 6
chunks = [chunk for row in rows for chunk in row['chunks']]
assert len(chunks) == 215 and sum(c['count'] for c in chunks) == 101274
assert sum(c['foreground_mmu'] == 0 for c in chunks) == 12
assert sum(c['foreground_mmu'] == 14 for c in chunks) == 203
status_bytes = payload_bytes = borrower_bytes = completed_pairs = 0
for row in rows:
    assert row['restored'] and not row['borrower_failures'] and 'capture_error' not in row
    data = bytearray()
    for chunk in row['chunks']:
        status = H/chunk['status_file']; payload = H/chunk['payload_file']
        assert sha(status) == chunk['status_sha256'] and sha(payload) == chunk['payload_sha256']
        raw = status.read_bytes(); part = payload.read_bytes()
        assert len(raw) == 12 and len(part) == chunk['count'] == chunk['payload_bytes']
        assert raw[0] == chunk['code'] == 1 and raw[9] == chunk['mode_register']
        assert raw[10] == chunk['common_register'] and raw[11] == chunk['foreground_mmu']
        assert not raw[9]&0x40 and raw[10]&15 == 4 and raw[11] in (0, 14)
        assert int.from_bytes(raw[7:9], 'little') == chunk['address_resyncs'] == 0
        assert chunk['address'] == row['address']+len(data)
        data.extend(part); status_bytes += len(raw); payload_bytes += len(part)
    assert len(data) == row['count'] and data == (H/(row['label']+'.bin')).read_bytes()
    assert set(row['borrower_checks']) == {'output', 'scratch', 'metadata', 'resident'}
    for check in row['borrower_checks'].values():
        before = H/check['before_file']; after = H/check['after_file']
        assert sha(before) == check['before_sha256'] and sha(after) == check['after_sha256']
        assert before.read_bytes() == after.read_bytes() and check['matches']
        assert not check['different_offsets'] and not check['changes']
        assert before.stat().st_size == check['bytes'] == check['observed_bytes']
        borrower_bytes += 2*check['bytes']; completed_pairs += 1
assert (status_bytes, payload_bytes, borrower_bytes, completed_pairs) == (2580, 101274, 642048, 264)

assert [d['selected'] for d in r['desktops']] == [0, 1, 0, 1, 2]
for row in r['desktops']:
    label = row['label']; selected = row['selected']
    bitmap = H/(label+'-surface.bin')
    assert bitmap.read_bytes() == surface(selected) and sha(bitmap) == row['surface_sha256']
    assert (H/(label+'-vdc.bin')).read_bytes() == console(80, selected)
    assert row['irq_advanced'] and row['surface_bytes'] == 9216 and row['vdc_bytes'] == 2000
    mode = dict(zip(FIELDS, (H/(label+'-mode.bin')).read_bytes()))
    assert mode == row['registers']
    assert mode['vic_d011']&0x7f == 0x3b and mode['vic_d016']&0x1f == 8 and mode['vic_d018']&0xfe == 0x80
    assert mode['vic_irq_mask']&15 == 1 and mode['vic_sprites'] == 0
    assert mode['cia2_port']&3 == 0 and mode['cia2_ddr']&3 == 3
    assert mode['foreground_mmu'] in (0, 14) and not mode['mode']&0x40 and mode['common']&15 == 4
    assert (mode['cpu_ddr'], mode['cpu_port']) == (0x2f, 0x75) and mode['text_graphics'] == 255
    assert mode['text_display']&128 and not mode['cpu_speed']&1
    heap = (H/(label+'-heap.bin')).read_bytes()
    assert heap[0x50:0xff].count(0)+heap[0x104:0x1ff].count(0) == 372

oracles = {
    'calculator-new': lambda c: calculator_screen(c, '0', []),
    'calculator-result': lambda c: calculator_screen(c, '42', ['42']),
    'editor-new': lambda c: editor_screen(c, b'', 0),
    'editor-typed': lambda c: editor_screen(c, b'C128', 4, dirty=True),
    'files': lambda c: browser_screen(c, disk_records((H/'native.d64').read_bytes())),
    'workspace-returned': lambda c: expected_screen(c, 0),
}
assert r['screens'] == list(oracles)
for label, oracle in oracles.items():
    for columns, suffix in ((40, 'vic'), (80, 'vdc')):
        assert (H/(label+'-'+suffix+'.bin')).read_bytes() == oracle(columns)
assert [event['key'] for event in r['events']] == [9, 67, *b'12+30=', 27, 69, *b'C128', 27, 89, 70, 27, 27]
heap = (H/'final-native-heap.bin').read_bytes()
assert heap[0x50:0xff] == bytes(175) and heap[0x104:0x1ff] == bytes(251)
assert all(heap[0x400+i*8] == 0 for i in range(32))
assert dict(zip(FIELDS, (H/'workspace-returned-mode.bin').read_bytes())) == r['final_mode']
assert r['final_mode']['cpu_port'] == 0x73 and r['final_mode']['text_graphics'] == 0
layout = RunningLayout(A/'inputs', image_dir=A/'inputs/target/native-desktop')
for name in ('boot', 'return'):
    actual = {key:(H/f'resident-{name}-{key}.bin').read_bytes() for key in layout.regions}
    result = layout.compare(actual)
    assert result == r['resident_'+name] == read(H/f'resident-{name}-layout.json')
    assert result['passed'] and (result['immutable_bytes'], result['mutable_bytes']) == (11971, 1581)

assert len(r['paused_capture_batches']) == 647
assert all(b['pause_acknowledged'] and b['resume_attempted'] and b['resume_acknowledged']
           for b in r['paused_capture_batches'])
for control in r['host_control_requests']:
    assert control['request_started'] and control['response_received'] and not control['replayed']
    assert control['status'] == 200 and json.loads(bytes.fromhex(control['body_hex']))['errors'] == []
assert len(r['ram_write_receipts']) == 1906
for receipt in r['ram_write_receipts']:
    expected = f'{receipt["address"]:04x}-{receipt["address"]+receipt["bytes"]-1:04x}'
    reply = json.loads(bytes.fromhex(receipt['body_hex']))
    assert receipt['range_acknowledged'] and receipt['response_received'] and receipt['status'] == 200
    assert receipt['expected_range'] == reply['address'].lower() == expected and reply['errors'] == []
    assert not receipt['replayed'] and 1 <= receipt['bytes'] <= 128
assert read(H/'drives-before.json') == read(H/'drives-restored.json') == read(H/'drives-final.json')
settings = (H/'settings-before.bin').read_bytes()
assert settings == bytes.fromhex('507302f0a502030000')
# The five setting bytes are surrounded by borrowed scratch. The boot
# snapshot precedes restoration of all nine bytes; it is not the final readback.
assert settings[2:7] == bytes.fromhex(r['legacy_boot_settings_hex'])[2:7]
settings_writes = [q for q in r['ram_write_receipts'] if q['address'] == 0x7350]
assert len(settings_writes) == 1 and settings_writes[0]['bytes'] == 9
assert settings_writes[0]['sha256'] == hashlib.sha256(settings).hexdigest()
assert r['dos_paths_before_hex'] == {'1':'2f', '2':'2f557362302f6336342f232d612f'}
files = {r['native_disk_upload_path']:H/'native.d64', r['restore_prg_path']:A/'inputs/target/uos.prg'}
assert len(files) == 2 and set(r['temporary_readbacks']) == set(files)
assert r['restore_prg_owned'] and r['restore_prg_verified_before_mounts']
for path, expected in files.items():
    saved = r['temporary_readbacks'][path]
    assert saved['sha256'] == sha(expected) and saved['bytes'] == expected.stat().st_size
    assert (H/('readback-'+Path(path).name+'.bin')).read_bytes() == expected.read_bytes()
assert sum(x['bytes'] for x in r['temporary_readbacks'].values()) == 176884
assert {x['path'] for x in r['temporary_deletions'] if x['started'] and x['confirmed']} == set(files)
print('PASS: full physical desktop, 101274 payload bytes, 264 restored borrower pairs, 1906 write receipts and verified original deployment/two-file cleanup')
