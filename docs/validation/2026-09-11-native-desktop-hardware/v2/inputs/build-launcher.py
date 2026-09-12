#!/usr/bin/env python3
"""Build an isolated desktop disk while retaining the base kernel and apps."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from native_image import seal, validate
from launcher_scene import OPS, TEXT, surface

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'target/native'
LAUNCHER = ROOT/'launcher'
source = (ROOT/'client/scene.inc').read_text()
(LAUNCHER/'scene.inc').write_text(source)
source = (ROOT/'client/text-scene.inc').read_text().replace('lda #7', 'lda #text_commands_count')
source = source.replace('        jmp draw_clip_text', '        lda #0\n        clc\n        rts').replace('.include "clip-text.inc"', '')
(LAUNCHER/'text-scene.inc').write_text(source)
rows = [f'scene_commands_count={len(OPS)}']
for mode, coords, value in OPS:
    rows.extend(['        .sint '+','.join(map(str, coords)), f'        .byte {mode},{value}'])
(LAUNCHER/'scene-commands.inc').write_text('\n'.join(rows)+'\n')
rows = [f'text_commands_count={len(TEXT)}']
for x, y, pen, label in TEXT:
    rows.extend([f'        .sint {x},{y}', f'        .byte {pen},{len(label)}',
                 '        .byte '+','.join(map(str, label))])
(LAUNCHER/'text-commands.inc').write_text('\n'.join(rows)+'\n')
images = {}
for name in ('desktop', 'files'):
    subprocess.run(['64tass', '-a', '-B', str(ROOT/f'src/native/{name}.asm'),
                    '-o', str(OUT/f'{name}.prg'), '-l', str(OUT/f'{name}.sym'),
                    '-L', str(OUT/f'{name}.lst')], check=True, capture_output=True)
    path = OUT/f'{name}.prg'
    path.write_bytes(seal(path.read_bytes()))
    images[name] = validate(path.read_bytes()) | {'prg_bytes':path.stat().st_size,
                                                 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
disk = LAUNCHER/'desktop.d64'
shutil.copyfile(OUT/'uos128.d64', disk)
subprocess.run(['c1541', '-attach', str(disk), '-delete', 'browse',
                '-write', str(OUT/'desktop.prg'), 'browse',
                '-write', str(OUT/'files.prg'), 'files'], check=True, capture_output=True)
boot = LAUNCHER/'boot'
boot.mkdir(exist_ok=True)
subprocess.run(['64tass','-a','-B','-D','NATIVE_DESKTOP_BOOT=1',str(ROOT/'src/native/uos128.asm'),
                '-o',str(boot/'uos128.prg'),'-l',str(boot/'uos128.sym'),'-L',str(boot/'uos128.lst')],
               check=True,capture_output=True)
import re
symbols={m[1]:int(m[2],16) for m in re.finditer(r'^(\w+)\s*=\s*\$([0-9a-f]+)',(boot/'uos128.sym').read_text(),re.M)}
layout=dict(main_end=symbols['native_code_end'],low_end=symbols['native_low_end'],
            service_end=symbols['native_service_end'],load_end=symbols['native_load_end'])
assert layout['main_end']<=0x3800 and layout['low_end']<=0x1c00 and layout['service_end']<=0x5000
assert layout['load_end']<=0x6000
boot_disk=LAUNCHER/'desktop-boot.d64'
shutil.copyfile(disk,boot_disk)
subprocess.run(['c1541','-attach',str(boot_disk),'-delete','u','-write',str(boot/'uos128.prg'),'u'],
               check=True,capture_output=True)
for selected in range(3):
    (LAUNCHER/f'expected-{selected}.bin').write_bytes(surface(selected))
report = dict(main_integrated=False, physical_hardware_io=False, images=images,
              kernel_sha256=hashlib.sha256((OUT/'uos128.prg').read_bytes()).hexdigest(),
              disk_sha256=hashlib.sha256(disk.read_bytes()).hexdigest(),
              surface_pages=36, rectangles=len(OPS), labels=len(TEXT),
              boot_kernel_sha256=hashlib.sha256((boot/'uos128.prg').read_bytes()).hexdigest(),
              boot_disk_sha256=hashlib.sha256(boot_disk.read_bytes()).hexdigest(),boot_layout=layout)
(LAUNCHER/'build.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
