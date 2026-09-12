import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/var/tmp/arc-scratch/uos-owned-abort-prototype')
WORK = Path(__file__).resolve().parent
FROZEN = json.loads((WORK / 'frozen.json').read_text())
HARNESS = json.loads((WORK / 'harness/SHA256.json').read_text())
SUITES = ['native_heap', 'native_apps', 'native_files', 'native_calc', 'native_browser',
          'native_document', 'native_editor', 'native_relocation', 'native_ultimate',
          'native_loader_ultimate', 'native_editor_ultimate', 'native_usb_apps',
          'native_browser_ultimate', 'native_directory', 'native_directory_ultimate',
          'native_editor_redraw', 'native_file_dialog', 'native_fields', 'native_field_apps',
          'native_capture', 'native_modules', 'native_module_editor', 'native_owned_abort',
          'native_sdk_module']
report = dict(passed=False, hardware_io=False, suites={}, images={
    name: entry['sha256'] for name, entry in json.loads((ROOT / 'target/native/images.json').read_text()).items()})


def intact():
    for name, record in FROZEN.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == record['sha256'], name
    for name, expected in HARNESS.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name


def run(suite):
    started = time.monotonic()
    path = WORK / 'cpu' / (suite + '.json')
    with (WORK / 'cpu' / (suite + '.log')).open('w') as log:
        result = subprocess.run([sys.executable, '-B', '-u', str(ROOT / 'tests' / ('ci_' + suite + '.py')),
                                 '--report', str(path)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    intact()
    if not result.returncode:
        assert json.loads(path.read_text())['passed']
    return suite, dict(exit_code=result.returncode, seconds=round(time.monotonic()-started, 3), source=path.name)


intact()
remaining = []
for suite in SUITES:
    path = WORK / 'cpu' / (suite + '.json')
    if path.exists():
        saved = json.loads(path.read_text())
        saved_kernel = saved.get('kernel_sha256', saved.get('images', {}).get('uos128.prg'))
        assert saved['passed'] and saved_kernel == report['images']['uos128.prg']
        report['suites'][suite] = dict(exit_code=0, source=path.name, retained_from_initial_exact_image_checks=True)
    else:
        remaining.append(suite)
print(f"Retaining {len(report['suites'])} exact-image passes; running {len(remaining)} remaining CPU suites", flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for future in concurrent.futures.as_completed([pool.submit(run, suite) for suite in remaining]):
        suite, result = future.result()
        report['suites'][suite] = result
        (WORK / 'cpu/report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(suite, result, flush=True)
intact()
report['passed'] = len(report['suites']) == 24 and all(result['exit_code'] == 0 for result in report['suites'].values())
(WORK / 'cpu/report.json').write_text(json.dumps(report, indent=2) + '\n')
print('Owned-abort CPU qualification ' + ('PASS' if report['passed'] else 'FAIL'), flush=True)
sys.exit(0 if report['passed'] else 1)
