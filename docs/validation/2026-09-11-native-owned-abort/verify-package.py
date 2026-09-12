#!/usr/bin/env python3
"""Rebuild the saved abort-completion sources privately; no hardware I/O."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ARCHIVE = Path(__file__).resolve().parent
BASE = ARCHIVE.parent / '2026-09-11-native-modules'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ARCHIVE / 'oracle'))
from native_files_check import exact_d64_files
from native_module import validate as validate_module

parser = argparse.ArgumentParser()
parser.add_argument('--record', action='store_true')
args = parser.parse_args()
read = lambda name: json.loads((ARCHIVE / name).read_text())
digest = lambda data: hashlib.sha256(data).hexdigest()
rows = lambda path: [line for line in path.read_text().splitlines()
                     if line.strip() and not line.startswith(';')]
frozen = read('frozen.json')
assert len(frozen) == 47
for name, record in frozen.items():
    data = (ARCHIVE / 'frozen' / name).read_bytes()
    assert len(data) == record['bytes'] and digest(data) == record['sha256'], name
images, layout = read('images.json'), read('layout.json')
baseline = json.loads((BASE / 'package/report.json').read_text())
assert baseline['passed']
layout_changes = {key:[old,layout[key]] for key,old in baseline['layout'].items()
                  if old != layout[key]}
assert layout_changes == {'module_code_start':[0x4678,0x4687],
                           'module_code_end':[0x490a,0x4919]}
source_changes = []
for path in (ARCHIVE / 'frozen/src').rglob('*'):
    if not path.is_file(): continue
    name = path.relative_to(ARCHIVE / 'frozen')
    old = BASE / 'package/clean' / name
    if old.read_bytes() != path.read_bytes():
        source_changes.append(name.as_posix())
        diff = ''.join(difflib.unified_diff(old.read_text().splitlines(True),
            path.read_text().splitlines(True), fromfile='a/'+name.as_posix(),
            tofile='b/'+name.as_posix()))
        assert diff == (ARCHIVE / 'change.patch').read_text()
assert source_changes == ['src/native/ultimate.inc']
package = ARCHIVE / 'package'
with tempfile.TemporaryDirectory(prefix='uos-abort-archive-rebuild-') as scratch:
    clean = Path(scratch)
    shutil.copytree(ARCHIVE / 'frozen/src', clean / 'src')
    for name in ('build-native.py','native_image.py','native_module.py'):
        shutil.copyfile(ARCHIVE / 'frozen' / name, clean / name)
    result = subprocess.run([sys.executable,'-B',str(clean/'build-native.py')],
                            cwd=clean,capture_output=True,text=True)
    assert result.returncode == 0, result.stdout+result.stderr
    for name, record in images.items():
        data = (clean/'target/native'/name).read_bytes()
        assert len(data) == record['bytes'] and digest(data) == record['sha256'],name
        assert data == (ARCHIVE/'frozen/target/native'/name).read_bytes(),name
        assert data == (package/'clean/target/native'/name).read_bytes(),name
    for name, expected in (('images.json',images),('layout.json',layout)):
        assert json.loads((clean/'target/native'/name).read_text()) == expected
    for name in ('boot','calc','browse','editor','uos128'):
        assert rows(clean/'target/native'/f'{name}.lst') == rows(package/'clean/target/native'/f'{name}.lst')
    assert (clean/'target/native/uos128.sym').read_bytes() == (ARCHIVE/'uos128.sym').read_bytes()
    unchanged = ['boot.prg','calc.prg','browse.prg','editor.prg','edpick.prg']
    for name in unchanged:
        assert (clean/'target/native'/name).read_bytes() == (BASE/'package/clean/target/native'/name).read_bytes()
    disk = (clean/'target/native/uos128.d64').read_bytes()
    members = {b'U':'uos128.prg',b'CALC':'calc.prg',b'BROWSE':'browse.prg',
               b'EDITOR':'editor.prg',b'EDPICK.PRG':'edpick.prg'}
    files = exact_d64_files(disk)
    assert set(files) == set(members)
    assert disk[:256] == (clean/'target/native/boot.prg').read_bytes()[2:]
    assert not disk[17*21*256+5]&1
    for name, image in members.items():
        data = (clean/'target/native'/image).read_bytes()
        assert files[name] == (2,data)
        output = clean/('extracted-'+image)
        subprocess.run(['c1541','-attach',str(clean/'target/native/uos128.d64'),
                        '-read',name.decode().lower(),str(output)],check=True,capture_output=True)
        assert output.read_bytes() == data == (package/output.name).read_bytes()
    module = validate_module((clean/'target/native/edpick.prg').read_bytes(),
                             (clean/'target/native/editor.prg').read_bytes())
legacy = read('legacy-images.json')
assert legacy == baseline['legacy_images'] and len(legacy) == 18
report = dict(passed=True,hardware_io=False,frozen_files=47,reproducible_images=7,
              extracted_files=5,unchanged_programs=unchanged,
              preceding_native_prgs_unchanged=unchanged,legacy_images_unchanged=18,
              legacy_images=legacy,preceding_source_commit='2bde88b41e7227c2d8fc3fe2e185a20ae6e2df73',
              layout_changes=layout_changes,extra_resident_bytes=15,
              additional_reserved_pages=0,images=images,layout=layout,module=module)
destination = package/'report.json'
if args.record: destination.write_text(json.dumps(report,indent=2)+'\n')
else: assert read('package/report.json') == report
print('PASS: exact 15-byte source patch; seven reproducible images; five extracted files; ABI and heap unchanged')

