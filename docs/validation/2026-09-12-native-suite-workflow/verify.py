#!/usr/bin/env python3
"""Recheck retained suite bytes and distinguish the rejected physical capture."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sha = lambda data: hashlib.sha256(data).hexdigest()
read_json = lambda name: json.loads((ROOT/name).read_text())


def capture_audit(folder, report):
    captures = report['captures'] + report['mode_captures']
    chunks = total = borrowers = 0
    for capture in captures:
        payload = bytearray()
        for chunk in capture['chunks']:
            status = (folder/chunk['status_file']).read_bytes()
            data = (folder/chunk['payload_file']).read_bytes()
            assert sha(status) == chunk['status_sha256'] and len(status) == 12
            assert status[0] == chunk['code'] == 1
            assert not status[9] & 0x40 and status[10] & 15 == 4
            assert status[11] in (0, 0x0e)
            assert sha(data) == chunk['payload_sha256'] and len(data) == chunk['count']
            payload.extend(data)
            chunks += 1
        assert len(payload) == capture['count']
        assert payload == (folder/(capture['label']+'.bin')).read_bytes()
        total += len(payload)
        differences = []
        for name, borrower in capture['borrower_checks'].items():
            before = (folder/borrower['before_file']).read_bytes()
            after = (folder/borrower['after_file']).read_bytes()
            assert len(before) == len(after) == borrower['bytes']
            assert sha(before) == borrower['before_sha256']
            assert sha(after) == borrower['after_sha256']
            offsets = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
            assert offsets == borrower['different_offsets']
            assert borrower['matches'] == (before == after)
            assert borrower['changes'] == [dict(address=borrower['address']+i,
                before=before[i], after=after[i], field=change['field'])
                for i, change in zip(offsets, borrower['changes'])]
            assert len(borrower['changes']) == len(offsets)
            if offsets:
                differences.append(name)
            borrowers += 1
        assert capture['restored'] == (not differences)
        assert [item['region'] for item in capture['borrower_failures']] == differences
    assert all(batch['pause_acknowledged'] and batch['resume_acknowledged']
               for batch in report['paused_capture_batches'])
    return dict(captures=len(captures), chunks=chunks, payload_bytes=total, borrower_pairs=borrowers)


def audit():
    source = ROOT/'inputs'
    manifest = read_json('frozen-inputs.json')
    assert len(manifest) == 387
    for name, digest in manifest.items():
        assert sha((source/name).read_bytes()) == digest, name
    assert set(manifest) == {str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
    base = read_json('base-inputs.json')
    assert len(base) == 383
    changed = [name for name, digest in base.items() if digest != manifest[name]]
    assert changed == ['hw_native_desktop_check.py']
    assert set(manifest)-set(base) == {'native_suite_workflow.py', 'tests/ci_native_suite_iec.py',
                                     'tests/ci_native_suite_oracles.py', 'run-hardware.py'}
    provenance = read_json('provenance.json')
    assert provenance['base_commit'] == (ROOT/'base-commit.txt').read_text().strip()
    assert not provenance['physical_claude_launched'] and not provenance['authenticated_claude_session']
    assert provenance['main_vice_terminal_exit_code'] == provenance['main_oracles_terminal_exit_code'] == 0
    for name, digest in provenance['images'].items():
        assert sha((source/'target/native-desktop'/name).read_bytes()) == digest

    sys.path[:0] = [str(source), str(source/'apps/claude/host')]
    from launcher_scene import surface, console
    from native_controls_check import panel_screen
    from native_running_layout import RunningLayout
    import font
    import petscii
    layout = RunningLayout(source, image_dir=source/'target/native-desktop')

    vice = read_json('vice/report.json')
    assert vice['passed'] and vice['native_checks_passed'] and vice['all_host_processes_terminal']
    assert not vice['physical_hardware_io'] and vice['images'] == provenance['images']
    assert sha((ROOT/'vice/suite.d64').read_bytes()) == vice['images']['uos128.d64']
    vice_stats = capture_audit(ROOT/'vice', vice)
    assert all(c['restored'] for c in vice['captures']+vice['mode_captures'])
    assert [row['selected'] for row in vice['desktops']] == [0, 1, 0, 1, 2, 3, 4, 4]
    for row in vice['desktops']:
        actual = (ROOT/'vice'/(row['label']+'-surface.bin')).read_bytes()
        assert actual == surface(row['selected']) and sha(actual) == row['surface_sha256']
        assert (ROOT/'vice'/(row['label']+'-vdc.bin')).read_bytes() == console(80, row['selected'])
    for prefix in ('resident-boot', 'resident-return'):
        observed = {region: (ROOT/'vice'/(prefix+'-'+region+'.bin')).read_bytes() for region in layout.regions}
        result = layout.compare(observed)
        assert result['passed'] and result == read_json('vice/'+prefix+'-layout.json')
    heap = (ROOT/'vice/final-native-heap.bin').read_bytes()
    assert heap[0x50:0xff] == bytes(175) and heap[0x104:0x1ff] == bytes(251)
    assert all(heap[0x400+i*8] == 0 for i in range(32))

    suite = vice['suite_apps']
    assert suite['passed'] and len(suite['ultimate']) == 5 and len(suite['claude']) == 2
    for panel in suite['ultimate']:
        for suffix, columns in (('-vic', 40), ('-vdc', 80)):
            assert (ROOT/'vice'/(panel['label']+suffix+'.bin')).read_bytes() == panel_screen(columns, panel['body'])
    initial = ['UOS CLAUDE LINK READY', '❯ ✳ ⏺', 'Keyboard, glyphs and return test']
    def terminal(typed):
        expected = bytearray(b' '*2000)
        for row, line in enumerate(initial+(['KEY RECEIVED: p', 'ESCAPE RECEIVED'] if typed else [])):
            codes = bytes(petscii.to_screen_code(c) for c in line)
            expected[row*80:row*80+len(codes)] = codes
        return expected
    for row, outcome in zip(suite['claude'], (2, 0)):
        label = row['label']
        assert row['passed'] and row['close_outcome'] == outcome
        assert row['host_exit_code'] == row['host_final_code'] == 0 and row['host_process_terminal']
        assert (ROOT/'vice'/(label+'-close-outcome.bin')).read_bytes() == bytes([outcome])
        assert '--no-panel' in row['bridge_command']
        assert any('tests/fixtures/claude-session.py' in part for part in row['bridge_command'])
        assert (ROOT/'vice'/(label+'-connected-mirror.bin')).read_bytes() == terminal(False)
        for name, size in (('font', 4096), ('nmi', 2), ('gate', 2)):
            before = (ROOT/'vice'/('claude-'+name+'-before.bin')).read_bytes()
            assert len(before) == size
            assert before == (ROOT/'vice'/(label+'-'+name+'-after.bin')).read_bytes()
        counters = row['counters']
        assert counters['_rxDropped'] == counters['_rxOverruns'] == 0
        assert counters['_nmiCount'] >= counters['_rxCount'] >= 3+10*len(list(font.definitions()))
        for name, value in counters.items():
            assert int.from_bytes((ROOT/'vice'/(label+name+'.bin')).read_bytes(), 'little') == value
    for suffix in ('-typed-mirror', '-help-mirror', '-vdc'):
        assert (ROOT/'vice'/('claude-f8'+suffix+'.bin')).read_bytes() == terminal(True)
    during = (ROOT/'vice/claude-f8-font.bin').read_bytes()
    for code, bitmap in font.definitions():
        assert during[16*code:16*code+16] == bytes(bitmap)+bytes(8)
    for name in ('suite-oracles.json', 'main-oracles.json'):
        report = read_json(name)
        assert report['passed'] and not report['physical_hardware_io'] and len(report['cases']) == 3

    hardware = read_json('hardware-failed/report.json')
    attempt = read_json('physical-attempt.json')
    assert not hardware['passed'] and not attempt['passed'] and hardware['physical_hardware_io']
    assert attempt['process_finished'] and attempt['all_host_processes_terminal']
    assert hardware['native_error'] == attempt['error']['message']
    assert not hardware['events'] and not hardware['desktops'] and not hardware['screens']
    assert hardware['suite_apps'] == dict(ultimate=[], claude=[])
    assert not hardware['uncertain_host_writes'] and not hardware.get('cleanup_error')
    assert all(hardware[k] for k in ('legacy_desktop_restored', 'dos_paths_restored',
                                    'controls_restored', 'cleanup_complete', 'images_unchanged'))
    hardware_stats = capture_audit(ROOT/'hardware-failed', hardware)
    assert len(hardware['captures']) == 5 and not hardware['mode_captures']
    assert all(c['restored'] for c in hardware['captures'][:-1])
    failed = hardware['captures'][-1]
    assert failed['label'] == 'resident-boot-main-0fa0' and not failed['restored']
    assert failed['borrower_checks']['output']['matches'] and failed['borrower_checks']['scratch']['matches']
    assert [item['region'] for item in failed['borrower_failures']] == ['metadata', 'resident']
    borrowers = failed['borrower_checks']
    observation = failed['input_observation']
    assert (observation['keys_before'], observation['keys_after'],
            observation['last_key_before'], observation['last_key_after']) == (0, 3, 0, 17)
    meta_changes = borrowers['metadata']['changes']
    assert [c['address'] for c in meta_changes] == [0x3d08, 0x3d09, 0x3d11, 0x3d12, 0x3d13, 0x3d15, 0x3d2f]
    assert meta_changes[-1]['before'] == 0 and meta_changes[-1]['after'] == 3
    resident_changes = borrowers['resident']['changes']
    assert [c['address'] for c in resident_changes] == [0x1719, 0x172b, 0x17cb, 0x17cd, 0x17cf]
    classified = [dict(c, declaration=layout.mutable[c['address']]) for c in resident_changes]
    low_start, low_image = layout.regions['low']
    for side in ('before', 'after'):
        raw = (ROOT/'hardware-failed'/borrowers['resident'][side+'_file']).read_bytes()
        assert all(a == b for i, (a, b) in enumerate(zip(raw, low_image)) if low_start+i not in layout.mutable)
    captured_code_bytes = 0
    for capture in hardware['captures']:
        raw = (ROOT/'hardware-failed'/(capture['label']+'.bin')).read_bytes()
        start = capture['address']
        for address, value in enumerate(raw, start):
            if address not in layout.mutable:
                region_start, expected = next((a, data) for a, data in layout.regions.values()
                                             if a <= address < a+len(data))
                assert value == expected[address-region_start], hex(address)
                captured_code_bytes += 1
    receipts = hardware['ram_write_receipts']
    assert all(r['range_acknowledged'] and r['status'] == 200 and not r['replayed'] for r in receipts)
    for row in receipts:
        start, end = row['address'], row['address']+row['bytes']
        assert all(end <= a or start >= b for a, b in ((0xd0, 0xd3), (0x34a, 0x354)))
    assert not any(r['path'].startswith('/v1/configs/') for r in hardware['host_control_requests'])
    owned = {'/Temp/temp00B0': sha((ROOT/'hardware-failed/native.d64').read_bytes()),
             '/Temp/uos-hardware-native-desktop-40g5lqpe-restore.prg':
             sha((ROOT/'hardware-failed/restore-loader-readback.bin').read_bytes())}
    assert set(owned) == set(hardware['temporary_readbacks'])
    for path, digest in owned.items():
        assert hardware['temporary_readbacks'][path]['sha256'] == digest
    assert {r['path'] for r in hardware['temporary_deletions'] if r['confirmed']} == set(owned)
    final = read_json('modem-final.json')
    assert final['passed'] and final['method'] == 'GET' and not final['mutations']
    assert final['before'] == final['after'] == hardware['modem_settings_before']
    for index, item in enumerate(final['after']):
        reply = read_json(f'modem-final-{index}.json')
        assert reply['errors'] == [] and reply['Modem Settings'][item]['current'] == final['after'][item]
    return dict(passed=True, physical_suite_passed=False, physical_claude_launched=False,
        input_source='Unestablished; three consumed inputs, last cursor down. No scripted input or buffer write.',
        changed_resident_bytes=classified, physical_captured_immutable_bytes=captured_code_bytes,
        vice=vice_stats, hardware_failed=hardware_stats, acknowledged_ram_writes=len(receipts),
        original_deployment_restored=True, owned_upload_cleanup_complete=True,
        final_modem_settings_match=True)


if __name__ == '__main__':
    if '--record' not in sys.argv:
        seal = {}
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            assert name not in seal and not Path(name).is_absolute() and '..' not in Path(name).parts
            seal[name] = digest
            assert sha((ROOT/name).read_bytes()) == digest, name
        assert set(seal) == {str(p.relative_to(ROOT)) for p in ROOT.rglob('*')
                             if p.is_file() and p.name != 'SHA256SUMS'}
    result = audit()
    if '--record' in sys.argv:
        (ROOT/'audit.json').write_text(json.dumps(result, indent=2)+'\n')
    else:
        assert result == read_json('audit.json')
    print(json.dumps(result, indent=2))
