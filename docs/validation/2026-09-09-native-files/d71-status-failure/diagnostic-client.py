#!/usr/bin/env python3
"""Native IEC stream integration through a disk-loaded client in x128."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import ci_fm as ci
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from native_files_check import NativeFiles,prepare,workflow
from native_capture import wait
from hwlib import lst_symbol


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--format',choices=('d64','d71','d81'),default='d64')
    parser.add_argument('--status-delay',action='store_true',help='diagnostic: delay only the emulator copy before transfer DOS status')
    parser.add_argument('--status-at-close-only',action='store_true',help='diagnostic: check DOS on open/close, IEC status on each transfer')
    args=parser.parse_args();fmt=('d64','d71','d81').index(args.format)
    work=Path(tempfile.mkdtemp(prefix='uos-native-files-iec-'))
    print(f'Native IEC evidence: {work}',flush=True)
    disk,fixtures=prepare(work,fmt=fmt)
    data_disk=work/('data.'+args.format) if fmt else disk
    quiet=.5 if fmt else .02
    open_quiet=5 if fmt else .02
    report=dict(passed=False,kernel_sha256=hashlib.sha256((ROOT/'target/native/uos128.prg').read_bytes()).hexdigest(),
                test_disk_sha256=hashlib.sha256(disk.read_bytes()).hexdigest(),format=args.format,
                data_disk_sha256=hashlib.sha256(data_disk.read_bytes()).hexdigest(),
                observation_quiet_seconds=dict(transfer=quiet,open=open_quiet))
    def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    xv=ci.cbm.Xvfb();log=(work/'vice.log').open('w')
    extra=['-9',str(data_disk),'-drive9true','-drive9type',('1541','1571','1581')[fmt]] if fmt else []
    process=subprocess.Popen(['x128','-default','-8',str(disk),'-drive8true','-drive8type','1541',*extra,
                              '-sounddev','dummy','-jamaction','0','-warp','-binarymonitor',
                              '-binarymonitoraddress',f'ip4://127.0.0.1:{port}'],
                             env=dict(os.environ,DISPLAY=xv.display,__EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL),
                             stdout=log,stderr=subprocess.STDOUT)
    mon=None
    try:
        deadline=time.monotonic()+30
        while mon is None:
            assert process.poll() is None
            try:mon=ci.Monitor(port=port)
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        client=NativeFiles(mon,work,device=9 if fmt else 8,fmt=fmt,quiet=quiet,open_quiet=open_quiet)
        wait(lambda:client.read_ram(0x1c13,6)==b'UOS128' and client.read_ram(0x3d12)==b'\1','native file boot',60)
        client.key(ord('C'),expected=None)
        assert client.read_ram(0x3d20)==bytes([32]) and client.read_ram(0x3d23)==b'\2'
        if args.status_delay:
            status=lst_symbol('native/uos128','fs_drive_status')
            site=lst_symbol('native/uos128','fs_transfer_status')+8
            assert client.read_ram(site,3)==b'\x20'+status.to_bytes(2,'little')
            assembly=work/'delay.asm'
            assembly.write_text('*=$1800\npha\ntxa\npha\ntya\npha\nldx #0\nouter: ldy #0\ninner: dey\nbne inner\ndex\nbne outer\npla\ntay\npla\ntax\npla\njmp $'+f'{status:04x}'+'\n')
            patch=work/'delay.prg'
            subprocess.run(['64tass','-a',str(assembly),'-o',str(patch)],check=True,capture_output=True)
            client.put(0x1800,patch.read_bytes()[2:]);client.put(site,b'\x20\0\x18')
            report['diagnostic_patch']=dict(site=site,code=patch.read_bytes().hex())
        if args.status_at_close_only:
            status=lst_symbol('native/uos128','fs_drive_status')
            site=lst_symbol('native/uos128','fs_transfer_status')+8
            assert client.read_ram(site,3)==b'\x20'+status.to_bytes(2,'little')
            client.put(site,b'\xea'*3)
            report['diagnostic_patch']=dict(site=site,code='eaeaea')
        workflow(client,fixtures,report,save)
        out=work/'copied-c1541.seq'
        subprocess.run(['c1541','-attach',str(data_disk),'-read','copy,s,r',str(out)],check=True,capture_output=True)
        assert out.read_bytes()==fixtures['source']
        report.update(passed=True,c1541_copy_matches=True)
        print('PASS: native IEC copy over 64 KiB, file types, EOF, exclusive create and app cleanup',flush=True)
    except BaseException as error:
        report['error']=str(error)
        if mon:
            try:
                (work/'failure-files.bin').write_bytes(bytes(mon.read_mem(0x3d80,0x3de3)))
                (work/'failure-app.bin').write_bytes(bytes(mon.read_mem(0x6000,0x6fff)))
                (work/'failure-kernel.bin').write_bytes(bytes(mon.read_mem(0x1c00,0x37ff)))
            except Exception as diagnostic:report['diagnostic_error']=str(diagnostic)
        raise
    finally:
        save();process.terminate();process.wait(timeout=10);xv.stop();log.close()


if __name__=='__main__':main()
