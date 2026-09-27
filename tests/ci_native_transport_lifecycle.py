#!/usr/bin/env python3
"""A failed focused capture must restore and clean up before its error returns."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from urllib.parse import unquote

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import hw_native_desktop_check as lifecycle


class Capture:
    def __init__(self,*args,**kwargs):self.records=[]


class Device:
    def __init__(self,fail_at):
        self.ram=bytearray(65536);self.ram[0x33c:0x33e]=lifecycle.desk_tick().to_bytes(2,'little')
        self.ram[0x7350:0x7359]=bytes.fromhex('507302f0a502030000')
        self.uncertain_writes=[];self.connect_failures=[];self.control_requests=[];self.upload_checks=[]
        self.record_event=lambda:None
        self.paths={1:b'/',2:b'/Usb0/c64/#-a/'}
        self.mounted='/Temp/temp0098';self.files={};self.events=[];self.fail_at=fail_at
    def read_mem(self,at,count):return bytes(self.ram[at:at+count])
    def version(self):return '{"version":"offline lifecycle control","errors":[]}'
    def write_mem(self,at,data):self.ram[at:at+len(data)]=data
    def drives(self):
        return json.dumps(dict(errors=[],drives=[dict(a=dict(enabled=True,bus_id=8,
            image_file=self.mounted,image_path='/Temp/')),dict(b=dict(enabled=False,bus_id=9,
            image_file='',image_path=''))]))
    def mount(self,data,*args):
        self.events.append('mount-native');self.mounted='/Temp/temp00AD';self.files[self.mounted]=data
    def reset(self):self.events.append('reset')
    def _call(self,method,path,data=None):
        assert method=='GET' and path.endswith(':info')
        name=unquote(path[len('/v1/files'):-len(':info')])
        assert name not in self.files
        return 404,b'{"errors":["missing"]}'


class Probe:
    def __init__(self,ult,work):self.ult=ult
    def command(self,data):
        assert data[1]==7
        return dict(code=85,carry=False)
    def ok(self,data):
        if data[1]==0x12:return dict(records=[(self.ult.paths[data[0]],0)])
        assert data[:2]==b'\1\x09'
        name=data[2:].decode();assert name in self.ult.files
        self.ult.events.append('delete-'+name);del self.ult.files[name]


def prepare(ult,probe,work,report,save,before):
    program=(ROOT/'target/uos.prg').read_bytes()
    path='/Temp/'+work.name+'-restore.prg';ult.files[path]=program
    report.update(restore_disk_path=ult.mounted,restore_prg_path=path,restore_prg_owned=True,
                  restore_prg_verified_before_mounts=True)
    save();return program


def restore(ult,mon,read,report,save,before,settings,drives,program):
    ult.events.append('restore-original')
    if ult.fail_at=='restore':raise RuntimeError('original restore failed')
    ult.mounted=report['restore_disk_path'];mon.write_mem(0x7350,settings)
    assert drives('restored')==before
    report['legacy_desktop_restored']=True;save()


def raw_read(probe,path,wanted,work,label):
    ult=probe.ult;ult.events.append('readback-'+path.decode())
    if ult.fail_at=='readback':raise AssertionError('stored file differs')
    assert ult.files[path.decode()]==wanted
    return dict(bytes=len(wanted))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();result=dict(passed=False,physical_hardware_io=False,cases=[])
    # The hardware script pins the images it was qualified with; this offline
    # lifecycle check exercises the current build's images instead.
    images={name:hashlib.sha256((ROOT/'target/native-desktop'/f).read_bytes()).hexdigest()
            for name,f in (('disk','uos128.d64'),('kernel','uos128.prg'))}
    for fault in (None,'workflow','restore','readback'):
        with tempfile.TemporaryDirectory(prefix='uos-transport-lifecycle-') as temporary:
            work=Path(temporary);ult=Device(fault)
            def workflow(mon,capture,work,disk,report,save):
                ult.events.append('workflow')
                if fault is not None:raise RuntimeError('original capture failure')
                report['native_checks_passed']=True;save()
            with patch.object(lifecycle.tempfile,'mkdtemp',return_value=str(work)), \
                 patch.object(lifecycle,'NativeCapture',Capture), \
                 patch.object(lifecycle,'Probe',Probe), \
                 patch.object(lifecycle,'prepare_restore',prepare), \
                 patch.object(lifecycle,'restore_desktop',restore), \
                 patch.object(lifecycle,'raw_read',raw_read), \
                 patch.object(lifecycle,'quiet_boot',lambda _:None), \
                 patch.object(lifecycle.ci,'wait_desktop_live',lambda *args:True):
                try:lifecycle.run(ult,workflow=workflow,cleanup_after_failure=True,expected_images=images)
                except (RuntimeError,AssertionError) as error:
                    assert fault is not None
                    message=str(error)
                else:assert fault is None;message=None
            report=json.loads((work/'report.json').read_text())
            assert report['passed']==(fault is None)
            assert ult.events[:4]==['mount-native','reset','workflow','restore-original']
            deleted=[x for x in ult.events if x.startswith('delete-')]
            if fault in (None,'workflow'):
                assert report['legacy_desktop_restored'] and report['cleanup_complete']
                assert len(deleted)==2 and not ult.files
                assert all(x['confirmed'] for x in report['temporary_deletions'])
                assert report['dos_paths_restored'] and report['controls_restored'] and report['images_unchanged']
                if fault=='workflow':assert message=='original capture failure'
            else:
                assert not deleted and len(ult.files)==2
                assert not report.get('cleanup_complete')
            if fault=='restore':assert not any(x.startswith('readback-') for x in ult.events)
            result['cases'].append(dict(fault=fault,error=message,events=ult.events,
                cleanup_complete=report.get('cleanup_complete',False),passed=True))
    result['passed']=True;args.report.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: successful and failed workflows clean up; failed restoration or readback preserves files; no hardware I/O')


if __name__=='__main__':main()
