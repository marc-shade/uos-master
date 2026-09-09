#!/usr/bin/env python3
"""Boot the native C128 disk and exercise its memory workspace in x128."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import ci_fm as ci

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from native_capture import NativeCapture, expected_screen
READY, KEYS, RESULT = 0x3d12, 0x3d13, 0x3d16


def main():
    work = Path(tempfile.mkdtemp(prefix='uos-native-x128-'))
    print(f'Native emulator evidence: {work}',flush=True)
    stock = ROOT/'target/native/uos128.d64'
    disk = work/'native.d64'; shutil.copy2(stock,disk)
    report = dict(disk_sha256=hashlib.sha256(stock.read_bytes()).hexdigest(),passed=False)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    xv = ci.cbm.Xvfb()
    log = (work/'vice.log').open('w')
    process = subprocess.Popen(['x128','-default','-8',str(disk),'-drive8true',
                                '-drive8type','1541','-sounddev','dummy','-jamaction','0',
                                '-warp','-binarymonitor','-binarymonitoraddress',f'ip4://127.0.0.1:{port}'],
                               env=dict(os.environ,DISPLAY=xv.display,__EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL),
                               stdout=log,stderr=subprocess.STDOUT)
    mon=None
    try:
        deadline=time.monotonic()+30
        while mon is None:
            assert process.poll() is None,'x128 exited'
            try:mon=ci.Monitor(port=port)
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        banks=mon.banks();mon.resume();report['monitor_banks']=banks

        def read(address,count=1,bank=0):
            data=bytes(mon.read_mem(address,address+count-1,bank=bank));mon.resume();return data

        def wait(predicate,label,seconds=30):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                if predicate():return
                time.sleep(.1)
            raise AssertionError(label)

        wait(lambda:read(0x1c13,6)==b'UOS128' and read(READY)==b'\1','native boot marker',60)
        report['mmu']=read(0xd500,12).hex()
        report['mailbox']=read(0x3d00,32).hex()
        report['kernal_gateways']=read(0x2a2,0x5a).hex()
        for name in ('ram00','ram01'):
            (work/(name+'-vectors.bin')).write_bytes(read(0xff00,256,bank=banks[name]))
        (work/'vic-initial.bin').write_bytes(read(0x400,1000))
        assert read(0x3d0e,3)==bytes([191,251,32]),report
        assert not read(0xd505)[0]&0x40,'entered C64 mode'
        capture=NativeCapture(mon,work,quiet=.2)
        report['captures']=capture.records

        def key(value):
            wait(lambda:read(READY)==b'\1' and read(0xd0)==b'\0','input ready')
            previous=int.from_bytes(read(KEYS,2),'little')
            mon.write_mem(READY,b'\0')
            mon.write_mem(0x34a,bytes([value]));mon.write_mem(0xd0,b'\1');mon.resume()
            wait(lambda:int.from_bytes(read(KEYS,2),'little')==previous+1 and read(READY)==b'\1',f'key {value:02x}',60)
            assert read(RESULT)==b'\0',read(0x3d00,32).hex()

        allocations=[]
        def check_blocks():
            for bank,page in allocations:
                expected=bytes((i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(8192))
                actual=read(page*256,8192,bank=banks[f'ram0{bank}'])
                assert actual==expected,f'bank {bank} independent byte comparison'
                (work/f'bank-{bank}-data.bin').write_bytes(actual)

        for bank,keycode in ((0,ord('1')),(1,ord('2'))):
            key(keycode);key(ord('A'))
            allocations.append((bank,read(0x3d03)[0]))
            key(ord('W'));key(ord('V'));check_blocks()
            pages=read(0x3d0e,2)
            assert pages[bank]==(191 if bank==0 else 251)-32
            print(f'PASS: native bank {bank} allocation, 8192-byte write and verify',flush=True)
        # Both live blocks must retain their distinct contents across switches.
        key(ord('1'));key(ord('V'));check_blocks();key(ord('F'))
        key(ord('2'));key(ord('V'));key(ord('F'))
        assert read(0x3d0e,3)==bytes([191,251,32])
        vic=read(0x400,1000);vdc=read(0,2000,bank=banks['vdc'])
        (work/'vic-final.bin').write_bytes(vic);(work/'vdc-final.bin').write_bytes(vdc)
        assert vic==expected_screen(40,1) and vdc==expected_screen(80,1),'complete native screens differ'
        for bank,page in allocations:
            # Released bytes remain observable until the next allocation. Use
            # the independent capture path that will run on physical hardware.
            actual=capture.capture(f'probe-bank-{bank}',bank=bank,address=page*256,count=2000)
            assert actual==read(page*256,2000,bank=banks[f'ram0{bank}'])
        observed=capture.capture('probe-vdc',mode=1)
        assert observed==vdc,'native IRQ VDC capture differs from monitor memory'
        key(ord('1'));key(ord('2'))  # foreground still consumes keys after captures
        assert hashlib.sha256(stock.read_bytes()).hexdigest()==report['disk_sha256']
        report.update(passed=True,native_mode=True,banks=2,bytes_per_bank=8192,
                      all_allocations_released=True,stock_disk_unchanged=True)
        print('PASS: native cold boot, both RAM banks, retained independent blocks and release',flush=True)
    except BaseException as error:
        report['error']=str(error)
        if mon:
            try:
                report['mmu_failure']=bytes(mon.read_mem(0xd500,0xd50b)).hex()
                report['mailbox_failure']=bytes(mon.read_mem(0x3d00,0x3d1f)).hex()
                (work/'vic-failure.bin').write_bytes(bytes(mon.read_mem(0x400,0x7e7)))
                report['registers_failure']=mon._recv(mon._send(0x31,b'\0'))[1].hex()
            except Exception as diagnostic_error:report['diagnostic_error']=str(diagnostic_error)
        raise
    finally:
        (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        process.terminate();process.wait(timeout=10);xv.stop();log.close()


if __name__=='__main__':main()
