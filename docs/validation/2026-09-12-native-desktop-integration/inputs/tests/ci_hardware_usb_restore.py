#!/usr/bin/env python3
"""Fault-test USB qualification's uploads and existing-file desktop recovery."""
import argparse
from contextlib import ExitStack,redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from ci_hardware_editor_restore import Device as IECDevice

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import hw_native_ultimate_check as workflow


class Device(IECDevice):
    def _call(self,method,path,data=None):
        result=super()._call(method,path,data)
        if self.scenario=='reset-uncertain' and method=='PUT' and path=='/v1/machine:reset':
            raise TimeoutError('reset response lost after request')
        return result


def created_loader(scenario,destination):
    from urllib.parse import unquote
    target=destination/'product/target';target.mkdir(parents=True)
    program=b'\x01\x08'+bytes((i*17)&255 for i in range(2034))
    (target/'uos.prg').write_bytes(program);(target/'ultos.d64').write_bytes(bytes(174848))
    work=destination/'evidence';work.mkdir();name='/Temp/'+work.name+'-restore.prg'
    files={'/Temp/original':bytes(174848)}
    if scenario=='collision':files[name]=b'KEEP'
    commands=[];active=None;report={}
    def call(method,path,data=None):
        assert method=='GET'
        path=unquote(path[len('/v1/files'):-len(':info')])
        if scenario=='unavailable':return 503,json.dumps({'errors':['unavailable']}).encode()
        return (200,json.dumps({'errors':[],'files':{'size':len(files[path])}}).encode()) if path in files else (404,b'{"errors":["not found"]}')
    def command(raw):
        nonlocal active
        commands.append(raw)
        if raw[:3]==b'\x01\x02\x07':
            assert raw[3:].decode()==name and name not in files
            active=name;files[name]=bytearray()
        elif raw[:4]==b'\x01\x05\0\0':
            assert active==name and len(raw[4:])<=511
            if scenario=='write-error':raise RuntimeError('write response error')
            files[name].extend(raw[4:14] if scenario=='short-write' else raw[4:])
        elif raw==b'\x01\x03':
            active=None
            if scenario=='close-error':raise RuntimeError('close response error')
        else:raise AssertionError(raw)
        return {}
    def read(probe,path,wanted,folder,label):
        assert active is None and bytes(files[path.decode()])==wanted,'loader byte verification failed'
        return dict(bytes=len(wanted),verified=True)
    ult=SimpleNamespace(_call=call,file_info=lambda path:{'size':len(files[path])})
    with patch.object(workflow,'ROOT',destination/'product'),patch.object(workflow,'raw_read',read):
        try:
            actual=workflow.prepare_restore(ult,SimpleNamespace(ok=command),work,report,lambda:None,
                {'a':{'image_file':'original','image_path':'/Temp'}})
        except (AssertionError,RuntimeError) as error:
            assert scenario!='created';failure=str(error)
            assert not report.get('restore_prg_verified_before_mounts')
        else:
            assert scenario=='created' and actual==program and report['restore_prg_verified_before_mounts']
            failure=None
    if scenario in ('collision','unavailable'):assert not commands
    else:assert sum(raw==b'\x01\x03' for raw in commands)==1
    if scenario=='collision':assert files[name]==b'KEEP'
    return dict(passed=True,error=failure,report=report,commands=[raw.hex() for raw in commands])


def navigation_pages():
    from hw_native_usb_browser import Navigation
    n=Navigation.__new__(Navigation)
    rows=[b' '+f'FILE {i}'.encode() for i in range(11)]
    state=dict(base=0,row=0,device=1,keys=[])
    def key(k,**kwargs):
        state['keys'].append(k)
        if k==ord('N'):state['base']+=8;state['row']=0
        elif k==ord('B'):state['base']-=8;state['row']=0
        elif k==9:state['device']=3-state['device'];state['base']=state['row']=0
        elif k==17:state['row']+=1
        elif k==145:state['row']-=1
    n.client=SimpleNamespace(key=key);n.private_path=n.path=b'/PRIVATE/'
    n.device=1;n.base=n.row=0;n.error=None
    n.private_entries=rows[:8];n.outputs={r[1:]:b'' for r in rows[8:]}
    n.entries=rows[:8];n.more=True;n.selected_name=rows[0][1:]
    n.details={'pages':[]};n.frame=lambda *a,**k:None;n.save=lambda:None
    n.raw_page=lambda label:(dict(path_hex=n.path.hex(),base=state['base'],selected=state['row'],
        device=state['device'],more=state['base']+8<len(rows)),rows[state['base']:state['base']+8])
    n.select(rows[10][1:]);assert (state['base'],state['row'])==(8,2)
    n.check('selected-last')
    n.select(rows[1][1:]);assert (state['base'],state['row'])==(0,1)
    n.check('selected-first-page')
    n.select(rows[10][1:]);n.launch(rows[9][1:],'context-reload',2)
    assert (state['base'],state['row'],state['device'])==(8,1,2)
    assert len(n.details['pages'])>=5
    return dict(passed=True,observations=n.details,keys=state['keys'])


def check(scenario,destination):
    target=destination/'product/target';(target/'native').mkdir(parents=True)
    program=b'\x01\x08'+bytes((i*17)&255 for i in range(2034))
    (target/'uos.prg').write_bytes(program)
    for file in ('ultos.d64','native/uos128.d64'):(target/file).write_bytes(bytes(174848))
    work=destination/'evidence';work.mkdir()
    device=Device(scenario,program)
    def raw_read(probe,path,wanted,folder,label):
        if path==b'/Temp/recovery':
            assert wanted==program
            if scenario=='bad-loader':raise AssertionError('recovery loader bytes differ')
            device.loader_checked=True
        elif scenario=='fixture-failure':raise AssertionError('fixture bytes differ')
        return dict(bytes=len(wanted),verified=True)
    def boot_check(*args):
        if scenario=='restore-file-lost':device.files['/Temp/recovery']=0
        raise AssertionError('simulated native boot observation failure')
    client=SimpleNamespace(read=lambda a,n=1:device.read_mem(a,n),events=[],frames=[],
        capture=SimpleNamespace(records=[]),heaps=[],states=[],observations=[],modules=[])
    probe=SimpleNamespace(ok=lambda command:{'records':[(b'/',0)]},
                          command=lambda command:{'code':85,'carry':False})
    with ExitStack() as stack:
        for name,value in [('ROOT',destination/'product'),('hashes',lambda:{'test':'fixed'}),
            ('desk_tick',lambda:0x1f5e),('wait',lambda predicate,label,*args:predicate() or (_ for _ in ()).throw(AssertionError(label))),
            ('quiet_boot',lambda label:None),('Probe',lambda *args:probe),('raw_read',raw_read),
            ('USBEditorClient',lambda *args,**kwargs:client),('verify_boot_layout',boot_check)]:
            stack.enter_context(patch.object(workflow,name,value))
        stack.enter_context(patch.object(workflow.tempfile,'mkdtemp',return_value=str(work)))
        stack.enter_context(patch.object(workflow.ci,'wait_desktop_live',lambda mon,timeout:device.read_mem(0x33c,2)==b'\x5e\x1f'))
        stack.enter_context(redirect_stdout(io.StringIO()))
        try:workflow.run(device,restore_prg_path='/Temp/recovery')
        except (AssertionError,RuntimeError,TimeoutError) as error:failure=str(error)
        else:raise AssertionError('injected failure was ignored')
    report=json.loads((work/'report.json').read_text())
    assert not report['passed'] and device.mounts['a']['image_file']=='/Temp/original'
    assert device.mounts['b']['image_file']==''
    assert not any(method=='POST' and 'runners' in path for method,path in device.calls)
    if scenario in ('bad-loader','fixture-failure'):
        assert report['preflight_error']==failure
        assert not any(method!='GET' for method,path in device.calls)
    else:
        assert report['images_unchanged']
        assert sum(method=='POST' for method,path in device.calls)==1
        if scenario=='short-a':assert not any(':reset' in path for method,path in device.calls)
        if scenario=='restore-file-lost':
            assert report['error']=='simulated native boot observation failure' and report['legacy_restore_error']==failure
            assert not any('runners' in path for method,path in device.calls)
        else:
            assert report['legacy_desktop_restored'] and device.read_mem(0x7350,9)==device.settings
            assert device.read_mem(0x33c,2)==b'\x5e\x1f'
        if scenario=='reset-uncertain':
            resets=[r for r in device.control_requests if r['path']=='/v1/machine:reset']
            assert len(resets)==1 and resets[0]['request_started'] and not resets[0]['response_received']
    assert device.read_mem(0x9000,256)==bytes(256)
    return dict(passed=True,error=failure,report=report,calls=device.calls)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);args=parser.parse_args()
    report=dict(passed=False,hardware_io=False,cases={})
    try:
        with tempfile.TemporaryDirectory(prefix='uos-usb-restore-tests-') as folder:
            for scenario in ('bad-loader','fixture-failure','short-a','native-failure','restore-file-lost','reset-uncertain'):
                report['cases'][scenario]=check(scenario,Path(folder)/scenario)
            for scenario in ('created','collision','unavailable','short-write','write-error','close-error'):
                report['cases']['create-'+scenario]=created_loader(scenario,Path(folder)/('create-'+scenario))
            report['cases']['private-list-over-eight-and-context-refresh']=navigation_pages()
        report['passed']=True
    finally:
        if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: {len(report["cases"])} USB preparation/restoration cases; no hardware I/O')


if __name__=='__main__':main()
