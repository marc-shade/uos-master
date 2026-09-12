"""Rebuild the isolated owned-abort candidate from its saved sources."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

WORK = Path(__file__).resolve().parent
BASE = Path('/home/marc/geos128/uos/docs/validation/2026-09-11-native-modules/package/clean')
frozen = json.loads((WORK / 'frozen.json').read_text())
for name, expected in frozen.items():
    data = (WORK / 'frozen' / name).read_bytes()
    assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'], name
images = json.loads((WORK / 'frozen/target/native/images.json').read_text())
layout = json.loads((WORK / 'frozen/target/native/layout.json').read_text())
assert layout['managed_pages'] == 426
assert layout['module_code_start'] == 0x4687 and layout['module_code_end'] == 0x4919
baseline_layout = json.loads((BASE / 'target/native/layout.json').read_text())
differences = {name: (baseline_layout[name], value) for name, value in layout.items() if baseline_layout[name] != value}
assert set(differences) == {'module_code_start', 'module_code_end'}
assert all(after-before == 15 for before, after in differences.values())
for source in (WORK / 'frozen/src').rglob('*'):
    if not source.is_file():
        continue
    relative = source.relative_to(WORK / 'frozen')
    if relative.as_posix() != 'src/native/ultimate.inc':
        assert source.read_bytes() == (BASE / relative).read_bytes(), relative
package = WORK / 'package'
package.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='uos-owned-abort-rebuild-') as scratch:
    clean = Path(scratch)
    shutil.copytree(WORK / 'frozen/src', clean / 'src')
    for name in ('build-native.py', 'native_image.py', 'native_module.py'):
        shutil.copyfile(WORK / 'frozen' / name, clean / name)
    result = subprocess.run([sys.executable, '-B', str(clean / 'build-native.py')],
                            cwd=clean, capture_output=True, text=True)
    (package / 'build.log').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    for name, expected in images.items():
        data = (clean / 'target/native' / name).read_bytes()
        assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256'], name
    assert json.loads((clean / 'target/native/layout.json').read_text()) == layout
    assert json.loads((clean / 'target/native/images.json').read_text()) == images
    for name in ('boot.prg', 'calc.prg', 'browse.prg', 'editor.prg', 'edpick.prg'):
        assert (clean / 'target/native' / name).read_bytes() == (BASE / 'target/native' / name).read_bytes()
    members = {'U': 'uos128.prg', 'CALC': 'calc.prg', 'BROWSE': 'browse.prg',
               'EDITOR': 'editor.prg', 'EDPICK.PRG': 'edpick.prg'}
    for name, image in members.items():
        destination = package / ('extracted-' + image)
        subprocess.run(['c1541', '-attach', str(clean / 'target/native/uos128.d64'),
                        '-read', name.lower(), str(destination)], check=True, capture_output=True)
        assert destination.read_bytes() == (clean / 'target/native' / image).read_bytes()
    shutil.copytree(clean, package / 'clean', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
report = dict(passed=True, hardware_io=False, frozen_files=47, reproducible_images=7,
              extracted_files=5, unchanged_programs=['boot.prg', 'calc.prg', 'browse.prg', 'editor.prg', 'edpick.prg'],
              layout_changes={name: list(values) for name, values in differences.items()},
              extra_resident_bytes=15, additional_reserved_pages=0, images=images, layout=layout)
(package / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print('PASS: seven candidate images rebuilt; five disk members extracted; five app/boot PRGs unchanged; no heap pages added')
