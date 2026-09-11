import concurrent.futures,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path('/home/marc/geos128/uos')
WORK=Path(__file__).resolve().parent
FROZEN=json.loads((WORK/'frozen.json').read_text())
SUITES=['native_heap','native_apps','native_files','native_calc','native_browser','native_document','native_editor','native_relocation','native_ultimate','native_loader_ultimate','native_editor_ultimate','native_usb_apps','native_browser_ultimate','native_directory','native_directory_ultimate','native_editor_redraw','native_file_dialog','native_fields','native_field_apps','native_capture','native_modules','native_module_editor','hardware_transport','hardware_uploads','hardware_editor_restore']
report=dict(passed=False,suites={})
def intact():
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==entry['sha256'] for name,entry in FROZEN.items()), 'Frozen native files changed'
def run(suite):
    started=time.monotonic()
    with (WORK/'cpu'/f'{suite}.log').open('w') as log:
        p=subprocess.run(['/home/marc/.venvs/uos-tests/bin/python','-u',str(ROOT/'tests'/f'ci_{suite}.py'),'--report',str(WORK/'cpu'/f'{suite}.json')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    intact()
    result=dict(exit_code=p.returncode,seconds=round(time.monotonic()-started,3))
    if not p.returncode:assert json.loads((WORK/'cpu'/f'{suite}.json').read_text())['passed']
    return suite,result
intact()
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    for future in concurrent.futures.as_completed([pool.submit(run,suite) for suite in SUITES]):
        suite,result=future.result();report['suites'][suite]=result
        (WORK/'cpu/report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(suite,result,flush=True)
intact();report['passed']=all(r['exit_code']==0 for r in report['suites'].values())
(WORK/'cpu/report.json').write_text(json.dumps(report,indent=2)+'\n')
print('CPU qualification '+('PASS' if report['passed'] else 'FAIL'),flush=True)
sys.exit(0 if report['passed'] else 1)
