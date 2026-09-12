#!/usr/bin/env python3
"""Fault the diagnostic lease and verify vector/code restoration and evidence."""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from native_input_trace import InputTrace,assemble


class Monitor:
    def __init__(self,expected):
        self.ram=bytearray((i*37+81)&255 for i in range(65536));r=self.ram
        r[0x1c13:0x1c19]=b'UOS128';r[0x3d11:0x3d13]=b'\0\1';r[0xd0:0xd2]=b'\0\0'
        r[0x3d20]=32;r[0x3d23]=2;r[0x3d91]=r[0x99]=0;r[0x3850:0x3858]=bytes(8)
        r[0x3d60:0x3d80]=(ROOT/'target/native-desktop/desktop.prg').read_bytes()[2:34]
        r[0x1c3b:0x1c3e]=expected;r[0x33c:0x33e]=b'\x00\xc7'
        self.writes=[];self.fail=False
    def read_mem(self,start,end):return self.ram[start:end+1]
    def resume(self):pass
    def write_mem(self,start,data):
        self.writes.append((start,bytes(data)))
        if self.fail and start==0x5000:
            self.fail=False;self.ram[start:start+128]=data[:128];raise OSError('injected partial trace write')
        self.ram[start:start+len(data)]=data


def run(work):
    _,expected=assemble(work)
    cases=[]
    for mode in ('ordinary','occupied','partial','corrupt'):
        folder=work/mode;folder.mkdir();mon=Monitor(expected);report={}
        if mode=='occupied':mon.ram[0x3850]=8
        if mode=='partial':mon.fail=True
        before=bytes(mon.ram)
        trace=InputTrace(mon,folder,lambda label:nullcontext(),report,lambda:None,quiet=0)
        try:trace.install()
        except (AssertionError,OSError):assert mode in ('occupied','partial')
        else:
            assert mode in ('ordinary','corrupt')
            if mode=='ordinary':assert trace.snapshot('ordinary')['records']==[]
            else:mon.ram[0x5200]^=1
        try:trace.restore()
        except AssertionError:
            assert mode=='corrupt' and report['input_trace']['restored']
            snapshots=report['input_trace']['snapshots'];assert snapshots[-1]['decode_error']
            assert (folder/snapshots[-1]['file']).read_bytes()[0x200]!=ord('U')
        else:assert mode!='corrupt'
        assert bytes(mon.ram)==before,mode
        if mode=='occupied':assert not mon.writes and not trace.installed
        else:assert report['input_trace']['restored'] and not trace.installed
        cases.append(mode+': original RAM and vectors preserved/restored')
    return cases


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    report=dict(passed=False,physical_hardware_io=False)
    try:
        with tempfile.TemporaryDirectory(prefix='uos-input-host-') as work:report['cases']=run(Path(work))
        report['passed']=True;print('PASS:',len(report['cases']),'input diagnostic host controls',flush=True)
    except BaseException as error:report['error']=repr(error);raise
    finally:args.report.write_text(json.dumps(report,indent=2)+'\n')
