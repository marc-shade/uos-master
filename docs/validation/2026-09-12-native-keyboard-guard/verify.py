#!/usr/bin/env python3
"""Offline audit of native keyboard qualification; no hardware operations."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sha = lambda raw: hashlib.sha256(raw).hexdigest()
read_json = lambda name: json.loads((ROOT/name).read_text())
from capture_audit import captures


def audit():
    source = ROOT/'inputs'
    manifest = read_json('frozen-inputs.json')
    assert len(manifest) == 391
    assert set(manifest) == {str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
    for name, digest in manifest.items():
        assert sha((source/name).read_bytes()) == digest, name
    base = read_json('base-inputs.json')
    assert len(base) == 386
    assert set(manifest)-set(base) == {'src/native/keyboard.inc', 'tests/ci_native_keyboard.py',
        'tests/ci_native_keyboard_iec.py', 'tests/vice_keyboard.py', 'docs/NATIVE-KEYBOARD.md'}
    for name, digest in base.items():
        if name.endswith('.prg') and not name.endswith('/uos128.prg'):
            assert manifest[name] == digest, ('app image changed', name)
    provenance = read_json('provenance.json')
    assert provenance['base_commit'] == (ROOT/'base-commit.txt').read_text().strip() == '2eba45b3cb5fd6cfe93639759aec0c6a0795f9f3'
    assert not provenance['physical_hardware_io'] and not provenance['authenticated_claude_session']
    assert provenance['vice_keyboard_terminal_exit'] == provenance['vice_suite_terminal_exit'] == 0
    rebuild = read_json('main-rebuild.json')
    assert rebuild['passed'] and len(rebuild['images']) == 19
    assert all(manifest[name] == digest for name, digest in rebuild['images'].items())
    for prefix in ('native', 'native-desktop'):
        layout = read_json('inputs/target/'+prefix+'/layout.json')
        assert layout['managed_pages'] == 426
        assert layout['main_start'] < layout['keycheck_start'] < layout['keycheck_end'] <= layout['main_end'] <= 0x3800
        assert layout['query_end'] == layout['keyboard_start'] < layout['keyboard_end'] <= 0x4bfc
    cpu_counts = {'keyboard-cpu-qualified.json': 10, 'keyboard-startup.json': 4,
        'keyboard-claude.json': 11, 'keyboard-relocation.json': 9, 'keyboard-capture.json': 48,
        'keyboard-running-layout.json': 7, 'keyboard-desktop-cpu.json': 24}
    for name, count in cpu_counts.items():
        report = read_json(name)
        assert report['passed'] and len(report['cases']) == count, name
    cpu = read_json('keyboard-cpu-qualified.json')
    assert not cpu['physical_hardware_io']
    for prefix, digest in cpu['images'].items():
        assert digest == manifest['target/'+prefix+'/uos128.prg']

    sys.path[:0] = [str(source), str(source/'apps/claude/host')]
    from native_running_layout import RunningLayout
    from launcher_scene import surface, console
    from native_controls_check import panel_screen
    import font
    import petscii
    running = RunningLayout(source, image_dir=source/'target/native-desktop')
    def resident(folder, prefix):
        observed = {region: (folder/(prefix+'-'+region+'.bin')).read_bytes() for region in running.regions}
        result = running.compare(observed)
        assert result['passed']
        assert result == json.loads((folder/(prefix+'-layout.json')).read_text())
        return result['immutable_bytes']

    keyboard = read_json('vice-keyboard/report.json')
    assert keyboard['passed'] and not keyboard['physical_hardware_io']
    assert keyboard['kernel_sha256'] == manifest['target/native-desktop/uos128.prg']
    key_stats = captures(ROOT/'vice-keyboard', keyboard)
    assert not key_stats['rejected'] and key_stats['captures'] == 15
    assert keyboard['resident']['passed']
    resident(ROOT/'vice-keyboard', 'keyboard-resident')
    assert (ROOT/'vice-keyboard/keyboard-surface.bin').read_bytes() == surface(1)
    assert (ROOT/'vice-keyboard/keyboard-vdc.bin').read_bytes() == console(80,1)
    expected = [('Down',0,1,0,0,17,True), ('Up',1,2,0,0,145,True),
                ('j',2,2,0,1,145,True), ('j',2,3,1,1,148,False),
                ('j',3,3,1,2,148,True), ('Down',3,4,2,2,17,True)]
    assert [tuple(row[k] for k in ('key','keys_before','keys_after','rejects_before','rejects_after','last_key','guard_enabled')) for row in keyboard['events']] == expected
    metadata = keyboard['captures'][0]['borrower_checks']['metadata']
    raw = (ROOT/'vice-keyboard'/metadata['before_file']).read_bytes()
    assert raw[0x3d1c-metadata['address']:0x3d20-metadata['address']] == b'\xad\xc6\x02\0'

    suite = read_json('vice-suite/report.json')
    assert suite['passed'] and suite['native_checks_passed'] and suite['all_host_processes_terminal']
    assert not suite['physical_hardware_io']
    for name, digest in suite['images'].items():
        assert manifest['target/native-desktop/'+name] == digest
    assert sha((ROOT/'vice-suite/suite.d64').read_bytes()) == suite['images']['uos128.d64']
    suite_stats = captures(ROOT/'vice-suite', dict(suite, captures=suite['captures']+suite['mode_captures']))
    assert suite_stats['captures'] == 135 and not suite_stats['rejected']
    assert [row['selected'] for row in suite['desktops']] == [0,1,0,1,2,3,4,4]
    for row in suite['desktops']:
        assert (ROOT/'vice-suite'/(row['label']+'-surface.bin')).read_bytes() == surface(row['selected'])
        assert (ROOT/'vice-suite'/(row['label']+'-vdc.bin')).read_bytes() == console(80,row['selected'])
    resident(ROOT/'vice-suite','resident-boot')
    resident(ROOT/'vice-suite','resident-return')
    heap = (ROOT/'vice-suite/final-native-heap.bin').read_bytes()
    assert heap[0x50:0xff] == bytes(175) and heap[0x104:0x1ff] == bytes(251)
    assert all(heap[0x400+i*8] == 0 for i in range(32))
    apps = suite['suite_apps']
    assert apps['passed'] and len(apps['ultimate']) == 5 and len(apps['claude']) == 2
    for panel in apps['ultimate']:
        for suffix, columns in (('-vic',40),('-vdc',80)):
            assert (ROOT/'vice-suite'/(panel['label']+suffix+'.bin')).read_bytes() == panel_screen(columns,panel['body'])
    def terminal(typed):
        text = ['UOS CLAUDE LINK READY','❯ ✳ ⏺','Keyboard, glyphs and return test']
        text += ['KEY RECEIVED: p','ESCAPE RECEIVED'] if typed else []
        result = bytearray(b' '*2000)
        for index, line in enumerate(text):
            data = bytes(petscii.to_screen_code(c) for c in line)
            result[80*index:80*index+len(data)] = data
        return result
    for row, outcome in zip(apps['claude'], (2,0)):
        label = row['label']
        assert row['passed'] and row['close_outcome'] == outcome and row['host_process_terminal']
        assert row['host_exit_code'] == row['host_final_code'] == 0
        assert any('tests/fixtures/claude-session.py' in part for part in row['bridge_command'])
        assert (ROOT/'vice-suite'/(label+'-close-outcome.bin')).read_bytes() == bytes([outcome])
        assert (ROOT/'vice-suite'/(label+'-connected-mirror.bin')).read_bytes() == terminal(False)
        for name, size in (('font',4096),('nmi',2),('gate',2)):
            before = (ROOT/'vice-suite'/('claude-'+name+'-before.bin')).read_bytes()
            assert len(before) == size
            assert before == (ROOT/'vice-suite'/(label+'-'+name+'-after.bin')).read_bytes()
        counters = row['counters']
        assert counters['_rxDropped'] == counters['_rxOverruns'] == 0
        assert counters['_nmiCount'] >= counters['_rxCount'] >= 3+10*len(list(font.definitions()))
        for name, value in counters.items():
            assert int.from_bytes((ROOT/'vice-suite'/(label+name+'.bin')).read_bytes(),'little') == value
    for suffix in ('-typed-mirror','-help-mirror','-vdc'):
        assert (ROOT/'vice-suite'/('claude-f8'+suffix+'.bin')).read_bytes() == terminal(True)
    custom = (ROOT/'vice-suite/claude-f8-font.bin').read_bytes()
    for code, bitmap in font.definitions():
        assert custom[16*code:16*code+16] == bytes(bitmap)+bytes(8)
    for folder in ('numpad-fixture','resource-fixture','missing-bridge-dependency'):
        assert not read_json('preliminary/'+folder+'/report.json')['passed']
    return dict(passed=True, physical_hardware_io=False, physical_input_source_established=False,
        frozen_inputs=len(manifest), byte_identical_images=19, unchanged_app_images=True,
        cpu_cases=cpu_counts, vice_keyboard=key_stats, vice_suite=suite_stats,
        controlled_joystick_insert_reproduced=True, guard_rejections_counted=True,
        final_free_pages=426, authenticated_claude_session=False)


if __name__ == '__main__':
    if '--record' not in sys.argv:
        seal = {}
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ',1)
            assert name not in seal and not Path(name).is_absolute() and '..' not in Path(name).parts
            assert sha((ROOT/name).read_bytes()) == digest, name
            seal[name] = digest
        assert set(seal) == {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}
    result = audit()
    if '--record' in sys.argv:
        (ROOT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    else:
        assert result == read_json('audit.json')
    print(json.dumps(result,indent=2))
