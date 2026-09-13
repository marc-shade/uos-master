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
from native_module import seal as seal_module

ROOT = Path(__file__).resolve().parent
OUT = ROOT/'target/native'


def build(*, out=None, desktop_boot=False):
    out = OUT if out is None else Path(out)
    out.mkdir(parents=True,exist_ok=True)
    for source,name in [('uos128','uos128'),('boot','boot'),('calc','calc'),('browser','browse'),('editor','editor')]:
        branch=['-B'] if source in ('uos128','browser','editor') or (source=='calc' and desktop_boot) else []
        defines=['-D','NATIVE_DESKTOP_BOOT=1'] if source=='uos128' and desktop_boot else []
        if source=='calc' and desktop_boot:defines=['-D','NATIVE_CALC_GRAPHICS=1']
        labels=['-l',str(out/'uos128.sym')] if source=='uos128' else []
        subprocess.run(['64tass','-a',*defines,*branch,*labels,str(ROOT/'src/native'/f'{source}.asm'),
                        '-o',str(out/f'{name}.prg'),'-L',str(out/f'{name}.lst')],check=True)
    (out/'calc.prg').write_bytes(seal((out/'calc.prg').read_bytes()))
    (out/'browse.prg').write_bytes(seal((out/'browse.prg').read_bytes()))
    editor=(out/'editor.prg').read_bytes()
    core_size=int.from_bytes(editor[10:12],'little')
    core=seal(editor[:core_size+2])
    (out/'editor.prg').write_bytes(core)
    position=core_size+2
    for name in ('edpick','edfind'):
        size=int.from_bytes(editor[position+8:position+10],'little')
        module=(0x6000+core_size).to_bytes(2,'little')+editor[position:position+size]
        (out/f'{name}.prg').write_bytes(seal_module(module,core))
        position+=size
    assert position==len(editor),'unexpected trailing editor module data'
    disk = out/'uos128.d64'
    subprocess.run(['c1541','-format','uos128,01','d64',str(disk)],check=True,capture_output=True)
    data = bytearray(disk.read_bytes())
    boot = (out/'boot.prg').read_bytes()
    assert boot[:2] == b'\0\x0b' and len(boot) == 258
    # The boot block is outside file chains. Reserve it in the BAM before
    # adding files, so ordinary disk allocation cannot overwrite it later.
    bam = 17*21*256
    assert data[bam+4] == 21 and data[bam+5] & 1
    data[bam+4] -= 1
    data[bam+5] &= 0xfe
    data[:256] = boot[2:]
    disk.write_bytes(data)
    subprocess.run(['c1541','-attach',str(disk),'-write',str(out/'uos128.prg'),'u'],
                   check=True,capture_output=True)
    subprocess.run(['c1541','-attach',str(disk),'-write',str(out/'calc.prg'),'calc'],
                   check=True,capture_output=True)
    subprocess.run(['c1541','-attach',str(disk),'-write',str(out/'browse.prg'),'browse'],
                   check=True,capture_output=True)
    subprocess.run(['c1541','-attach',str(disk),'-write',str(out/'editor.prg'),'editor'],
                   check=True,capture_output=True)
    subprocess.run(['c1541','-attach',str(disk),'-write',str(out/'edpick.prg'),'edpick.prg'],
                   check=True,capture_output=True)
    subprocess.run(['c1541','-attach',str(disk),'-write',str(out/'edfind.prg'),'edfind.prg'],
                   check=True,capture_output=True)
    assert disk.read_bytes()[:256] == boot[2:]
    report = {p.name:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
              for p in (out/'uos128.prg',out/'boot.prg',out/'calc.prg',out/'browse.prg',out/'editor.prg',out/'edpick.prg',out/'edfind.prg',disk)}
    (out/'images.json').write_text(json.dumps(report,indent=2)+'\n')
    symbols=(out/'uos128.sym').read_text()
    def address(name):
        match=re.search(r'^'+re.escape(name)+r'\s*=\s*\$([0-9a-fA-F]+)\s*$',symbols,re.M)
        assert match,name
        return int(match[1],16)
    layout=dict(main_start=0x1c01,main_end=address('native_code_end'),
                low_start=address('native_low_start'),low_end=address('native_low_end'),
                low_padded_end=address('native_low_padded_end'),low_limit=0x1c00,
                metadata_start=0x3800,metadata_end=address('native_metadata_end'),
                staging_start=address('native_low_image'),load_end=address('native_load_end'),
                service_start=address('native_service_start'),service_end=address('native_service_end'),
                module_code_start=address('module_load'),module_code_end=address('native_module_code_end'),
                module_context_start=address('module_source'),module_context_end=address('native_module_context_end'),
                module_gate_start=address('module_start'),module_gate_end=address('native_module_gate_end'),
                display_gate_start=address('display_show'),display_gate_end=address('native_display_gate_end'),
                display_show_start=address('display_prepare'),display_show_end=address('native_display_show_end'),
                display_restore_start=address('display_restore'),display_restore_end=address('native_display_restore_end'),
                display_close_start=address('display_close'),display_close_end=address('native_display_close_end'),
                source_path_start=0x3f00,source_path_end=0x4000,
                query_start=address('ultimate_query'),query_end=address('native_query_end'),
                keyboard_start=address('native_keyboard_init'),keyboard_end=address('native_keyboard_end'),
                keyin_start=address('native_keyin'),keyin_end=address('native_keyin_end'),
                command_start=address('ultimate_command'),command_end=address('native_command_end'),
                keycheck_start=address('native_keycheck'),keycheck_end=address('native_keycheck_end'),
                nmi_gate_start=address('native_nmi_gate'),nmi_gate_end=address('native_nmi_gate_end'),
                service_limit=0x5000,app_base=0x6000,managed_pages=426)
    assert layout['main_end']<=layout['metadata_start'] and layout['low_padded_end']<=layout['low_limit']
    assert layout['metadata_end']<=layout['service_start']<layout['service_end']<=layout['service_limit']
    assert layout['service_limit']<=layout['staging_start'] and layout['load_end']<=layout['app_base']
    assert layout['load_end']-layout['staging_start']==layout['low_padded_end']-layout['low_start']
    assert layout['module_code_start']==address('nu_code_end')<layout['module_code_end']<=0x4a00
    assert 0x4f20==layout['module_context_start']<layout['module_context_end']<=0x5000
    assert layout['query_start']==0x4b00<layout['query_end']<=0x4bfc
    assert layout['query_end']==layout['command_start']<layout['command_end']<=0x4bfc
    assert layout['command_end']==layout['keyboard_start']<layout['keyboard_end']<=0x4bfc
    assert layout['display_show_end']==layout['keyin_start']<layout['keyin_end']<=0x4a00
    assert layout['main_start']<layout['keycheck_start']<layout['keycheck_end']<=0x3800
    assert layout['nmi_gate_start']==0x1bf0 and layout['nmi_gate_end']==0x1bf8
    assert layout['low_start']<layout['module_gate_start']<layout['module_gate_end']<=layout['low_limit']
    for start,end,next_boundary in (('display_gate_start','display_gate_end','metadata_start'),
                                   ('display_show_start','display_show_end',None),
                                   ('display_restore_start','display_restore_end','service_limit'),
                                   ('display_close_start','display_close_end','low_limit')):
        assert layout[start]<layout[end]<=(layout[next_boundary] if next_boundary else 0x4a00)
    assert report['uos128.prg']['bytes']==layout['load_end']-layout['main_start']+2
    (out/'layout.json').write_text(json.dumps(layout,indent=2)+'\n')
    print(f'Native C128 boot disk: {disk}')


if __name__ == '__main__':
    build()
