#!/usr/bin/env python3
"""Rebuild only the private source snapshot; verify every packaged native PRG."""
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

parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
images=json.loads((ARCHIVE/'images.json').read_text())
layout=json.loads((ARCHIVE/'layout.json').read_text())
snapshot=ARCHIVE/'package/clean'
temporary=tempfile.TemporaryDirectory(prefix='uos-native-directory-rebuild-')
clean=Path(temporary.name)
shutil.copytree(snapshot/'src',clean/'src')
for name in ('build-native.py','native_image.py'):
    shutil.copyfile(snapshot/name,clean/name)
built=subprocess.run([sys.executable,str(clean/'build-native.py')],capture_output=True,text=True)
if built.returncode:
    print(built.stdout+built.stderr,file=sys.stderr)
    built.check_returncode()
for name,record in images.items():
    data=(clean/'target/native'/name).read_bytes()
    assert len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256'],name
    assert data==(snapshot/'target/native'/name).read_bytes(),name
assert json.loads((clean/'target/native/layout.json').read_text())==layout
assert json.loads((clean/'target/native/images.json').read_text())==images
for name in ('uos128.sym',):assert (clean/'target/native'/name).read_bytes()==(ARCHIVE/name).read_bytes()
def listing_rows(path):
    return [line for line in path.read_text().splitlines() if line.strip() and not line.startswith(';')]
for name in ('uos128','boot','calc','browse','editor'):
    assert listing_rows(clean/'target/native'/f'{name}.lst')==listing_rows(snapshot/'target/native'/f'{name}.lst'),name
assert layout['service_start']==0x4000 and layout['service_end']<=0x5000
assert layout['staging_start']==0x5000 and layout['load_end']==0x5500
assert layout['managed_pages']==426
disk=(clean/'target/native/uos128.d64').read_bytes();files=exact_d64_files(disk)
assert set(files)=={b'U',b'CALC',b'BROWSE',b'EDITOR'}
assert disk[:256]==(clean/'target/native/boot.prg').read_bytes()[2:]
assert not disk[17*21*256+5]&1,'boot block is free in BAM'
for name,image in ((b'U','uos128.prg'),(b'CALC','calc.prg'),(b'BROWSE','browse.prg'),(b'EDITOR','editor.prg')):
    expected=(clean/'target/native'/image).read_bytes()
    assert files[name]==(2,expected)
    dest=clean/('extracted-'+image)
    subprocess.run(['c1541','-attach',str(clean/'target/native/uos128.d64'),'-read',name.decode().lower(),str(dest)],
                   check=True,capture_output=True)
    assert dest.read_bytes()==expected
    if args.record:
        (ARCHIVE/'package'/dest.name).write_bytes(expected)
    else:
        assert (ARCHIVE/'package'/dest.name).read_bytes()==expected
for name in ('calc.prg','browse.prg','editor.prg'):validate((clean/'target/native'/name).read_bytes())
assert (clean/'target/native/editor.prg').read_bytes()[8]==3
for app,pages,minor in (('calc',16,4),('browse',28,5)):
    data=(clean/'target/native'/(app+'.prg')).read_bytes()
    assert data[8]==minor and data[12]==pages
assert (clean/'target/native/editor.prg').read_bytes()[12]==48 and images['editor.prg']['bytes']==12202
reference='1a93d06aa9d22970de185be428b8548ed546ac88'
legacy={}
tested=json.loads((ARCHIVE/'build.json').read_text())
for relative in sorted(name for name in tested if not name.startswith('target/native/')):
    before=subprocess.run(['git','show',reference+':'+relative],cwd=ROOT,check=True,capture_output=True).stdout
    value=hashlib.sha256(before).hexdigest();assert tested[relative]==value,relative
    legacy[relative]=value
assert len(legacy)==18
unchanged=[]
for name in ('boot.prg','calc.prg','editor.prg'):
    before=subprocess.run(['git','show',reference+':target/native/'+name],cwd=ROOT,check=True,capture_output=True).stdout
    assert (clean/'target/native'/name).read_bytes()==before
    unchanged.append(name)
report=dict(passed=True,images=images,layout=layout,reproducible_images=6,extracted_files=4,
            legacy_images_unchanged=len(legacy),legacy_images=legacy,preceding_source_commit=reference,
            preceding_native_prgs_unchanged=unchanged,editor_required_minor=3,calculator_required_minor=4,browser_required_minor=5)
if args.record:
    (ARCHIVE/'package/report.json').write_text(json.dumps(report,indent=2)+'\n')
else:
    assert report==json.loads((ARCHIVE/'package/report.json').read_text())
temporary.cleanup()
print('PASS: six reproducible native images; four disk extractions; 18 legacy images and three native PRGs unchanged')
