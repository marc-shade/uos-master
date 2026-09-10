import concurrent.futures,hashlib,json,pathlib,subprocess,time,tempfile
root=pathlib.Path('/home/marc/geos128/uos')
work=pathlib.Path(tempfile.mkdtemp(prefix='uos-fields-cpu-followup-',dir='/var/tmp/arc-scratch'))
print('CPU evidence: '+str(work),flush=True)
images={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'target/native').iterdir() if p.suffix in ('.prg','.d64')}
names=['apps','loader_ultimate','editor','editor_ultimate','editor_redraw','file_dialog','field_apps']
report=dict(passed=False,images=images,suites={},parallel_jobs=2)
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(name):
 command=['/home/marc/.venvs/uos-tests/bin/python','-u',str(root/'tests'/('ci_native_'+name+'.py')),'--report',str(work/(name+'.json'))]
 start=time.monotonic()
 with (work/(name+'.log')).open('w') as log:r=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
 return name,dict(exit_code=r.returncode,elapsed_seconds=round(time.monotonic()-start,3),command=command)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for future in concurrent.futures.as_completed([pool.submit(run,name) for name in names]):
  name,result=future.result();report['suites'][name]=result
  assert images=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'target/native').iterdir() if p.suffix in ('.prg','.d64')},'build changed'
  (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
  print(name+': '+str(result['exit_code']),flush=True)
report['passed']=all(r['exit_code']==0 for r in report['suites'].values())
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(('PASS' if report['passed'] else 'FAIL')+': '+str(work),flush=True)
raise SystemExit(0 if report['passed'] else 1)
