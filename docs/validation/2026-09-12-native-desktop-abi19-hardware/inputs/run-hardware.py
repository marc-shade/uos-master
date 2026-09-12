#!/usr/bin/env python3
"""Run one frozen ABI 1.9 desktop qualification and verified restoration."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
if __name__=='__main__':
    root=Path(__file__).resolve().parent
    manifest=root/'frozen-inputs.json'
    for name,digest in json.loads(manifest.read_text()).items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
    for name,digest in json.loads((root/'external-inputs.json').read_text()).items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    from hw_native_desktop_check import run
    from native_capture_transport import ReceiptUltimate,PausedHardwareMonitor
    path=root/'physical-attempt.json'
    attempt=dict(passed=False,process_started=True,full_desktop_qualification=True,
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
    with path.open('x') as output:output.write(json.dumps(attempt,indent=2)+'\n')
    try:
        run(ReceiptUltimate(timeout=60),monitor_class=PausedHardwareMonitor,paused_capture=True)
        attempt['passed']=True
    except BaseException as error:
        attempt['error']=dict(type=type(error).__name__,message=str(error))
        raise
    finally:
        attempt['process_finished']=True
        path.write_text(json.dumps(attempt,indent=2)+'\n')
