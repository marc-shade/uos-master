#!/usr/bin/env python3
"""Fault-inject accepted but incomplete uploads without any hardware I/O."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from hw_ultimate_check import VerifiedUltimate


class Cartridge(VerifiedUltimate):
    def __init__(self,*,stored=174848,post_error=None,post_reply=None):
        super().__init__(host='reference.invalid',timeout=60)
        self.stored=stored;self.post_error=post_error;self.post_reply=post_reply
        self.sent=[];self.persisted=[]
        self.record_event=lambda:self.persisted.append(copy.deepcopy((self.control_requests,self.upload_checks)))

    def _call(self,method,path,data=None):
        self.sent.append((method,path,data))
        if method=='POST':
            assert self.persisted[-1][0][-1]['request_started']
            assert not self.persisted[-1][0][-1]['response_received']
            if self.post_error:raise self.post_error
            if self.post_reply:return self.post_reply
        if method=='GET' and path=='/v1/drives':
            body=dict(drives=[dict(a=dict(enabled=True,bus_id=8,image_file='/Temp/test',image_path=''))],errors=[])
        elif method=='GET' and path.endswith(':info'):body=dict(files=dict(size=self.stored),errors=[])
        else:body=dict(errors=[])
        return 200,json.dumps(body).encode()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);args=parser.parse_args()
    report=dict(passed=False,hardware_io=False,cases={})
    disk=bytes((i*73+i//251)&255 for i in range(174848))
    try:
        for label,size in [('zero-byte',0),('truncated',63488),('oversized',174849)]:
            device=Cartridge(stored=size)
            try:device.mount(disk);device.reset()
            except RuntimeError as error:assert 'upload is incomplete' in str(error)
            else:raise AssertionError('incomplete upload allowed a boot')
            assert len([r for r in device.sent if r[0]=='POST'])==1
            assert not any(':reset' in r[1] for r in device.sent)
            assert device.upload_checks==[dict(path='/Temp/test',drive='a',expected_bytes=len(disk),
                                               size_verified=False,stored_bytes=size)]
            assert device.persisted[-1][1]==device.upload_checks
            report['cases'][label+'-success-response-blocks-boot']=True

        device=Cartridge();device.mount(disk);device.reset()
        assert device.upload_checks[0]['size_verified']
        assert device.sent[0]==('POST','/v1/drives/a:mount?type=d64&mode=readwrite',disk)
        assert device.control_requests[0]['sent_sha256']==hashlib.sha256(disk).hexdigest()
        assert device.sent[-1][:2]==('PUT','/v1/machine:reset')
        report['cases']['full-size-upload-allows-one-boot']=True

        for label,reply in [('json-error',(200,b'{"errors":["disk full"]}')),
                            ('http-error',(503,b'{"errors":["unavailable"]}')),
                            ('invalid-json',(200,b'broken'))]:
            device=Cartridge(post_reply=reply)
            try:device.mount(disk);device.reset()
            except (RuntimeError,ValueError):pass
            else:raise AssertionError('failed control allowed a boot')
            assert len(device.sent)==1 and len(device.control_requests)==1
            record=device.control_requests[0]
            assert record['response_received'] and record['status']==reply[0] and record['body_hex']==reply[1].hex()
            assert device.persisted[-1][0]==device.control_requests
            report['cases'][label+'-recorded-without-replay']=True

        device=Cartridge(post_error=SystemExit('response lost after sending'))
        try:device.mount(disk)
        except SystemExit:pass
        else:raise AssertionError('lost response accepted')
        assert len(device.sent)==1 and not device.control_requests[0]['response_received']
        assert device.persisted[-1][0]==device.control_requests
        report['cases']['unknown-acceptance-persisted-without-replay']=True

        for action in ('disk','loader'):
            device=Cartridge(stored=0)
            try:
                if action=='disk':device.mount_existing('/Temp/test',expected_bytes=174848)
                else:device.run_existing('/Temp/test',expected_bytes=2036)
            except AssertionError:pass
            else:raise AssertionError('empty recovery file accepted')
            assert len(device.sent)==1 and device.sent[0][0]=='GET' and not device.control_requests
            report['cases']['empty-recovery-'+action+'-refused-before-control']=True

        device=Cartridge(stored=2036);device.run_existing('/Temp/test',expected_bytes=2036)
        assert device.sent==[('GET','/v1/files/Temp/test:info',None),
                            ('PUT','/v1/runners:run_prg?file=%2FTemp%2Ftest',None)]
        assert device.control_requests[0]['response_received']
        report['cases']['existing-loader-start-does-not-upload']=True
        report['passed']=True
    finally:
        if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: {len(report["cases"])} hardware upload/restoration cases; no hardware I/O')


if __name__=='__main__':main()
