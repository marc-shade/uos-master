"""Physical editor/selector workflow, invoked by hw_ultimate_check --editor.

All file mutations stay in one fresh private /Usb0 directory. Raw protocol
reads independently verify the UI-created file after the editor has exited.
"""
import hashlib
import json
import sys
import time
import uuid

from hw_storage_check import ci, ROOT, read_vdc, wait_for
from hw_uci_check import Probe
from hwlib import lst_symbol
from ci_storage import launch, check_getcap
from cap_hw_screen import grab, render


def inspect_editor(mon, work):
    """Save foreground state without installing a probe or requiring a live UI."""
    state = {}
    for label, start, end in (
            ('kernal',0x90,0xca),('stack',0x100,0x1ff),
            ('vectors',0x314,0x33d),('files',0x4100,0x413f),
            ('gateway',0x4c80,0x4c92),('editor',0x5000,0x61ff),
            ('picker',0x6200,0x6ea4),('uci',0xdf1c,0xdf1c)):
        data = bytes(mon.read_mem(start,end))
        (work/(label+'-state.bin')).write_bytes(data)
        state[label] = dict(start=hex(start),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        if label not in ('editor','picker','stack'):
            state[label]['hex'] = data.hex()
    for module,names in (('uos-edit',('ready','edlen','dirty','ed_result','sysdev')),
                         ('uos-picker',('ready','editing','error','count','pathlen'))):
        data = (work/('editor-state.bin' if module == 'uos-edit' else 'picker-state.bin')).read_bytes()
        base = 0x5000 if module == 'uos-edit' else 0x6200
        state[module] = {
            name: int.from_bytes(data[lst_symbol(module,name)-base:][:2 if name in ('edlen','pathlen') else 1],'little')
            for name in names}
    (work/'editor-state.json').write_text(json.dumps(state,indent=2)+'\n')
    print(json.dumps(state,indent=2),flush=True)
    return state


def diagnose_exit(ult, mon, work, require_editor=True):
    """Inspect a waiting editor without overwriting its code/document."""
    import subprocess
    report = {}
    assert bytes(mon.read_mem(0x4122,0x4123)) == b'\0\0'
    assert mon.read_mem(0x4c88,0x4c88) == b'\0'
    assert mon.read_mem(0xdf1c,0xdf1c) == b'\0'
    end = lst_symbol('uos-edit','ed_title')
    actual = bytes(mon.read_mem(0x5000,end-1))
    expected = (ROOT/'target/uos-edit.prg').read_bytes()[2:2+end-0x5000]
    (work/'editor-code.bin').write_bytes(actual)
    report['code_differences'] = [(hex(i+0x5000),a,b) for i,(a,b) in enumerate(zip(actual,expected)) if a!=b]
    if require_editor:
        assert actual[:16] == expected[:16], 'current program is not the expected editor'
    code = work/'irq-state.prg'
    subprocess.run(['64tass','-a',str(ROOT/'probes/irq-state.asm'),'-o',str(code)],check=True,capture_output=True)
    saved = bytes(mon.read_mem(0x7c00,0x7dff))
    irq = bytes(mon.read_mem(0x314,0x315))
    try:
        mon.write_mem(0x7c00,code.read_bytes()[2:])
        mon.write_mem(0x7cf0,irq+b'\0\0')
        mon.write_mem(0x314,b'\0\x7c')
        time.sleep(2)
        assert mon.read_mem(0x7cf3,0x7cf3) == b'\1'
        data = bytes(mon.read_mem(0x7d00,0x7dff))
        (work/'irq-states.bin').write_bytes(data)
        report['samples'] = [dict(pc=hex(int.from_bytes(data[i:i+2],'little')),a=data[i+2],
                                  x=data[i+3],y=data[i+4],p=data[i+5],sp=data[i+6]) for i in range(0,256,8)]
    finally:
        if bytes(mon.read_mem(0x314,0x315)) != irq:
            mon.write_mem(0x314,irq)
            time.sleep(0.1)
        mon.write_mem(0x7c00,saved)
        assert bytes(mon.read_mem(0x7c00,0x7dff)) == saved
        (work/'exit-diagnosis.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)
    return report


def cleanup_editor_fixture(ult, mon, work, saved_report, restarted=False):
    """Verify/remove the exact fixture after a failed host exit assertion."""
    import re
    record = json.loads(saved_report.read_text())
    root = record['private_directory'].encode()
    assert re.fullmatch(rb'/Usb0/uos-picker-[0-9a-f]{12}',root)
    folders = [root,root+b'/'+b'a'*112,root+b'/'+b'a'*112+b'/'+b'b'*112]
    assert record['directories'] == [d.decode() for d in folders]
    assert record['source'].encode() == folders[-1]+b'/source-'+b'n'*52+b'.txt'
    assert record['saved'].encode() == folders[-1]+b'/saved-note.txt'
    controls = bytes(mon.read_mem(0x9000,0x90ff))
    mon.write_mem(0x9000,b'\0'+b'\xff'*255)
    recovery = {}
    try:
        sample = diagnose_exit(ult,mon,work,require_editor=not restarted)
        main, end = lst_symbol('uos','main_loop'),lst_symbol('uos','esc_to_desk')
        assert any(main <= int(s['pc'],16) < end and s['sp'] == 255 for s in sample['samples']), 'not in the desktop loop'
        recovery['desktop_foreground_proven_by_irq'] = True
        probe = Probe(ult,work)
        for ctx in (1,2):
            info = probe.command(bytes([ctx,7]))
            assert info['code'] == 85 and not info['carry'],info
        recovery['cwd_after_editor'] = probe.ok(b'\x02\x12')['records'][0][0].decode()
        assert recovery['cwd_after_editor'] == root.decode()+'/'
        for key,expected_name in [('source','expected-source.bin'),('saved','expected-saved.bin')]:
            probe.ok(b'\x01\x02\x01'+record[key].encode())
            try:
                result = probe.command(b'\x01\x04\0\x10')
                assert not result['carry'] and not result['clipped'] and not result['full'],result
                assert result['code'] == 0 or (result['code'] == 255 and not result['status']),result
                data = b''.join(d for d,c in result['records'] if not c)
                (saved_report.parent/(key+'-independent-after-exit.bin')).write_bytes(data)
                assert data == (saved_report.parent/expected_name).read_bytes(),key
                recovery[key] = dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
            finally:
                probe.ok(b'\x01\x03')
        for ctx,path in record['original_cwds_hex'].items():
            probe.ok(bytes([int(ctx),0x11])+bytes.fromhex(path))
        for key in ('saved','source'):
            probe.ok(b'\x01\x09'+record[key].encode())
        for folder in reversed(folders):
            probe.ok(b'\x01\x09'+folder)
        recovery['private_files_removed'] = True
        recovery['desktop_live'] = ci.wait_desktop_live(mon,90)
    finally:
        mon.write_mem(0x9000,controls)
        record['exit_recovery'] = recovery
        saved_report.write_text(json.dumps(record,indent=2)+'\n')
    print('PASS: recovered exact editor fixture; independent saved/source bytes match; desktop live',flush=True)


def abort_editor_load(ult, mon, work, saved_report):
    """Restart a stalled, read-only selector LOAD after saving its document."""
    from hw_ultimate_check import build_hashes
    record = json.loads(saved_report.read_text())
    assert record['build'] == build_hashes(), 'recovery needs the unchanged test image'
    assert any(c['label'] == 'saved-verified' for c in record['captures'])
    assert bytes(mon.read_mem(0x4122,0x4123)) == b'\0\0'
    assert mon.read_mem(0x4c88,0x4c88) == b'\0'
    assert mon.read_mem(0x4c8e,0x4c8e) == b'\1'
    assert mon.read_mem(0xdf1c,0xdf1c) == b'\0'
    state = inspect_editor(mon,work)
    actual = (work/'editor-state.bin').read_bytes()
    size = int.from_bytes(actual[lst_symbol('uos-edit','edlen')-0x5000:][:2],'little')
    document = actual[0xf00:0xf00+size]
    assert document == (saved_report.parent/'expected-saved.bin').read_bytes()
    assert state['uos-edit']['dirty'] == 0 and state['uos-edit']['ready'] == 0
    end = lst_symbol('uos-edit','ed_title')-0x5000
    assert actual[:end] == (ROOT/'target/uos-edit.prg').read_bytes()[2:2+end]
    (work/'document-before-restart.bin').write_bytes(document)
    record['load_abort'] = dict(document_saved=True,bytes=size,no_open_service_handles=True,
                               no_directory_lease=True,evidence=str(work))
    saved_report.write_text(json.dumps(record,indent=2)+'\n')
    print('Restarting the unchanged image after the read-only LOAD stall; 60 seconds quiet',flush=True)
    ult.run_prg((ROOT/'target/uos.prg').read_bytes())
    time.sleep(60)
    assert ci.wait_desktop_live(mon,120)
    cleanup_editor_fixture(ult,mon,work,saved_report,restarted=True)


def editor_workflow(ult, mon, work, report):
    from hw_ultimate_check import build_hashes, ascii_to_petscii
    report.update(editor_workflow=True, captures=[],drives_before=json.loads(ult.drives()),
                  host_sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                for name in ('hw_editor_check.py','hw_ultimate_check.py','hw_storage_check.py')})
    controls = bytes(mon.read_mem(0x9000, 0x90ff))
    settings = bytes(mon.read_mem(0x7350, 0x7358))
    (work/'controls-before.bin').write_bytes(controls)
    (work/'settings-before.bin').write_bytes(settings)
    mon.write_mem(0x9000, b'\0'+b'\xff'*255)
    probe = Probe(ult, work)
    root = ('/Usb0/uos-picker-'+uuid.uuid4().hex[:12]).encode()
    folders = [root, root+b'/'+b'a'*112]
    folders.append(folders[-1]+b'/'+b'b'*112)
    basename = b'source-'+b'n'*52+b'.txt'
    source = folders[-1]+b'/'+basename
    saved = folders[-1]+b'/saved-note.txt'
    payload = (b'ASCII Mixed Case 123\r\n'*36)[:735]
    expected = payload+b'OK\n'
    report.update(private_directory=root.decode(), directories=[p.decode() for p in folders],
                  source=source.decode(), saved=saved.decode(), source_bytes=len(payload),
                  saved_bytes=len(expected), save_command_bytes=3+len(saved),
                  expected_sha256=hashlib.sha256(expected).hexdigest(),operations=[],
                  input_observation='no RAM reads between publishing a key and its quiet interval')
    (work/'expected-source.bin').write_bytes(payload)
    (work/'expected-saved.bin').write_bytes(expected)
    esym = {n:lst_symbol('uos-edit',n) for n in ('ready','edlen','dirty','ed_result')}
    psym = {n:lst_symbol('uos-picker',n) for n in ('ready','editing','error','count','pathlen')}
    original, created, owned = {}, [], []
    active = 'desktop'
    raw_open = None
    code_before = {}

    def save_report():
        report['read_retries'] = ult.read_retries
        (work/'report.json').write_text(json.dumps(report, indent=2)+'\n')

    def value(table, name, size=1):
        return int.from_bytes(mon.read_mem(table[name],table[name]+size-1),'little')

    def ready(module):
        table = esym if module == 'editor' else psym
        if mon.read_mem(0x4c8e,0x4c8e) != (b'\1' if module == 'picker' else b'\0'):
            return False
        return value(table,'ready') == 1 and mon.read_mem(0xc6,0xc6) == b'\0'

    def press(key, target=None, quiet=0.3):
        nonlocal active
        current = active
        wait_for(lambda: ready(current), current+' input', 120)
        table = esym if current == 'editor' else psym
        mon.write_mem(table['ready'], b'\0')
        data = bytes([key]) if isinstance(key,int) else key
        assert len(data) == 1
        target = target or current
        operation = dict(current=current,key=data.hex(),target=target,quiet_seconds=quiet,complete=False)
        report['operations'].append(operation)
        save_report()
        # Do not observe RAM after making input visible until IEC/UCI I/O
        # has had its quiet interval. inject_keys polls C6 immediately.
        mon.write_mem(0x277,data)
        mon.write_mem(0xc6,b'\1')
        time.sleep(quiet)
        deadline = time.monotonic()+180
        while not ready(target):
            if time.monotonic() > deadline:
                raise AssertionError(f'{current} input {data.hex()} did not reach {target}')
            time.sleep(1 if quiet >= 30 else 0.2)
        active = target
        operation['complete'] = True
        save_report()

    def capture(label):
        assert ready(active)
        one_meta, two_meta = {}, {}
        one = read_vdc(mon,work,one_meta)
        two = read_vdc(mon,work,two_meta)
        (work/f'{label}.vdc.bin').write_bytes(one)
        (work/f'{label}.repeat.vdc.bin').write_bytes(two)
        assert one[160:1920] == two[160:1920], (label,'VDC captures disagree')
        bitmap = grab(ult,verbose=False)
        (work/f'{label}.vic.bin').write_bytes(bitmap)
        render(bitmap,str(work/f'{label}.png'))
        report['captures'].append(dict(label=label,first=one_meta,repeat=two_meta))
        save_report()
        print(f'PASS: {label}, paired VDC and VIC capture',flush=True)

    def document():
        size = value(esym,'edlen',2)
        assert size <= 768
        return bytes(mon.read_mem(0x5f00,0x5f00+size-1)) if size else b''

    def enter_leaf_folder():
        assert active == 'picker'
        assert bytes(mon.read_mem(0x7400,0x7400+len(root))) == root+b'/'
        for _ in range(2):
            assert value(psym,'count') == 1
            press(13,quiet=30)
        assert bytes(mon.read_mem(0x7400,0x7400+len(folders[-1]))) == folders[-1]+b'/'

    def filename(name):
        press(0x85)
        assert value(psym,'editing') == 1
        press(0x15)
        for c in ascii_to_petscii(name):
            press(c)
        assert bytes(mon.read_mem(0x7200,0x7200+len(name))) == name+b'\0'

    def leave_editor():
        nonlocal active
        if value(esym,'ready') not in (2,255):
            assert ready('editor')
            ci.inject_keys(mon,b'\x1b')
            if value(esym,'dirty'):
                wait_for(lambda:value(esym,'ready') == 2 and mon.read_mem(0xc6,0xc6) == b'\0',
                         'editor discard confirmation',120)
        if value(esym,'ready') == 2:
            ci.inject_keys(mon,b'Y')
        time.sleep(0.5)
        wait_for(lambda:value(esym,'ready') == 255,'editor one-way exit',120)
        assert ci.wait_desktop_live(mon,90)
        active = 'desktop'
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)

    def independent_read(path, expected_bytes, label):
        nonlocal raw_open
        raw_open = 1
        probe.ok(b'\x01\x02\x01'+path)
        result = probe.command(b'\x01\x04\0\x10')
        assert not result['carry'] and not result['full'] and not result['clipped'], result
        assert result['code'] == 0 or (result['code'] == 255 and not result['status']), result
        data = b''.join(p for p,clipped in result['records'] if not clipped)
        probe.ok(b'\x01\x03')
        raw_open = None
        (work/f'{label}.bin').write_bytes(data)
        assert data == expected_bytes, label
        report['checks'].append(f'{label}: {len(data)} independent bytes match')
        print(f'PASS: {label}, {len(data)} independent bytes',flush=True)

    try:
        save_report()
        report['getcap'] = check_getcap(mon,work)
        assert bytes(mon.read_mem(0x4122,0x4123)) == b'\0\0'
        assert mon.read_mem(0x4c88,0x4c88) == b'\0'
        for ctx in (1,2):
            available = probe.command(bytes([ctx,7]))
            assert available['code'] == 85 and not available['carry'], available
            original[ctx] = probe.ok(bytes([ctx,0x12]))['records'][0][0]
        report['original_cwds_hex'] = {ctx:p.hex() for ctx,p in original.items()}
        for start,end in ((lst_symbol('uos-files','begin'),lst_symbol('uos-files','busy')),
                          (lst_symbol('uos-files','pick_file'),lst_symbol('uos-files','pick_gateway_end'))):
            code_before[start] = (end,bytes(mon.read_mem(start,end-1)))
            (work/f'resident-before-{start:04x}.bin').write_bytes(code_before[start][1])
        for folder in folders:
            probe.ok(b'\x01\x16'+folder)
            created.append(folder)
            save_report()
        raw_open = 1
        owned.append(source)
        probe.ok(b'\x01\x02\x07'+source)
        for offset in range(0,len(payload),511):
            probe.ok(b'\x01\x05\0\0'+payload[offset:offset+511])
        probe.ok(b'\x01\x03')
        raw_open = None
        independent_read(source,payload,'source-before')
        probe.ok(b'\x02\x11'+root)
        launch(mon,b'UOS-EDIT')
        active = 'editor'
        print('Editor LOAD: allowing 30 seconds of quiet IEC I/O',flush=True)
        time.sleep(30)
        wait_for(lambda: ready('editor'),'loaded editor',180)
        assert document() == b''
        press(0x86,'picker',quiet=30)
        enter_leaf_folder()
        assert bytes(mon.read_mem(0x7602,0x7602+len(basename))) == basename+b'\0'
        capture('open-selector')
        press(13,'editor',quiet=30)
        assert document() == payload and value(esym,'dirty') == 0 and value(esym,'ed_result') == 0
        assert bytes(mon.read_mem(0x4122,0x4123)) == b'\0\0' and mon.read_mem(0x4c88,0x4c88) == b'\0'
        capture('opened-note')
        for key in (0xcf,0xcb,13):
            press(key)
        assert document() == expected and value(esym,'dirty') == 1
        press(0x85,'picker',quiet=30)
        assert document() == expected, 'modal LOAD changed the document'
        enter_leaf_folder()
        filename(b'saved-note.txt')
        capture('save-name')
        owned.append(saved)
        started = time.monotonic()
        press(13,'editor',quiet=30)
        report['save_completion_observed_seconds'] = time.monotonic()-started
        assert document() == expected and value(esym,'dirty') == 0 and value(esym,'ed_result') == 0
        assert mon.read_mem(0x4c88,0x4c88) == b'\0'
        capture('saved-verified')
        press(0x85,'picker',quiet=30)
        enter_leaf_folder()
        filename(b'saved-note.txt')
        press(13,quiet=30)
        assert value(psym,'error') == 255 and value(psym,'editing') == 1
        capture('existing-rejected')
        press(27)
        press(27,'editor',quiet=30)
        assert document() == expected and value(esym,'dirty') == 0
        press(0x86,'picker',quiet=30)
        press(13,quiet=30)
        press(27,'editor',quiet=30)
        assert document() == expected and mon.read_mem(0x4c88,0x4c88) == b'\0'
        press(ord('!'))
        ci.inject_keys(mon,b'\x1b')
        wait_for(lambda:value(esym,'ready') == 2 and mon.read_mem(0xc6,0xc6) == b'\0',
                 'editor cancel-discard confirmation',120)
        ci.inject_keys(mon,b'N')
        wait_for(lambda:ready('editor'),'cancelled discard',120)
        assert document() == expected+b'!' and value(esym,'dirty') == 1
        leave_editor()
        assert probe.ok(b'\x02\x12')['records'][0][0] == root+b'/'
        report['checks'].append('Open, modal document retention, verified Save As, existing-file rejection, cancel and dirty-exit protection')
        independent_read(source,payload,'source-unchanged')
        independent_read(saved,expected,'saved-independent')
    finally:
        error = sys.exc_info()[1]
        if error is not None:
            report['failure'] = f'{type(error).__name__}: {error}'
        try:
            # A failed transition can leave a different modal UI active.
            if active in ('editor','picker') and ready('picker'):
                active = 'picker'
            elif active in ('editor','picker') and ready('editor'):
                active = 'editor'
            if active == 'picker':
                if value(psym,'editing'):
                    press(27)
                press(27,'editor',quiet=30)
            if active == 'editor':
                leave_editor()
            assert active == 'desktop' and ci.wait_desktop_live(mon,90)
            mon.write_mem(0x9000,b'\0'+b'\xff'*255)
            assert bytes(mon.read_mem(0x4122,0x4123)) == b'\0\0'
            assert mon.read_mem(0x4c88,0x4c88) == b'\0'
            if raw_open is not None:
                probe.ok(bytes([raw_open,3]))
            for ctx,path in original.items():
                probe.ok(bytes([ctx,0x11])+path)
            for path in reversed(owned):
                result = probe.command(b'\x01\x09'+path)
                missing = result['code'] == 255 and result['status'] == "FILE DOESN'T EXIST"
                assert not result['carry'] and (result['code'] == 0 or missing), result
            for folder in reversed(created):
                probe.ok(b'\x01\x09'+folder)
            report['private_files_removed'] = bool(created)
            for start,(end,data) in code_before.items():
                assert bytes(mon.read_mem(start,end-1)) == data, 'resident file code changed'
            assert bytes(mon.read_mem(0x7350,0x7358)) == settings
            assert ci.wait_desktop_live(mon,90)
            report['paths_settings_code_restored'] = True
            report['drives_after'] = json.loads(ult.drives())
            assert report['drives_after'] == report['drives_before'], 'drive configuration changed'
        except BaseException as cleanup_error:
            report['cleanup_failure'] = f'{type(cleanup_error).__name__}: {cleanup_error}'
            if error is None:
                raise
        finally:
            mon.write_mem(0x9000,controls)
            save_report()
    assert report['build'] == build_hashes()
    report['passed'] = True
    save_report()
    print(f'HW-EDITOR PASS; shared selector and verified Save As; evidence {work}',flush=True)
