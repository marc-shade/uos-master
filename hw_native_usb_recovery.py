"""Reclaim the verified inputs from the recorded missing-launch USB interruption."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote

from hw_native_check import hashes
from hw_native_ultimate_check import raw_read
from hw_native_usb_apps import app_fixtures
from hw_native_usb_browser import EMPTY_FOLDER,directory_oracle
from hw_storage_check import HardwareMonitor,ci
from hw_uci_check import Probe
from hwlib import desk_tick
from native_capture import ROOT


def plan(report,work,build):
    assert not report['passed'] and report['legacy_desktop_restored'] and report['images_unchanged']
    assert report['build']==build and not report['uncertain_host_writes']
    assert report['error']=='' and not report['editor_states'] and not report['usb_apps']['passed']
    assert report['usb_apps']['calculator_states'][-1]['label']=='usb-history-existing'
    assert report['usb_apps']['browser_returns'][-1]['label']=='usb-browser-after-calculator'
    assert report['frames'][-1]=='usb-missing-path'
    assert report['private_directory_created'] and report['private_subdirectory_created']
    assert report['restore_prg_verified_before_mounts'] and report['restore_prg_owned']
    directory=report['private_directory'].encode()
    assert re.fullmatch(rb'/Usb0/uos-native-[0-9a-f]{12}',directory)
    names={b'NOTE.TXT',b'EMPTY.TXT',b'LARGE.TXT'}|set(app_fixtures())
    assert set(report['fixture_readbacks'])=={name.decode() for name in names}
    expected={}
    for name in sorted(names):
        data=(work/('fixture-'+name.decode()+'.bin')).read_bytes()
        record=report['fixture_readbacks'][name.decode()]
        assert record['path']==(directory+b'/'+name).decode()
        assert record['bytes']==len(data) and record['sha256']==hashlib.sha256(data).hexdigest()
        assert data==(work/('fixture-readback-'+name.decode()+'.bin')).read_bytes()
        expected[directory+b'/'+name]=data
    for name,data in app_fixtures().items():assert expected[directory+b'/'+name]==data
    expected[directory+b'/HISTORY']=b'42\r'
    disk=report['native_disk_upload_path'].encode();loader=report['restore_prg_path'].encode()
    assert re.fullmatch(rb'/Temp/temp[0-9a-fA-F]{4}',disk)
    first=(work/'workflow.log').read_text().splitlines()[0]
    assert first.startswith('Native Ultimate hardware evidence: ')
    original_name=Path(first.split(': ',1)[1]).name.encode()
    assert re.fullmatch(rb'uos-hardware-native-directories-[a-z0-9_]{8}',original_name)
    assert loader==b'/Temp/'+original_name+b'-restore.prg'
    assert len({disk,loader,report['restore_disk_path'].encode()})==3
    expected[disk]=(ROOT/'target/native/uos128.d64').read_bytes()
    expected[loader]=(ROOT/'target/uos.prg').read_bytes()
    assert (work/'native.d64').read_bytes()==expected[disk]
    assert (work/'restore-loader-readback.bin').read_bytes()==expected[loader]
    return directory,expected


def delete_checked(ult,probe,path,result,save):
    assert all(item['path']!=path.decode() for item in result['deletions']),'deletion already attempted'
    action=dict(path=path.decode(),started=True,acknowledged=False,confirmed=False)
    result['deletions'].append(action);save()
    probe.ok(b'\x01\x09'+path)
    action['acknowledged']=True;save()
    status,body=ult._call('GET','/v1/files'+quote(path.decode(),safe='/')+':info')
    action['file_info_after']=dict(status=status,response=json.loads(body));save()
    assert status==404 and action['file_info_after']['response'].get('errors'),'deletion not confirmed'
    action['confirmed']=True;save()


def cleanup(ult,saved_report):
    work=saved_report.parent;report=json.loads(saved_report.read_text());build=hashes()
    directory,expected=plan(report,work,build)
    destination=work/'failed-usb-cleanup.json'
    assert not destination.exists(),'cleanup has already been attempted; inspect its journal before another action'
    result=dict(passed=False,source_report_sha256=hashlib.sha256(saved_report.read_bytes()).hexdigest(),
                readbacks={},deletions=[],hardware_io=True)
    def save():destination.write_text(json.dumps(result,indent=2)+'\n')
    def read(address,count=1):return bytes(mon.read_mem(address,address+count-1))
    def drives():
        data=json.loads(ult.drives());assert not data['errors'];return data
    def flatten(data):return {key:value for row in data['drives'] for key,value in row.items()}
    mon=HardwareMonitor(ult);probe=Probe(ult,work)
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and ci.wait_desktop_live(mon,120)
    assert read(0x4122,2)==bytes(2)
    settings=(work/'settings-before.bin').read_bytes();assert read(0x7350,9)==settings
    before=drives();assert before==json.loads((work/'drives-restored.json').read_text())
    for info in flatten(before).values():
        mounted=info.get('image_file','')
        if mounted and not mounted.startswith('/'):mounted=info['image_path'].rstrip('/')+'/'+mounted
        assert mounted.encode() not in expected,'a cleanup input is mounted'
    controls=read(0x9000,256);save()
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        original={int(target):bytes.fromhex(path) for target,path in report['dos_paths_before_hex'].items()}
        assert set(original)=={1,2}
        observed={}
        for target in (1,2):
            available=probe.command(bytes([target,7]));assert available['code']==85 and not available['carry']
            observed[target]=probe.ok(bytes([target,0x12]))['records'][0][0]
            assert observed[target] in (original[target],directory,directory+b'/'),'unexpected DOS path'
        result['observed_paths_hex']={str(t):p.hex() for t,p in observed.items()};save()
        try:
            listing=directory_oracle(probe,directory)
            records=[bytes.fromhex(raw) for raw in listing['pages']['0']['entries_hex']]
            private={path.rsplit(b'/',1)[1] for path in expected if path.startswith(directory+b'/')}
            assert listing['count']==len(records)==len(private)+1 and not listing['pages']['0']['full']
            assert {entry[1:] for entry in records}==private|{EMPTY_FOLDER}
            assert all(bool(entry[0]&16)==(entry[1:]==EMPTY_FOLDER) for entry in records)
            empty=directory_oracle(probe,directory+b'/'+EMPTY_FOLDER);assert empty['count']==0
            result['directory_oracles']=dict(private=listing,empty=empty);save()
            for index,(path,data) in enumerate(expected.items()):
                print('Failed USB run readback: '+path.decode(),flush=True)
                result['readbacks'][path.decode()]=raw_read(probe,path,data,work,f'cleanup-readback-{index:02}')
                save()
        finally:
            for target,path in original.items():
                probe.ok(bytes([target,0x11])+path)
                assert probe.ok(bytes([target,0x12]))['records'][0][0]==path
            result['dos_paths_restored']=True;save()
        assert set(result['readbacks'])=={path.decode() for path in expected}
        for path in expected:delete_checked(ult,probe,path,result,save)
        delete_checked(ult,probe,directory+b'/'+EMPTY_FOLDER,result,save)
        delete_checked(ult,probe,directory,result,save)
    except BaseException as error:result['error']=str(error);raise
    finally:mon.write_mem(0x9000,controls);save()
    assert drives()==before and read(0x7350,9)==settings and ci.wait_desktop_live(mon,120)
    assert hashes()==build
    result['passed']=True;save()
    print(f'PASS: failed USB run inputs verified and removed; desktop and DOS paths restored; {destination}',flush=True)
