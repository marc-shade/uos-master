"""Native IEC and calculator export on C128; independent cartridge readback.

Only private uploaded D64 images are written. The legacy desktop is restored
before using the C64 UCI probe to retrieve those exact firmware Temp images.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time

from hw_storage_check import HardwareMonitor,ci
from hw_native_check import hashes,quiet_boot
from hw_uci_check import Probe
from hwlib import desk_tick,lst_symbol
from native_capture import NativeCapture,calculator_screen,wait,ROOT
from native_files_check import NativeFiles,prepare,workflow,exact_d64_files


def run(ult):
    work=Path(tempfile.mkdtemp(prefix='uos-hardware-native-files-'))
    print(f'Native file hardware evidence: {work}',flush=True)
    disk,fixtures=prepare(work,size=1557)
    mon=HardwareMonitor(ult);client=NativeFiles(mon,work,quiet=4,open_quiet=15)
    capture=NativeCapture(mon,work)
    report=dict(passed=False,build=hashes(),host=ult.host,legacy_desktop_restored=False,
                captures=capture.records,quiet_seconds=dict(boot=60,app_load=30,open=15,transfer=4))
    def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def read(address,count=1):return client.read_ram(address,count)
    def drives(label):
        data=json.loads(ult.drives());assert not data['errors'],data
        (work/f'drives-{label}.json').write_text(json.dumps(data,indent=2)+'\n')
        return {name:value for record in data['drives'] for name,value in record.items()}
    def image_path(state):
        image=state['a']['image_file']
        path=image if image.startswith('/') else state['a']['image_path'].rstrip('/')+'/'+image
        assert path.startswith('/Temp/') and '..' not in path,path
        return path.encode()
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little'),'expected deployed legacy desktop'
    assert ci.wait_desktop_live(mon,120)
    settings=read(0x7350,9);(work/'settings-before.bin').write_bytes(settings)
    before=drives('before');assert before['a']['enabled'] and before['a']['bus_id']==8
    assert read(0x4122,2)==bytes(2),'legacy file handles remain owned'
    (work/'ultimate-version.json').write_text(ult.version())
    probe=Probe(ult,work);controls=read(0x9000,256)
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        original={t:probe.ok(bytes([t,0x12]))['records'][0][0] for t in (1,2)}
        report['dos_paths_before_hex']={t:p.hex() for t,p in original.items()}
    finally:mon.write_mem(0x9000,controls)
    switched=False
    try:
        ult.mount((ROOT/'target/native/uos128.d64').read_bytes(),'a','d64','readwrite')
        switched=True;calculator_path=image_path(drives('calculator'))
        report['calculator_disk_path']=calculator_path.decode();save()
        ult.reset();quiet_boot('Native calculator export boot')
        wait(lambda:read(0x1c13,6)==b'UOS128' and read(0x3d12)==b'\1','native boot',120)
        print('Loading native calculator; 30 seconds without RAM DMA',flush=True)
        client.key(ord('C'),expected=None,quiet=30)
        for key in b'12+30=S':client.key(key,expected=None)
        for key in b'PHYSHIST':client.key(key,expected=None)
        client.key(13,expected=None,quiet=20)
        assert capture.capture('save-status',address=lst_symbol('native/calc','save_status'),count=1)==b'\1',read(0x3d80,32).hex()
        assert read(0x98)==b'\0' and read(0x3de0,4)==bytes(4)
        for label,status in [('calculator-saved','HISTORY SAVED AND VERIFIED'),
                             ('calculator-existing','FILE EXISTS - CHOOSE ANOTHER NAME')]:
            if label=='calculator-existing':
                for key in b'SPHYSHIST':client.key(key,expected=None)
                client.key(13,expected=None,quiet=15)
                assert capture.capture('existing-status',address=lst_symbol('native/calc','save_status'),count=1)==b'\3'
            vic=read(0x400,1000);(work/(label+'-vic.bin')).write_bytes(vic)
            vdc=capture.capture(label+'-vdc',mode=1)
            repeat=capture.capture(label+'-vdc-repeat',mode=1)
            assert vdc==repeat and vic==calculator_screen(40,'42',['42'],save_status=status)
            assert vdc==calculator_screen(80,'42',['42'],save_status=status)
            save()
        client.key(27,expected=None)
        assert read(0x3d0e,3)==bytes([175,251,32]) and read(0x98)==b'\0'
        report['calculator_save_reopen_compare_and_exclusive_rejection']=True;save()

        ult.mount(disk.read_bytes(),'a','d64','readwrite')
        files_path=image_path(drives('files'))
        report['files_disk_path']=files_path.decode();save()
        print('Loading native file client; 30 seconds without RAM DMA',flush=True)
        client.key(ord('C'),expected=None,quiet=30)
        workflow(client,fixtures,report,save)
        report['native_checks_passed']=True
    except BaseException as error:
        report['error']=str(error)
        for label,address,count in [('files',0x3d80,0x64),('app',0x6000,4096),('kernel',0x1c00,0x1c00)]:
            try:(work/f'failure-{label}.bin').write_bytes(read(address,count))
            except Exception as diagnostic:report['diagnostic_error']=str(diagnostic)
        raise
    finally:
        save()
        if switched:
            print('Restoring the deployed legacy desktop before cartridge readback',flush=True)
            ult.mount((ROOT/'target/ultos.d64').read_bytes(),'a','d64','readwrite')
            ult.run_prg((ROOT/'target/uos.prg').read_bytes());quiet_boot('Legacy desktop boot')
            wait(lambda:read(0x33c,2)==desk_tick().to_bytes(2,'little'),'legacy desktop vector',120)
            assert ci.wait_desktop_live(mon,120) and read(0x7350,9)==settings
            after=drives('restored')
            assert {k:v for k,v in before.items() if k!='a'}=={k:v for k,v in after.items() if k!='a'}
            report['legacy_desktop_restored']=True
        report['images_unchanged']=report['build']==hashes();save()

    readback(ult,work,report,fixtures,original)


def readback(ult,work,report,fixtures,original):
    mon=HardwareMonitor(ult)
    def read(address,count=1):return bytes(mon.read_mem(address,address+count-1))
    def save():(work/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    assert report.get("native_checks_passed") and report["legacy_desktop_restored"]
    assert read(0x33c,2)==desk_tick().to_bytes(2,"little") and ci.wait_desktop_live(mon,120)
    assert read(0x4122,2)==bytes(2),"legacy handles remain owned"
    settings=(work/"settings-before.bin").read_bytes();assert read(0x7350,9)==settings
    probe=Probe(ult,work)
    calculator_path=report["calculator_disk_path"].encode();files_path=report["files_disk_path"].encode()
    assert all(p.startswith(b"/Temp/") and b".." not in p for p in (calculator_path,files_path))
    # The native stream itself is not the byte oracle. Read the complete,
    # closed D64 through raw Ultimate DOS, independently inspect its linked
    # sectors, and cross-check every nonempty file with c1541.
    controls=read(0x9000,256)
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        for label,path,expected in [('calculator',calculator_path,{'physhist':b'42\r'}),
                                    ('files',files_path,{**fixtures,'copy':fixtures['source']})]:
            print(f'Reading back the closed {label} D64 through Ultimate DOS',flush=True)
            data=bytearray();probe.ok(b'\x01\x02\x01'+path)
            try:
                while len(data)<174848:
                    result=probe.command(b'\x01\x04\x00\x10')
                    assert not result['carry'] and not result['full'] and not result['clipped'],result
                    assert result['code']==0 or (result['code']==255 and not result['status']),result
                    chunk=b''.join(record for record,clipped in result['records'] if not clipped)
                    assert len(chunk)==min(4096,174848-len(data)),(label,len(data),len(chunk))
                    data.extend(chunk)
                    if len(data)%65536==0:print(f'{label} disk readback: {len(data)} bytes',flush=True)
                end=probe.command(b'\x01\x04\x01\x00')
                assert not end['carry'] and not end['full'] and not end['clipped'],end
                assert end['code']==255 and not end['status'] and all(not data for data,_ in end['records']),end
            finally:probe.ok(b'\x01\x03')
            retrieved=work/(label+'-readback.d64');retrieved.write_bytes(data)
            verify_disk(work,label,expected,report)
            save()
    except BaseException as error:
        report['readback_error']=str(error)
        raise
    finally:
        try:
            for target,path in original.items():
                probe.ok(bytes([target,0x11])+path)
                assert probe.ok(bytes([target,0x12]))['records'][0][0]==path
            report['dos_paths_restored']=True
        finally:
            mon.write_mem(0x9000,controls);save()
    assert report['images_unchanged'] and report['build']==hashes()
    assert ci.wait_desktop_live(mon,120) and read(0x7350,9)==settings
    report['passed']=True;save()
    print(f'HW-NATIVE-FILES PASS; exported history and binary files independently verified; desktop restored; {work}',flush=True)


def resume_readback(ult,saved_report):
    report=json.loads(saved_report.read_text());work=saved_report.parent
    assert report.get("native_checks_passed") and report["legacy_desktop_restored"]
    if "readback_error" in report:
        report.setdefault("prior_readback_errors",[]).append(report.pop("readback_error"))
    fixtures={n:(work/(n+".bin")).read_bytes() for n in ["source",*report["small_files"]]}
    assert hashlib.sha256(fixtures["source"]).hexdigest()==report["native_copy_sha256"]
    original={int(t):bytes.fromhex(path) for t,path in report["dos_paths_before_hex"].items()}
    if all((work/(label+'-readback.d64')).exists() for label in ('calculator','files')):
        verify_disk(work,'calculator',{'physhist':b'42\r'},report)
        verify_disk(work,'files',{**fixtures,'copy':fixtures['source']},report)
        assert report['dos_paths_restored'] and report['build']==hashes()
        mon=HardwareMonitor(ult)
        assert ci.wait_desktop_live(mon,120)
        assert bytes(mon.read_mem(0x7350,0x7358))==(work/'settings-before.bin').read_bytes()
        report['passed']=True;report['verified_complete_cached_readbacks']=True
        saved_report.write_text(json.dumps(report,indent=2)+'\n')
        print(f'HW-NATIVE-FILES PASS; complete saved cartridge readbacks verified; desktop live; {work}',flush=True)
        return
    readback(ult,work,report,fixtures,original)


def verify_disk(work,label,expected,report):
    retrieved=work/(label+'-readback.d64');data=retrieved.read_bytes()
    files=exact_d64_files(data);c1541_matches=0
    for name,content in expected.items():
        kind='u' if name=='user' else 'p' if name=='program' else 's'
        assert files[name.upper().encode()]==({'s':1,'p':2,'u':3}[kind],content),(label,name,'linked sectors')
        out=work/(label+'-'+name+'-c1541.bin')
        subprocess.run(['c1541','-attach',str(retrieved),'-read',name+','+kind+',r',str(out)],check=True,capture_output=True)
        if content:
            assert out.read_bytes()==content,(label,name);c1541_matches+=1
        else:
            # c1541 itself returns padding for an empty SEQ. Retain its exact
            # output and independently require the stored sector extent=0.
            report['c1541_empty_extraction']=dict(stored_bytes=0,extracted_bytes=out.stat().st_size,
                sha256=hashlib.sha256(out.read_bytes()).hexdigest())
    report.setdefault('independent_readback',{})[label]=dict(bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),files_verified=len(expected),
        linked_sector_files=len(expected),c1541_nonempty_files=c1541_matches)
