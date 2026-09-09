#!/usr/bin/env python3
"""Build the native C128 kernel and an allocated, autobooting D64.

Outputs stay in target/native so C64-mode app discovery cannot mistake a
native image for a legacy application. Uses the same 64tass/c1541 toolchain.
"""
from pathlib import Path
import hashlib
import json
import re
import subprocess
from native_image import seal

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'target/native'


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    for source,name in [('uos128','uos128'),('boot','boot'),('calc','calc'),('browser','browse')]:
        branch=['-B'] if source=='browser' else []
        labels=['-l',str(OUT/'uos128.sym')] if source=='uos128' else []
        subprocess.run(['64tass','-a',*branch,*labels,str(ROOT/'src/native'/f'{source}.asm'),
                        '-o',str(OUT/f'{name}.prg'),'-L',str(OUT/f'{name}.lst')],check=True)
    (OUT/'calc.prg').write_bytes(seal((OUT/'calc.prg').read_bytes()))
    (OUT/'browse.prg').write_bytes(seal((OUT/'browse.prg').read_bytes()))
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
    subprocess.run(['c1541','-attach',str(disk),'-write',str(OUT/'calc.prg'),'calc'],
                   check=True,capture_output=True)
    subprocess.run(['c1541','-attach',str(disk),'-write',str(OUT/'browse.prg'),'browse'],
                   check=True,capture_output=True)
    assert disk.read_bytes()[:256] == boot[2:]
    report = {p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
              for p in (OUT/'uos128.prg',OUT/'boot.prg',OUT/'calc.prg',OUT/'browse.prg',disk)}
    (OUT/'images.json').write_text(json.dumps(report,indent=2)+'\n')
    symbols=(OUT/'uos128.sym').read_text()
    def address(name):
        match=re.search(r'^'+re.escape(name)+r'\s*=\s*\$([0-9a-fA-F]+)\s*$',symbols,re.M)
        assert match,name
        return int(match[1],16)
    layout=dict(main_start=0x1c01,main_end=address('native_code_end'),
                low_start=address('native_low_start'),low_end=address('native_low_end'),
                low_padded_end=address('native_low_padded_end'),low_limit=0x1c00,
                metadata_start=0x3800,metadata_end=address('native_metadata_end'),
                staging_start=address('native_low_image'),load_end=address('native_load_end'),
                app_base=0x6000,managed_pages=442)
    assert layout['main_end']<=layout['metadata_start'] and layout['low_padded_end']<=layout['low_limit']
    assert layout['metadata_end']<=layout['staging_start'] and layout['load_end']<=layout['app_base']
    assert layout['load_end']-layout['staging_start']==layout['low_padded_end']-layout['low_start']
    assert report['uos128.prg']['bytes']==layout['load_end']-layout['main_start']+2
    (OUT/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    print(f'Native C128 boot disk: {disk}')


if __name__ == '__main__':
    build()
