#!/usr/bin/env python3
"""Audit partial native observations and cleanup without promoting a failed run."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
INPUTS = ROOT/'v2/inputs'
WORK = ROOT/'v2/hardware-failed'
sys.path[:0] = [str(INPUTS), str(INPUTS/'tests')]
from launcher_scene import surface, console
from native_capture import calculator_screen
from native_editor_check import editor_screen
from native_running_layout import RunningLayout
from native_mode_capture import FIELDS

read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
parser = argparse.ArgumentParser()
parser.add_argument('--record', action='store_true')
args = parser.parse_args()
report = read(WORK/'report.json')
assert not report['passed'] and report['physical_hardware_io'] and not report.get('native_checks_passed')
assert report['native_error'] == 'native heap changed during observation'
assert report['legacy_desktop_restored'] and report['images_unchanged']
assert not report['uncertain_host_writes'] and not report['host_connect_failures']
assert 'legacy_restore_error' not in report and 'cleanup_error' not in report
images = {n:h for n,h in read(ROOT/'v2/input-manifest.json').items() if n.startswith('target/') and n.endswith(('.prg','.d64'))}
assert report['build'] == images
layout = RunningLayout(INPUTS)
observations = {name:(WORK/f'resident-boot-{name}.bin').read_bytes() for name in layout.regions}
assert layout.compare(observations) == report['resident_boot'] == read(WORK/'resident-boot-layout.json')
assert report['resident_boot']['passed'] and report['resident_boot']['immutable_bytes'] == 11971
assert [r['label'] for r in report['desktops']] == ['desktop-boot','desktop-editor-selected','desktop-after-calculator']
for row in report['desktops']:
    label = row['label']; selected = int(label == 'desktop-editor-selected')
    expected = surface(selected)
    assert (WORK/(label+'-surface.bin')).read_bytes() == expected
    assert b''.join((WORK/f'{label}-surface-{offset:04x}.bin').read_bytes() for offset in range(0,9216,2000)) == expected
    assert (WORK/(label+'-vdc.bin')).read_bytes() == console(80,selected)
    regs = dict(zip(FIELDS,(WORK/(label+'-mode.bin')).read_bytes()))
    assert regs == row['registers'] and regs['cpu_ddr'] == 0x2f and regs['cpu_port'] == 0x75
    assert regs['foreground_mmu'] == 14 and regs['common']&15 == 4 and not regs['mode']&0x40
    assert regs['vic_d011']&0x7f == 0x3b and regs['vic_d016']&0x1f == 8 and regs['vic_d018']&0xfe == 0x80
    assert regs['vic_sprites'] == 0 and regs['vic_irq_mask']&15 == 1
    assert regs['cia2_port']&3 == 0 and regs['cia2_ddr']&3 == 3
    assert regs['text_graphics'] == 255 and regs['text_display']&128 and not regs['cpu_speed']&1
assert report['screens'] == ['calculator-new','calculator-result','editor-new','editor-typed']
for label in report['screens']:
    for columns,suffix in ((40,'vic'),(80,'vdc')):
        if label == 'calculator-new': expected = calculator_screen(columns,'0',[])
        elif label == 'calculator-result': expected = calculator_screen(columns,'42',['42'])
        elif label == 'editor-new': expected = editor_screen(columns,b'',0)
        else: expected = editor_screen(columns,b'C128',4,dirty=True)
        assert (WORK/(label+'-'+suffix+'.bin')).read_bytes() == expected
for offset in range(0,8000,2000):
    assert (WORK/f'desktop-after-editor-surface-{offset:04x}.bin').read_bytes() == surface()[offset:offset+2000]
assert not (WORK/'desktop-after-editor-surface.bin').exists()
assert bytes(r['key'] for r in report['events']) == b'\tC12+30=\x1bEC128\x1bY'
assert all(c['restored'] for c in report['captures'][:-1]+report['mode_captures'])
assert report['captures'][-1]['label'] == 'desktop-after-editor-surface-1770' and not report['captures'][-1]['restored']
captures = report['captures']+report['mode_captures']
for row in captures:
    assert row['probe_sha256'] == sha(WORK/('native-mode.prg' if 'source' in row else 'native-read.prg'))
    assert len((WORK/(row['label']+'.bin')).read_bytes()) == row['count']
    assert sum(c['count'] for c in row['chunks']) == row['count']
    assert all(c['code'] == 1 and c['address_resyncs'] == 0 and c['foreground_mmu'] == 14 for c in row['chunks'])
cleanup = read(WORK/'failed-desktop-cleanup.json')
assert cleanup['passed'] and cleanup['original_deployment_restored'] and cleanup['dos_paths_restored'] and cleanup['controls_restored']
assert cleanup['source_report_sha256'] == sha(WORK/'report.json')
assert not cleanup['uncertain_writes'] and not cleanup['connect_failures'] and not cleanup['control_requests']
assert cleanup['dos_paths_before_hex'] == report['dos_paths_before_hex']
assert read(WORK/'drives-before.json') == read(WORK/'drives-restored.json')
expected = {report['native_disk_upload_path']:INPUTS/'target/native/uos128.d64', report['restore_prg_path']:INPUTS/'target/uos.prg'}
assert len(expected) == 2 and report['restore_disk_path'] not in expected
assert set(cleanup['readbacks']) == {r['path'] for r in cleanup['deletions']} == set(expected)
assert all(r['started'] and r['confirmed'] for r in cleanup['deletions'])
for path,source in expected.items():
    assert (WORK/('cleanup-readback-'+Path(path).name+'.bin')).read_bytes() == source.read_bytes()
    assert cleanup['readbacks'][path] == dict(path=path,bytes=source.stat().st_size,sha256=sha(source))
result = dict(passed=True,physical_run_passed=False,desktop_views=3,screen_pairs=4,
              captures=len(captures),irq_chunks=sum(len(r['chunks']) for r in captures),
              cpu_captured_bytes=sum(r['count'] for r in captures),partial_return_surface_bytes=8000,
              metadata_failure_bytes_retained=False,initiating_cause_proven=False,
              original_deployment_restored=True,owned_files_verified_and_removed=2,owned_bytes=176884)
if args.record:
    (ROOT/'v2-failure-verification.json').write_text(json.dumps(result,indent=2)+'\n')
else:
    assert result == read(ROOT/'v2-failure-verification.json')
print('PASS: failed V2 partial observations retained; two exact uploads reclaimed; no full native qualification claimed')
