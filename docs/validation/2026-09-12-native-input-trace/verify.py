#!/usr/bin/env python3
"""Offline evidence audit. Does not invoke the archived physical runner."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
read_json = lambda name: json.loads((ROOT/name).read_text())


def captures(folder, report):
    chunks = total = pairs = 0
    failures = []
    for capture in report['captures']:
        payload = bytearray()
        for chunk in capture['chunks']:
            status = (folder/chunk['status_file']).read_bytes()
            data = (folder/chunk['payload_file']).read_bytes()
            assert sha(status) == chunk['status_sha256'] and len(status) == 12
            assert status[0] == chunk['code'] == 1
            assert not status[9] & 0x40 and status[10] & 15 == 4
            assert status[11] == chunk['foreground_mmu'] in (0, 14)
            assert sha(data) == chunk['payload_sha256'] and len(data) == chunk['count']
            payload.extend(data)
            chunks += 1
        assert len(payload) == capture['count']
        assert payload == (folder/(capture['label']+'.bin')).read_bytes()
        total += len(payload)
        changed = []
        for name, row in capture['borrower_checks'].items():
            before = (folder/row['before_file']).read_bytes()
            after = (folder/row['after_file']).read_bytes()
            assert len(before) == len(after) == row['bytes']
            assert sha(before) == row['before_sha256'] and sha(after) == row['after_sha256']
            offsets = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
            assert row['matches'] == (before == after)
            assert offsets == row['different_offsets']
            assert len(offsets) == len(row['changes'])
            for i, change in zip(offsets, row['changes']):
                assert (change['address'], change['before'], change['after']) == (row['address']+i, before[i], after[i])
            if offsets:
                changed.append(name)
            pairs += 1
        assert capture['restored'] == (not changed)
        assert [r['region'] for r in capture['borrower_failures']] == changed
        if changed:
            failures.append(capture['label'])
    for batch in report.get('paused_capture_batches', []):
        assert batch['pause_acknowledged'] and batch['resume_acknowledged']
    return dict(captures=len(report['captures']), chunks=chunks, payload_bytes=total,
                borrower_pairs=pairs, rejected=failures)


def trace(folder, report, restored):
    from native_input_trace import decode
    row = report['input_trace']
    assert row['installed'] and row['held_input'] and row['restored'] == restored
    assert not row['reserved_by_heap']
    assert row['original_keycheck'] == 'adc6'
    assert sha((folder/'native-input-trace.prg').read_bytes()) == row['prg_sha256']
    assert sha((folder/'native-input-gate.prg').read_bytes()) == row['gate_sha256']
    snapshots = []
    for snapshot in row['snapshots']:
        raw = (folder/snapshot['file']).read_bytes()
        assert sha(raw) == snapshot['sha256']
        decoded = decode(raw)
        assert all(snapshot[k] == value for k, value in decoded.items())
        assert decoded['overflow'] == 0 and decoded['hold'] == 1
        snapshots.append(decoded)
    assert all(b['finish'] >= b['start'] for b in row['batches'])
    for name in ('pages', 'gate', 'keyin', 'keycheck') if restored else ('gate',):
        assert (folder/('input-trace-'+name+'-before.bin')).read_bytes() == (folder/('input-trace-'+name+'-after.bin')).read_bytes()
    ownership = (folder/'input-trace-ownership-before.bin').read_bytes()
    assert len(ownership) == 512 and ownership[0x50:0x58] == bytes(8)
    return snapshots


def audit():
    source = ROOT/'inputs'
    manifest = read_json('frozen-inputs.json')
    assert len(manifest) == 395
    assert sha((ROOT/'frozen-inputs.json').read_bytes()) == '118d47233058691004caff10db22a38768098ca6aab7815b38a683db96df10f1'
    assert set(manifest) == {str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
    for name, digest in manifest.items():
        assert sha((source/name).read_bytes()) == digest, name
    base = read_json('base-inputs.json')
    assert len(base) == 386 and all(manifest[name] == digest for name, digest in base.items())
    assert set(manifest)-set(base) == {'PLAN.md', 'native_input_trace.py', 'native_input_workflow.py',
        'probes/native-input-gate.asm', 'probes/native-input-trace.asm', 'run-input-hardware.py',
        'tests/ci_native_input_trace.py', 'tests/ci_native_input_trace_host.py', 'tests/ci_native_input_trace_iec.py'}
    assert (ROOT/'base-commit.txt').read_text().strip() == '81a21418a0a5bde52f78935945bbce514d6ff7ae'
    for name, count in [('input-cpu.json', 3), ('input-host.json', 4)]:
        report = read_json(name)
        assert report['passed'] and not report['physical_hardware_io'] and len(report['cases']) == count

    sys.path.insert(0, str(source))
    vice = read_json('vice/report.json')
    assert vice['passed'] and not vice['physical_hardware_io'] and vice['resident_restored']
    vice_stats = captures(ROOT/'vice', vice)
    assert vice_stats['rejected'] == ['trace-input-ram']
    vt = trace(ROOT/'vice', vice, True)
    assert [(r['type'], r['key']) for r in vt[-1]['records']] == [('scan', 17), ('consumed', 17), ('scan', 17), ('consumed', 17), ('consumed', 80)]
    assert [r['original_y'] for r in vt[-1]['records'] if r['type'] == 'scan'] == [84, 84]
    shared = vice['shared_workflow']
    assert shared['input_diagnostic']['completed'] and not shared['physical_hardware_io']
    assert shared['input_diagnostic']['initial_keys'] == shared['input_diagnostic']['final_keys']
    shared_stats = captures(ROOT/'vice/shared', shared)
    assert not shared_stats['rejected']
    assert trace(ROOT/'vice/shared', shared, True)[-1]['records'] == []

    hw = read_json('hardware-failed/report.json')
    attempt = read_json('physical-attempt.json')
    assert not hw['passed'] and not attempt['passed'] and attempt['process_finished']
    assert hw['physical_hardware_io'] and attempt['physical_hardware_io']
    assert attempt['manifest_sha256'] == sha((ROOT/'frozen-inputs.json').read_bytes())
    assert hw['native_error'] == attempt['error']['message'] == "('input diagnostic restoration differs', 'pages')"
    assert all(hw[k] for k in ('legacy_desktop_restored', 'dos_paths_restored', 'controls_restored', 'cleanup_complete', 'images_unchanged'))
    assert not hw['events'] and not hw['desktops'] and not hw['screens']
    assert not hw['uncertain_host_writes'] and not hw.get('cleanup_error')
    diagnostic = hw['input_diagnostic']
    assert not diagnostic['completed'] and not diagnostic['app_qualification']
    assert diagnostic['capture_rejected']['index'] == 0
    assert diagnostic['capture_rejected']['message'] == 'native metadata/ABI changed during observation ($3d13 N_KEYS, $3d15 N_LASTKEY)'
    assert diagnostic['idle_seconds'] == 30 and diagnostic['pause_batches'] == 12
    ht = trace(ROOT/'hardware-failed', hw, False)
    assert [len(t['records']) for t in ht] == [0, 0, 12]
    assert ht[-1]['scans'] == ht[-1]['consumed'] == 6
    records = ht[-1]['records']
    keys = [17, 17, 17, 17, 148, 148]
    indices = [7, 7, 7, 7, 89, 89]
    for i, (key, index) in enumerate(zip(keys, indices)):
        scan, consumed = records[2*i:2*i+2]
        assert (scan['type'], consumed['type']) == ('scan', 'consumed')
        assert scan['key'] == consumed['key'] == consumed['last_key_after'] == key
        assert scan['original_y'] == scan['scan_index_before'] == index
        assert scan['state_before_hex'].startswith('80fa')
        assert scan['original_x'] == scan['shift_flags'] == 0
        assert scan['function_count_before'] == consumed['function_count_before'] == 0
        assert scan['mmu_before'] == 0 and consumed['mmu_before'] == consumed['mmu_after'] == 14
        assert consumed['keys_before'] == scan['keys_before'] == i and consumed['keys_after'] == i+1
        assert scan['jiffy_before'] <= consumed['jiffy_after'] <= scan['jiffy_before']+1
        assert scan['cia1_ddr_a'] == scan['cia1_port_a'] == scan['extended_keyboard_lines'] == 255
        assert scan['cia1_ddr_b'] == 0 and scan['cia1_port_b'] == (255 if i < 4 else 253)
    hw_stats = captures(ROOT/'hardware-failed', hw)
    assert hw_stats['captures'] == 1 and hw_stats['chunks'] == 4 and hw_stats['payload_bytes'] == 2000
    failed = hw['captures'][0]
    assert hw_stats['rejected'] == ['input-observer-0']
    assert all(c['foreground_mmu'] == 14 for c in failed['chunks'])
    assert [r['region'] for r in failed['borrower_failures']] == ['metadata']
    assert failed['borrower_checks']['metadata']['changes'] == [
        dict(address=0x3d13, before=0, after=6, field='N_KEYS'),
        dict(address=0x3d15, before=0, after=148, field='N_LASTKEY')]

    correlation = read_json('rom-correlation.json')
    rom = (ROOT/correlation['excerpt']).read_bytes()
    assert len(rom) == correlation['bytes'] == 2048 and sha(rom) == correlation['sha256']
    before = (ROOT/'hardware-failed/input-trace-pages-before.bin').read_bytes()
    after = (ROOT/'hardware-failed/input-trace-pages-after.bin').read_bytes()
    assert after == rom and sum(a != b for a, b in zip(before, after)) == 2017
    pauses = [r for r in diagnostic['phases'] if r['phase'] == 2]
    assert len(pauses) == 12 and pauses[9]['index'] == 9
    assert bytes.fromhex(pauses[9]['header']) == rom[0x200:0x20f]
    assert all(bytes.fromhex(r['header']) == b'UIT1\x01\x14\0\0\0\x02\x01\0\0\0\0' for r in pauses if r['index'] != 9)
    assert all(bytes.fromhex(r['keyboard_state'])[4:] == b'\0\0\0\0XX' and bytes.fromhex(r['buffer']) == bytes(10) for r in pauses)
    correlation = read_json('keyboard-correlation.json')
    table = (ROOT/correlation['excerpt']).read_bytes()
    assert len(table) == correlation['bytes'] == 96 and sha(table) == correlation['sha256']
    excerpt = (ROOT/correlation['source_excerpt']).read_bytes()
    source_table = bytes(int(v, 16) for line in excerpt.splitlines() if b'.byte' in line
        for v in line.split(b'.byte', 1)[1].split(b';', 1)[0].strip().replace(b'$', b'').split(b','))
    assert len(source_table) == correlation['table_bytes'] == 89 and source_table == table[:89]
    assert [table[i] for i in (7, 84, 88, 89)] == [17, 17, 255, 148]

    for row in hw['ram_write_receipts']:
        assert row['range_acknowledged'] and row['status'] == 200 and not row['replayed']
        start, end = row['address'], row['address']+row['bytes']
        assert all(end <= a or start >= b for a, b in ((0xd0, 0xd3), (0x34a, 0x354)))
    assert not any(r['path'].startswith('/v1/configs/') for r in hw['host_control_requests'])
    assert hw['legacy_boot_settings_hex'] == '507302f0a502030000'
    owned = {'/Temp/temp00B1': ('native.d64', 174848),
        '/Temp/uos-hardware-native-transport-_lkgq2n4-restore.prg': ('restore-loader-readback.bin', 2036)}
    assert set(owned) == set(hw['temporary_readbacks'])
    for path, (filename, size) in owned.items():
        raw = (ROOT/'hardware-failed'/filename).read_bytes()
        assert len(raw) == size == hw['temporary_readbacks'][path]['bytes']
        assert sha(raw) == hw['temporary_readbacks'][path]['sha256']
    assert {r['path'] for r in hw['temporary_deletions'] if r['confirmed']} == set(owned)
    return dict(passed=True, physical_diagnostic_passed=False, native_apps_qualified=False,
        input_signal_source='Unestablished', observed_keys=keys, observed_scan_indices=indices,
        high_ram_restoration_established=False, high_host_readback_matches_basic_rom=True,
        strict_metadata_rejection_preserved=True, original_deployment_restored=True,
        owned_upload_cleanup_complete=True, frozen_inputs=len(manifest),
        vice=vice_stats, vice_shared=shared_stats, hardware=hw_stats)


if __name__ == '__main__':
    if '--record' not in sys.argv:
        seal = {}
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            assert name not in seal and not Path(name).is_absolute() and '..' not in Path(name).parts
            assert sha((ROOT/name).read_bytes()) == digest, name
            seal[name] = digest
        assert set(seal) == {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}
    result = audit()
    if '--record' in sys.argv:
        (ROOT/'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    else:
        assert result == read_json('audit.json')
    print(json.dumps(result, indent=2))
