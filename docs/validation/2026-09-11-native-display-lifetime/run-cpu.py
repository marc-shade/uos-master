#!/usr/bin/env python3
"""Qualify the frozen private native display kernel; never access hardware."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path('/var/tmp/arc-scratch/uos-native-display-lifetime')
WORK=Path(__file__).resolve().parent
FROZEN=json.loads((WORK/'frozen.json').read_text())
SUITES=['native_heap','native_apps','native_files','native_calc','native_browser',
        'native_document','native_editor','native_relocation','native_ultimate',
        'native_loader_ultimate','native_editor_ultimate','native_usb_apps',
        'native_browser_ultimate','native_directory','native_directory_ultimate',
        'native_editor_redraw','native_file_dialog','native_fields','native_field_apps',
        'native_capture','native_modules','native_module_editor','native_owned_abort',
        'native_sdk_module','native_display']
report=dict(passed=False,hardware_io=False,suites={},images={name:r['sha256'] for name,r in
            json.loads((WORK/'images.json').read_text()).items()})
def intact():
    for name,expected in FROZEN.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
def run(suite):
    started=time.monotonic();output=WORK/'cpu'/(suite+'.json')
    with (WORK/'cpu'/(suite+'.log')).open('w') as log:
        process=subprocess.run([sys.executable,'-B','-u',str(ROOT/'tests'/('ci_'+suite+'.py')),
                                '--report',str(output)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    intact()
    if not process.returncode:assert json.loads(output.read_text())['passed']
    return suite,dict(exit_code=process.returncode,seconds=round(time.monotonic()-started,3),source=output.name)
intact();remaining=[]
for suite in SUITES:
    source=WORK/'cpu'/(suite+'.json')
    if source.exists():
        old=json.loads(source.read_text())
        kernel=old.get('kernel_sha256',old.get('image_sha256',old.get('images',{}).get('uos128.prg')))
        assert old['passed'] and kernel==report['images']['uos128.prg']
        report['suites'][suite]=dict(exit_code=0,source=source.name,retained_initial_exact_image=True)
    else:remaining.append(suite)
print(f'Retaining {len(report["suites"])} exact-image CPU passes; running {len(remaining)} suites',flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for future in concurrent.futures.as_completed([pool.submit(run,suite) for suite in remaining]):
        suite,result=future.result();report['suites'][suite]=result
        (WORK/'cpu/report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(suite,result,flush=True)
intact()
report['passed']=len(report['suites'])==25 and all(item['exit_code']==0 for item in report['suites'].values())
(WORK/'cpu/report.json').write_text(json.dumps(report,indent=2)+'\n')
print('Native display CPU qualification '+('PASS' if report['passed'] else 'FAIL'),flush=True)
sys.exit(0 if report['passed'] else 1)
