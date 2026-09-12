"""Observe the sealed native desktop on hardware, then restore the deployment."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.parse import quote

from hw_storage_check import HardwareMonitor,ci
from hw_native_check import hashes,quiet_boot
from hw_native_ultimate_check import prepare_restore,restore_desktop,raw_read
from hw_uci_check import Probe
from hwlib import desk_tick
from native_capture import ROOT,NativeCapture,wait,expected_screen,calculator_screen
from native_running_layout import verify_running_layout
from native_mode_capture import NativeModeCapture
from native_browser_check import disk_records,browser_screen
from native_editor_check import editor_screen
from launcher_scene import surface,console


def run_native_workflow(mon,capture,work,disk,report,save,*,key_quiet=4,key_poll=2,kernel_prefix='native-desktop',additional_apps=None):
    """Shared CPU workflow; caller owns boot, restoration and temporary files."""
    modes=NativeModeCapture(mon,work,quiet=capture.quiet,kernel_prefix=kernel_prefix,batch=capture.batch)
    report['mode_captures']=modes.records
    def read(address,count=1):
        data=bytes(mon.read_mem(address,address+count-1));mon.resume();return data
    def ready():return read(0x3d12)==b'\1' and read(0xd0,2)==bytes(2)
    def key(value):
        wait(ready,'native desktop/app idle',180)
        start=time.monotonic();notice=start
        with capture.batch(f'key-{value:02x}'):
            assert ready(),'native input changed before key injection'
            previous=int.from_bytes(read(0x3d13,2),'little')
            mon.write_mem(0x3d12,b'\0');mon.write_mem(0x34a,bytes([value]));mon.write_mem(0xd0,b'\1');mon.resume()
        time.sleep(key_quiet)
        while not (ready() and int.from_bytes(read(0x3d13,2),'little')==(previous+1)&65535):
            elapsed=time.monotonic()-start;assert elapsed<900,('native desktop key timeout',value,elapsed)
            if time.monotonic()-notice>=30:
                print(f'Native desktop key {value:02X}: waiting for complete operation ({elapsed:.0f}s)',flush=True);notice=time.monotonic()
            time.sleep(key_poll)
        report['events'].append(dict(key=value,elapsed_seconds=round(time.monotonic()-start,3)));save()
    def screens(label,oracle):
        for mode,columns,address in ((0,40,0x400),(1,80,0)):
            actual=capture.capture(label+('-vic' if mode==0 else '-vdc'),mode=mode,address=address,count=columns*25)
            assert actual==oracle(columns),(label,columns)
        report['screens'].append(label);save();print('Verified native screens:',label,flush=True)
    def desktop(label,selected=0):
        assert read(0x3d2f)==bytes([selected]),'saved native desktop selection differs'
        assert read(0x3d60,32)==(ROOT/'target/native-desktop/desktop.prg').read_bytes()[2:34]
        assert read(0x3d20)==b'\x20' and read(0x3d23)==b'\2'
        before_jiffy=read(0xa0,3)
        actual=b''.join(capture.capture(label+f'-surface-{offset:04x}',address=0xc000+offset,
                         count=min(2000,9216-offset)) for offset in range(0,9216,2000))
        (work/(label+'-surface.bin')).write_bytes(actual);assert actual==surface(selected)
        vdc=capture.capture(label+'-vdc',mode=1,address=0,count=2000);assert vdc==console(80,selected)
        registers=modes.snapshot(label+'-mode')
        assert registers['vic_d011']&0x7f==0x3b and registers['vic_d016']&0x1f==8 and registers['vic_d018']&0xfe==0x80
        assert registers['vic_irq_mask']&15==1 and registers['vic_sprites']==0
        assert registers['cia2_port']&3==0 and registers['cia2_ddr']&3==3
        assert registers['foreground_mmu'] in (0,0x0e) and not registers['mode']&0x40 and registers['common']&15==4
        assert (registers['cpu_ddr'],registers['cpu_port'])==(0x2f,0x75) and registers['text_graphics']==255
        assert registers['text_display']&128 and not registers['cpu_speed']&1
        assert read(0xa0,3)!=before_jiffy
        heap=read(0x3800,0x600);(work/(label+'-heap.bin')).write_bytes(heap)
        app_pages=(ROOT/'target/native-desktop/desktop.prg').read_bytes()[12]
        assert heap[0x50:0xff].count(0)+heap[0x104:0x1ff].count(0)==426-36-app_pages
        report['desktops'].append(dict(label=label,selected=selected,surface_bytes=9216,
            surface_sha256=hashlib.sha256(actual).hexdigest(),vdc_bytes=2000,irq_advanced=True,registers=registers,
            qualification='CPU-captured display RAM and mode registers; no physical video pixel capture'))
        save();print('Verified native desktop RAM, VDC and display mode:',label,flush=True)
    wait(lambda:read(0x1c13,6)==b'UOS128' and ready(),'native graphical desktop boot',300)
    report['resident_boot']=verify_running_layout(capture,ROOT,'resident-boot',image_dir=ROOT/'target'/kernel_prefix);save()
    desktop('desktop-boot')
    key(9);desktop('desktop-editor-selected',1)
    key(ord('C'));screens('calculator-new',lambda cols:calculator_screen(cols,'0',[]))
    for value in b'12+30=':key(value)
    screens('calculator-result',lambda cols:calculator_screen(cols,'42',['42']))
    key(27);desktop('desktop-after-calculator')
    key(ord('E'));screens('editor-new',lambda cols:editor_screen(cols,b'',0))
    document=b'C128'
    for value in document:key(value)
    screens('editor-typed',lambda cols:editor_screen(cols,document,4,dirty=True))
    key(27);key(ord('Y'));desktop('desktop-after-editor',1)
    key(ord('F'));screens('files',lambda cols:browser_screen(cols,disk_records(disk.read_bytes())))
    key(27);desktop('desktop-after-files',2)
    if additional_apps is not None:
        additional_apps(key=key,screens=screens,desktop=desktop,read=read)
    key(27);screens('workspace-returned',lambda cols:expected_screen(cols,0))
    report['resident_return']=verify_running_layout(capture,ROOT,'resident-return',image_dir=ROOT/'target'/kernel_prefix);save()
    final_mode=modes.snapshot('workspace-returned-mode');report['final_mode']=final_mode;save()
    heap=read(0x3800,0x600);(work/'final-native-heap.bin').write_bytes(heap)
    assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251)
    assert all(heap[0x400+i*8]==0 for i in range(32))
    assert read(0x3d20)==b'\0' and read(0x3d23)==b'\0'
    assert final_mode['cpu_ddr']==0x2f and final_mode['cpu_port']==0x73 and final_mode['text_graphics']==0
    assert all(item['restored'] for item in capture.records)
    assert all(item['restored'] for item in modes.records)
    report['native_checks_passed']=True;save()


def run(ult, *, workflow=run_native_workflow, monitor_class=HardwareMonitor,
        paused_capture=False, cleanup_after_failure=True, expected_images=None,
        preflight=None, full_desktop_workflow=None):
    focused=(workflow is not run_native_workflow) if full_desktop_workflow is None else not full_desktop_workflow
    work=Path(tempfile.mkdtemp(prefix='uos-hardware-native-transport-' if focused else 'uos-hardware-native-desktop-'))
    print(f'Native {"capture transport" if focused else "desktop"} hardware evidence: {work}',flush=True)
    disk=work/'native.d64';shutil.copyfile(ROOT/'target/native-desktop/uos128.d64',disk)
    if expected_images is None:
        expected_images=dict(disk='bffb5dd7f136e952c4be93ca556657e6f8fd05f2f9248fb8154b718fad11e266',
                             kernel='c01eacde129088bf1682b1fe5861a875084cff85534d961e35a84f50b195468b')
    assert set(expected_images)=={'disk','kernel'} and all(re.fullmatch(r'[0-9a-f]{64}',v) for v in expected_images.values())
    assert hashlib.sha256(disk.read_bytes()).hexdigest()==expected_images['disk']
    assert hashlib.sha256((ROOT/'target/native-desktop/uos128.prg').read_bytes()).hexdigest()==expected_images['kernel']
    report=dict(passed=False,physical_hardware_io=True,build=hashes(),events=[],desktops=[],screens=[],
                legacy_desktop_restored=False,uncertain_host_writes=ult.uncertain_writes,
                host_connect_failures=ult.connect_failures,host_control_requests=ult.control_requests,
                host_upload_checks=ult.upload_checks)
    report['full_desktop_workflow']=not focused
    report['image_admission']=dict(expected_images)
    def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    ult.record_event=save;save()
    mon=monitor_class(ult)
    capture=NativeCapture(mon,work,quiet=2,kernel_prefix='native-desktop',
                          batch=mon.paused if paused_capture else None)
    report['paused_capture_batches']=getattr(mon,'batches',[])
    report['ram_write_receipts']=getattr(ult,'ram_write_receipts',[])
    report['captures']=capture.records
    def read(address,count=1):return bytes(mon.read_mem(address,address+count-1))
    def drives(label):
        data=json.loads(ult.drives());assert not data['errors']
        (work/f'drives-{label}.json').write_text(json.dumps(data,indent=2)+'\n')
        return {name:value for row in data['drives'] for name,value in row.items()}
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and ci.wait_desktop_live(mon,120)
    assert read(0x4122,2)==bytes(2)
    settings=read(0x7350,9);(work/'settings-before.bin').write_bytes(settings)
    before=drives('before');assert before['a']['enabled'] and before['a']['bus_id']==8
    (work/'ultimate-version.json').write_text(ult.version())
    probe=Probe(ult,work);controls=read(0x9000,256);original={}
    report['stage']='legacy-preflight';report['preflight_commands']=[];save()
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        for target in (1,2):
            report['preflight_commands'].append(dict(command_hex=bytes([target,7]).hex(),completed=False));save()
            available=probe.command(bytes([target,7]));assert available['code']==85 and not available['carry']
            report['preflight_commands'][-1]['completed']=True;save()
            report['preflight_commands'].append(dict(command_hex=bytes([target,0x12]).hex(),completed=False));save()
            original[target]=probe.ok(bytes([target,0x12]))['records'][0][0]
            report['preflight_commands'][-1]['completed']=True;save()
        report['dos_paths_before_hex']={str(t):p.hex() for t,p in original.items()}
        if preflight is not None:
            preflight(ult,mon,probe,work,report,save)
        report['stage']='prepare-legacy-restoration';save()
        program=prepare_restore(ult,probe,work,report,save,before)
    except BaseException as error:
        report['preflight_error']=dict(type=type(error).__name__,message=str(error))
        # Observe only fixed RAM and the nondestructive UCI status register.
        # Preserve pending command state; recovery owns any subsequent action.
        report['preflight_failure_state']={}
        for name,address,count in [('tick',0x33c,2),('irq',0x314,2),
                ('probe',0x5000,len(probe.code)),('command',0x5500,16),
                ('probe_state',0x5f00,32),('panic',0xd00,288),
                ('app_state',0x4122,2),('uci_status',0xdf1c,1)]:
            try:
                data=read(address,count);(work/('preflight-error-'+name+'.bin')).write_bytes(data)
                report['preflight_failure_state'][name]=dict(address=address,bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            except Exception as observation_error:
                report['preflight_failure_state'][name]=dict(error=str(observation_error))
        save();raise
    finally:
        mon.write_mem(0x9000,controls)
        report['preflight_controls_restored']=read(0x9000,256)==controls;save()
    assert report['preflight_controls_restored']
    report['stage']='native-boot';save()
    switched=False;deferred_error=None
    try:
        switched=True
        ult.mount(disk.read_bytes(),'a','d64','readonly')
        mounted=drives('native')['a'];path=mounted['image_file']
        if not path.startswith('/'):path=mounted['image_path'].rstrip('/')+'/'+path
        assert re.fullmatch(r'/Temp/temp[0-9a-fA-F]{4}',path) and path!=report['restore_disk_path']
        report['native_disk_upload_path']=path;save()
        ult.reset();quiet_boot('Native desktop boot')
        workflow(mon,capture,work,disk,report,save)
    except BaseException as error:
        report['native_error']=str(error);save()
        if not cleanup_after_failure:raise
        deferred_error=error
    finally:
        try:
            if switched:restore_desktop(ult,mon,read,report,save,before,settings,drives,program)
        finally:report['images_unchanged']=report['build']==hashes();save()
    assert report['legacy_desktop_restored'] and report['images_unchanged']
    controls=read(0x9000,256)
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        for target,path in original.items():
            assert probe.ok(bytes([target,0x12]))['records'][0][0]==path
        report['dos_paths_restored']=True
        temporary={report['native_disk_upload_path']:disk.read_bytes(),report['restore_prg_path']:program}
        assert len(temporary)==2 and report['restore_prg_owned']
        current=drives('before-cleanup')
        report['temporary_readbacks']={};report['temporary_deletions']=[];save()
        for path,expected in temporary.items():
            for drive in current.values():
                mounted=drive.get('image_file','')
                if mounted and not mounted.startswith('/'):mounted=drive['image_path'].rstrip('/')+'/'+mounted
                assert mounted!=path
            report['temporary_readbacks'][path]=raw_read(probe,path.encode(),expected,work,'readback-'+Path(path).name);save()
        for path in temporary:
            action=dict(path=path,started=True,confirmed=False);report['temporary_deletions'].append(action);save()
            probe.ok(b'\x01\x09'+path.encode())
            status,body=ult._call('GET','/v1/files'+quote(path,safe='/')+':info')
            assert status==404 and json.loads(body).get('errors')
            action['confirmed']=True;save()
    except BaseException as error:report['cleanup_error']=str(error);save();raise
    finally:
        mon.write_mem(0x9000,controls);report['controls_restored']=read(0x9000,256)==controls;save()
    assert report['controls_restored'] and not report['uncertain_host_writes']
    assert drives('final')==before and read(0x7350,9)==settings and ci.wait_desktop_live(mon,120)
    assert report['build']==hashes()
    report['cleanup_complete']=True;save()
    if deferred_error is not None:raise deferred_error
    report['passed']=True;save()
    print(f'HW-NATIVE-{"TRANSPORT" if focused else "DESKTOP"} PASS; bounded workflow; original deployment restored; {work}',flush=True)
