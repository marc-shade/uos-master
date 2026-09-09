#!/usr/bin/env python3
"""Rebuild a private package and compare images; never rebuild the source tree.

Usage: python3 verify.py REPOSITORY OUTPUT_DIRECTORY
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


root=Path(sys.argv[1]).resolve()
work=Path(sys.argv[2]).resolve()
work.mkdir(parents=True,exist_ok=True)
clean=work/'clean'
assert not clean.exists(), 'use a fresh output directory'
shutil.copytree(root/'src/native',clean/'src/native')
for name in ('build-native.py','native_image.py'):
    shutil.copy2(root/name,clean/name)
with (work/'build.log').open('w') as log:
    subprocess.run([sys.executable,str(clean/'build-native.py')],check=True,stdout=log,stderr=subprocess.STDOUT)
images={}
for name in ('uos128.prg','calc.prg','boot.prg','uos128.d64'):
    actual=(clean/'target/native'/name).read_bytes()
    assert actual==(root/'target/native'/name).read_bytes(),name
    images[name]=dict(bytes=len(actual),sha256=hashlib.sha256(actual).hexdigest())
disk=clean/'target/native/uos128.d64'
data=disk.read_bytes();bam=data[17*21*256:18*21*256]
assert data[:256]==(clean/'target/native/boot.prg').read_bytes()[2:]
assert not bam[5]&1, 'boot block must be allocated'
track_free=[]
for track,size in enumerate([21]*17+[19]*7+[18]*6+[17]*5,1):
    count=bam[track*4]
    mask=int.from_bytes(bam[track*4+1:track*4+4],'little')
    assert not mask>>size and mask.bit_count()==count,(track,count,mask)
    track_free.append(count)
directory=subprocess.run(['c1541','-attach',str(disk),'-list'],check=True,capture_output=True,text=True)
(work/'directory.txt').write_text(directory.stdout)
for disk_name,image_name in [('u','uos128.prg'),('calc','calc.prg')]:
    extracted=work/(disk_name+'-extracted.prg')
    subprocess.run(['c1541','-attach',str(disk),'-read',disk_name,str(extracted)],check=True,capture_output=True)
    assert extracted.read_bytes()==(root/'target/native'/image_name).read_bytes()
reference=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
legacy={}
for path in sorted((root/'target').glob('*.prg'))+[root/'target/ultos.d64']:
    relative=str(path.relative_to(root));actual=path.read_bytes()
    assert actual==subprocess.check_output(['git','show',reference+':'+relative],cwd=root),relative
    legacy[relative]=hashlib.sha256(actual).hexdigest()
sys.path.insert(0,str(clean))
from native_image import validate
report=dict(passed=True,reproducible_images=len(images),images=images,
            boot_sector_reserved=True,bam_counts_match=True,track_free_counts=track_free,
            extracted_files=2,legacy_images_unchanged=len(legacy),legacy_reference_commit=reference,
            legacy_images=legacy,calculator=validate((clean/'target/native/calc.prg').read_bytes()))
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'PASS: {len(images)} reproducible images, allocated boot block, matching BAM counts, '
      f'2 extracted PRGs, {len(legacy)} unchanged legacy images')
