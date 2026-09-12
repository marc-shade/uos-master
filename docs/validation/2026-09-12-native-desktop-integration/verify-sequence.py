#!/usr/bin/env python3
"""Audit the shared native desktop sequence from VICE or physical captures."""
import argparse
import ast
import subprocess
import tempfile
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ARCHIVE = Path(__file__).resolve().parent
INPUTS = ARCHIVE/'inputs'
sys.path[:0] = [str(INPUTS), str(INPUTS/'tests')]
from launcher_scene import surface, console
from native_mode_capture import FIELDS
from native_capture import expected_screen, calculator_screen
from native_editor_check import editor_screen
from native_browser_check import browser_screen, disk_records
from native_running_layout import RunningLayout

read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
parser = argparse.ArgumentParser()
parser.add_argument('--hardware', action='store_true')
parser.add_argument('--record', action='store_true')
args = parser.parse_args()
assert not args.hardware, 'Physical qualification is retained in the separate hardware archive'
work = ARCHIVE/'emulator/shared-sequence'
outer = read(work/'report.json')
report = outer if args.hardware else outer['hardware_sequence']
assert outer['passed'] and outer['physical_hardware_io'] == args.hardware
assert report['native_checks_passed'] and 'native_error' not in report
context = read(ARCHIVE/'candidate-context.json')
disk = work/('native.d64' if args.hardware else 'desktop.d64')
assert sha(disk) == context['disk_sha256']
records = disk_records(disk.read_bytes())
layout = RunningLayout(INPUTS, image_dir=INPUTS/'target/native-desktop')
for label, field in [('resident-boot', 'resident_boot'), ('resident-return', 'resident_return')]:
    observations = {}
    for name, (start, expected) in layout.regions.items():
        data = (work/f'{label}-{name}.bin').read_bytes()
        assert data == b''.join((work/f'{label}-{name}-{offset:04x}.bin').read_bytes() for offset in range(0, len(expected), 2000))
        observations[name] = data
    audit = layout.compare(observations)
    assert audit['passed'] and audit == report[field] == read(work/f'{label}-layout.json')
assert [row['label'] for row in report['desktops']] == [
    'desktop-boot', 'desktop-editor-selected', 'desktop-after-calculator', 'desktop-after-editor', 'desktop-after-files']
for row in report['desktops']:
    label, selected = row['label'], row['selected']
    expected = surface(selected)
    assert selected == int(label == 'desktop-editor-selected')
    assert (work/f'{label}-surface.bin').read_bytes() == expected
    assert b''.join((work/f'{label}-surface-{offset:04x}.bin').read_bytes() for offset in range(0, 9216, 2000)) == expected
    assert row['surface_sha256'] == hashlib.sha256(expected).hexdigest()
    assert (work/f'{label}-vdc.bin').read_bytes() == console(80, selected)
    assert row['irq_advanced'] and row['surface_bytes'] == 9216 and row['vdc_bytes'] == 2000
    regs = dict(zip(FIELDS, (work/f'{label}-mode.bin').read_bytes()))
    assert regs == row['registers'] and len(regs) == 15
    assert regs['vic_d011']&0x7f == 0x3b and regs['vic_d016']&0x1f == 8 and regs['vic_d018']&0xfe == 0x80
    assert regs['vic_irq_mask']&15 == 1 and regs['vic_sprites'] == 0
    assert regs['cia2_port']&3 == 0 and regs['cia2_ddr']&3 == 3
    assert regs['foreground_mmu'] == 0x0e and not regs['mode']&0x40 and regs['common']&15 == 4
    assert regs['cpu_ddr'] == 0x2f and regs['cpu_port'] == 0x75 and regs['text_graphics'] == 255
    assert regs['text_display']&128 and not regs['cpu_speed']&1
    heap = (work/f'{label}-heap.bin').read_bytes()
    assert heap[0x50:0xff].count(0)+heap[0x104:0x1ff].count(0) == 372
    handles = [heap[0x400+i*8:0x408+i*8] for i in range(32) if heap[0x400+i*8]]
    assert len(handles) == 2 and {r[:4] for r in handles} == {bytes([32, 0, 0x60, 18]), bytes([32, 0, 0xc0, 36])}
assert report['screens'] == ['calculator-new', 'calculator-result', 'editor-new', 'editor-typed', 'files', 'workspace-returned']
for label in report['screens']:
    for columns, suffix in [(40, 'vic'), (80, 'vdc')]:
        if label == 'calculator-new': expected = calculator_screen(columns, '0', [])
        elif label == 'calculator-result': expected = calculator_screen(columns, '42', ['42'])
        elif label == 'editor-new': expected = editor_screen(columns, b'', 0)
        elif label == 'editor-typed': expected = editor_screen(columns, b'C128', 4, dirty=True)
        elif label == 'files': expected = browser_screen(columns, records)
        elif label == 'workspace-returned': expected = expected_screen(columns, 0)
        assert (work/f'{label}-{suffix}.bin').read_bytes() == expected
heap = (work/'final-native-heap.bin').read_bytes()
assert heap[0x50:0xff] == bytes(175) and heap[0x104:0x1ff] == bytes(251)
assert all(heap[0x400+i*8] == 0 for i in range(32))
assert bytes(row['key'] for row in report['events']) == b'\tC12+30=\x1bEC128\x1bYF\x1b\x1b'
chunks = count = 0
for capture in report['captures']:
    assert capture['restored'] and capture['address_resyncs'] == 0
    assert capture['probe_sha256'] == sha(work/'native-read.prg')
    assert len((work/(capture['label']+'.bin')).read_bytes()) == capture['count']
    offset = 0
    for chunk in capture['chunks']:
        assert chunk['address'] == capture['address']+offset and chunk['code'] == 1
        assert 1 <= chunk['count'] <= 512 and chunk['address_resyncs'] == 0
        assert chunk['foreground_mmu'] == 0x0e and chunk['common_register']&15 == 4 and not chunk['mode_register']&0x40
        offset += chunk['count']
    assert offset == capture['count']
    chunks += len(capture['chunks'])
    count += capture['count']
assert len(report['captures']) == 60 and chunks == 209 and count == 101184
assert len(report['mode_captures']) == 6
assert [r['label'] for r in report['mode_captures']] == [r['label']+'-mode' for r in report['desktops']]+['workspace-returned-mode']
for row in report['mode_captures']:
    assert row['source'] == 'fixed CPU mode-register snapshot' and row['fields'] == list(FIELDS)
    assert row['restored'] and row['address_resyncs'] == 0
    assert row['probe_sha256'] == sha(work/'native-mode.prg')
    assert row['mode'] == row['bank'] == row['address'] == 0 and row['count'] == 15
    raw = (work/(row['label']+'.bin')).read_bytes()
    assert len(raw) == 15 and len(row['chunks']) == 1
    chunk = row['chunks'][0]
    assert chunk['address'] == 0 and chunk['count'] == 15 and chunk['code'] == 1 and chunk['address_resyncs'] == 0
    assert chunk['foreground_mmu'] == raw[0] == 14
    assert chunk['mode_register'] == raw[1] and not raw[1]&0x40
    assert chunk['common_register'] == raw[2] and raw[2]&15 == 4
final_mode = dict(zip(FIELDS, (work/'workspace-returned-mode.bin').read_bytes()))
assert final_mode == report['final_mode']
assert final_mode['cpu_ddr'] == 0x2f and final_mode['cpu_port'] == 0x73 and final_mode['text_graphics'] == 0
with tempfile.TemporaryDirectory(prefix='uos-desktop-mode-audit-') as temporary:
    for name in ('native-mode', 'native-read'):
        output = Path(temporary)/(name+'.prg')
        subprocess.run(['64tass','-a',str(INPUTS/'probes'/(name+'.asm')),'-o',str(output)],check=True,capture_output=True)
        assert output.read_bytes() == (work/(name+'.prg')).read_bytes()
if not args.hardware:
    used = work/'used-sources'
    for name in ('native_mode_capture.py','probes/native-mode.asm'):
        assert (used/name).read_bytes() == (INPUTS/name).read_bytes()
    def shared(path):
        source = path.read_text()
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'run_native_workflow')
        return ast.get_source_segment(source, node)
    assert shared(used/'hw_native_desktop_check.py') == shared(INPUTS/'hw_native_desktop_check.py')
    assert hashlib.sha256(shared(INPUTS/'hw_native_desktop_check.py').encode()).hexdigest() == context['shared_native_workflow_sha256']
result = dict(passed=True, physical_hardware_io=args.hardware, captures=66, irq_chunks=chunks+6,
              captured_bytes=count+90, mode_captures=6, mode_bytes=90, desktop_views=5, text_screen_pairs=6, events=19,
              immutable_kernel_bytes_per_audit=11971, full_native_heap_cleanup=True,
              cpu_observed_mode_registers=True, physical_video_pixels_captured=False)
if args.hardware:
    for field in ('legacy_desktop_restored', 'images_unchanged', 'dos_paths_restored', 'restore_prg_owned',
                  'controls_restored', 'restore_prg_verified_before_mounts'):
        assert report[field]
    assert not report['uncertain_host_writes'] and 'cleanup_error' not in report and 'legacy_restore_error' not in report
    images = {name: digest for name, digest in read(ARCHIVE/'input-manifest.json').items()
              if name.startswith('target/') and name.endswith(('.prg', '.d64'))}
    assert report['build'] == images
    def drives(label):
        data = read(work/f'drives-{label}.json')
        assert not data['errors']
        return {name: value for row in data['drives'] for name, value in row.items()}
    assert drives('before') == drives('restored') == drives('final')
    temporary = {report['native_disk_upload_path']: INPUTS/'target/native/uos128.d64',
                 report['restore_prg_path']: INPUTS/'target/uos.prg'}
    assert len(temporary) == 2 and set(report['temporary_readbacks']) == set(temporary)
    assert {row['path'] for row in report['temporary_deletions']} == set(temporary)
    assert all(row['started'] and row['confirmed'] for row in report['temporary_deletions'])
    for path, original in temporary.items():
        assert path != report['restore_disk_path']
        assert (work/('readback-'+Path(path).name+'.bin')).read_bytes() == original.read_bytes()
        assert report['temporary_readbacks'][path] == dict(path=path, bytes=original.stat().st_size, sha256=sha(original))
    result.update(original_deployment_restored=True, temporary_files_read_back_and_removed=2,
                  temporary_bytes=sum(p.stat().st_size for p in temporary.values()))
name = 'hardware-verification.json' if args.hardware else 'sequence-verification.json'
if args.record:
    (ARCHIVE/name).write_text(json.dumps(result, indent=2)+'\n')
else:
    assert result == read(ARCHIVE/name)
print('PASS: shared desktop sequence; 101,274 CPU-captured bytes, including six fixed mode snapshots; complete cleanup')
