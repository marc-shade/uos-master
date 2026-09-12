"""Reclaim exact private files from the recorded USB interruptions."""
import ast
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


def plan(report,work,build,*,stage='missing-launch'):
    assert not report['passed'] and report['legacy_desktop_restored'] and report['images_unchanged']
    assert report['build']==build and not report['uncertain_host_writes']
    assert report['usb_apps']['calculator_states'][-1]['label']=='usb-history-existing'
    if stage=='missing-launch':
        assert report['error']=='' and not report['editor_states'] and not report['usb_apps']['passed']
        assert report['usb_apps']['browser_returns'][-1]['label']=='usb-browser-after-calculator'
        assert report['frames'][-1]=='usb-missing-path'
    else:
        assert stage=='second-context-reopen','unknown recovery stage'
        assert report['usb_apps']['passed'] and not report.get('native_checks_passed')
        assert not report['output_readbacks'] and report['frames'][-1]=='ultimate-new-after-save'
        states=report['editor_states'];last=states[-1]
        assert last['label']=='ultimate-reopen-second-context'
        assert ast.literal_eval(report['error'])==(last['label'],{k:v for k,v in last.items() if k!='label'})
        assert (last['length'],last['dirty'],last['fault'],last['status'],last['mode'],last['device'],last['fmt'])==(0,0,0,9,0,2,3)
        assert last['field']==report['private_directory']+'/LARGE COPY.TXT'
        assert [s['label'] for s in states[-4:]]==['ultimate-large-save-verified',
            'ultimate-existing-file-rejected','ultimate-new-after-save','ultimate-reopen-second-context']
        for label,name,length,status in (('ultimate-saved-long-path','A LONG SAVED DOCUMENT NAME.TXT',38,1),
                ('ultimate-large-save-verified','LARGE COPY.TXT',66056,1),
                ('ultimate-existing-file-rejected','LARGE COPY.TXT',66056,7)):
            matches=[s for s in states if s['label']==label];assert len(matches)==1
            saved=matches[0]
            assert saved['name']==report['private_directory']+'/'+name
            assert (saved['length'],saved['dirty'],saved['fault'],saved['status'],saved['device'],saved['fmt'])==(length,0,0,status,1,3)
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
    if stage=='second-context-reopen':
        raw=expected[directory+b'/NOTE.TXT']
        assert raw==b'ONE "QUOTED" LINE\r\nTWO\nTHREE\r'+bytes([0,255])+b' END\r\n'
        expected[directory+b'/A LONG SAVED DOCUMENT NAME.TXT']=raw[:5]+b'!'+raw[5:]
        raw=expected[directory+b'/LARGE.TXT']
        assert raw==(b'0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n'*1800)[:66053]
        data=raw[:65537]+b'C12'+raw[65537:]
        assert data==(work/'saved-expected.bin').read_bytes()
        expected[directory+b'/LARGE COPY.TXT']=data
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


def inspect_reopen(ult,saved_report):
    """Observe retained DOS file metadata; do not close files or change paths."""
    work=saved_report.parent;report=json.loads(saved_report.read_text());build=hashes()
    plan(report,work,build,stage='second-context-reopen')
    prior=json.loads((work/'failed-usb-cleanup.json').read_text())
    assert not prior['passed'] and not prior['readbacks'] and not prior['deletions']
    assert prior['source_report_sha256']==hashlib.sha256(saved_report.read_bytes()).hexdigest()
    folder=work/'reopen-inspection';folder.mkdir()
    destination=folder/'report.json'
    result=dict(passed=False,files={},paths_hex={},hardware_io=True,
                source_report_sha256=prior['source_report_sha256'])
    def save():destination.write_text(json.dumps(result,indent=2)+'\n')
    mon=HardwareMonitor(ult);probe=Probe(ult,folder)
    def read(address,count=1):return bytes(mon.read_mem(address,address+count-1))
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and ci.wait_desktop_live(mon,120)
    assert read(0x4122,2)==bytes(2)
    settings=(work/'settings-before.bin').read_bytes();assert read(0x7350,9)==settings
    before=json.loads(ult.drives());assert before==json.loads((work/'drives-restored.json').read_text())
    controls=read(0x9000,256);save()
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        for target in (1,2):
            info=probe.command(bytes([target,7]))
            result['files'][str(target)]={k:v for k,v in info.items() if k!='records'}
            result['files'][str(target)]['records']=[dict(data_hex=data.hex(),clipped=clipped) for data,clipped in info['records']]
            save()
            assert not info['carry'] and info['code'] in (0,85),info
            result['paths_hex'][str(target)]=probe.ok(bytes([target,0x12]))['records'][0][0].hex();save()
    finally:
        mon.write_mem(0x9000,controls)
        result['controls_restored']=read(0x9000,256)==controls;save()
    assert result['controls_restored'] and json.loads(ult.drives())==before and read(0x7350,9)==settings
    assert ci.wait_desktop_live(mon,120) and hashes()==build
    result['passed']=True;save()
    print(json.dumps(result,indent=2),flush=True)


def retained_reopen(report,work,expected,inspection):
    """Require the observed read handle and the failed native owner's exact extent."""
    assert inspection['passed'] and inspection['controls_restored']
    assert inspection['source_report_sha256']==hashlib.sha256((work/'report.json').read_bytes()).hexdigest()
    assert inspection['paths_hex']==report['dos_paths_before_hex']
    files=inspection['files'];assert set(files)=={'1','2'}
    assert files['1']['code']==85 and not files['1']['carry']
    info=files['2']
    assert info['code']==0 and not info['carry'] and not info['full'] and not info['clipped']
    assert info['count']==len(info['records'])==1 and not info['records'][0]['clipped']
    raw=bytes.fromhex(info['records'][0]['data_hex'])
    assert raw[8:12]==b'TXT ' and raw[12:]==b'LARGE COPY.TXT'
    wanted=expected[report['private_directory'].encode()+b'/LARGE COPY.TXT']
    assert int.from_bytes(raw[:4],'little')==len(wanted)==66056
    context=(work/'failure-context.bin').read_bytes();assert len(context)==228
    record=context[0xc0:0xd0]
    assert record[:4]==bytes([32,2,0,14]) and record[7]==17
    assert int.from_bytes(record[8:12],'little')==64000
    assert int.from_bytes(record[13:16],'little')==2056 and context[0xd0]==0
    return raw,wanted


def close_retained_reopen(probe,work,result,save,info,wanted):
    """Read the retained context from zero and compare every byte before CLOSE."""
    observed=probe.ok(b'\x02\x07')
    assert not observed['full'] and not observed['clipped'] and observed['records']==[(info,0)]
    action=dict(context=2,file_info_hex=info.hex(),seek_started=True,seek_acknowledged=False,
                close_started=False,close_acknowledged=False,close_confirmed=False)
    result['retained_read_handle']=action;save()
    probe.ok(b'\x02\x06\0\0\0\0');action['seek_acknowledged']=True;save()
    data=bytearray()
    while len(data)<len(wanted):
        reply=probe.command(b'\x02\x04\0\x10')
        assert not reply['carry'] and not reply['full'] and not reply['clipped'],reply
        assert reply['code']==0 or reply['code']==255 and not reply['status'],reply
        assert all(not clipped for _,clipped in reply['records'])
        chunk=b''.join(part for part,_ in reply['records'])
        assert len(chunk)==min(4096,len(wanted)-len(data))
        data.extend(chunk)
    (work/'retained-context-two-readback.bin').write_bytes(data)
    assert data==wanted,'retained file differs; leave it open and do not delete any input'
    end=probe.command(b'\x02\x04\x01\0')
    assert not end['carry'] and not end['full'] and not end['clipped']
    assert end['code'] in (0,255) and not end['status'] and all(not part and not clipped for part,clipped in end['records'])
    action.update(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),all_bytes_verified=True,
                  close_started=True);save()
    probe.ok(b'\x02\x03');action['close_acknowledged']=True;save()
    closed=probe.command(b'\x02\x07');assert closed['code']==85 and not closed['carry'],closed
    action['close_confirmed']=True;save()
    print('Retained DOS context 2: all 66,056 bytes match; owned read handle closed',flush=True)


def cleanup(ult,saved_report,*,stage='missing-launch',release_reopen=False):
    work=saved_report.parent;report=json.loads(saved_report.read_text());build=hashes()
    directory,expected=plan(report,work,build,stage=stage)
    if release_reopen:
        assert stage=='second-context-reopen'
        prior=json.loads((work/'failed-usb-cleanup.json').read_text())
        assert not prior['passed'] and not prior['readbacks'] and not prior['deletions']
        assert prior['stage']==stage and prior['source_report_sha256']==hashlib.sha256(saved_report.read_bytes()).hexdigest()
        inspection=json.loads((work/'reopen-inspection/report.json').read_text())
        retained_info,retained_bytes=retained_reopen(report,work,expected,inspection)
    destination=work/('failed-usb-reopen-cleanup.json' if release_reopen else 'failed-usb-cleanup.json')
    assert not destination.exists(),'cleanup has already been attempted; inspect its journal before another action'
    result=dict(passed=False,source_report_sha256=hashlib.sha256(saved_report.read_bytes()).hexdigest(),
                readbacks={},deletions=[],hardware_io=True,stage=stage,
                uncertain_host_writes=ult.uncertain_writes,host_connect_failures=ult.connect_failures,
                planned_files=[dict(path=path.decode(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                    for path,data in expected.items()])
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
        if release_reopen:
            available=probe.command(b'\x01\x07');assert available['code']==85 and not available['carry'],available
            close_retained_reopen(probe,work,result,save,retained_info,retained_bytes)
        observed={}
        for target in (1,2):
            available=probe.command(bytes([target,7]));assert available['code']==85 and not available['carry'],(target,available)
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
    finally:
        try:
            mon.write_mem(0x9000,controls)
            result['controls_restored']=read(0x9000,256)==controls
            assert result['controls_restored']
        finally:save()
    assert drives()==before and read(0x7350,9)==settings and ci.wait_desktop_live(mon,120)
    assert hashes()==build
    result['passed']=True;save()
    print(f'PASS: failed USB run inputs verified and removed; desktop and DOS paths restored; {destination}',flush=True)
