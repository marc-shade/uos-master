#!/usr/bin/env python3
"""Audit module manifests, lifecycle captures, source identity and warm reuse."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ARCHIVE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ARCHIVE/'oracle'))
from native_image import validate as validate_app
from native_module import validate

parser=argparse.ArgumentParser()
parser.add_argument('--record',action='store_true')
parser.add_argument('--emulator-only',action='store_true');args=parser.parse_args()
read=lambda path:json.loads(path.read_text())
digest=lambda data:hashlib.sha256(data).hexdigest()
native=ARCHIVE/'package/clean/target/native'
app=(native/'editor.prg').read_bytes();module=(native/'edpick.prg').read_bytes()
info=validate(module,app);parent=validate_app(app)
assert parent['pages']==79 and parent['window']==info['origin']==0x90ce
assert info['bytes']==7722 and info['origin']+info['bytes']==0xaef8
assert info['parent_crc16']==parent['crc16']
cpu=read(ARCHIVE/'cpu-modules.json');editor=read(ARCHIVE/'cpu-module-editor.json')
assert cpu['passed'] and len(cpu['cases'])==109
assert editor['passed'] and len(editor['cases'])==12
assert set(editor['cases'])=={f'{source}-{fault}-retry-warm-save'
    for source in ('iec','usb1','usb2') for fault in ('missing','crc','short','parent')}
images=read(ARCHIVE/'images.json')
assert cpu['kernel_sha256']==images['uos128.prg']['sha256']
assert all(sha==images[name]['sha256'] for name,sha in editor['images'].items())
listings={name:(native/(name+'.lst')).read_text() for name in ('uos128','editor')}
def address(app,name):
    match=re.search(r'^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?'+re.escape(name)+r':',listings[app],re.M)
    if match:return int(match[1],16)
    match=re.search(r'^'+re.escape(name)+r'\s*=\s*\$([0-9a-fA-F]+)\s*$',(native/'uos128.sym').read_text(),re.M)
    assert match,name
    return int(match[1],16)
token_address=address('editor','ed_picker_token')
source_address=address('uos128','m_source_device')
folders=[f'emulator-editor-{fmt}' for fmt in ('d64','d71','d81')]
if not args.emulator_only:folders+=['hardware','hardware-iec']
observations=[]
for folder in folders:
    directory=ARCHIVE/folder;report=read(directory/'report.json');assert report['passed']
    captures={item['label']:item for item in report['captures']}
    def captured(label,origin,count):
        record=captures[label]
        assert (record['mode'],record['bank'],record['address'],record['count'])==(0,0,origin,count)
        assert record['restored']
        data=(directory/(label+'.bin')).read_bytes();assert len(data)==count
        return data
    states=report['modules'];assert [item['state'] for item in states]==[0,3,2,3,2]
    assert states[0]['token']==0 and len({item['token'] for item in states[1:]})==1
    expected_source=(1,3,len(report['private_directory'].encode())+1) if folder=='hardware' else (8,0,0)
    for item in states:
        label=item['label'];state=item['state']
        assert all(item[key]==value for key,value in info.items())
        raw=captured(label+'-state',0x3d17,5)
        assert raw==item['token'].to_bytes(3,'little')+bytes([0,state])
        assert bool(item['token'])==bool(state)
        assert captured(label+'-parent',0x3d60,32)==app[2:34]
        header=captured(label+'-header',info['origin'],16)
        assert header==(module[2:18] if state else bytes(16))
        if state:
            assert captured(label+'-manifest',0x3d50,16)==header
            assert captured(label+'-token',token_address,3)==raw[:3]
        source=captured(label+'-source',source_address,3)
        assert tuple(source)==expected_source
        assert tuple(source)==(item['source_device'],item['source_format'],item['source_parent_length'])
    elapsed=report['module_cold_picker_seconds']
    assert elapsed>0 and any(event.get('key')==9 and event['elapsed_seconds']==elapsed for event in report['events'])
    observations.append(dict(folder=folder,states=[item['state'] for item in states],
        token=states[1]['token'],source_device=expected_source[0],source_format=expected_source[1],
        source_parent_length=expected_source[2],cold_picker_seconds=elapsed,
        same_token_after_cancel=True,original_core_header_intact=True))
result=dict(passed=True,cpu_module_cases=109,cpu_editor_cases=12,module=info,
    app_sha256=digest(app),module_sha256=digest(module),workflows=observations,
    qualification='CPU-observed manifests, source fields, tokens and lifecycle match the packaged build. Cold picker time includes module loading and the first directory scan. Loaded module body bytes are not independently recaptured in these observations.',
    full_os_complete=False)
destination=ARCHIVE/('module-emulator-verification.json' if args.emulator_only else 'module-verification.json')
if args.record:destination.write_text(json.dumps(result,indent=2)+'\n')
else:assert result==read(destination)
print(f'PASS: {len(observations)} module workflows; original core/source, cold load and unchanged warm token')
