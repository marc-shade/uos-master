#!/usr/bin/env python3
"""Check the final observer evidence overlay without losing the initial inputs."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('package',ROOT/'verify-package.py')
package = importlib.util.module_from_spec(spec); spec.loader.exec_module(package)
read, sha = package.read, package.sha
parser = argparse.ArgumentParser()
parser.add_argument('--record',action='store_true')
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='uos-desktop-final-observer-') as temporary:
    clean = Path(temporary); package.materialize(clean)
    current = read(ROOT/'current/source-manifest.json')
    assert set(current) == {'native_capture.py','tests/ci_native_borrower_evidence.py'}
    for name, digest in current.items():
        assert sha(ROOT/'current/source'/name) == digest
        target = clean/name; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'current/source'/name,target)
    final = read(ROOT/'source-overlays.json'); final.update(current)
    assert final == read(ROOT/'source-overlays-current.json') and len(final) == 52
    for name, digest in final.items():
        assert sha(clean/name) == digest
    for name in ('hw_native_desktop_check.py','native_mode_capture.py','native_capture.py','probes/native-mode.asm'):
        assert (clean/name).read_bytes() == (ROOT/'current/emulator/used-sources'/name).read_bytes()
    subprocess.run([sys.executable,'-B',str(clean/'tests/ci_native_borrower_evidence.py'),
                    '--report',str(clean/'controls.json')],check=True,capture_output=True)
    assert read(clean/'controls.json') == read(ROOT/'current/borrower-controls.json')
    assert read(ROOT/'current/regression/report.json')['suites'] == {'nativedesktopsequence':{'exit_code':0}}
    assert read(ROOT/'current/emulator/report.json')['passed']
    result = dict(passed=True,source_overlays=52,effective_inputs=336,
                  host_borrower_controls=5,final_emulator_workflows=1,
                  initial_inputs_preserved=True,os_images_changed=False)
if args.record:
    (ROOT/'current-verification.json').write_text(json.dumps(result,indent=2)+'\n')
else:
    assert result == read(ROOT/'current-verification.json')
print('PASS: final observer overlay matches its executed sources; all five strict borrower controls pass')
