#!/usr/bin/env python3
"""Recheck complete captured display/code bytes and observer restoration."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
ARCHIVE = Path(__file__).resolve().parent
INPUTS = ARCHIVE/'inputs'
sys.path[:0] = [str(INPUTS), str(INPUTS/'tests')]
from launcher_scene import surface, console
from native_capture import expected_screen, calculator_screen
from native_editor_check import editor_screen
from native_browser_check import browser_screen, disk_records
from native_running_layout import RunningLayout

read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
parser = argparse.ArgumentParser()
parser.add_argument('--record', action='store_true')
args = parser.parse_args()
context = read(ARCHIVE/'candidate-context.json')
layout = RunningLayout(INPUTS)
totals = dict(workflows=0, captures=0, irq_chunks=0, captured_bytes=0,
              surfaces=0, pixels=0, vdc_frames=0, fallback_frames=0, screen_pairs=0)
for name in ('cpu-observation', 'running-layout'):
    work = ARCHIVE/'emulator'/name
    report = read(work/'report.json')
    assert report['passed'] and not report['physical_hardware_io'] and 'error' not in report
    assert report['options']['desktop_boot'] and not report['options']['missing_desktop']
    assert report['kernel_sha256'] == sha(work/'uos128.prg') == context['kernel_sha256']
    assert report['disk_sha256'] == sha(work/'desktop.d64') == context['disk_sha256']
    assert sha(work/'desktop.prg') == context['desktop_sha256']
    assert sha(work/'files.prg') == context['files_sha256']
    observations = {row['label']: row for row in report['observations']}
    for label, observation in observations.items():
        for field, data in observation.items():
            if field != 'label':
                assert (work/f'{label}-{field}.bin').read_bytes() == bytes.fromhex(data)
    final = observations['final']
    heap = bytes.fromhex(final['heap'])
    assert heap[0x50:0xff] == bytes(175) and heap[0x104:0x1ff] == bytes(251)
    assert all(heap[0x400+i*8] == 0 for i in range(32))
    assert bytes.fromhex(final['app'])[0] == bytes.fromhex(final['app'])[3] == 0
    assert final['port'] == '2f73' and final['display_tag'] == '00'
    for row in report['desktops']:
        label, selected, error, fallback = (row[k] for k in ('label', 'selected', 'error', 'fallback'))
        assert (work/f'{label}-80.bin').read_bytes() == console(80, selected, error, fallback)
        totals['vdc_frames'] += 1
        obs = observations[label]
        heap = bytes.fromhex(obs['heap'])
        active = [(i+1, heap[0x400+i*8:0x408+i*8]) for i in range(32) if heap[0x400+i*8]]
        assert len(active) == 2
        assert any(r[:4] == bytes([32, 0, 0x60, 18]) for slot, r in active)
        if fallback:
            assert (work/f'{label}-40.bin').read_bytes() == console(40, selected, error, True)
            assert obs['port'] == '2f73' and obs['display_tag'] == '00'
            assert any(r[:4] == bytes([16, 0, 0xdf, 32]) for slot, r in active)
            totals['fallback_frames'] += 1
            continue
        assert obs['port'] == '2f75' and obs['display_tag'] != '00'
        assert any(r[:4] == bytes([32, 0, 0xc0, 36]) and slot == int(obs['display_tag'], 16) for slot, r in active)
        assert heap[0x50:0xff].count(0)+heap[0x104:0x1ff].count(0) == 372
        expected = surface(selected, error)
        assert (work/f'{label}-surface.bin').read_bytes() == expected
        raw = (work/f'{label}-display-get.bin').read_bytes()
        fields, = struct.unpack_from('<I', raw)
        width, height, xoff, yoff, innerw, innerh, bpp = struct.unpack_from('<6HB', raw, 4)
        length, = struct.unpack_from('<I', raw, 4+fields)
        pixels = raw[8+fields:]
        assert fields >= 13 and bpp == 8 and length == width*height
        assert length-len(pixels) == row['missing_canvas_tail_bytes'] and length-len(pixels) in (0, 4)
        x0, y0, w, h = row['rectangle']
        assert (w, h) == (320, 200) and 0 <= x0 <= width-w and 0 <= y0 <= height-h
        expected_pixels = bytearray()
        for y in range(200):
            for x in range(320):
                color = expected[8192+y//8*40+x//8]
                ink = expected[y//8*320+x//8*8+y%8] & (128 >> (x%8))
                expected_pixels.append(color >> 4 if ink else color & 15)
        actual = b''.join(pixels[(y0+y)*width+x0:(y0+y)*width+x0+320] for y in range(200))
        assert actual == expected_pixels
        totals['surfaces'] += 1
        totals['pixels'] += len(actual)
    records = disk_records((work/'desktop.d64').read_bytes())
    for label in report['screens']:
        for columns in (40, 80):
            if label in ('workspace-returned', 'workspace-all-free'):
                expected = expected_screen(columns, 0)
            elif label == 'workspace-owner-retained':
                heap = bytes.fromhex(observations['occupied-surface-fallback']['heap'])
                slot, rec = next((i+1, heap[0x400+i*8:0x408+i*8]) for i in range(32) if heap[0x400+i*8] == 16)
                expected = expected_screen(columns, 0, (143, 251), 31, bytes([slot])+rec[4:7])
            elif label == 'calculator-new':
                expected = calculator_screen(columns, '0', [])
            elif label == 'calculator-result':
                expected = calculator_screen(columns, '42', ['42'])
            elif label == 'editor-new':
                expected = editor_screen(columns, b'', 0)
            elif label in ('editor-typed', 'editor-kept', 'editor-discard-prompt'):
                expected = editor_screen(columns, b'Native desktop', 14, dirty=True, mode=5 if label == 'editor-discard-prompt' else 0)
            elif label == 'files':
                expected = browser_screen(columns, records)
            else:
                raise AssertionError(('unknown screen', label))
            assert (work/f'{label}-{columns}.bin').read_bytes() == expected
        totals['screen_pairs'] += 1
    for capture in report['captures']:
        assert capture['restored'] and capture['address_resyncs'] == 0
        assert capture['probe_sha256'] == sha(work/'native-read.prg')
        assert len((work/(capture['label']+'.bin')).read_bytes()) == capture['count']
        count = 0
        for chunk in capture['chunks']:
            assert chunk['address'] == capture['address']+count and chunk['code'] == 1
            assert 1 <= chunk['count'] <= 512 and chunk['address_resyncs'] == 0
            assert chunk['foreground_mmu'] == 0x0e and chunk['common_register'] & 15 == 4
            assert not chunk['mode_register'] & 0x40
            count += chunk['count']
        assert count == capture['count']
        totals['captures'] += 1
        totals['irq_chunks'] += len(capture['chunks'])
        totals['captured_bytes'] += count
    if name == 'cpu-observation':
        assert (work/'cpu-surface.bin').read_bytes() == surface()
        parts = b''.join((work/f'cpu-surface-{offset:04x}.bin').read_bytes() for offset in range(0, 9216, 2000))
        assert parts == surface()
        assert (work/'cpu-vdc.bin').read_bytes() == console(80)
        before, after = (observations[n] for n in ('before-cpu-observation', 'after-cpu-observation'))
        for field in ('app', 'heap', 'port', 'text', 'display_tag', 'keys'):
            assert before[field] == after[field]
        for at in (0x11, 0x15, 0x16, 0x18, 0x1a):
            mask = 0x7f if at == 0x11 else 255
            assert bytes.fromhex(before['vic'])[at]&mask == bytes.fromhex(after['vic'])[at]&mask
        assert before['jiffy'] != after['jiffy']
    else:
        for label, field in [('resident-boot', 'resident_boot'), ('resident-return', 'resident_return')]:
            captured = {}
            for region, (address, expected) in layout.regions.items():
                captured[region] = (work/f'{label}-{region}.bin').read_bytes()
                parts = b''.join((work/f'{label}-{region}-{offset:04x}.bin').read_bytes() for offset in range(0, len(expected), 2000))
                assert captured[region] == parts
            audit = layout.compare(captured)
            assert audit == report[field] == read(work/f'{label}-layout.json')
            assert audit['passed'] and audit['immutable_bytes'] == 11971 and audit['mutable_bytes'] == 1581
    totals['workflows'] += 1
assert totals == dict(workflows=2, captures=24, irq_chunks=81, captured_bytes=38320,
                      surfaces=12, pixels=768000, vdc_frames=14, fallback_frames=2, screen_pairs=11)
failure = read(ARCHIVE/'history/layout-initial/resident-boot-layout.json')
assert not failure['passed'] and len(failure['unexpected_changes']) == 7
assert all(row['address'] in layout.mutable for row in failure['unexpected_changes'])
assert failure['kernel_sha256'] == context['kernel_sha256']
result = dict(passed=True, physical_hardware_io=False, totals=totals,
              immutable_bytes_per_audit=11971, mutable_bytes_retained_per_audit=1581,
              complete_final_cleanup=True, initial_harness_failure_retained=True)
if args.record:
    (ARCHIVE/'observer-verification.json').write_text(json.dumps(result, indent=2)+'\n')
else:
    assert result == read(ARCHIVE/'observer-verification.json')
print('PASS: two observer workflows; 38,320 CPU-captured bytes; 768,000 pixels; exact code and final cleanup')
