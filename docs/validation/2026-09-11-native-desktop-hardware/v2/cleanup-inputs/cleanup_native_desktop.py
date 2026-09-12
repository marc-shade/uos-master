"""Recover only the two verified uploads from the retained V2 desktop failure."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote
from hw_storage_check import HardwareMonitor, ci
from hw_uci_check import Probe
from hwlib import desk_tick
from hw_native_check import hashes
from hw_native_ultimate_check import raw_read
from native_capture import ROOT


def plan(report, work, build):
    assert not report['passed'] and report['physical_hardware_io']
    assert report['native_error'] == 'native heap changed during observation'
    assert report['legacy_desktop_restored'] and report['images_unchanged'] and report['build'] == build
    assert not report['uncertain_host_writes'] and not report['host_connect_failures']
    assert report['restore_prg_owned'] and report['restore_prg_verified_before_mounts']
    assert report['preflight_controls_restored'] and not report.get('native_checks_passed')
    assert 'cleanup_error' not in report and 'legacy_restore_error' not in report
    assert report['captures'][-1]['label'] == 'desktop-after-editor-surface-1770'
    assert not report['captures'][-1]['restored'] and all(r['restored'] for r in report['captures'][:-1])
    assert all(r['restored'] for r in report['mode_captures'])
    assert report['screens'] == ['calculator-new', 'calculator-result', 'editor-new', 'editor-typed']
    assert bytes(r['key'] for r in report['events']) == b'\tC12+30=\x1bEC128\x1bY'
    disk, loader = report['native_disk_upload_path'], report['restore_prg_path']
    assert re.fullmatch(r'/Temp/temp[0-9a-fA-F]{4}', disk)
    assert loader == '/Temp/'+work.name+'-restore.prg'
    assert disk != loader and report['restore_disk_path'] not in (disk, loader)
    expected = {disk:(ROOT/'target/native/uos128.d64').read_bytes(), loader:(ROOT/'target/uos.prg').read_bytes()}
    assert expected[disk] == (work/'native.d64').read_bytes()
    assert expected[loader] == (work/'restore-loader-readback.bin').read_bytes()
    assert report['restore_prg_readback'] == dict(path=loader,bytes=len(expected[loader]),sha256=hashlib.sha256(expected[loader]).hexdigest())
    mounted = [r for r in report['host_control_requests'] if r['method'] == 'POST']
    assert len(mounted) == 1 and mounted[0]['sent_sha256'] == hashlib.sha256(expected[disk]).hexdigest()
    assert mounted[0]['path'] == '/v1/drives/a:mount?type=d64&mode=readonly' and mounted[0]['status'] == 200
    return expected


def cleanup(ult, saved_report):
    work = saved_report.parent
    report = json.loads(saved_report.read_text())
    build = hashes(); expected = plan(report, work, build)
    destination = work/'failed-desktop-cleanup.json'
    assert not destination.exists(), 'cleanup has already been attempted; inspect its journal'
    result = dict(passed=False, source_report_sha256=hashlib.sha256(saved_report.read_bytes()).hexdigest(),
                  physical_hardware_io=True, readbacks={}, deletions=[],
                  uncertain_writes=ult.uncertain_writes, connect_failures=ult.connect_failures,
                  control_requests=ult.control_requests, planned_files=[dict(path=p,bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for p,b in expected.items()])
    def save(): destination.write_text(json.dumps(result, indent=2)+'\n')
    ult.record_event = save; save()
    mon = HardwareMonitor(ult)
    def read(address, count=1): return bytes(mon.read_mem(address, address+count-1))
    def drives():
        raw = json.loads(ult.drives()); assert not raw['errors']
        return raw
    before = json.loads((work/'drives-before.json').read_text())
    settings = (work/'settings-before.bin').read_bytes()
    assert drives() == before and read(0x7350, 9) == settings
    assert read(0x33c, 2) == desk_tick().to_bytes(2, 'little') and ci.wait_desktop_live(mon, 120)
    assert read(0x4122, 2) == bytes(2)
    for entry in before['drives']:
        for drive in entry.values():
            mounted = drive.get('image_file', '')
            if mounted and not mounted.startswith('/'): mounted = drive['image_path'].rstrip('/')+'/'+mounted
            assert mounted not in expected
    controls = read(0x9000, 256); probe = Probe(ult, work)
    original = {int(t):bytes.fromhex(p) for t,p in report['dos_paths_before_hex'].items()}
    assert set(original) == {1,2}
    try:
        mon.write_mem(0x9000, b'\0'+b'\xff'*255)
        for target, path in original.items():
            available = probe.command(bytes([target,7])); assert available['code'] == 85 and not available['carry']
            assert probe.ok(bytes([target,0x12]))['records'][0][0] == path
        result['dos_paths_before_hex'] = report['dos_paths_before_hex']; save()
        for path, wanted in expected.items():
            print('Verifying owned desktop upload:',path,len(wanted),'bytes',flush=True)
            result['readbacks'][path] = raw_read(probe,path.encode(),wanted,work,'cleanup-readback-'+Path(path).name); save()
        for path in expected:
            action = dict(path=path,started=True,confirmed=False); result['deletions'].append(action); save()
            probe.ok(b'\x01\x09'+path.encode())
            status, body = ult._call('GET','/v1/files'+quote(path,safe='/')+':info')
            assert status == 404 and json.loads(body).get('errors')
            action['confirmed'] = True; save()
            print('Removed verified owned upload:',path,flush=True)
        for target, path in original.items():
            assert probe.ok(bytes([target,0x12]))['records'][0][0] == path
        result['dos_paths_restored'] = True
    except BaseException as error:
        result['error'] = str(error); raise
    finally:
        mon.write_mem(0x9000,controls); result['controls_restored'] = read(0x9000,256) == controls; save()
    assert result['controls_restored'] and not result['uncertain_writes']
    assert drives() == before and read(0x7350,9) == settings and ci.wait_desktop_live(mon,120)
    assert hashes() == build
    result.update(passed=True,original_deployment_restored=True); save()
    print('PASS: both owned uploads read back and reclaimed; original desktop/settings/drives/DOS paths restored',flush=True)
