"""Physical native editor on system/data D64s, with independent data readback."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

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


def recover_boot_timeout(ult,saved_report,*,reinitialize=False):
    """Recover the exact terminal boot failure with recorded, unreplayed controls."""
    report=json.loads(saved_report.read_text());work=saved_report.parent
    assert report.get('error')=='native editor boot' and not report.get('native_checks_passed')
    assert not report['passed'] and report['build']==hashes()
    assert not report.get('uncertain_host_writes')
    mon=HardwareMonitor(ult)
    def read(address,count=1):return bytes(mon.read_mem(address,address+count-1))
    if reinitialize:
        previous=json.loads((work/'boot-resume-recovery.json').read_text())
        assert not previous['passed'] and previous['error']=='resumed desktop vector'
        assert not previous['uncertain_host_writes']
        assert len(previous['requests'])==1 and previous['requests'][0]['status']==200
        assert json.loads(bytes.fromhex(previous['requests'][0]['body_hex']))['errors']==[]
    result=dict(passed=False,source_report=str(saved_report),requests=[],replayed=False,reinitialize=reinitialize)
    destination=work/('boot-reinitialize-recovery.json' if reinitialize else 'boot-resume-recovery.json')
    assert not destination.exists()
    def save():destination.write_text(json.dumps(result,indent=2)+'\n')
    def control(method,endpoint,data=None):
        entry=dict(method=method,endpoint=endpoint,request_started=True,response_received=False,replayed=False)
        if data is not None:entry.update(sent_bytes=len(data),sent_sha256=hashlib.sha256(data).hexdigest())
        result['requests'].append(entry);save()
        status,body=ult._call(method,endpoint,data)
        entry.update(response_received=True,status=status,body_hex=body.hex());save()
        reply=json.loads(body);assert status==200 and reply.get('errors')==[],(status,reply)
    def drives():
        value=json.loads(ult.drives());assert not value['errors']
        return {key:item for entry in value['drives'] for key,item in entry.items()}
    try:
        before=drives();result['drives_before']=before
        assert before['a']['enabled'] and before['a']['bus_id']==8
        assert before['b']['enabled'] and before['b']['bus_id']==9 and not before['b']['image_file']
        result['vector_before']=read(0x33c,2).hex();save()
        if reinitialize:
            control('PUT','/v1/machine:reboot')
            print('Recorded cartridge reinitialization response',flush=True)
            quiet_boot('Cartridge reinitialization')
            control('POST','/v1/runners:run_prg',(ROOT/'target/uos.prg').read_bytes())
            print('Recorded deployed desktop reload response',flush=True)
            quiet_boot('Desktop reload recovery')
        else:
            control('PUT','/v1/machine:resume')
            print('Recorded one resume response; waiting for the deployed desktop',flush=True)
            quiet_boot('Desktop resume recovery')
        wait(lambda:read(0x33c,2)==desk_tick().to_bytes(2,'little'),'resumed desktop vector',120)
        assert ci.wait_desktop_live(mon,120)
        settings=(work/'settings-before.bin').read_bytes();current=read(0x7350,9)
        result['settings_before_hex']=current.hex()
        assert current[2:7]==settings[2:7] and read(0x4122,2)==bytes(2)
        mon.write_mem(0x7350,settings)
        assert read(0x7350,9)==settings
        after=drives();assert after==before
        original={key:item for entry in json.loads((work/'drives-before.json').read_text())['drives'] for key,item in entry.items()}
        assert {k:v for k,v in after.items() if k!='a'}=={k:v for k,v in original.items() if k!='a'}
        result.update(passed=True,desktop_live=True,settings_restored_hex=settings.hex(),drives_after=after,
                      other_drives_restored=True,images_unchanged=report['build']==hashes())
        print('PASS: deployed desktop resumed, all saved settings and other drives restored',flush=True)
    except BaseException as error:
        result['error']=str(error)
        try:result['vector_after']=read(0x33c,2).hex()
        except BaseException as diagnostic:result['diagnostic_error']=str(diagnostic)
        raise
    finally:
        result['uncertain_host_writes']=ult.uncertain_writes
        result['host_connect_failures']=ult.connect_failures
        save()


def recover_basic_boot(ult,saved_report):
    """Reload the deployed loader from IEC at an observed C64 READY prompt."""
    report=json.loads(saved_report.read_text());work=saved_report.parent
    assert report.get('error')=='native editor boot' and not report.get('native_checks_passed')
    assert not report['passed'] and report['build']==hashes() and not report.get('uncertain_host_writes')
    previous=json.loads((work/'boot-reinitialize-recovery.json').read_text())
    assert not previous['passed'] and previous['error']=='resumed desktop vector'
    assert not previous['uncertain_host_writes']
    assert all(r['response_received'] and r['status']==200 and
               json.loads(bytes.fromhex(r['body_hex']))['errors']==[] for r in previous['requests'])
    destination=work/'boot-basic-recovery.json';assert not destination.exists()
    result=dict(passed=False,source_report=str(saved_report),requests=[],commands=[],replayed=False)
    mon=HardwareMonitor(ult)
    def read(address,count=1):return bytes(mon.read_mem(address,address+count-1))
    def save():destination.write_text(json.dumps(result,indent=2)+'\n')
    def write(address,data):
        assert len(data)<=128
        request=dict(address=address,data_hex=data.hex(),request_started=True,response_received=False,replayed=False)
        result['requests'].append(request);save()
        status,body=ult._call('PUT',f'/v1/machine:writemem?address={address:04X}&data={data.hex().upper()}')
        request.update(response_received=True,status=status,body_hex=body.hex());save()
        assert status==200 and json.loads(body).get('errors')==[],(status,body)
    def command(text):
        result['commands'].append(text);save()
        payload=text.encode('ascii')+b'\r'
        for start in range(0,len(payload),10):
            wait(lambda:read(0xc6)==b'\0','BASIC keyboard drain',30)
            packet=payload[start:start+10]
            write(0x277,packet);write(0xc6,bytes([len(packet)]))
            time.sleep(1)
    def drives():
        data=json.loads(ult.drives());assert not data['errors']
        return {k:v for entry in data['drives'] for k,v in entry.items()}
    try:
        before=drives();result['drives_before']=before
        assert before['a']['enabled'] and before['a']['bus_id']==8
        assert before['b']['enabled'] and before['b']['bus_id']==9 and not before['b']['image_file']
        low=read(0,1024);(work/'basic-before-low.bin').write_bytes(low)
        screen=read(0x400,1000);(work/'basic-before-vic.bin').write_bytes(screen)
        assert low[0x314:0x316]==b'\x31\xea' and low[0x2b:0x2d]==b'\x01\x08'
        assert low[0xc6]==0 and low[0x33c:0x33e]==bytes(2)
        assert b'\x03\x0f\x0d\x0d\x0f\x04\x0f\x12\x05 64 \x02\x01\x13\x09\x03' in screen
        program=(ROOT/'target/uos.prg').read_bytes();assert program[:2]==b'\x01\x08'
        command('LOAD"UOS",8,1')
        quiet_boot('Direct IEC loader recovery')
        loaded=read(0x801,len(program)-2);(work/'basic-loaded-program.bin').write_bytes(loaded)
        result['loaded_payload_sha256']=hashlib.sha256(loaded).hexdigest()
        result['loaded_payload_differences']=[i for i,(a,b) in enumerate(zip(loaded,program[2:])) if a!=b]
        save();assert loaded==program[2:],'direct IEC loader bytes differ; RUN withheld'
        command('RUN');quiet_boot('Direct IEC desktop recovery')
        wait(lambda:read(0x33c,2)==desk_tick().to_bytes(2,'little'),'direct IEC desktop vector',120)
        assert ci.wait_desktop_live(mon,120) and read(0x4122,2)==bytes(2)
        settings=(work/'settings-before.bin').read_bytes();current=read(0x7350,9)
        result['boot_settings_hex']=current.hex();assert current[2:7]==settings[2:7]
        write(0x7350,settings);assert read(0x7350,9)==settings
        after=drives();assert after==before
        original={k:v for entry in json.loads((work/'drives-before.json').read_text())['drives'] for k,v in entry.items()}
        assert {k:v for k,v in after.items() if k!='a'}=={k:v for k,v in original.items() if k!='a'}
        result.update(passed=True,desktop_live=True,settings_restored_hex=settings.hex(),drives_after=after,
                      other_drives_restored=True,images_unchanged=report['build']==hashes())
        print('PASS: direct IEC boot restored the deployed desktop and all saved settings/drives',flush=True)
    except BaseException as error:
        result['error']=str(error)
        try:
            (work/'basic-failure-vic.bin').write_bytes(read(0x400,1000))
            (work/'basic-failure-low.bin').write_bytes(read(0,1024))
        except BaseException as diagnostic:result['diagnostic_error']=str(diagnostic)
        raise
    finally:
        result['uncertain_host_writes']=ult.uncertain_writes
        result['host_connect_failures']=ult.connect_failures
        save()


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
    # JSON reload breaks the live lists retained by run(). Include failures
    # from this readback too, whether it shares that client or uses a fresh one.
    observations={key:(list(report.get(key,[])),getattr(ult,attribute),len(getattr(ult,attribute)))
                  for key,attribute in (('host_connect_failures','connect_failures'),
                                        ('uncertain_host_writes','uncertain_writes'))}
    def save():
        for key,(previous,current,start) in observations.items():report[key]=previous+current[start:]
        saved_report.write_text(json.dumps(report,indent=2)+'\n')
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
