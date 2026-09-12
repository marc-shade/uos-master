#!/usr/bin/env python3
"""Run one frozen five-app native suite qualification and restore deployment."""
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import quote

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
EXPECTED_IMAGES = dict(
    disk='9809bace09b871d31a6ccd82d48d99086d5f2fbaf9953cb1eb9f177cc072cdcf',
    kernel='1ac2547dff0ebeb1306bb12ba0a2baa59026d1f912a195e72b0bca1acaed49ed')


def main():
    manifest = ROOT/'frozen-inputs.json'
    for name, digest in json.loads(manifest.read_text()).items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    for name, digest in json.loads((ROOT/'external-inputs.json').read_text()).items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    from hw_native_desktop_check import run
    from native_capture_transport import ReceiptUltimate, PausedHardwareMonitor
    from native_suite_workflow import suite_preflight, run_suite_workflow, physical_bridge_factory, close_bridges
    attempt = dict(passed=False, process_started=True, physical_hardware_io=True,
        full_desktop_workflow=True, selected_apps=['Calculator','Editor','Files','Ultimate','Claude'],
        images=EXPECTED_IMAGES, manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
    path = ROOT/'physical-attempt.json'
    with path.open('x') as output:
        output.write(json.dumps(attempt,indent=2)+'\n')
    def save_attempt(): path.write_text(json.dumps(attempt,indent=2)+'\n')
    ult = ReceiptUltimate(timeout=60)
    factory = physical_bridge_factory(ult.host)
    state = {}
    def preflight(ult, mon, probe, work, report, save):
        state.update(work=work, report=report, save=save)
        attempt['work'] = str(work); save_attempt()
        suite_preflight(ult,mon,probe,work,report,save)
    def workflow(mon,capture,work,disk,report,save):
        run_suite_workflow(mon,capture,work,disk,report,save,bridge_factory=factory)
    try:
        run(ult,workflow=workflow,monitor_class=PausedHardwareMonitor,paused_capture=True,
            expected_images=EXPECTED_IMAGES,preflight=preflight,full_desktop_workflow=True)
        report = state['report']
        report['modem_settings_after'] = final = {}
        for item, expected in report['modem_settings_before'].items():
            endpoint = '/v1/configs/'+quote('Modem Settings',safe='')+'/'+quote(item,safe='')
            code, body = ult._call('GET',endpoint)
            reply = json.loads(body)
            assert code == 200 and not reply['errors']
            final[item] = reply['Modem Settings'][item]['current']; state['save']()
            assert final[item] == expected, ('modem configuration changed',item)
        report['suite_and_restoration_passed'] = True; state['save']()
        attempt['passed'] = True
    except BaseException as error:
        attempt['error'] = dict(type=type(error).__name__,message=str(error))
        raise
    finally:
        close_bridges(factory)
        attempt['all_host_processes_terminal'] = all(proc.poll() is not None for proc,_ in factory.processes)
        attempt['process_finished'] = True; save_attempt()


if __name__ == '__main__': main()
