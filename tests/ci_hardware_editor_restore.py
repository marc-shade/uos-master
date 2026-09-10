#!/usr/bin/env python3
"""Exercise IEC orchestration failures with a simulated cartridge and memory."""
import argparse
from contextlib import ExitStack,redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit,unquote

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import hw_native_editor_check as workflow
from hw_ultimate_check import VerifiedUltimate


class Device(VerifiedUltimate):
    def __init__(self,scenario,program):
        super().__init__(host='reference.invalid')
        self.scenario=scenario;self.program=program;self.calls=[];self.loader_checked=False
        self.ram=bytearray(65536);self.ram[0x33c:0x33e]=b'\x5e\x1f'
        self.settings=bytes.fromhex('507302f0a502030000');self.ram[0x7350:0x7359]=self.settings
        self.mounts={drive:dict(enabled=True,bus_id=number,type='1541',image_file=path,image_path='')
                     for drive,number,path in [('a',8,'/Temp/original'),('b',9,'')]}
        self.files={'/Temp/original':174848,'/Temp/recovery':len(program)}

    def read_mem(self,address,length):return bytes(self.ram[address:address+length])
    def write_mem(self,address,data):self.ram[address:address+len(data)]=data

    def _call(self,method,path,data=None):
        self.calls.append((method,path))
        route=urlsplit(path);params=parse_qs(route.query)
        body={'errors':[]}
        if method=='GET':
            if route.path=='/v1/drives':body['drives']=[{k:dict(v)} for k,v in self.mounts.items()]
            elif route.path=='/v1/version':body['version']='0.1'
            else:
                name=unquote(route.path[len('/v1/files'):-len(':info')])
                body['files']={'size':self.files[name]}
        elif method=='POST':
            assert self.loader_checked,'a drive was switched before complete recovery-loader verification'
            drive=route.path.split('/')[3][0];name='/Temp/upload-'+drive
            self.mounts[drive]['image_file']=name
            self.files[name]=63488 if self.scenario=='short-'+drive else len(data)
        elif ':remove' in route.path:self.mounts[route.path.split('/')[3][0]]['image_file']=''
        elif ':mount' in route.path:self.mounts['a']['image_file']=params['image'][0]
        elif route.path=='/v1/machine:reset':
            self.ram[0x33c:0x33e]=b'\0\0';self.ram[0x1c13:0x1c19]=b'UOS128';self.ram[0x3d12]=1
        elif route.path=='/v1/runners:run_prg':
            assert params['file']==['/Temp/recovery']
            self.ram[0x33c:0x33e]=b'\x5e\x1f';self.ram[0x7350:0x7359]=b'XX'+self.settings[2:7]+b'YY'
        else:raise AssertionError((method,path))
        return 200,json.dumps(body).encode()


def check(scenario,destination):
    target=destination/'product/target';target.mkdir(parents=True)
    program=b'\x01\x08'+bytes((i*17)&255 for i in range(2034))
    (target/'uos.prg').write_bytes(program);(target/'ultos.d64').write_bytes(bytes(174848))
    work=destination/'evidence';work.mkdir()
    def prepare(folder):
        disk=folder/'native.d64';disk.write_bytes(bytes(174848))
        data=folder/'documents.d64';data.write_bytes(bytes(174848))
        return disk,data,{}
    device=Device(scenario,program)
    def raw_read(probe,path,wanted,folder,label):
        assert path==b'/Temp/recovery' and wanted==program
        if scenario=='bad-loader':raise AssertionError('recovery loader bytes differ')
        device.loader_checked=True
        return {'bytes':len(wanted),'verified':True}
    def native_check(*args):
        if scenario=='restore-file-lost':device.files['/Temp/recovery']=0
        raise AssertionError('simulated editor failure')
    def wait(predicate,label,*args):assert predicate(),label
    probe=SimpleNamespace(ok=lambda command:{'records':[(b'/',0)]})
    with ExitStack() as stack:
        for name,value in [('ROOT',destination/'product'),('hashes',lambda:{'test':'fixed'}),
                           ('prepare_editor',prepare),('desk_tick',lambda:0x1f5e),('wait',wait),
                           ('quiet_boot',lambda label:None),('Probe',lambda *args:probe),
                           ('editor_workflow',native_check),
                           ('EditorClient',lambda *args,**kwargs:SimpleNamespace(read=lambda a,n=1:device.read_mem(a,n)))]:
            stack.enter_context(patch.object(workflow,name,value))
        stack.enter_context(patch.object(workflow.tempfile,'mkdtemp',return_value=str(work)))
        stack.enter_context(patch.object(workflow.ci,'wait_desktop_live',lambda mon,timeout:device.read_mem(0x33c,2)==b'\x5e\x1f'))
        stack.enter_context(patch('hw_native_ultimate_check.raw_read',raw_read))
        stack.enter_context(redirect_stdout(io.StringIO()))
        try:workflow.run(device,restore_prg_path='/Temp/recovery')
        except (AssertionError,RuntimeError) as error:failure=str(error)
        else:raise AssertionError('injected failure was ignored')
    report=json.loads((work/'report.json').read_text())
    assert not report['passed']
    assert device.mounts['a']['image_file']=='/Temp/original' and device.mounts['b']['image_file']==''
    assert not any(method=='POST' and 'runners' in path for method,path in device.calls)
    if scenario=='bad-loader':
        assert report['preflight_error']==failure and not any(method!='GET' for method,path in device.calls)
    else:
        assert report['data_drive_restored'] and report['images_unchanged']
        if scenario=='short-b':assert not any(':reset' in path for _,path in device.calls)
        if scenario=='restore-file-lost':
            assert report['error']=='simulated editor failure' and report['legacy_restore_error']==failure
            assert not any('runners' in path for _,path in device.calls)
        else:
            assert device.read_mem(0x33c,2)==b'\x5e\x1f' and device.read_mem(0x7350,9)==device.settings
            if scenario!='short-b':assert report['legacy_desktop_restored']
    return dict(passed=True,error=failure,report=report,calls=device.calls)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);args=parser.parse_args()
    report=dict(passed=False,hardware_io=False,cases={})
    try:
        with tempfile.TemporaryDirectory(prefix='uos-editor-restore-tests-') as folder:
            for scenario in ('bad-loader','short-b','short-a','editor-failure','restore-file-lost'):
                report['cases'][scenario]=check(scenario,Path(folder)/scenario)
        report['passed']=True
    finally:
        if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: {len(report["cases"])} IEC restoration failure scenarios; no hardware I/O')


if __name__=='__main__':main()
