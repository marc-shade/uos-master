#!/usr/bin/env python3
"""Rebuild the saved module sources privately and compare all packaged bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ARCHIVE=Path(__file__).resolve().parent
ROOT=ARCHIVE.parents[2]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ARCHIVE/'oracle'))
from native_files_check import exact_d64_files
from native_image import validate
from native_module import validate as validate_module

parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
read=lambda name:json.loads((ARCHIVE/name).read_text())
digest=lambda data:hashlib.sha256(data).hexdigest()
images=read('images.json');layout=read('layout.json');snapshot=ARCHIVE/'package/clean'
def listing_rows(path):
    return [line for line in path.read_text().splitlines() if line.strip() and not line.startswith(';')]

frozen=read('frozen.json');assert len(frozen)==47
for name,record in frozen.items():
    data=(ARCHIVE/'frozen'/name).read_bytes()
    assert len(data)==record['bytes'] and digest(data)==record['sha256'],name
harness=read('harness/SHA256.json')
assert len(harness)==123
for name,expected in harness.items():
    assert digest((ARCHIVE/'harness'/name).read_bytes())==expected,name
for source in (ARCHIVE/'oracle').glob('*.py'):
    assert source.read_bytes()==(ARCHIVE/'harness'/source.name).read_bytes(),source.name

with tempfile.TemporaryDirectory(prefix='uos-native-module-rebuild-') as temporary:
    clean=Path(temporary)
    shutil.copytree(snapshot/'src',clean/'src')
    for name in ('build-native.py','native_image.py','native_module.py'):
        shutil.copyfile(snapshot/name,clean/name)
    result=subprocess.run([sys.executable,str(clean/'build-native.py')],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    for name,record in images.items():
        data=(clean/'target/native'/name).read_bytes()
        assert len(data)==record['bytes'] and digest(data)==record['sha256'],name
        assert data==(snapshot/'target/native'/name).read_bytes()==(ARCHIVE/'frozen/target/native'/name).read_bytes(),name
    for name,expected in (('layout.json',layout),('images.json',images)):
        assert json.loads((clean/'target/native'/name).read_text())==expected
    assert (clean/'target/native/uos128.sym').read_bytes()==(ARCHIVE/'uos128.sym').read_bytes()
    for name in ('uos128','boot','calc','browse','editor'):
        assert listing_rows(clean/'target/native'/f'{name}.lst')==listing_rows(snapshot/'target/native'/f'{name}.lst'),name
    assert (layout['main_end'],layout['low_end'],layout['low_padded_end'])==(0x37a9,0x1bc1,0x1c00)
    assert (layout['service_start'],layout['service_end'],layout['staging_start'],layout['load_end'])==(0x4000,0x4fb8,0x5000,0x5900)
    assert (layout['module_code_start'],layout['module_code_end'])==(0x4678,0x490a)
    assert (layout['module_gate_start'],layout['module_gate_end'])==(0x1a7b,0x1bc1)
    assert (layout['module_context_start'],layout['module_context_end'])==(0x4f20,0x4fb8)
    assert (layout['source_path_start'],layout['source_path_end'],layout['managed_pages'])==(0x3f00,0x4000,426)
    disk=(clean/'target/native/uos128.d64').read_bytes();files=exact_d64_files(disk)
    members={b'U':'uos128.prg',b'CALC':'calc.prg',b'BROWSE':'browse.prg',b'EDITOR':'editor.prg',b'EDPICK.PRG':'edpick.prg'}
    assert set(files)==set(members)
    assert disk[:256]==(clean/'target/native/boot.prg').read_bytes()[2:]
    assert not disk[17*21*256+5]&1,'boot block is free in BAM'
    for name,image in members.items():
        expected=(clean/'target/native'/image).read_bytes();assert files[name]==(2,expected)
        destination=clean/('extracted-'+image)
        subprocess.run(['c1541','-attach',str(clean/'target/native/uos128.d64'),'-read',name.decode().lower(),str(destination)],
                       check=True,capture_output=True)
        assert destination.read_bytes()==expected
        if args.record:(ARCHIVE/'package'/destination.name).write_bytes(expected)
        else:assert (ARCHIVE/'package'/destination.name).read_bytes()==expected
    for app,pages,minor in (('calc',16,6),('browse',28,6),('editor',79,7)):
        data=(clean/'target/native'/(app+'.prg')).read_bytes();validate(data)
        assert data[8]==minor and data[12]==pages
    module=validate_module((clean/'target/native/edpick.prg').read_bytes(),(clean/'target/native/editor.prg').read_bytes())
    assert module['origin']==0x90ce and module['bytes']==7722

reference='ac99ce23cfadcc311c3d5780edec9ed85df2df38';legacy={};tested=read('build.json')
for relative in sorted(name for name in tested if not name.startswith('target/native/')):
    before=subprocess.run(['git','show',reference+':'+relative],cwd=ROOT,check=True,capture_output=True).stdout
    assert digest(before)==tested[relative],relative;legacy[relative]=digest(before)
assert len(legacy)==18
unchanged=['boot.prg','browse.prg','calc.prg']
for name in unchanged:
    before=subprocess.run(['git','show',reference+':target/native/'+name],cwd=ROOT,check=True,capture_output=True).stdout
    assert digest(before)==images[name]['sha256'],name
report=dict(passed=True,images=images,layout=layout,reproducible_images=7,extracted_files=5,
    legacy_images_unchanged=18,legacy_images=legacy,preceding_source_commit=reference,
    preceding_native_prgs_unchanged=unchanged,required_minor=7,calculator_pages=16,browser_pages=28,editor_pages=79,
    module=module,frozen_files=47,harness_files=123)
path=ARCHIVE/'package/report.json'
if args.record:path.write_text(json.dumps(report,indent=2)+'\n')
else:assert report==json.loads(path.read_text())
print('PASS: seven images rebuilt; five disk files extracted; module and parent verified; frozen sources and harness intact')
