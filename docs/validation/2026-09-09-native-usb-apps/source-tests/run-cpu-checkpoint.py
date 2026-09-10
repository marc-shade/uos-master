import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

root=Path('/home/marc/geos128/uos')
work=Path(tempfile.mkdtemp(prefix='uos-native-usb-cpu-',dir='/var/tmp/arc-scratch'))
names=['heap','relocation','capture','apps','files','directory','ultimate','calc','browser',
       'document','editor','editor_ultimate','editor_redraw','loader_ultimate','usb_apps']
def hashes():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root/'target/native').glob('*.prg'))}
report=dict(passed=False,images=hashes(),suites={})
print(f'CPU evidence: {work}',flush=True)
def run(name):
    start=time.monotonic()
    with (work/(name+'.log')).open('w') as log:
        child=subprocess.run(['/home/marc/.venvs/uos-tests/bin/python','-u',
            str(root/'tests'/('ci_native_'+name+'.py')),'--report',str(work/(name+'.json'))],
            cwd=root,stdout=log,stderr=subprocess.STDOUT)
    return name,dict(exit_code=child.returncode,elapsed_seconds=round(time.monotonic()-start,3))
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
    futures=[executor.submit(run,name) for name in names]
    for future in concurrent.futures.as_completed(futures):
        name,result=future.result();report['suites'][name]=result
        assert report['images']==hashes(),'product images changed during CPU tests'
        (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(f'{name}: exit {result["exit_code"]} ({result["elapsed_seconds"]} seconds)',flush=True)
        if result['exit_code']:
            print((work/(name+'.log')).read_text()[-4000:],flush=True)
report['passed']=all(item['exit_code']==0 for item in report['suites'].values())
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'{"PASS" if report["passed"] else "FAIL"}: {len(names)} CPU suites; {work}',flush=True)
raise SystemExit(0 if report['passed'] else 1)
