#!/usr/bin/env python3
"""Exercise an explicitly restored native VIC client on a disposable disk."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode=True
ROOT=Path('/home/marc/geos128/uos')
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import ci_fm as ci
from native_capture import expected_screen,wait

work=Path(tempfile.mkdtemp(prefix='uos-native-vic-placement-',dir='/var/tmp/arc-scratch'))
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=ROOT/'target/native/uos128.d64'
report=dict(passed=False,physical_hardware_io=False,kernel_display_lease=False,
            source_disk_sha256=digest(source),events=[],observations=[],screens=[])
print(f'Native VIC placement evidence: {work}',flush=True)
for name in ('display.asm','display.sym','display.lst','DISPLAY.PRG','run.py'):
    shutil.copyfile(HERE/name,work/name)
shutil.copyfile(ROOT/'src/native/api.inc',work/'api.inc')
symbols={m[1]:int(m[2],16) for m in re.finditer(r'^(\w+)\s*=\s*\$([0-9a-f]+)',(work/'display.sym').read_text(),re.M)}
disk=work/'native.d64';shutil.copyfile(source,disk)
subprocess.run(['c1541','-attach',str(disk),'-delete','calc','-write',str(work/'DISPLAY.PRG'),'calc'],
               check=True,capture_output=True)
report['private_disk_start_sha256']=digest(disk)
report['prototype_sha256']=digest(work/'DISPLAY.PRG')
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
xv=ci.cbm.Xvfb();process=None;mon=None
log=(work/'vice.log').open('w')
command=['x128','-default','-40col','-8',str(disk),'-drive8true','-drive8type','1541',
         '-VDC16KB','-sounddev','dummy','-jamaction','0','-warp','-binarymonitor',
         '-binarymonitoraddress',f'ip4://127.0.0.1:{port}']
report['command']=command
try:
    process=subprocess.Popen(command,env=dict(os.environ,DISPLAY=xv.display,
        __EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL),stdout=log,stderr=subprocess.STDOUT)
    deadline=time.monotonic()+30
    while mon is None:
        assert process.poll() is None,'x128 exited'
        try:mon=ci.Monitor(port=port)
        except OSError:
            if time.monotonic()>deadline:raise
            time.sleep(.1)
    banks=mon.banks();report['banks']=banks;mon.resume()
    def read(at,count=1,bank=0):
        data=bytes(mon.read_mem(at,at+count-1,bank=bank));mon.resume();return data
    def ready():return read(0x3d12)==b'\1' and read(0xd0,2)==bytes(2)
    def key(value):
        wait(ready,'native foreground ready',120)
        before=int.from_bytes(read(0x3d13,2),'little');started=time.monotonic()
        mon.write_mem(0x3d12,b'\0');mon.write_mem(0x34a,bytes([value]));mon.write_mem(0xd0,b'\1');mon.resume()
        wait(lambda:ready() and int.from_bytes(read(0x3d13,2),'little')==(before+1)&65535,
             f'native key {value:02x} completion',120)
        report['events'].append(dict(key=value,elapsed_seconds=round(time.monotonic()-started,3)))
    def observation(label):
        record=dict(label=label)
        for name,at,count,bank in (('vic',0xd000,64,0),('mmu',0xd500,12,0),
                ('cia2',0xdd00,3,0),('text_mode',0xd7,3,0),('jiffy',0xa0,3,0),
                ('irq_vector',0x314,2,0),('heap',0x3800,0x600,banks['ram00']),
                ('app',0x3d20,13,0),('prototype',symbols['phase'],12,0)):
            data=read(at,count,bank);(work/f'{label}-{name}.bin').write_bytes(data)
            record[name]=data.hex()
        report['observations'].append(record)
        return record
    def screenshot(label):
        path=work/f'{label}.png'
        subprocess.run(['magick','import','-display',xv.display,'-window','root',str(path)],
                       check=True,capture_output=True)
    def screens(label,*,free=(175,251),slots=32,handle=bytes(4),result=0):
        for columns,at,bank in ((40,0x400,banks['ram00']),(80,0,banks['vdc'])):
            data=read(at,columns*25,bank);(work/f'{label}-{columns}.bin').write_bytes(data)
            assert data==expected_screen(columns,0,free,slots,handle,result),(label,columns)
        report['screens'].append(dict(label=label,columns=[40,80],free=free,slots=slots,
                                     handle=handle.hex(),result=result))
    wait(lambda:read(0x1c13,6)==b'UOS128' and ready(),'native workspace boot',60)
    before=observation('boot');screens('boot');screenshot('boot')
    assert bytes.fromhex(before['text_mode'])[1]==0
    assert before['irq_vector']=='65fa'
    baseline={name:before[name] for name in ('mmu','irq_vector')}
    expected_surface=b'\xaa'*8192+b'\xe6'*1024
    for label,exit_key in (('explicit-exit',0x1b),('normal-return',13)):
        key(ord('C'))
        assert read(symbols['phase'],3)==bytes([2,0,1]),read(symbols['phase'],3).hex()
        samples=[]
        for index in range(3):
            time.sleep(.2);record=observation(f'{label}-active-{index}');samples.append(record)
            vic=bytes.fromhex(record['vic']);cia=bytes.fromhex(record['cia2'])
            assert vic[0x11]&0x7f==0x3b and vic[0x16]&0x3f==8 and vic[0x18]&0xfe==0x80
            assert vic[0x1a]&15==1 and cia[0]&3==0 and cia[2]&3==3
            assert bytes.fromhex(record['text_mode'])[1]==255
            assert all(record[name]==value for name,value in baseline.items())
        assert len({r['jiffy'] for r in samples})==3,'jiffy stopped in bitmap mode'
        surface=read(0xc000,9216,banks['ram00']);(work/f'{label}-surface.bin').write_bytes(surface)
        assert surface==expected_surface,'VIC surface differs from the complete expected bytes'
        screenshot(label+'-bitmap')
        key(exit_key)
        after=observation(label+'-restored');screens(label+'-restored');screenshot(label+'-restored')
        assert read(0x3d20)==b'\0' and read(0x3d23)==b'\0'
        assert bytes.fromhex(after['text_mode'])[1]==0
        for name,value in baseline.items():assert after[name]==value
        av=bytes.fromhex(after['vic']);bv=bytes.fromhex(before['vic'])
        assert av[0x11]&0x7f==bv[0x11]&0x7f and av[0x16:0x19]==bv[0x16:0x19]
        assert bytes.fromhex(after['cia2'])[0]&3==bytes.fromhex(before['cia2'])[0]&3
        assert read(0x3800+0xc0,36)==bytes(36),'surface ownership leaked'
        print(f'PASS: {label}, complete surface, IRQ liveness and both consoles restored',flush=True)
    key(ord('A'));workspace_handle=read(0x3d04,4)
    screens('workspace-allocation',free=(143,251),slots=31,handle=workspace_handle)
    occupied=read(0xc000,9216,banks['ram00']);state=observation('before-refused-reservation')
    key(ord('C'))
    assert read(symbols['phase'],3)==bytes([1,2,0]),read(symbols['phase'],3).hex()
    failed=observation('refused-reservation')
    assert read(0xc000,9216,banks['ram00'])==occupied,'refused reservation changed surface bytes'
    assert bytes.fromhex(failed['text_mode'])[1]==0 and bytes.fromhex(failed['cia2'])[0]&3==3
    key(0x1b)
    screens('refused-restored',free=(143,251),slots=31,handle=workspace_handle,result=2)
    key(ord('F'));screens('all-released');observation('all-released');screenshot('all-released')
    report['surface_bytes_per_success']=9216
    report['successful_presentations']=2
    report['refused_reservation_preserved_existing_bytes']=True
    report['source_disk_unchanged']=digest(source)==report['source_disk_sha256']
    report['private_disk_unchanged']=digest(disk)==report['private_disk_start_sha256']
    assert report['source_disk_unchanged'] and report['private_disk_unchanged']
    report['passed']=True
finally:
    if mon:
        try:mon.quit_emulator()
        except (EOFError,OSError):pass
        mon.close()
    if process:
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate();process.wait(timeout=10)
    xv.stop();log.close()
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: disposable native VIC placement experiment',flush=True)
