#!/usr/bin/env python3
"""Inspect native display/IRQ prerequisites on a private emulator disk."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT=Path('/home/marc/geos128/uos')
sys.path.insert(0,str(ROOT/'tests'))
import ci_fm as ci
work=Path(tempfile.mkdtemp(prefix='uos-native-display-probe-',dir='/var/tmp/arc-scratch'))
shutil.copyfile(__file__,work/'probe.py')
disk=work/'native.d64'
source=ROOT/'target/native/uos128.d64'
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
shutil.copyfile(source,disk)
report=dict(passed=False,purpose='Read-only native display/IRQ prerequisites',
            physical_hardware_io=False,graphics_mode_tested=False,
            source_disk_sha256=digest(source),observations=[])
print(f'Native display probe evidence: {work}',flush=True)
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
xv=ci.cbm.Xvfb()
log=(work/'vice.log').open('w')
process=None
mon=None
command=['x128','-default','-8',str(disk),'-drive8true','-drive8type','1541',
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
    report['banks']=mon.banks()
    mon.resume()
    def read(at,count=1):
        data=bytes(mon.read_mem(at,at+count-1));mon.resume();return data
    deadline=time.monotonic()+60
    while read(0x1c13,6)!=b'UOS128' or read(0x3d12)!=b'\1':
        assert time.monotonic()<deadline,'native boot timeout'
        time.sleep(.1)
    for i in range(3):
        record={}
        for name,at,count in (('vic',0xd000,64),('mmu',0xd500,12),('cia2',0xdd00,16),
                              ('jiffy',0xa0,3),('heap_mailbox',0x3d00,32),
                              ('irq_vector',0x314,2),('kernal_vectors',0x300,80)):
            data=read(at,count)
            (work/f'{name}-{i}.bin').write_bytes(data)
            record[name]=data.hex()
        report['observations'].append(record)
        time.sleep(.2)
    assert all(bytes.fromhex(r['mmu'])[0]==0x0e for r in report['observations'])
    assert all(not bytes.fromhex(r['mmu'])[5]&0x40 for r in report['observations'])
    assert all(bytes.fromhex(r['heap_mailbox'])[14:17]==bytes([175,251,32]) for r in report['observations'])
    report['jiffy_values_differ']=len({r['jiffy'] for r in report['observations']})>1
    report['vic_interrupt_masks']=[bytes.fromhex(r['vic'])[0x1a]&15 for r in report['observations']]
    report['common_and_vic_bank_registers']=[bytes.fromhex(r['mmu'])[6] for r in report['observations']]
    report['source_disk_unchanged']=digest(source)==report['source_disk_sha256']
    report['private_disk_unchanged']=digest(disk)==report['source_disk_sha256']
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
print(json.dumps({key:report[key] for key in ('passed','jiffy_values_differ','vic_interrupt_masks',
    'common_and_vic_bank_registers','source_disk_unchanged','graphics_mode_tested')},indent=2),flush=True)

