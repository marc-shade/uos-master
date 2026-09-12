#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from native_image import seal,validate
from graphics_oracle import OPS,TEXT_OPS,CLIP_BOX,CLIP_TEXT,surface
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
data=[f'scene_commands_count={len(OPS)}']
for mode,coords,value in OPS:data.extend(['        .sint '+','.join(map(str,coords)),f'        .byte {mode},{value}'])
(client/'scene-commands.inc').write_text('\n'.join(data)+'\n')
x,y,pen,label=CLIP_TEXT
code=['draw_clip_text:','        ldx #7','clip_text_bounds:','        lda clip_box,x','        sta gfx_x0,x',
      '        dex','        bpl clip_text_bounds','        jsr gfx_set_clip','        bcs clip_text_return']
for index,value in enumerate((x,y)):
    code.extend([f'        lda #{value&255}',f'        sta gfx_x0+{index*2}',
                 f'        lda #{(value>>8)&255}',f'        sta gfx_x0+{index*2+1}'])
code.extend([f'        lda #{pen}','        sta gfx_pen',f'        lda #{len(label)}','        sta gfx_text_length',
             f'        ldx #{len(label)-1}','clip_text_copy:','        lda clip_label,x','        sta gfx_text_buffer,x',
             '        dex','        bpl clip_text_copy','        jmp gfx_text','clip_text_return:','        rts',
             'clip_box: .sint '+','.join(map(str,CLIP_BOX)),
             'clip_label: .byte '+','.join(map(str,label))])
(client/'clip-text.inc').write_text('\n'.join(code)+'\n')
subprocess.run(['64tass','-a','-B',str(client/'display.asm'),'-o',str(client/'DISPLAY.PRG'),
    '-l',str(client/'display.sym'),'-L',str(client/'display.lst')],check=True,capture_output=True)
program=seal((client/'DISPLAY.PRG').read_bytes());(client/'DISPLAY.PRG').write_bytes(program)
expected=surface();(client/'expected-surface.bin').write_bytes(expected)
report=dict(client=validate(program),program_sha256=hashlib.sha256(program).hexdigest(),
    expected_surface_sha256=hashlib.sha256(expected).hexdigest(),operations=OPS,
    text_operations=[dict(x=x,y=y,pen=pen,text_hex=label.hex()) for x,y,pen,label in TEXT_OPS],
    clip_demo=dict(box=CLIP_BOX,x=CLIP_TEXT[0],y=CLIP_TEXT[1],pen=CLIP_TEXT[2],text_hex=CLIP_TEXT[3].hex()),
    core_sha256=hashlib.sha256((client/'graphics-core.inc').read_bytes()).hexdigest())
(client/'build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['client']))
