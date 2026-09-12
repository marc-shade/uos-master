"""Repeat only the SDK workflow after correcting its exit label."""
import json
from pathlib import Path
import subprocess
import sys
import time

WORK = Path(__file__).resolve().parent
ROOT = Path('/var/tmp/arc-scratch/uos-owned-abort-sdk-current')
started = time.monotonic()
with (WORK / 'cpu/native_sdk_module.log').open('w') as log:
    result = subprocess.run([sys.executable, '-B', '-u', str(ROOT / 'tests/ci_native_sdk_module.py'),
                             '--output', str(WORK / 'sdk-current-build'),
                             '--report', str(WORK / 'cpu/native_sdk_module.json')],
                            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
assert result.returncode == 0, (WORK / 'cpu/native_sdk_module.log').read_text()
sdk = json.loads((WORK / 'cpu/native_sdk_module.json').read_text())
report = json.loads((WORK / 'cpu/report.json').read_text())
assert sdk['passed'] and sdk['kernel_sha256'] == report['images']['uos128.prg']
assert len(sdk['cases']) == 15
current = json.loads(Path('/var/tmp/arc-scratch/uos-sdk-module-example/build.json').read_text())
assert sdk['build'] == current
report['suites']['native_sdk_module'] = dict(exit_code=0, seconds=round(time.monotonic()-started, 3),
    source='native_sdk_module.json', harness_delta='harness-sdk-correction',
    preceding_observations_retained='cpu-original-sdk', reason='Corrected exit label; unchanged kernel and API.')
assert report['passed'] and len(report['suites']) == 24
(WORK / 'cpu/report.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: current SDK example repeats all 15 workflows on the owned-abort candidate; original observations retained')
