import json,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parent
names=['document','editor','editor_ultimate','editor_redraw','module_editor','desktop']
result={'passed':False,'tests':{}}
for name in names:
    start=time.monotonic()
    command=['/home/marc/.venvs/uos-tests/bin/python3',str(root/('tests/ci_native_'+name+'.py')),'--report',str(root/('regression-'+name+'.json'))]
    with (root/('regression-'+name+'.log')).open('w') as log:
        run=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
    result['tests'][name]={'exit_code':run.returncode,'elapsed_seconds':round(time.monotonic()-start,3)}
    (root/'regressions.json').write_text(json.dumps(result,indent=2)+'\n')
    print(name,run.returncode,flush=True)
result['passed']=all(row['exit_code']==0 for row in result['tests'].values())
(root/'regressions.json').write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(0 if result['passed'] else 1)
