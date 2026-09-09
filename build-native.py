#!/usr/bin/env python3
"""Build the native C128 kernel and an allocated, autobooting D64.

Outputs stay in target/native so C64-mode app discovery cannot mistake a
native image for a legacy application. Uses the same 64tass/c1541 toolchain.
"""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'target/native'


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    for source,name in [('uos128','uos128'),('boot','boot')]:
        subprocess.run(['64tass','-a',str(ROOT/'src/native'/f'{source}.asm'),
                        '-o',str(OUT/f'{name}.prg'),'-L',str(OUT/f'{name}.lst')],check=True)
    disk = OUT/'uos128.d64'
    subprocess.run(['c1541','-format','uos128,01','d64',str(disk)],check=True,capture_output=True)
    data = bytearray(disk.read_bytes())
    boot = (OUT/'boot.prg').read_bytes()
    assert boot[:2] == b'\0\x0b' and len(boot) == 258
    # The boot block is outside file chains. Reserve it in the BAM before
    # adding files, so ordinary disk allocation cannot overwrite it later.
    bam = 17*21*256
    assert data[bam+4] == 21 and data[bam+5] & 1
    data[bam+4] -= 1
    data[bam+5] &= 0xfe
    data[:256] = boot[2:]
    disk.write_bytes(data)
    subprocess.run(['c1541','-attach',str(disk),'-write',str(OUT/'uos128.prg'),'u'],
                   check=True,capture_output=True)
    assert disk.read_bytes()[:256] == boot[2:]
    report = {p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
              for p in (OUT/'uos128.prg',OUT/'boot.prg',disk)}
    (OUT/'images.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'Native C128 boot disk: {disk}')


if __name__ == '__main__':
    build()
