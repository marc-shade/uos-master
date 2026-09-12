#!/usr/bin/env python3
"""Rebuild the isolated display candidate and audit its exact software inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ARCHIVE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ARCHIVE/'frozen'))
from native_files_check import exact_d64_files
from native_module import validate as validate_module

parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
read=lambda name:json.loads((ARCHIVE/name).read_text())
sha=lambda b:hashlib.sha256(b).hexdigest()
frozen=read('frozen.json');assert len(frozen)==218
for name,digest in frozen.items():assert sha((ARCHIVE/'frozen'/name).read_bytes())==digest,name
context=read('candidate-context.json')
assert not context['main_integrated'] and not context['physical_hardware_io']
assert len(context['runtime_inputs'])==19
for name,digest in context['runtime_inputs'].items():assert sha((ARCHIVE/'runtime'/name).read_bytes())==digest,name
assert read('legacy-inputs.json')=={Path(name).name:digest for name,digest in context['runtime_inputs'].items() if name.startswith('target/')}
images=read('images.json');layout=read('frozen/target/native/layout.json')
cpu=read('cpu/report.json');assert cpu['passed'] and len(cpu['suites'])==25 and not cpu['hardware_io']
assert cpu['images']=={name:record['sha256'] for name,record in images.items()}
retained=[]
for name,entry in cpu['suites'].items():
    assert entry['exit_code']==0
    report=read('cpu/'+entry['source']);assert report['passed']
    observed=report.get('kernel_sha256',report.get('image_sha256',report.get('images',{}).get('uos128.prg')))
    if name=='native_capture':
        assert observed is None and report['probe_sha256']
        capture_digest=report['probe_sha256']
    else:assert observed==images['uos128.prg']['sha256'],name
    if entry.get('retained_initial_exact_image'):retained.append(name)
assert sorted(retained)==['native_loader_ultimate','native_modules']
baseline=ARCHIVE.parent/'2026-09-11-native-owned-abort/frozen-live/target/native'
unchanged=['boot.prg','calc.prg','browse.prg','editor.prg','edpick.prg']
assert sha((baseline/'uos128.prg').read_bytes())=='45281b86a55f93c6402a7b0159075148d0f19086471c504bf859332c0b25e63d'
for name in unchanged:assert (baseline/name).read_bytes()==(ARCHIVE/'frozen/target/native'/name).read_bytes(),name
with tempfile.TemporaryDirectory(prefix='uos-display-archive-rebuild-') as directory:
    clean=Path(directory)
    shutil.copytree(ARCHIVE/'frozen/src',clean/'src')
    shutil.copytree(ARCHIVE/'frozen/probes',clean/'probes')
    for name in ('build-native.py','native_image.py','native_module.py'):shutil.copyfile(ARCHIVE/'frozen'/name,clean/name)
    process=subprocess.run([sys.executable,'-B',str(clean/'build-native.py')],cwd=clean,capture_output=True,text=True)
    assert process.returncode==0,process.stdout+process.stderr
    for name,record in images.items():
        data=(clean/'target/native'/name).read_bytes()
        assert len(data)==record['bytes'] and sha(data)==record['sha256'],name
    assert json.loads((clean/'target/native/layout.json').read_text())==layout
    assert (clean/'target/native/uos128.sym').read_bytes()==(ARCHIVE/'frozen/target/native/uos128.sym').read_bytes()
    subprocess.run(['64tass','-a',str(clean/'probes/native-read.asm'),'-o',str(clean/'capture.prg')],check=True,capture_output=True)
    assert sha((clean/'capture.prg').read_bytes())==capture_digest
    disk=(clean/'target/native/uos128.d64').read_bytes();files=exact_d64_files(disk)
    members={b'U':'uos128.prg',b'CALC':'calc.prg',b'BROWSE':'browse.prg',b'EDITOR':'editor.prg',b'EDPICK.PRG':'edpick.prg'}
    assert set(files)==set(members) and disk[:256]==(clean/'target/native/boot.prg').read_bytes()[2:]
    assert not disk[17*21*256+5]&1
    for member,name in members.items():
        data=(clean/'target/native'/name).read_bytes();assert files[member]==(2,data)
        output=clean/('extracted-'+name)
        subprocess.run(['c1541','-attach',str(clean/'target/native/uos128.d64'),'-read',member.decode().lower(),str(output)],check=True,capture_output=True)
        assert output.read_bytes()==data
    module=validate_module((clean/'target/native/edpick.prg').read_bytes(),(clean/'target/native/editor.prg').read_bytes())
assert layout['managed_pages']==426
for prefix,limit in (('main',0x3800),('low',0x1c00),('service',0x5000)):
    assert layout[prefix+'_end']<=limit
assert layout['module_code_end']==layout['display_show_start']<layout['display_show_end']<=0x4a00
assert layout['module_context_end']==layout['display_restore_start']
assert layout['module_gate_end']==layout['display_close_start']
report=dict(passed=True,hardware_io=False,production_integrated=False,frozen_inputs=218,
    additional_runtime_inputs=19,
    cpu_suites=25,retained_cpu_suites=sorted(retained),capture_probe_sha256=capture_digest,
    reproducible_images=7,extracted_members=5,
    unchanged_programs=unchanged,images=images,layout=layout,module=module,additional_heap_pages=0)
destination=ARCHIVE/'package-report.json'
if args.record:destination.write_text(json.dumps(report,indent=2)+'\n')
else:assert read('package-report.json')==report
print('PASS: 218 frozen inputs; 25 exact-image CPU suites; seven rebuilt images; five unchanged apps/boot programs')
