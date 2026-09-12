#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from native_image import seal,validate
from graphics_oracle import OPS,TEXT_OPS,surface
from graphics.font import font

ROOT=Path(__file__).resolve().parent;client=ROOT/'client'
shutil.copyfile(ROOT/'graphics/graphics-core.inc',client/'graphics-core.inc')
shutil.copyfile(ROOT/'graphics/text-core.inc',client/'text-core.inc')
(client/'font8.bin').write_bytes(font())
data=[]
for x,y,pen,label in TEXT_OPS:
    data.extend([f'        .sint {x},{y}',f'        .byte {pen},{len(label)}',
                 '        .byte '+','.join(str(code) for code in label)])
(client/'text-commands.inc').write_text('\n'.join(data)+'\n')
subprocess.run(['64tass','-a','-B',str(client/'display.asm'),'-o',str(client/'DISPLAY.PRG'),
    '-l',str(client/'display.sym'),'-L',str(client/'display.lst')],check=True,capture_output=True)
program=seal((client/'DISPLAY.PRG').read_bytes());(client/'DISPLAY.PRG').write_bytes(program)
expected=surface();(client/'expected-surface.bin').write_bytes(expected)
report=dict(client=validate(program),program_sha256=hashlib.sha256(program).hexdigest(),
    expected_surface_sha256=hashlib.sha256(expected).hexdigest(),operations=OPS,
    text_operations=[dict(x=x,y=y,pen=pen,text_hex=label.hex()) for x,y,pen,label in TEXT_OPS],
    core_sha256=hashlib.sha256((client/'graphics-core.inc').read_bytes()).hexdigest())
(client/'build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['client']))
