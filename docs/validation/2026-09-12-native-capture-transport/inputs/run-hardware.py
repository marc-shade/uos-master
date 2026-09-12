#!/usr/bin/env python3
"""One focused capture experiment, with the existing verified deployment lifecycle."""
import sys
import hashlib
import json
from pathlib import Path
sys.dont_write_bytecode = True
from hw_native_desktop_check import run
from native_capture_transport import ReceiptUltimate, PausedHardwareMonitor
from native_transport_workflow import run_transport_workflow

if __name__ == '__main__':
    root=Path(__file__).resolve().parent
    manifest=root/'frozen-inputs.json'
    for name,digest in json.loads(manifest.read_text()).items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
    for name,digest in json.loads((root/'external-inputs.json').read_text()).items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    path=root/'physical-attempt.json'
    attempt=dict(passed=False,manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
                 full_desktop_qualification=False,process_started=True)
    with path.open('x') as output:output.write(json.dumps(attempt,indent=2)+'\n')
    try:
        run(ReceiptUltimate(timeout=60), workflow=run_transport_workflow,
            monitor_class=PausedHardwareMonitor, paused_capture=True, cleanup_after_failure=True)
        attempt['passed']=True
    except BaseException as error:
        attempt['error']=dict(type=type(error).__name__,message=str(error))
        raise
    finally:
        attempt['process_finished']=True
        path.write_text(json.dumps(attempt,indent=2)+'\n')
