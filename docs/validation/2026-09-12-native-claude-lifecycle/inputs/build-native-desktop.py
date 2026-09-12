#!/usr/bin/env python3
"""Build the native graphical desktop and retain the diagnostic workspace."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
OUT = ROOT/'target/native-desktop'
from native_image import seal, validate


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def build():
    native = module('native_builder', ROOT/'build-native.py')
    native.build()
    native.build(out=OUT, desktop_boot=True)
    font = module('native_font', ROOT/'src/native/graphics/font.py')
    (ROOT/'src/native/graphics/font8.bin').write_bytes(font.font())
    from launcher_scene import write_assembly
    write_assembly(ROOT/'src/native/desktop')
    module('claude_builder', ROOT/'build-native-claude.py').build(OUT)
    for name in ('desktop', 'files', 'controls'):
        subprocess.run(['64tass', '-a', '-B', str(ROOT/f'src/native/{name}.asm'),
                        '-o', str(OUT/f'{name}.prg'), '-l', str(OUT/f'{name}.sym'),
                        '-L', str(OUT/f'{name}.lst')], check=True)
        path = OUT/f'{name}.prg'
        path.write_bytes(seal(path.read_bytes()))
        validate(path.read_bytes())
    workspace = OUT/'workspace.d64'
    shutil.copyfile(ROOT/'target/native/uos128.d64', workspace)
    subprocess.run(['c1541', '-attach', str(workspace), '-delete', 'browse',
                    '-write', str(OUT/'desktop.prg'), 'browse',
                    '-write', str(OUT/'files.prg'), 'files',
                    '-write', str(OUT/'controls.prg'), 'ultimate',
                    '-write', str(OUT/'claude.prg'), 'claude'], check=True, capture_output=True)
    desktop = OUT/'uos128.d64'
    shutil.copyfile(workspace, desktop)
    subprocess.run(['c1541', '-attach', str(desktop), '-delete', 'u',
                    '-write', str(OUT/'uos128.prg'), 'u'], check=True, capture_output=True)
    images = {p.name: dict(bytes=p.stat().st_size, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
              for p in sorted(OUT.iterdir()) if p.suffix in ('.prg', '.d64')}
    (OUT/'images.json').write_text(json.dumps(images, indent=2)+'\n')
    deployment = dict(abi='1.10', direct_desktop_disk='uos128.d64',
                      workspace_with_desktop_disk='workspace.d64',
                      standalone_diagnostic_disk='../native/uos128.d64',
                      desktop=validate((OUT/'desktop.prg').read_bytes()),
                      files=validate((OUT/'files.prg').read_bytes()),
                      controls=validate((OUT/'controls.prg').read_bytes()),
                      claude=validate((OUT/'claude.prg').read_bytes()),
                      surface_pages=36,
                      free_pages_at_desktop=426-36-validate((OUT/'desktop.prg').read_bytes())['pages'],
                      selection_state_address=0x3d2f, selection_lifetime='until native restart',
                      disk_entries={'u': 'uos128.prg', 'browse': 'desktop.prg',
                                    'files': 'files.prg', 'calc': 'calc.prg',
                                    'editor': 'editor.prg', 'edpick.prg': 'edpick.prg',
                                    'ultimate': 'controls.prg', 'claude': 'claude.prg'})
    (OUT/'deployment.json').write_text(json.dumps(deployment, indent=2)+'\n')
    print(f'Native graphical desktop disk: {desktop}')
    print(f'Native diagnostic workspace disk: {ROOT/"target/native/uos128.d64"}')


if __name__ == '__main__':
    build()
