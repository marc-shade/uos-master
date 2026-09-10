#!/usr/bin/env python3
"""Read-only hardware observations after a terminal native boot timeout."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

sys.dont_write_bytecode=True
sys.path.insert(0,'/home/marc/geos128/uos')
from hw_ultimate_check import ObservingUltimate
from hwlib import desk_tick

destination=Path(tempfile.mkdtemp(prefix='uos-fields-boot-diagnostic-'))
device=ObservingUltimate(timeout=60)
report=dict(hardware_writes=False,expected_desktop_vector=desk_tick(),observations={})
program=Path('/home/marc/geos128/uos/target/uos.prg').read_bytes()
program_address=int.from_bytes(program[:2],'little')
try:
    print('Read-only evidence:',destination,flush=True)
    for name,call in (('version',device.version),('drives',device.drives)):
        report[name]=json.loads(call())
    for name,endpoint in (('info','/v1/info'),('menu-screen','/v1/machine:menu_screen')):
        status,data=device._call('GET',endpoint)
        (destination/(name+'.response')).write_bytes(data)
        report[name]=dict(status=status,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    report['uploaded_file_info']={}
    for name in ('temp0096','temp0097','temp0098','temp0099','temp009A','temp009B','temp009C','temp009D','temp009E'):
        status,data=device._call('GET','/v1/files/Temp/'+name+':info')
        (destination/(name+'-info.response')).write_bytes(data)
        report['uploaded_file_info'][name]=dict(status=status,body=data.decode('utf-8','replace'))
    for name,address,count in (('low-ram',0,1024),('vic-text',0x400,1000),('legacy-entry',0x800,256),
                               ('legacy-program',program_address,len(program)-2),
                               ('native-entry',0x1c00,64),('native-mailbox',0x3d00,228),
                               ('legacy-settings-direct',0x7350,9)):
        data=device.read_mem(address,count)
        (destination/(name+'.bin')).write_bytes(data)
        report['observations'][name]=dict(address=address,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        if count<256:report['observations'][name]['hex']=data.hex()
    low=(destination/'low-ram.bin').read_bytes()
    report['observed_desktop_vector']=int.from_bytes(low[0x33c:0x33e],'little')
    observed=(destination/'legacy-program.bin').read_bytes()
    report['deployed_program_differences']=[i for i,(a,b) in enumerate(zip(observed,program[2:])) if a!=b]
    time.sleep(1)
    later=device.read_mem(0,1024);(destination/'low-ram-later.bin').write_bytes(later)
    report['low_ram_changed_offsets']=[i for i,(a,b) in enumerate(zip(low,later)) if a!=b]
    print(json.dumps({k:v for k,v in report.items() if k not in ('observations','deployed_program_differences')},indent=2))
finally:
    (destination/'report.json').write_text(json.dumps(report,indent=2)+'\n')
