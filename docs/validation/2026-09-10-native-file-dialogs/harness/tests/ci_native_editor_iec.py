#!/usr/bin/env python3
"""Native editor on actual C128 ROM and true IEC drive emulation."""
import argparse
import hashlib
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
from native_editor_check import EditorClient,prepare_editor,editor_workflow
from native_capture import wait
from native_files_check import exact_d64_files


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--format',choices=('d64','d71','d81'),default='d64')
    args=parser.parse_args();fmt=('d64','d71','d81').index(args.format)
    work=Path(tempfile.mkdtemp(prefix='uos-native-editor-iec-'))
    print(f'Native editor emulator evidence: {work}',flush=True)
    disk,data_disk,fixtures=prepare_editor(work,fmt)
    initial=data_disk.read_bytes();(work/('initial.'+args.format)).write_bytes(initial)
    report=dict(passed=False,build=json.loads((ROOT/'target/native/images.json').read_text()),format=args.format,
                initial_disk_sha256=hashlib.sha256(initial).hexdigest())
    def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    xv=ci.cbm.Xvfb();log=(work/'vice.log').open('w')
    extra=['-9',str(data_disk),'-drive9true','-drive9type',('1541','1571','1581')[fmt]] if data_disk!=disk else []
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
        client=EditorClient(mon,work)
        wait(lambda:client.read(0x1c13,6)==b'UOS128' and client.read(0x3d12)==b'\1','native editor boot',60)
        editor_workflow(client,disk,data_disk,fixtures,fmt,report,save)
        want=(work/'saved-expected.seq').read_bytes()
        for name,data in {**fixtures,'saved':want}.items():
            if not data:continue
            out=work/(name+'-c1541.seq')
            subprocess.run(['c1541','-attach',str(data_disk),'-read',name+',s,r',str(out)],check=True,capture_output=True)
            assert out.read_bytes()==data,name
        if not fmt:
            expected=exact_d64_files(initial);expected[b'SAVED']=(1,want)
            assert exact_d64_files(data_disk.read_bytes())==expected
        assert report['build']==json.loads((ROOT/'target/native/images.json').read_text())
        report.update(passed=True,independent_export_matches=True,nonempty_fixtures_unchanged=True,
                      final_disk_sha256=hashlib.sha256(data_disk.read_bytes()).hexdigest())
        print('PASS: native editor, ROM key expansion, dual screens, over-64-KiB edit/save/reopen and complete cleanup',flush=True)
    except BaseException as error:
        report['error']=str(error);report['emulator_exit_at_failure']=process.poll()
        report['display']=xv.display;report['display_exit_at_failure']=xv.proc.poll()
        if mon:
            try:
                (work/'failure-vic.bin').write_bytes(bytes(mon.read_mem(0x400,0x7e7)))
                (work/'failure-app.bin').write_bytes(bytes(mon.read_mem(0x6000,0x9fff)))
                (work/'failure-context.bin').write_bytes(bytes(mon.read_mem(0x3d00,0x3de3)))
            except Exception as diagnostic:report['diagnostic_error']=str(diagnostic)
        raise
    finally:
        save();process.terminate();process.wait(timeout=10);xv.stop();log.close()


if __name__=='__main__':main()
