#!/usr/bin/env python3
"""One frozen input diagnostic; parent harness restores all original state."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent


def main():
    manifest=ROOT/'frozen-inputs.json'
    for name,digest in json.loads(manifest.read_text()).items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    for name,digest in json.loads((ROOT/'external-inputs.json').read_text()).items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    from hw_native_desktop_check import run
    from native_capture_transport import ReceiptUltimate,PausedHardwareMonitor
    from native_input_workflow import run_input_workflow
    path=ROOT/'physical-attempt.json'
    attempt=dict(passed=False,process_started=True,process_finished=False,physical_hardware_io=True,
        full_app_qualification=False,manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
    with path.open('x') as output:output.write(json.dumps(attempt,indent=2)+'\n')
    def save():path.write_text(json.dumps(attempt,indent=2)+'\n')
    def preflight(ult,mon,probe,work,report,persist):
        attempt['work']=str(work);save()
    try:
        run(ReceiptUltimate(timeout=60),workflow=run_input_workflow,monitor_class=PausedHardwareMonitor,
            paused_capture=True,preflight=preflight,
            expected_images=dict(disk='9809bace09b871d31a6ccd82d48d99086d5f2fbaf9953cb1eb9f177cc072cdcf',
                                 kernel='1ac2547dff0ebeb1306bb12ba0a2baa59026d1f912a195e72b0bca1acaed49ed'))
        attempt['passed']=True
    except BaseException as error:attempt['error']=dict(type=type(error).__name__,message=str(error));raise
    finally:attempt['process_finished']=True;save()


if __name__=='__main__':main()
