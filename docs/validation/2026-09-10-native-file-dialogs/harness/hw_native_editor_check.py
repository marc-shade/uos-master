"""Physical native editor on system/data D64s, with independent data readback."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from hw_storage_check import HardwareMonitor,ci
from hw_native_check import hashes,quiet_boot
from hw_uci_check import Probe
from hwlib import desk_tick
from native_editor_check import EditorClient,prepare_editor,editor_workflow
from native_capture import ROOT,wait
from native_files_check import exact_d64_files


def run(ult):
    work=Path(tempfile.mkdtemp(prefix='uos-hardware-native-editor-'))
    print(f'Native editor hardware evidence: {work}',flush=True)
    disk,data_disk,fixtures=prepare_editor(work)
    mon=HardwareMonitor(ult);client=EditorClient(mon,work,quiet=4,scan_quiet=30,capture_quiet=2,poll=2,key_timeout=1800)
    read=client.read
    report=dict(passed=False,build=hashes(),host=ult.host,legacy_desktop_restored=False,
                native_disk_sha256=hashlib.sha256(disk.read_bytes()).hexdigest(),
                data_disk_sha256=hashlib.sha256(data_disk.read_bytes()).hexdigest(),
                host_request_timeout_seconds=ult.timeout,uncertain_host_writes=ult.uncertain_writes,
                host_connect_attempts=ult.connect_attempts,host_connect_failures=ult.connect_failures,
                quiet_seconds=dict(boot=60,scan_or_app=30,key=4,capture=2,poll=2),key_timeout_seconds=1800)
    def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def drives(label):
        data=json.loads(ult.drives());assert not data['errors'],data
        (work/f'drives-{label}.json').write_text(json.dumps(data,indent=2)+'\n')
        return {name:value for record in data['drives'] for name,value in record.items()}
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and ci.wait_desktop_live(mon,120)
    assert read(0x4122,2)==bytes(2),'legacy file handles remain owned'
    settings=read(0x7350,9);(work/'settings-before.bin').write_bytes(settings)
    before=drives('before');assert before['a']['enabled'] and before['a']['bus_id']==8
    assert before['b']['enabled'] and before['b']['bus_id']==9 and before['b']['type']=='1541'
    assert not before['b']['image_file'],'native editor workflow requires an initially empty drive B'
    (work/'ultimate-version.json').write_text(json.dumps(json.loads(ult.version()),indent=2)+'\n')
    probe=Probe(ult,work);controls=read(0x9000,256)
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        original={target:probe.ok(bytes([target,0x12]))['records'][0][0] for target in (1,2)}
        report['dos_paths_before_hex']={target:path.hex() for target,path in original.items()}
    finally:mon.write_mem(0x9000,controls)
    switched=False;data_switched=False
    try:
        data_switched=True
        ult.mount(data_disk.read_bytes(),'b','d64','readwrite')
        switched=True
        ult.mount(disk.read_bytes(),'a','d64','readwrite')
        mounted_drives=drives('native');mounted=mounted_drives['a'];path=mounted['image_file']
        if not path.startswith('/'):path=mounted['image_path'].rstrip('/')+'/'+path
        assert path.startswith('/Temp/') and '..' not in path,path
        report['native_disk_path']=path;save()
        mounted=mounted_drives['b'];path=mounted['image_file']
        if not path.startswith('/'):path=mounted['image_path'].rstrip('/')+'/'+path
        assert path.startswith('/Temp/') and '..' not in path,path
        report['data_disk_path']=path;save()
        ult.reset();quiet_boot('Native editor boot')
        wait(lambda:read(0x1c13,6)==b'UOS128' and read(0x3d12)==b'\1','native editor boot',120)
        editor_workflow(client,disk,data_disk,fixtures,0,report,save)
    except BaseException as error:
        report['error']=str(error)
        try:
            (work/'failure-context.bin').write_bytes(read(0x3d00,0xe4))
            (work/'failure-vic.bin').write_bytes(read(0x400,1000))
        except Exception as diagnostic:report['diagnostic_error']=str(diagnostic)
        raise
    finally:
        save()
        if data_switched:
            try:
                ult.unmount('b')
                report['data_drive_restored']=True
            except BaseException as error:
                report['data_drive_restore_error']=str(error)
        if switched:
            print('Restoring the deployed legacy desktop before independent readback',flush=True)
            ult.mount((ROOT/'target/ultos.d64').read_bytes(),'a','d64','readwrite')
            ult.run_prg((ROOT/'target/uos.prg').read_bytes());quiet_boot('Legacy desktop boot')
            wait(lambda:read(0x33c,2)==desk_tick().to_bytes(2,'little'),'legacy desktop vector',120)
            assert ci.wait_desktop_live(mon,120)
            restored=read(0x7350,9);report['legacy_boot_settings_hex']=restored.hex()
            # Native app RAM includes the inactive legacy settings record.
            # Boot reinitializes its active fields; preserve the saved header
            # and reserved bytes too, once the legacy desktop owns this RAM.
            assert restored[2:7]==settings[2:7],'legacy boot applied different settings'
            mon.write_mem(0x7350,settings)
            assert read(0x7350,9)==settings
            after=drives('restored')
            assert {k:v for k,v in before.items() if k!='a'}=={k:v for k,v in after.items() if k!='a'}
            report['legacy_desktop_restored']=True
        report['images_unchanged']=report['build']==hashes();save()
    readback(ult,work/'report.json')


def restore_record(ult,saved_report):
    """Finish only the settings-record restoration of an archived failed run."""
    report=json.loads(saved_report.read_text());work=saved_report.parent
    assert not report['passed'] and report['build']==hashes()
    mon=HardwareMonitor(ult)
    def read(address,count):return bytes(mon.read_mem(address,address+count-1))
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and ci.wait_desktop_live(mon,120)
    assert read(0x4122,2)==bytes(2)
    settings=(work/'settings-before.bin').read_bytes();current=read(0x7350,9)
    assert len(settings)==9 and current[2:7]==settings[2:7]
    before=json.loads((work/'drives-before.json').read_text())
    after=json.loads(ult.drives());assert not after['errors']
    flatten=lambda data:{k:v for entry in data['drives'] for k,v in entry.items()}
    left,right=flatten(before),flatten(after)
    assert {k:v for k,v in left.items() if k!='a'}=={k:v for k,v in right.items() if k!='a'}
    assert right['a']['enabled'] and right['a']['bus_id']==8
    mon.write_mem(0x7350,settings)
    assert read(0x7350,9)==settings and ci.wait_desktop_live(mon,120)
    recovery=dict(passed=True,legacy_desktop_live=True,active_fields_already_matched=True,
                  before_hex=current.hex(),restored_hex=settings.hex(),other_drives_unchanged=True,images_unchanged=report['build']==hashes())
    (work/'settings-recovery.json').write_text(json.dumps(recovery,indent=2)+'\n')
    print('PASS: live legacy desktop and all nine saved settings bytes restored',flush=True)


def readback(ult,saved_report):
    report=json.loads(saved_report.read_text());work=saved_report.parent
    assert report.get('native_checks_passed') and report['legacy_desktop_restored'] and report['images_unchanged']
    assert report['build']==hashes()
    separate='data_disk_path' in report
    original_disk=(work/('documents.d64' if separate else 'native.d64')).read_bytes()
    assert hashlib.sha256(original_disk).hexdigest()==report['data_disk_sha256' if separate else 'native_disk_sha256']
    wanted=(work/'saved-expected.seq').read_bytes()
    assert len(wanted)==report['saved_bytes'] and hashlib.sha256(wanted).hexdigest()==report['saved_sha256']
    expected=exact_d64_files(original_disk);expected[b'SAVED']=(1,wanted)
    original={int(t):bytes.fromhex(path) for t,path in report['dos_paths_before_hex'].items()}
    path=report['data_disk_path' if separate else 'native_disk_path'].encode();assert path.startswith(b'/Temp/') and b'..' not in path
    mon=HardwareMonitor(ult)
    def read(address,count=1):return bytes(mon.read_mem(address,address+count-1))
    def save():saved_report.write_text(json.dumps(report,indent=2)+'\n')
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and ci.wait_desktop_live(mon,120)
    assert read(0x4122,2)==bytes(2) and read(0x7350,9)==(work/'settings-before.bin').read_bytes()
    if 'readback_error' in report:report.setdefault('prior_readback_errors',[]).append(report.pop('readback_error'))
    probe=Probe(ult,work);controls=read(0x9000,256);output=work/'editor-readback.d64'
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        if not output.exists():
            print('Reading back the closed native editor D64 through Ultimate DOS',flush=True)
            data=bytearray();probe.ok(b'\x01\x02\x01'+path)
            try:
                while len(data)<174848:
                    result=probe.command(b'\x01\x04\x00\x10')
                    assert not result['carry'] and not result['full'] and not result['clipped'],result
                    assert result['code']==0 or (result['code']==255 and not result['status']),result
                    chunk=b''.join(record for record,clipped in result['records'] if not clipped)
                    assert len(chunk)==min(4096,174848-len(data)),len(chunk)
                    data.extend(chunk)
                    if len(data)%65536==0:print(f'Editor disk readback: {len(data)} bytes',flush=True)
                end=probe.command(b'\x01\x04\x01\x00')
                assert not end['carry'] and not end['full'] and not end['clipped'],end
                assert end['code']==255 and not end['status'] and all(not part for part,_ in end['records']),end
            finally:probe.ok(b'\x01\x03')
            output.write_bytes(data)
        data=output.read_bytes();actual=exact_d64_files(data)
        assert actual==expected,'stored files differ from fixtures plus verified edited document'
        sector_zero_unchanged=data[:256]==original_disk[:256]
        # Sector zero is reserved only on the older combined system/data
        # fixture. The separate document disk may legitimately allocate it.
        if not separate:assert sector_zero_unchanged,'native boot block changed'
        comparisons=0
        for name,(kind,content) in expected.items():
            if not content:continue
            destination=work/('readback-'+name.decode()+'.bin')
            spec=name.decode().lower()+','+{1:'s',2:'p',3:'u'}[kind]+',r'
            subprocess.run(['c1541','-attach',str(output),'-read',spec,str(destination)],check=True,capture_output=True)
            assert destination.read_bytes()==content,name
            comparisons+=1
        report['independent_readback']=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                                           exact_files=len(actual),c1541_nonempty_files=comparisons,
                                           empty_stored_bytes=len(actual[b'EMPTY'][1]),initial_sector_zero_unchanged=sector_zero_unchanged,
                                           data_disk_on_device_9=separate,
                                           saved_bytes=len(wanted),saved_sha256=hashlib.sha256(wanted).hexdigest())
    except BaseException as error:
        report['readback_error']=str(error)
        raise
    finally:
        try:
            for target,path in original.items():
                probe.ok(bytes([target,0x11])+path)
                assert probe.ok(bytes([target,0x12]))['records'][0][0]==path
            report['dos_paths_restored']=True
        finally:mon.write_mem(0x9000,controls);save()
    assert report['build']==hashes() and ci.wait_desktop_live(mon,120)
    assert read(0x7350,9)==(work/'settings-before.bin').read_bytes()
    report['passed']=True;save()
    print(f'HW-NATIVE-EDITOR PASS; files independently verified; legacy desktop restored; {work}',flush=True)
