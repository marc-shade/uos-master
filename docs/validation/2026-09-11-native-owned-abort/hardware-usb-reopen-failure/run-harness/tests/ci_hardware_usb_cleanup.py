#!/usr/bin/env python3
"""Check exact failed-run reclamation scope and deletion acknowledgement guards."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import hw_native_usb_recovery as recovery
from hw_native_usb_recovery import delete_checked


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);args=parser.parse_args()
    source=ROOT/'docs/validation/2026-09-11-native-modules/hardware-usb-initial-failure'
    original=json.loads((source/'report.json').read_text());cases={}
    # Test the recorded build even after later product images change.
    def plan(report):
        with tempfile.TemporaryDirectory(prefix='uos-usb-cleanup-model-') as temporary:
            product=Path(temporary);native=product/'target/native';native.mkdir(parents=True)
            (native/'uos128.d64').write_bytes((source/'native.d64').read_bytes())
            (product/'target/uos.prg').write_bytes((source/'restore-loader-readback.bin').read_bytes())
            apps={name:(source/('fixture-'+name.decode()+'.bin')).read_bytes() for name in
                  (b'BAD APP.PRG',b'EDPICK.PRG',b'TEXT EDITOR.PRG',b'USB CALCULATOR LONG NAME.PRG')}
            with patch.object(recovery,'ROOT',product),patch.object(recovery,'app_fixtures',return_value=apps):
                return recovery.plan(report,source,original['build'])
    directory,expected=plan(original)
    assert len(expected)==10 and sum(path.startswith(directory+b'/') for path in expected)==8
    cases['exact-eight-private-files-and-two-temporary-inputs']=True
    for name,change in (
        ('successful-run',lambda r:r.update(passed=True)),
        ('desktop-unrestored',lambda r:r.update(legacy_desktop_restored=False)),
        ('images-changed',lambda r:r.update(images_unchanged=False)),
        ('build-mismatch',lambda r:r.update(build={})),
        ('uncertain-write',lambda r:r.update(uncertain_host_writes=[{}])),
        ('different-error',lambda r:r.update(error='unrelated failure')),
        ('editor-started',lambda r:r.update(editor_states=[{}])),
        ('unknown-private-name',lambda r:r['fixture_readbacks'].update(UNKNOWN={})),
        ('mounted-original-as-input',lambda r:r.update(native_disk_upload_path=r['restore_disk_path'])),
        ('unowned-loader',lambda r:r.update(restore_prg_owned=False)),
    ):
        altered=copy.deepcopy(original);change(altered)
        try:plan(altered)
        except AssertionError:cases['reject-'+name]=True
        else:raise AssertionError(name+' was accepted')
    for scenario in ('success','lost-delete-reply','metadata-unavailable'):
        calls=[];result={'deletions':[]};saves=[]
        def remove(command):
            calls.append(command)
            assert command==b'\x01\x09/Temp/test-owned'
            if scenario=='lost-delete-reply':raise TimeoutError('reply lost')
        def metadata(method,path):
            assert method=='GET' and path=='/v1/files/Temp/test-owned:info'
            return (503,b'{"errors":["unavailable"]}') if scenario=='metadata-unavailable' else (404,b'{"errors":["not found"]}')
        def save():saves.append(copy.deepcopy(result))
        try:delete_checked(SimpleNamespace(_call=metadata),SimpleNamespace(ok=remove),b'/Temp/test-owned',result,save)
        except (AssertionError,TimeoutError):assert scenario!='success'
        else:assert scenario=='success'
        assert len(calls)==1 and saves[0]['deletions'][0]['started'] and not saves[0]['deletions'][0]['acknowledged']
        action=result['deletions'][0]
        assert action['confirmed']==(scenario=='success') and action['acknowledged']==(scenario!='lost-delete-reply')
        try:delete_checked(SimpleNamespace(_call=metadata),SimpleNamespace(ok=remove),b'/Temp/test-owned',result,save)
        except AssertionError:pass
        else:raise AssertionError('deletion replayed')
        assert len(calls)==1
        cases[scenario+'-no-replay']=True
    report=dict(passed=True,hardware_io=False,cases=cases,
        source_report_sha256=hashlib.sha256((source/'report.json').read_bytes()).hexdigest())
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: {len(cases)} USB cleanup scope and acknowledgement checks; no hardware I/O')


if __name__=='__main__':main()
