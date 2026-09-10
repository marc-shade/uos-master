"""Native editor/Ultimate USB workflow; private fixtures and raw DOS readback."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid

from hw_storage_check import HardwareMonitor,ci
from hw_native_check import hashes,quiet_boot
from hw_uci_check import Probe
from hwlib import desk_tick
from native_editor_check import EditorClient
from native_browser_check import disk_records,browser_screen
from native_capture import ROOT,wait,verify_boot_layout,expected_screen


class USBEditorClient(EditorClient):
    def literal(self,text,quiet=None):
        data=text.encode();assert all(32<=value<127 for value in data)
        delay=self.quiet if quiet is None else quiet
        for offset in range(0,len(data),10):
            chunk=data[offset:offset+10]
            wait(lambda:self.read(0x3d12)==b'\1' and self.read(0xd0,2)==bytes(2),'native literal input ready',120)
            before=int.from_bytes(self.read(0x3d13,2),'little');started=time.monotonic()
            self.put(0x3d12,b'\0');self.put(0x34a,chunk);self.put(0xd0,bytes([len(chunk)]))
            time.sleep(delay)
            wait(lambda:self.read(0xd0,2)==bytes(2) and self.read(0x3d12)==b'\1' and
                 int.from_bytes(self.read(0x3d13,2),'little')==(before+len(chunk))&65535,
                 'complete native GETIN literal queue',120)
            self.events.append(dict(literal_hex=chunk.hex(),native_getin_queue=True,
                                    quiet_seconds=delay,
                                    elapsed_seconds=round(time.monotonic()-started,3)))

    def prompt(self,key,text,confirm=None):
        self.key(key);self.literal(text);self.key(13,quiet=self.scan_quiet)
        if confirm is not None:self.key(ord(confirm),quiet=self.scan_quiet)


def raw_read(probe,path,wanted,work,label):
    data=bytearray();probe.ok(b'\x01\x02\x01'+path)
    try:
        while len(data)<len(wanted):
            result=probe.command(b'\x01\x04\0\x10')
            assert not result['carry'] and not result['full'] and not result['clipped'],result
            assert result['code']==0 or result['code']==255 and not result['status'],result
            assert all(not clipped for _,clipped in result['records'])
            chunk=b''.join(part for part,_ in result['records'])
            assert len(chunk)==min(4096,len(wanted)-len(data)),(label,len(data),len(chunk))
            data.extend(chunk)
        end=probe.command(b'\x01\x04\x01\0')
        assert not end['carry'] and not end['full'] and not end['clipped'],end
        assert end['code'] in (0,255) and not end['status'] and all(not part for part,_ in end['records']),end
    finally:probe.ok(b'\x01\x03')
    (work/(label+'.bin')).write_bytes(data)
    assert data==wanted,(label,'independent stored bytes differ')
    return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),path=path.decode())


def run(ult,*,redraw=False,usb_apps=False,usb_browser=False,fixture_report=None):
    if usb_browser:usb_apps=True
    prefix='uos-hardware-native-directories-' if usb_browser else 'uos-hardware-native-usb-apps-' if usb_apps else 'uos-hardware-native-redraw-' if redraw else 'uos-hardware-native-ultimate-'
    work=Path(tempfile.mkdtemp(prefix=prefix))
    print(f'Native Ultimate hardware evidence: {work}',flush=True)
    disk=work/'native.d64';shutil.copyfile(ROOT/'target/native/uos128.d64',disk)
    mon=HardwareMonitor(ult)
    client=USBEditorClient(mon,work,quiet=4,scan_quiet=30,capture_quiet=2,poll=2,key_timeout=1800)
    read=client.read;directory=('/Usb0/uos-native-'+uuid.uuid4().hex[:12]).encode()
    previous=None
    if fixture_report:
        assert usb_apps
        previous=json.loads(fixture_report.read_text())
        assert not previous['passed'] and previous['legacy_desktop_restored'] and previous['images_unchanged']
        assert previous['build']==hashes()
        if usb_browser:
            assert previous['error']=='' and not previous.get('usb_apps') and not previous['editor_states']
            assert not previous['usb_browser'].get('pages') and previous['private_subdirectory_created']
            assert not previous['uncertain_host_writes']
        else:
            assert previous['error']=='1' and previous['usb_apps']['passed']
            assert previous['editor_states'][-1]['label']=='ultimate-large-open' and not previous.get('large_save_seconds')
        directory=previous['private_directory'].encode()
    assert re.fullmatch(rb'/Usb0/uos-native-[0-9a-f]{12}',directory)
    fixtures={b'NOTE.TXT':b'ONE "QUOTED" LINE\r\nTWO\nTHREE\r'+bytes([0,255])+b' END\r\n',
              b'EMPTY.TXT':b'',b'LARGE.TXT':(b'0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n'*1800)[:66053]}
    if usb_apps:
        from hw_native_usb_apps import app_fixtures
        fixtures.update(app_fixtures())
    report=dict(passed=False,build=hashes(),host=ult.host,private_directory=directory.decode(),
                native_disk_sha256=hashlib.sha256(disk.read_bytes()).hexdigest(),legacy_desktop_restored=False,
                events=client.events,frames=client.frames,captures=client.capture.records,
                heap_observations=client.heaps,editor_states=client.states,ram_observations=client.observations,
                quiet_seconds=dict(boot=60,key_or_literal_queue=4,io_initial=30,capture=2,poll=2),
                host_request_timeout_seconds=ult.timeout,uncertain_host_writes=ult.uncertain_writes,
                fixture_readbacks={},output_readbacks={})
    if previous:
        report['fixture_reuse']=dict(source_report=str(fixture_report),
            source_report_sha256=hashlib.sha256(fixture_report.read_bytes()).hexdigest(),
            prior_outputs_readbacks={},prior_outputs_removed=False,complete_workflow_restarted=True)
    if redraw:report['redraw_timings']={}
    def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def drives(label):
        info=json.loads(ult.drives());assert not info['errors'],info
        (work/f'drives-{label}.json').write_text(json.dumps(info,indent=2)+'\n')
        return {key:value for record in info['drives'] for key,value in record.items()}
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and ci.wait_desktop_live(mon,120)
    assert read(0x4122,2)==bytes(2),'legacy files remain owned'
    settings=read(0x7350,9);(work/'settings-before.bin').write_bytes(settings)
    before=drives('before');assert before['a']['enabled'] and before['a']['bus_id']==8
    (work/'ultimate-version.json').write_text(ult.version())
    probe=Probe(ult,work);controls=read(0x9000,256);original={};navigation=None
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        for target in (1,2):
            available=probe.command(bytes([target,7]));assert available['code']==85 and not available['carry'],available
            original[target]=probe.ok(bytes([target,0x12]))['records'][0][0]
        report['dos_paths_before_hex']={str(t):p.hex() for t,p in original.items()};save()
        if previous:
            assert report['dos_paths_before_hex']==previous['dos_paths_before_hex']
            report['private_directory_reused']=True
        else:
            probe.ok(b'\x01\x16'+directory)
            report['private_directory_created']=True
        save()
        for name,data in fixtures.items():
            print(f'{"Rechecking" if previous else "Preparing"} private USB fixture {name.decode()}: {len(data)} bytes',flush=True)
            (work/('fixture-'+name.decode()+'.bin')).write_bytes(data)
            path=directory+b'/'+name
            if not previous:
                probe.ok(b'\x01\x02\x07'+path)
                try:
                    for offset in range(0,len(data),511):
                        probe.ok(b'\x01\x05\0\0'+data[offset:offset+511])
                        if offset and offset%(511*32)==0:print(f'USB fixture: {offset} bytes written',flush=True)
                finally:probe.ok(b'\x01\x03')
            report['fixture_readbacks'][name.decode()]=raw_read(probe,path,data,work,'fixture-readback-'+name.decode())
            save()
        if usb_browser:
            from hw_native_usb_browser import EMPTY_FOLDER,prepare_oracles
            if not previous:probe.ok(b'\x01\x16'+directory+b'/'+EMPTY_FOLDER)
            report['private_subdirectory_reused' if previous else 'private_subdirectory_created']=True;save()
            report['usb_browser']=dict(oracles=prepare_oracles(probe,directory,original[2]));save()
        if previous and usb_browser:
            assert set(previous['fixture_readbacks'])=={name.decode() for name in fixtures}
            members={bytes.fromhex(raw)[1:] for raw in report['usb_browser']['oracles']['private']['pages']['0']['entries_hex']}
            assert members==set(fixtures)|{EMPTY_FOLDER}
            report['fixture_reuse']['all_source_fixtures_rechecked']=True;save()
        if previous and not usb_browser:
            assert set(previous['fixture_readbacks'])=={name.decode() for name in fixtures}
            note=fixtures[b'NOTE.TXT']
            prior_outputs={b'HISTORY':b'42\r',b'A LONG SAVED DOCUMENT NAME.TXT':note[:5]+b'!'+note[5:]}
            for name,data in prior_outputs.items():
                print('Reading prior-run output before removal: '+name.decode(),flush=True)
                report['fixture_reuse']['prior_outputs_readbacks'][name.decode()]=raw_read(
                    probe,directory+b'/'+name,data,work,'prior-output-'+name.decode());save()
            for name in prior_outputs:probe.ok(b'\x01\x09'+directory+b'/'+name)
            report['fixture_reuse']['prior_outputs_removed']=True;save()
    finally:mon.write_mem(0x9000,controls)
    switched=False;outputs={}
    try:
        ult.mount(disk.read_bytes(),'a','d64','readonly');switched=True
        ult.reset();quiet_boot('Native Ultimate boot')
        wait(lambda:read(0x1c13,6)==b'UOS128' and read(0x3d12)==b'\1','native Ultimate boot',120)
        report['resident_boot']=verify_boot_layout(client.capture);save()
        protected=[]
        for bank in (0,1):
            client.key(ord('1')+bank);client.key(ord('A'));page=read(0x3d03)[0]
            assert page==(0xc0 if bank==0 else 4)
            client.key(ord('W'));client.key(ord('V'));assert read(0x3d16)==b'\0'
            protected.append((bank,page))
        original_keys=read(0x1000,256);(work/'function-keys-before.bin').write_bytes(original_keys)
        client.key(ord('B'),quiet=30)
        records=disk_records(disk.read_bytes())
        if usb_browser:
            from hw_native_usb_browser import Navigation
            navigation=Navigation(client,work,report,directory,outputs,save)
            navigation.start(records,fixtures[b'NOTE.TXT'])
        if usb_apps:
            from hw_native_usb_apps import workflow
            workflow(client,work,report,records,directory,outputs,save,navigation)
        else:
            client.select([r['name'] for r in records].index(b'EDITOR'))
            client.key(13,quiet=30)
        client.editor_active=True
        assert client.cpu_read('editor-saved-function-keys',client.addresses['ed_saved_keys'],256)==original_keys
        client.heap_equal('empty-editor-with-workspace',(143-(ROOT/'target/native/editor.prg').read_bytes()[12],219,29))
        current_format=client.cpu_read('editor-initial-format',client.addresses['ed_format'],1)[0]
        assert current_format in range(4)
        for _ in range((3-current_format)%4):client.key(0x8b)
        device=1
        def check(label,data,cursor,**kw):
            client.check(label,data,cursor,device=device,fmt=3,**kw);save()
        def path(name):return (directory+b'/'+name).decode()
        def timing(label,count,delay):
            report['redraw_timings'][label]=dict(event_index=len(client.events)-1,characters=count,
                quiet_seconds=delay,elapsed_seconds=client.events[-1]['elapsed_seconds'])
        def field_check(label,data,cursor,**kw):
            client.key(0x86)
            client.literal('/Usb0/Note',quiet=.1);timing(label+'-ten-characters',10,.1)
            check(label+'-field',data,cursor,mode=2,**kw)
            client.key(20,quiet=.1);check(label+'-shortened',data,cursor,mode=2,**kw)
            client.key(27,quiet=.1);check(label+'-cancelled',data,cursor,**kw)
        check('ultimate-editor-new',b'',0)
        raw=fixtures[b'NOTE.TXT'];client.prompt(0x85,path(b'NOTE.TXT'))
        check('ultimate-open-mixed',raw,0,name=path(b'NOTE.TXT'))
        if redraw:field_check('redraw-small',raw,0,name=path(b'NOTE.TXT'))
        client.prompt(0x88,'000005');client.key(ord('!'));want=raw[:5]+b'!'+raw[5:]
        check('ultimate-edited-quote',want,6,dirty=True,name=path(b'NOTE.TXT'))
        name=b'A LONG SAVED DOCUMENT NAME.TXT';client.prompt(0x86,path(name));outputs[name]=want
        check('ultimate-saved-long-path',want,6,name=path(name),status=1)
        client.prompt(0x85,path(b'MISSING.TXT'));check('ultimate-open-failure-keeps-document',want,6,name=path(name),status=2)
        client.prompt(0x85,path(b'EMPTY.TXT'));check('ultimate-open-empty',b'',0,name=path(b'EMPTY.TXT'))
        raw=fixtures[b'LARGE.TXT']
        print('Opening 66,053 bytes through the native Ultimate backend',flush=True)
        client.prompt(0x85,path(b'LARGE.TXT'));report['large_open_seconds']=client.events[-1]['elapsed_seconds']
        check('ultimate-large-open',raw,0,name=path(b'LARGE.TXT'))
        client.prompt(0x88,'010001')
        if redraw:
            check('redraw-large-cursor',raw,65537,name=path(b'LARGE.TXT'))
            client.key(0x1d,quiet=.1);timing('large-cursor-right',1,.1)
            check('redraw-large-right',raw,65538,name=path(b'LARGE.TXT'))
            client.key(0x9d,quiet=.1);timing('large-cursor-left',1,.1)
            check('redraw-large-left',raw,65537,name=path(b'LARGE.TXT'))
            field_check('redraw-large',raw,65537,name=path(b'LARGE.TXT'))
        client.literal('C128')
        if redraw:timing('large-insert-queue',4,4)
        client.key(20,quiet=.1 if redraw else None)
        if redraw:timing('large-backspace',1,.1)
        want=raw[:65537]+b'C12'+raw[65537:]
        check('ultimate-large-edited',want,65540,dirty=True,name=path(b'LARGE.TXT'))
        name=b'LARGE COPY.TXT';(work/'saved-expected.bin').write_bytes(want)
        print('Saving, closing, reopening and verifying all 66,056 bytes',flush=True)
        client.prompt(0x86,path(name));report['large_save_seconds']=client.events[-1]['elapsed_seconds'];outputs[name]=want
        check('ultimate-large-save-verified',want,65540,name=path(name),status=1)
        client.prompt(0x86,path(name));check('ultimate-existing-file-rejected',want,65540,name=path(name),status=7)
        client.key(0x87);check('ultimate-new-after-save',b'',0)
        client.prompt(0x8c,'2');device=2
        client.prompt(0x85,path(name));report['large_reopen_seconds']=client.events[-1]['elapsed_seconds']
        check('ultimate-reopen-second-context',want,0,name=path(name))
        client.prompt(0x88,'010001');check('ultimate-reopened-edit',want,65537,name=path(name))
        client.key(27,quiet=30);client.editor_active=False;client.selected=0
        assert read(0x1000,256)==original_keys
        (work/'function-keys-after.bin').write_bytes(read(0x1000,256))
        if navigation:
            navigation.device=2
            navigation.returned('usb-browser-after-editor')
        else:
            # The editor retains its Ultimate data preference on return.
            assert read(0x3d2a)==b'\3'
        client.key(ord('F'),quiet=30)
        client.frames_equal('browser-after-ultimate-editor',lambda cols:browser_screen(cols,records))
        client.key(27);client.heap_equal('workspace-after-ultimate-editor',(143,219,30))
        for bank,page in protected:
            client.key(ord('1')+bank);client.key(ord('V'));assert read(0x3d16)==b'\0'
            data=b''.join(client.capture.capture(f'workspace-{bank}-{offset:04x}',bank=bank,address=page*256+offset,
                                                count=min(2000,8192-offset)) for offset in range(0,8192,2000))
            assert data==bytes((i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(8192))
            (work/f'workspace-{bank}-all.bin').write_bytes(data);client.key(ord('F'))
        client.heap_equal('all-memory-released',(175,251,32))
        client.frames_equal('workspace-restored',lambda cols:expected_screen(cols,1))
        assert read(0x98)==b'\0' and read(0x3de0,4)==bytes(4) and read(0x3dc0)==b'\0' and read(0x3dd0)==b'\0'
        report.update(native_checks_passed=True,saved_bytes=len(want),saved_sha256=hashlib.sha256(want).hexdigest(),
                      all_owned_memory_and_files_released=True,function_key_bytes_restored=256,independent_workspace_bytes=16384)
    except BaseException as error:
        report['error']=str(error)
        try:
            (work/'failure-context.bin').write_bytes(read(0x3d00,0xe4))
            (work/'failure-vic.bin').write_bytes(read(0x400,1000))
            (work/'failure-ultimate-status.bin').write_bytes(read(0x4f00,32))
        except Exception as diagnostic:report['diagnostic_error']=str(diagnostic)
        raise
    finally:
        save()
        if switched:
            print('Restoring the deployed legacy desktop',flush=True)
            ult.mount((ROOT/'target/ultos.d64').read_bytes(),'a','d64','readwrite')
            ult.run_prg((ROOT/'target/uos.prg').read_bytes());quiet_boot('Legacy desktop boot')
            wait(lambda:read(0x33c,2)==desk_tick().to_bytes(2,'little'),'legacy desktop vector',120)
            assert ci.wait_desktop_live(mon,120)
            current=read(0x7350,9);report['legacy_boot_settings_hex']=current.hex()
            assert current[2:7]==settings[2:7],'legacy boot applied different settings'
            mon.write_mem(0x7350,settings);assert read(0x7350,9)==settings
            after=drives('restored')
            assert {k:v for k,v in before.items() if k!='a'}=={k:v for k,v in after.items() if k!='a'}
            report['legacy_desktop_restored']=True
        report['images_unchanged']=report['build']==hashes();save()
    controls=read(0x9000,256)
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        report['dos_paths_after_hex']={str(t):probe.ok(bytes([t,0x12]))['records'][0][0].hex() for t in (1,2)}
        if navigation:navigation.verify_final(probe)
        for name,data in {**fixtures,**outputs}.items():
            print(f'Independent closed-file readback: {name.decode()}',flush=True)
            report['output_readbacks'][name.decode()]=raw_read(probe,directory+b'/'+name,data,work,'final-readback-'+name.decode());save()
        for target,path_before in original.items():
            probe.ok(bytes([target,0x11])+path_before)
            assert probe.ok(bytes([target,0x12]))['records'][0][0]==path_before
        report['dos_paths_restored']=True
        # Remove only files created in this run, after complete byte evidence.
        for name in reversed(list({**fixtures,**outputs})):
            probe.ok(b'\x01\x09'+directory+b'/'+name)
        if usb_browser:probe.ok(b'\x01\x09'+directory+b'/'+EMPTY_FOLDER)
        probe.ok(b'\x01\x09'+directory);report['private_files_removed']=True
    except BaseException as error:report['readback_error']=str(error);raise
    finally:mon.write_mem(0x9000,controls);save()
    assert report['build']==hashes() and ci.wait_desktop_live(mon,120)
    assert read(0x7350,9)==settings
    report['passed']=True;save()
    print(f'HW-NATIVE-ULTIMATE PASS; all USB bytes verified; desktop restored; {work}',flush=True)


def cleanup_fixture_timeout(ult,saved_report):
    """Clean only the first NOTE fixture from an interrupted pre-boot setup."""
    report=json.loads(saved_report.read_text());work=saved_report.parent
    assert not report['passed'] and report['build']==hashes()
    assert report.get('private_directory_created') and not report['events'] and not report['fixture_readbacks']
    directory=report['private_directory'].encode()
    assert re.fullmatch(rb'/Usb0/uos-native-[0-9a-f]{12}',directory)
    expected=(work/'fixture-NOTE.TXT.bin').read_bytes();assert len(expected)==37
    mon=HardwareMonitor(ult)
    def read(address,count=1):return bytes(mon.read_mem(address,address+count-1))
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and ci.wait_desktop_live(mon,120)
    assert read(0x4122,2)==bytes(2)
    controls=read(0x9000,256);settings=read(0x7350,9);probe=Probe(ult,work)
    original=None;result=dict(passed=False,private_directory=directory.decode())
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        for target in (1,2):
            info=probe.command(bytes([target,7]));assert info['code']==85 and not info['carry'],info
        original=probe.ok(b'\x02\x12')['records'][0][0]
        probe.ok(b'\x02\x11'+directory)
        opened=probe.command(b'\x02\x13');assert not opened['carry'] and opened['code'] in (0,1),opened
        names=[]
        if opened['code']==0:
            entries=probe.ok(b'\x02\x14');assert not entries['full'] and not entries['clipped']
            for data,clipped in entries['records']:
                assert not clipped
                if data:
                    assert not data[0]&0x18 and data[1:].upper()==b'NOTE.TXT',data
                    names.append(data[1:])
        assert len(names)<=1
        probe.ok(b'\x02\x11'+original)
        if names:
            path=directory+b'/'+names[0]
            probe.ok(b'\x01\x02\x01'+path)
            try:
                metadata=probe.ok(b'\x01\x07')['records'][0][0]
                assert len(metadata)>=12 and not metadata[11]&0x18
                count=int.from_bytes(metadata[:4],'little');assert count<=len(expected)
            finally:probe.ok(b'\x01\x03')
            result['readback']=raw_read(probe,path,expected[:count],work,'timeout-fixture-readback')
            probe.ok(b'\x01\x09'+path)
        probe.ok(b'\x01\x09'+directory)
        result['private_files_removed']=True
    except BaseException as error:result['error']=str(error);raise
    finally:
        try:
            if original is not None:
                probe.ok(b'\x02\x11'+original)
                assert probe.ok(b'\x02\x12')['records'][0][0]==original
                result['dos_path_restored']=True
        finally:
            mon.write_mem(0x9000,controls)
            (work/'timeout-fixture-cleanup.json').write_text(json.dumps(result,indent=2)+'\n')
    assert read(0x7350,9)==settings and ci.wait_desktop_live(mon,120)
    result.update(passed=True,settings_unchanged=True,desktop_live=True)
    (work/'timeout-fixture-cleanup.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'PASS: inspected and removed only the interrupted private fixture; {work}',flush=True)
