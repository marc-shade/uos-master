#!/usr/bin/env python3
"""Check the late editor interruption's exact reclamation scope without hardware."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import hw_native_usb_recovery as recovery


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);args=parser.parse_args()
    source=ROOT/'docs/validation/2026-09-11-native-owned-abort/hardware-usb-reopen-failure'
    original=json.loads((source/'report.json').read_text());cases={}
    def plan(report,stage='second-context-reopen',corrupt=False):
        with tempfile.TemporaryDirectory(prefix='uos-reopen-cleanup-model-') as temporary:
            product=Path(temporary);native=product/'target/native';native.mkdir(parents=True)
            (native/'uos128.d64').write_bytes((source/'native.d64').read_bytes())
            (product/'target/uos.prg').write_bytes((source/'restore-loader-readback.bin').read_bytes())
            apps={name:(source/('fixture-'+name.decode()+'.bin')).read_bytes() for name in
                  (b'BAD APP.PRG',b'EDPICK.PRG',b'TEXT EDITOR.PRG',b'USB CALCULATOR LONG NAME.PRG')}
            original_read=Path.read_bytes
            def read(path):
                data=original_read(path)
                return data[:-1]+bytes([data[-1]^1]) if corrupt and path.name=='saved-expected.bin' else data
            with patch.object(recovery,'ROOT',product),patch.object(recovery,'app_fixtures',return_value=apps),\
                    patch.object(Path,'read_bytes',read):
                return recovery.plan(report,source,original['build'],stage=stage)
    directory,expected=plan(original)
    assert len(expected)==12 and sum(path.startswith(directory+b'/') for path in expected)==10
    assert expected[directory+b'/HISTORY']==b'42\r'
    assert expected[directory+b'/A LONG SAVED DOCUMENT NAME.TXT']==b'ONE "!QUOTED" LINE\r\nTWO\nTHREE\r\x00\xff END\r\n'
    large=expected[directory+b'/LARGE COPY.TXT']
    assert len(large)==66056 and large[65537:65540]==b'C12'
    cases['exact-ten-private-files-and-two-temporary-inputs']=True
    for name,change in (
        ('successful-run',lambda r:r.update(passed=True)),
        ('desktop-unrestored',lambda r:r.update(legacy_desktop_restored=False)),
        ('images-changed',lambda r:r.update(images_unchanged=False)),
        ('build-mismatch',lambda r:r.update(build={})),
        ('uncertain-write',lambda r:r.update(uncertain_host_writes=[{}])),
        ('different-error',lambda r:r.update(error="('unrelated failure', {})")),
        ('incomplete-apps',lambda r:r['usb_apps'].update(passed=False)),
        ('native-completed',lambda r:r.update(native_checks_passed=True)),
        ('readback-started',lambda r:r['output_readbacks'].update(UNKNOWN={})),
        ('different-frame',lambda r:r['frames'].append('unknown')),
        ('unverified-large-save',lambda r:r['editor_states'][-4].update(status=9)),
        ('different-saved-name',lambda r:r['editor_states'][-4].update(name='/Usb0/other')),
        ('different-saved-length',lambda r:r['editor_states'][-4].update(length=66055)),
        ('short-save-not-verified',lambda r:r['editor_states'][4].update(status=9)),
        ('unknown-private-name',lambda r:r['fixture_readbacks'].update(UNKNOWN={})),
        ('mounted-original-as-input',lambda r:r.update(native_disk_upload_path=r['restore_disk_path'])),
        ('unowned-loader',lambda r:r.update(restore_prg_owned=False)),
    ):
        altered=copy.deepcopy(original);change(altered)
        try:plan(altered)
        except AssertionError:cases['reject-'+name]=True
        else:raise AssertionError(name+' was accepted')
    for name,kwargs in (('wrong-stage',{'stage':'missing-launch'}),
                        ('unknown-stage',{'stage':'unknown'}),('changed-saved-bytes',{'corrupt':True})):
        try:plan(original,**kwargs)
        except AssertionError:cases['reject-'+name]=True
        else:raise AssertionError(name+' was accepted')
    inspection=json.loads((source/'reopen-inspection/report.json').read_text())
    info,wanted=recovery.retained_reopen(original,source,expected,inspection)
    cases['retained-native-owner-and-observed-read-file-match']=True
    for name,change in (
        ('inspection-failed',lambda r:r.update(passed=False)),
        ('controls-unrestored',lambda r:r.update(controls_restored=False)),
        ('inspection-other-report',lambda r:r.update(source_report_sha256='0'*64)),
        ('different-dos-path',lambda r:r['paths_hex'].update({'2':'2f'})),
        ('foreign-context-one',lambda r:r['files']['1'].update(code=0)),
        ('no-retained-handle',lambda r:r['files']['2'].update(code=85)),
        ('metadata-clipped',lambda r:r['files']['2'].update(clipped=1)),
        ('different-retained-name',lambda r:r['files']['2']['records'][0].update(data_hex=(info[:-1]+b'X').hex())),
        ('different-retained-size',lambda r:r['files']['2']['records'][0].update(data_hex=(b'\0'+info[1:]).hex())),
    ):
        altered=copy.deepcopy(inspection);change(altered)
        try:recovery.retained_reopen(original,source,expected,altered)
        except AssertionError:cases['reject-'+name]=True
        else:raise AssertionError(name+' was accepted')
    for scenario in ('success','different-bytes','lost-seek-reply','lost-close-reply','close-unconfirmed'):
        class Probe:
            def __init__(self):self.commands=[];self.position=0;self.open=True
            def command(self,command):
                self.commands.append(command);data=b'';code=0
                if command==b'\x02\x07':
                    if self.open:data=info
                    else:code=85
                    if not self.open and scenario=='close-unconfirmed':code=71
                elif command==b'\x02\x06\0\0\0\0':
                    self.position=0
                    if scenario=='lost-seek-reply':raise TimeoutError('lost seek reply')
                elif command==b'\x02\x03':
                    self.open=False
                    if scenario=='lost-close-reply':raise TimeoutError('lost close reply')
                else:
                    assert command[:2]==b'\x02\x04'
                    amount=int.from_bytes(command[2:],'little');data=wanted[self.position:self.position+amount]
                    if scenario=='different-bytes' and self.position==0:data=b'!'+data[1:]
                    self.position+=len(data);code=255
                return dict(code=code,carry=0,count=1,full=0,clipped=0,status='',records=[(data,0)])
            def ok(self,command):
                result=self.command(command);assert result['code']==0
                return result
        probe=Probe();result={};saves=[]
        with tempfile.TemporaryDirectory(prefix='uos-retained-close-model-') as temporary:
            try:recovery.close_retained_reopen(probe,Path(temporary),result,
                    lambda:saves.append(copy.deepcopy(result)),info,wanted)
            except (AssertionError,TimeoutError):assert scenario!='success'
            else:assert scenario=='success'
        action=result['retained_read_handle']
        assert sum(c==b'\x02\x06\0\0\0\0' for c in probe.commands)==1
        closes=sum(c==b'\x02\x03' for c in probe.commands)
        assert closes==int(scenario in ('success','lost-close-reply','close-unconfirmed'))
        assert action['close_started']==bool(closes)
        assert action['close_acknowledged']==(scenario in ('success','close-unconfirmed'))
        assert action['close_confirmed']==(scenario=='success')
        if closes:assert any(s['retained_read_handle'].get('all_bytes_verified') for s in saves)
        cases['retained-read-'+scenario+'-no-replay']=True
    report=dict(passed=True,hardware_io=False,cases=cases,
        expected_files=[dict(path=p.decode(),bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for p,b in expected.items()],
        source_report_sha256=hashlib.sha256((source/'report.json').read_bytes()).hexdigest())
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: {len(cases)} second-context reopen cleanup checks; no hardware I/O')


if __name__=='__main__':main()
