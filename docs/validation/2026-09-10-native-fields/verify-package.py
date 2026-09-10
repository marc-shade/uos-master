#!/usr/bin/env python3
"""Rebuild the saved field sources privately and compare every native image."""
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
digest=lambda data:hashlib.sha256(data).hexdigest()

def sources(destination):
    shutil.copytree(snapshot/'src',destination/'src')
    for name in ('build-native.py','native_image.py'):shutil.copyfile(snapshot/name,destination/name)

def build(destination):
    result=subprocess.run([sys.executable,str(destination/'build-native.py')],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr

def listing_rows(path):
    return [line for line in path.read_text().splitlines() if line.strip() and not line.startswith(';')]

with tempfile.TemporaryDirectory(prefix='uos-native-field-rebuild-') as temporary:
    clean=Path(temporary);sources(clean);build(clean)
    for name,record in images.items():
        data=(clean/'target/native'/name).read_bytes()
        assert len(data)==record['bytes'] and digest(data)==record['sha256'],name
        assert data==(snapshot/'target/native'/name).read_bytes(),name
    assert json.loads((clean/'target/native/layout.json').read_text())==layout
    assert json.loads((clean/'target/native/images.json').read_text())==images
    assert (clean/'target/native/uos128.sym').read_bytes()==(ARCHIVE/'uos128.sym').read_bytes()
    for name in ('uos128','boot','calc','browse','editor'):
        assert listing_rows(clean/'target/native'/f'{name}.lst')==listing_rows(snapshot/'target/native'/f'{name}.lst'),name
    assert (layout['main_end'],layout['low_end'],layout['low_padded_end'])==(0x379d,0x1ab9,0x1b00)
    assert (layout['service_start'],layout['service_end'],layout['staging_start'],layout['load_end'])==(0x4000,0x4f20,0x5000,0x5800)
    assert layout['managed_pages']==426
    disk=(clean/'target/native/uos128.d64').read_bytes();files=exact_d64_files(disk)
    assert set(files)=={b'U',b'CALC',b'BROWSE',b'EDITOR'}
    assert disk[:256]==(clean/'target/native/boot.prg').read_bytes()[2:]
    assert not disk[17*21*256+5]&1,'boot block is free in BAM'
    for name,image in ((b'U','uos128.prg'),(b'CALC','calc.prg'),(b'BROWSE','browse.prg'),(b'EDITOR','editor.prg')):
        expected=(clean/'target/native'/image).read_bytes();assert files[name]==(2,expected)
        destination=clean/('extracted-'+image)
        subprocess.run(['c1541','-attach',str(clean/'target/native/uos128.d64'),'-read',name.decode().lower(),str(destination)],
                       check=True,capture_output=True)
        assert destination.read_bytes()==expected
        if args.record:(ARCHIVE/'package'/destination.name).write_bytes(expected)
        else:assert (ARCHIVE/'package'/destination.name).read_bytes()==expected
    for app,pages in (('calc',16),('browse',28),('editor',79)):
        data=(clean/'target/native'/(app+'.prg')).read_bytes();validate(data)
        assert data[8]==6 and data[12]==pages

# Reproduce the failed CPU run's images, retaining the exact prompt overflow.
baseline=json.loads((ARCHIVE/'cpu-initial/report.json').read_text())['images']
with tempfile.TemporaryDirectory(prefix='uos-native-field-initial-rebuild-') as temporary:
    clean=Path(temporary);sources(clean)
    source=clean/'src/native/editor.asm';text=source.read_text()
    fixed='ed_field_help: .text " enter/esc",0'
    original='ed_field_help: .text "  enter/esc",0'
    assert text.count(fixed)==1;source.write_text(text.replace(fixed,original));build(clean)
    for name,expected in baseline.items():assert digest((clean/'target/native'/name).read_bytes())==expected,name
assert {name for name in baseline if baseline[name]!=images[name]['sha256']}=={'editor.prg','uos128.d64'}

reference='e9292239f8d41ae97a2a6da74922d16ec53d1240'
legacy={};tested=json.loads((ARCHIVE/'build.json').read_text())
for relative in sorted(name for name in tested if not name.startswith('target/native/')):
    before=subprocess.run(['git','show',reference+':'+relative],cwd=ROOT,check=True,capture_output=True).stdout
    assert digest(before)==tested[relative],relative;legacy[relative]=digest(before)
assert len(legacy)==18
before=subprocess.run(['git','show',reference+':target/native/boot.prg'],cwd=ROOT,check=True,capture_output=True).stdout
assert digest(before)==images['boot.prg']['sha256']
report=dict(passed=True,images=images,layout=layout,reproducible_images=6,extracted_files=4,
            legacy_images_unchanged=18,legacy_images=legacy,preceding_source_commit=reference,
            preceding_native_prgs_unchanged=['boot.prg'],required_minor=6,
            calculator_pages=16,browser_pages=28,editor_pages=79,
            initial_reproducible_images=6,initial_difference='one extra space in ed_field_help')
path=ARCHIVE/'package/report.json'
if args.record:path.write_text(json.dumps(report,indent=2)+'\n')
else:assert report==json.loads(path.read_text())
print('PASS: six native images rebuilt; four disk files extracted; initial prompt overflow reproduced')
