#!/usr/bin/env python3
"""Audit retained first-preflight failure and the separate legacy recovery."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
WORK = ROOT/'history/physical-preflight-v1'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
parser = argparse.ArgumentParser()
parser.add_argument('--record', action='store_true')
args = parser.parse_args()
attempt = read(WORK/'attempt/report.json')
assert not attempt['passed'] and attempt['physical_hardware_io']
for field in ('events', 'desktops', 'screens', 'captures', 'host_control_requests',
              'host_upload_checks', 'uncertain_host_writes', 'host_connect_failures'):
    assert attempt[field] == []
assert 'native_disk_upload_path' not in attempt and 'restore_prg_path' not in attempt
assert 'AssertionError: Timed out: UCI tick client' in (WORK/'attempt/workflow.log').read_text()
assert sha(WORK/'attempt/native.d64') == read(ROOT/'candidate-context.json')['disk_sha256']
settings = (WORK/'attempt/settings-before.bin').read_bytes()
drives = read(WORK/'attempt/drives-before.json')
probe = (WORK/'attempt/uci-stream.prg').read_bytes()[2:]
for folder in ('observation-initial', 'panic-observation'):
    report = read(WORK/folder/'report.json')
    assert len(report['samples']) == 2 and not report['memory_writes']
    assert not report['cartridge_commands'] and not report['machine_controls']
    assert not report['uncertain_writes'] and not report['connect_failures']
    assert read(WORK/folder/'drives.json') == drives
    for i, sample in enumerate(report['samples']):
        for name, record in sample.items():
            if not isinstance(record, dict):
                continue
            data = WORK/folder/f'{i}-{name}.bin'
            assert data.stat().st_size == record['bytes'] and sha(data) == record['sha256']
        assert (WORK/folder/f'{i}-settings.bin').read_bytes() == settings
        assert (WORK/folder/f'{i}-probe.bin').read_bytes()[:len(probe)] == probe
        assert (WORK/folder/f'{i}-command.bin').read_bytes()[:2] == b'\x01\x07'
        assert (WORK/folder/f'{i}-probe_state.bin').read_bytes()[:15] == b'\x5e\x1f\x02'+bytes(12)
        low = (WORK/folder/f'{i}-low.bin').read_bytes()
        if folder == 'observation-initial':
            assert low[0x33c:0x33e] == b'\x00\x50'
            assert (WORK/folder/f'{i}-uci.bin').read_bytes()[1]&0x3f == 0
        else:
            assert low[0x33c:0x33e] == b'\x5e\x1f'
            assert (WORK/folder/f'{i}-panic.bin').read_bytes()[0x10c:0x110] == b'4FFF'
            assert (WORK/folder/f'{i}-uci_status.bin').read_bytes()[0]&0x3f == 0
restore = read(WORK/'tick-restore/report.json')
assert not restore['passed'] and not restore['desktop_live']
assert restore['tick_restored_before_liveness'] and restore['final_tick_hex'] == '5e1f'
assert not restore['command_or_abort_resubmitted'] and not restore['uncertain_writes']
pc = read(WORK/'pc-observation/report.json')
assert pc['passed'] and pc['borrowed_page_restored'] and pc['original_irq_hex'] == '579e'
assert pc['no_cartridge_commands'] and pc['no_fifo_reads'] and not pc['uncertain_writes']
assert len(pc['samples']) == 8
for i, sample in enumerate(pc['samples']):
    data = (WORK/'pc-observation'/f'pc-{i}.bin').read_bytes()
    assert data.hex() == sample['raw_hex'] and data[:3] == bytes.fromhex('579e01')
    assert int.from_bytes(data[4:6], 'little') == sample['pc'] == 0x0dcb
    assert data[7:9] == bytes.fromhex(sample['port_hex']) == b'\x2f\x77'
    assert data[9] == sample['tick_second'] == 5 and data[10] == sample['cia_second']
    assert data[13] == sample['uci_state'] == 0
assert len({s['cia_second'] for s in pc['samples']}) > 1
reload = read(WORK/'reload/report.json')
assert reload['passed'] and reload['desktop_live'] and reload['settings_restored'] and reload['drives_unchanged']
assert reload['drives_before'] == reload['drives_after'] == drives
assert bytes.fromhex(reload['settings_hex']) == bytes.fromhex(reload['boot_settings_hex']) == settings
assert not reload['uncertain_writes'] and not reload['connect_failures'] and not reload['cartridge_probe_command_replayed']
assert len(reload['control_requests']) == 1
request = reload['control_requests'][0]
assert request['method'] == 'POST' and request['path'] == '/v1/runners:run_prg'
assert request['request_started'] and request['response_received'] and not request['replayed'] and request['status'] == 200
assert request['sent_bytes'] == (ROOT/'inputs/target/uos.prg').stat().st_size == 2036
assert request['sent_sha256'] == reload['sent_loader_sha256'] == sha(ROOT/'inputs/target/uos.prg')
for name, digest in read(WORK/'recovery-overrides.json').items():
    assert sha(WORK/'recovery-inputs'/name) == digest
with tempfile.TemporaryDirectory(prefix='uos-desktop-preflight-audit-') as temporary:
    root = Path(temporary)
    (root/'probes').mkdir()
    (root/'src').mkdir()
    for name in ('equates.inc', 'routines.inc'):
        (root/'src'/name).write_bytes((ROOT/'inputs/src'/name).read_bytes())
    for source, captured in [(ROOT/'inputs/probes/uci-stream.asm', WORK/'attempt/uci-stream.prg'),
                             (WORK/'recovery-inputs/probes/legacy-pc.asm', WORK/'pc-observation/legacy-pc.prg')]:
        staged = root/'probes'/source.name
        staged.write_bytes(source.read_bytes())
        output = root/'probe.prg'
        subprocess.run(['64tass', '-a', str(staged), '-o', str(output)], check=True, capture_output=True)
        assert output.read_bytes() == captured.read_bytes()
result = dict(passed=True, first_physical_attempt_passed=False, native_code_executed=False,
              probe_entry_markers_untouched=True, cpu_pc_samples=8, foreground_pc='0DCB',
              legacy_panic_text='4FFF', original_loader_bytes=2036,
              original_deployment_restored=True, initiating_cause_proven=False,
              first_observation_included_empty_fifo_reads=True, recovery_dos_paths_freshly_queried=False)
if args.record:
    (ROOT/'preflight-recovery-verification.json').write_text(json.dumps(result, indent=2)+'\n')
else:
    assert result == read(ROOT/'preflight-recovery-verification.json')
print('PASS: first legacy preflight failure retained; eight CPU PC samples; original loader/settings/drives restored')
