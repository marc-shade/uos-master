#!/usr/bin/env python3
"""Rebuild the drawing library/client against the pinned display candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ARCHIVE=Path(__file__).resolve().parent
BASE=ARCHIVE.parent/'2026-09-11-native-display-lifetime'
SOURCE=ARCHIVE/'source'
sha=lambda data:hashlib.sha256(data).hexdigest()
read=lambda path:json.loads(path.read_text())
parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
context=read(ARCHIVE/'candidate-context.json')
assert context['base_manifest_sha256']=='bee0cc0619f07d1a6824205fe4f815295224ae81c741a9244d54f4e972b8feaa'
assert sha((BASE/'SHA256SUMS').read_bytes())==context['base_manifest_sha256']
assert not context['main_integrated'] and not context['physical_hardware_io']
assert context['reused_cbm_sha256']=='508c86cb55a4728bef2ded2f8d1d0d807a75c2f807e397fd36686c539afdd553'
assert sha((BASE/'runtime/cbm').read_bytes())==context['reused_cbm_sha256']
frozen=read(BASE/'frozen.json');assert len(frozen)==218
for name,digest in frozen.items():assert sha((BASE/'frozen'/name).read_bytes())==digest,name
for name,digest in context['source_inputs'].items():assert sha((SOURCE/name).read_bytes())==digest,name
kernel=sha((BASE/'frozen/target/native/uos128.prg').read_bytes())
library=(SOURCE/'graphics/graphics.prg').read_bytes()
assert kernel==context['kernel_sha256'] and len(library)-2==2022
cases=interrupts=0;cpu={}
for name,count in [('report.json',173),('glyph-report.json',294),('text-report.json',140)]:
    report=read(SOURCE/'graphics'/name)
    assert report['passed'] and not report['hardware_io']
    assert report['kernel_sha256']==kernel and report['library_sha256']==sha(library)
    assert report['library_bytes']==2022 and len(report['cases'])==count
    assert {row['bank'] for row in report['cases']}=={0,1}
    cases+=count;interrupts+=report['interrupts']
    cpu[name]=dict(cases=count,interrupts=report['interrupts'],max_instructions=report['max_instructions'])
assert cases==607 and interrupts==12882
with tempfile.TemporaryDirectory(prefix='uos-graphics-archive-rebuild-') as directory:
    clean=Path(directory)
    shutil.copytree(BASE/'frozen',clean,dirs_exist_ok=True)
    shutil.copytree(SOURCE,clean,dirs_exist_ok=True)
    command=['64tass','-a','-B',str(clean/'graphics/graphics.asm'),'-o',str(clean/'graphics/graphics.prg')]
    subprocess.run(command,check=True,capture_output=True)
    assert (clean/'graphics/graphics.prg').read_bytes()==library
    subprocess.run([sys.executable,'-B',str(clean/'graphics/font.py')],check=True,capture_output=True)
    subprocess.run([sys.executable,'-B',str(clean/'build-demo.py')],cwd=clean,check=True,capture_output=True)
    for name in ('font8.bin','DISPLAY.PRG','expected-surface.bin','graphics-core.inc','text-core.inc','text-commands.inc'):
        data=(clean/'client'/name).read_bytes()
        assert data==(SOURCE/'client'/name).read_bytes()
        assert data==(ARCHIVE/'display-emulator'/name).read_bytes()
    assert (clean/'graphics/font8.bin').read_bytes()==(SOURCE/'graphics/font8.bin').read_bytes()
    build=read(clean/'client/build.json');assert build==read(SOURCE/'client/build.json')
    assert build['client']['pages']==12 and build['client']['bytes']==2884
    assert len(build['operations'])==9 and len(build['text_operations'])==7
    for name,digest in frozen.items():assert sha((clean/name).read_bytes())==digest,name
result=dict(passed=True,main_integrated=False,physical_hardware_io=False,
            reused_frozen_inputs=218,new_frozen_inputs=len(context['source_inputs']),
            reused_cbm_sha256=context['reused_cbm_sha256'],
            kernel_sha256=kernel,library_sha256=sha(library),library_bytes=2022,
            cpu=cpu,cpu_cases=cases,modeled_interrupts=interrupts,client=build['client'],
            original_ascii_glyphs=95,complete_surface_bytes=9216)
if args.record:(ARCHIVE/'package-report.json').write_text(json.dumps(result,indent=2)+'\n')
else:assert result==read(ARCHIVE/'package-report.json')
print('PASS: pinned 218 base inputs; 607 CPU cases; rebuilt 2022-byte library, font and 2886-byte client')
