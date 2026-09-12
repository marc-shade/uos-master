#!/usr/bin/env python3
"""Build the native MIT Claude terminal, including its owned BSS and C stack."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from native_image import seal, validate

ROOT = Path(__file__).resolve().parent


def build(out=None):
    out = Path(out) if out is not None else ROOT/'target/native-desktop'
    out.mkdir(parents=True, exist_ok=True)
    obj = out/'claude-build'
    obj.mkdir(exist_ok=True)
    src = ROOT/'src/native/claude'
    for name in ('main.c', 'c128hw.s', 'startup.s'):
        subprocess.run(['cl65', '-t', 'c128', '-O', '-g', '-c', '-o',
                        str(obj/(Path(name).stem+'.o')), str(src/name)], check=True)
    subprocess.run(['ld65', '-C', str(src/'uos.cfg'), '-m', str(out/'claude.map'),
                    '-Ln', str(out/'claude.lbl'), '-o', str(out/'claude.prg'),
                    str(obj/'startup.o'), str(obj/'main.o'), str(obj/'c128hw.o'),
                    'c128.lib'], check=True)
    image = out/'claude.prg'
    image.write_bytes(seal(image.read_bytes()))
    info = validate(image.read_bytes())
    info['sha256'] = hashlib.sha256(image.read_bytes()).hexdigest()
    (out/'claude.json').write_text(json.dumps(info, indent=2)+'\n')
    print('Native Claude:', json.dumps(info))
    return info


if __name__ == '__main__':
    build()
