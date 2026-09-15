#!/usr/bin/env python3
"""Build the native Sheet app with its checked BSS/stack allocation."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
from native_image import seal, validate

ROOT = Path(__file__).resolve().parent


def build(out=None):
    out = Path(out) if out else ROOT/'target/native-desktop'
    obj = out/'sheet-build'
    obj.mkdir(parents=True, exist_ok=True)
    src = ROOT/'src/native/sheet'
    subprocess.run(['64tass', '-a', '-B', '-b', str(src/'gui.asm'),
                    '-o', str(obj/'gui.bin'), '-l', str(out/'sheet-gui.sym'),
                    '-L', str(out/'sheet-gui.lst')], check=True)
    symbols = {name: int(value, 16) for name, value in re.findall(
        r'^(\w+)\s*=\s*\$([0-9a-fA-F]+)\s*$', (out/'sheet-gui.sym').read_text(), re.M)}
    glue = ['.segment "GUI"', '.incbin '+json.dumps(str(obj/'gui.bin'))]
    for name, value in sorted(symbols.items()):
        glue.append(f'.export {name} := ${value:04x}')
        if name.startswith('sg_'):
            glue.append(f'.export _{name} := ${value:04x}')
    (obj/'gui.s').write_text('\n'.join(glue)+'\n')
    subprocess.run(['ca65', '-o', str(obj/'gui.o'), str(obj/'gui.s')], check=True)
    for name in ('main.c', 'engine.c', 'workbook.c', 'bridge.s', 'startup.s'):
        # Identity character map: workbook records and graphical labels are
        # ASCII. PETSCII keyboard conversion happens at the app boundary.
        subprocess.run(['cl65', '-t', 'none', '-O', '-g', '-c', '-o',
                        str(obj/(Path(name).stem+'.o')), str(src/name)], check=True)
    subprocess.run(['ld65', '-C', str(src/'uos.cfg'), '-m', str(out/'sheet.map'),
                    '-Ln', str(out/'sheet.lbl'), '-o', str(out/'sheet.prg'),
                    *[str(obj/(name+'.o')) for name in ('startup', 'gui', 'main', 'engine', 'workbook', 'bridge')],
                    'none.lib'], check=True)
    path = out/'sheet.prg'
    path.write_bytes(seal(path.read_bytes()))
    info = validate(path.read_bytes())
    stack = re.search(r'^CSTACK\s+[0-9A-Fa-f]+\s+([0-9A-Fa-f]+)\s',
                      (out/'sheet.map').read_text(), re.M)
    assert stack, 'missing C stack extent'
    info['runtime_end'] = int(stack[1], 16)+1
    assert 0x6000+info['bytes'] <= info['runtime_end'] <= 0x6000+info['pages']*256 <= 0xc000
    (out/'sheet.json').write_text(json.dumps(info, indent=2)+'\n')
    print('Native Sheet:', json.dumps(info))
    return info


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path)
    build(parser.parse_args().out)
