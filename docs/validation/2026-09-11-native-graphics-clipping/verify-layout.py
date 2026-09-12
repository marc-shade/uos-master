#!/usr/bin/env python3
"""Audit retained layout evidence and rebuild each app-bound renderer."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ARCHIVE = Path(__file__).resolve().parent
BASE = ARCHIVE.parent / '2026-09-11-native-display-lifetime'
read = lambda path: json.loads(path.read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
parser = argparse.ArgumentParser()
parser.add_argument('--record', action='store_true')
args = parser.parse_args()
context = read(ARCHIVE / 'candidate-context.json')
assert sha((BASE / 'SHA256SUMS').read_bytes()) == context['base_manifest_sha256']
frozen = read(BASE / 'frozen.json')
for name, digest in frozen.items():
    assert sha((BASE / 'frozen' / name).read_bytes()) == digest, name
sys.path.insert(0, str(BASE / 'frozen'))
from native_image import validate as validate_app
from native_module import seal, validate

parent = (BASE / 'frozen/target/native/editor.prg').read_bytes()
assert validate_app(parent)['pages'] == 79
raw = (b'0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n' * 1800)[:66053]
edited = raw[:65537] + b'C12' + raw[65537:]
labels = [
    'large-document-with-reserved-surface', 'graphics-module-visible',
    'picker-ordinal-256-with-document-and-surface',
    'verified-save-with-surface-retained', 'graphics-reloaded-after-picker-and-save',
    'fragmented-surface-reservation-rejected-with-document-intact',
]
variants = {}
for name, directory, inputs, size, instructions in [
    ('before-bands', ARCHIVE / 'history/before-bands', context['history_inputs']['before-bands'], 2768, 17729767),
    ('bands', ARCHIVE / 'history/bands', context['history_inputs']['bands'], 2903, 4738938),
    ('clipping', ARCHIVE / 'source', context['source_inputs'], 3256, 5197786),
]:
    for filename, digest in inputs.items():
        assert sha((directory / filename).read_bytes()) == digest, (name, filename)
    module = (directory / 'module/GRAPHICS.PRG').read_bytes()
    assert len(module) == size
    manifest = validate(module, parent)
    assert manifest == read(directory / 'module/build.json')
    report = read(directory / 'graphics/layout-report.json')
    assert report['passed'] and not report['hardware_io']
    assert report['complete_lifecycle_passed'] and report['fragmented_reservation_rejection_passed']
    assert report['kernel_sha256'] == context['kernel_sha256']
    assert report['editor_sha256'] == sha(parent) and report['module_sha256'] == sha(module)
    assert [row['label'] for row in report['snapshots']] == labels
    for index, row in enumerate(report['snapshots']):
        expected = raw if index == 5 else edited
        assert row['document_bytes'] == len(expected) and row['document_sha256'] == sha(expected)
        assert row['document_state']['length'] == len(expected)
        assert row['document_state']['capacity'] == 17 * 4096
        assert row['document_state']['chunks'] == 17 and row['document_state']['fault'] == 0
        records = row['records']
        assert len({record['handle'] for record in records}) == len(records)
        assert sum(record['pages'] for record in records) + sum(row['free'][:2]) == 426
        assert len(records) + row['free'][2] == 32
        occupied = set()
        for record in records:
            for page in range(record['page'], record['page'] + record['pages']):
                slot = record['bank'], page
                assert slot not in occupied
                occupied.add(slot)
        assert any(record['owner'] == 32 and record['bank'] == 0 and record['page'] == 0x60 and record['pages'] == 79 for record in records)
        if index < 5:
            assert any(record['owner'] == 32 and record['bank'] == 0 and record['page'] == 0xc0 and record['pages'] == 36 for record in records)
            assert row['free'] == ([28, 3, 11] if index == 2 else [28, 11, 13])
        else:
            assert row['free'] == [63, 11, 13]
            assert any(record['owner'] == 77 and record['bank'] == 0 and record['page'] == 0xd0 and record['pages'] == 1 for record in records)
    calls = report['calls']
    assert [(row['entry'], row['error']) for row in calls] == [(0x1c5f, 0), (0x1c62, 0), (0x1c6b, 0), (0x1c62, 4), (0x1c5f, 0), (0x1c62, 0)]
    assert calls[1]['instructions'] == calls[5]['instructions'] == instructions
    with tempfile.TemporaryDirectory(prefix='uos-layout-rebuild-') as temporary:
        clean = Path(temporary)
        shutil.copytree(directory / 'module', clean / 'module')
        subprocess.run(['64tass', '-a', '-B', str(clean / 'module/graphics.asm'), '-o', str(clean / 'module/raw.prg')], check=True, capture_output=True)
        assert seal((clean / 'module/raw.prg').read_bytes(), parent) == module
    variants[name] = dict(frozen_inputs=len(inputs), module=manifest, module_sha256=sha(module),
                          scene_instructions=instructions, peak_free_pages=31, snapshots=6)

before = ARCHIVE / 'history/before-bands'
bands = ARCHIVE / 'history/bands'
for name in ('client/expected-surface.bin', 'module/text-commands.inc'):
    assert (before / name).read_bytes() == (bands / name).read_bytes()
assert read(before / 'client/build.json')['operations'] == read(bands / 'client/build.json')['operations']
first = read(before / 'first-attempt/layout-report.json')
assert not first['passed'] and first['error'] == "('service did not return', '0x1771')"
assert first['module_sha256'] == variants['before-bands']['module_sha256']
assert len(first['snapshots']) == len(first['calls']) == 1
assert 'range(15000000)' in (before / 'first-attempt/ci_native_graphics_layout.py').read_text()
assert 'range(60000000)' in (before / 'tests/ci_native_graphics_layout.py').read_text()
result = dict(passed=True, hardware_io=False, variants=variants,
              concurrent_cpu_model_only=True, heap_pages=426, peak_allocated_pages=395,
              same_scene_instruction_reduction=17729767 / 4738938,
              final_clipping_scene_has_additional_operations=True,
              retained_initial_instruction_bound_failure=True)
if args.record:
    (ARCHIVE / 'layout-verification.json').write_text(json.dumps(result, indent=2) + '\n')
else:
    assert result == read(ARCHIVE / 'layout-verification.json')
print('PASS: three rebuilt editor modules; complete document/layout evidence; 31 pages free at peak; retained initial instruction-limit failure')
