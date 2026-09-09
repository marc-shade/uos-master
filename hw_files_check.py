"""Physical shared-file and desktop-viewer workflow, invoked with --files.

Only a newly-created private /Usb0 directory is changed. Firmware raw READ
packets provide an independent byte oracle after the service has closed files.
"""
import hashlib
import json
import re
import subprocess
import time
import uuid

from hw_storage_check import ci, ROOT, read_vdc, wait_for, screen_code
from hw_uci_check import Probe
from hwlib import lst_symbol
from ci_storage import check_getcap, launch_from_apps
from cap_hw_screen import grab, render


def write_diagnostic(ult, mon, work):
    """Isolate firmware WRITE_DATA behavior from the shared file service."""
    assert bytes(mon.read_mem(0x4122,0x4123)) == b'\0\0'
    controls = bytes(mon.read_mem(0x9000,0x90ff))
    mon.write_mem(0x9000,b'\0'+b'\xff'*255)
    probe = Probe(ult,work)
    directory = ('/Usb0/uos-files-'+uuid.uuid4().hex[:12]).encode()
    report = dict(private_directory=directory.decode(),cases=[])
    created,owned,opened = False,[],False
    try:
        available = probe.command(b'\x01\x07')
        assert available['code']==85 and not available['carry'],available
        probe.ok(b'\x01\x16'+directory)
        created = True
        for chunks in ((511,),(512,),(511,1)):
            path=directory+b'/write-'+b'-'.join(str(n).encode() for n in chunks)+b'.bin'
            expected=bytes((i*73+(i//256)*17+11)&255 for i in range(sum(chunks)))
            owned.append(path)
            probe.ok(b'\x01\x02\x07'+path)
            opened=True
            offset=0
            for length in chunks:
                probe.ok(b'\x01\x05\0\0'+expected[offset:offset+length])
                offset+=length
            probe.ok(b'\x01\x03')
            opened=False
            probe.ok(b'\x01\x02\x01'+path)
            opened=True
            result=probe.command(b'\x01\x04'+len(expected).to_bytes(2,'little'))
            assert not result['carry'] and not result['clipped'] and not result['full'],result
            assert result['code']==0 or (result['code']==255 and not result['status']),result
            actual=b''.join(data for data,clipped in result['records'] if not clipped)
            probe.ok(b'\x01\x03')
            opened=False
            report['cases'].append(dict(chunks=chunks,match=actual==expected,
                                        expected=expected.hex(),actual=actual.hex()))
            print(f'Raw WRITE chunks {chunks}: {len(actual)} bytes, match={actual==expected}',flush=True)
    finally:
        try:
            if opened:
                probe.ok(b'\x01\x03')
            for path in reversed(owned):
                probe.ok(b'\x01\x09'+path)
            if created:
                probe.ok(b'\x01\x09'+directory)
                report['private_files_removed']=True
        finally:
            mon.write_mem(0x9000,controls)
            (work/'write-diagnostic.json').write_text(json.dumps(report,indent=2)+'\n')
    assert ci.wait_desktop_live(mon,90)
    print(f'Write diagnosis saved: {work}',flush=True)


def inspect_fixture(ult, mon, work, saved_report):
    """Read-only investigation, restricted to the private failed test folder."""
    report = json.loads(saved_report.read_text())
    directory = report['private_directory'].encode()
    assert re.fullmatch(rb'/Usb0/uos-files-[0-9a-f]{12}', directory)
    assert bytes(mon.read_mem(0x4122, 0x4123)) == b'\0\0'
    controls = bytes(mon.read_mem(0x9000, 0x90ff))
    mon.write_mem(0x9000, b'\0'+b'\xff'*255)
    probe = Probe(ult, work)
    original = None
    observations = {}
    def observe(label, command):
        result = probe.command(command)
        result['records'] = [(data.hex(), clipped) for data, clipped in result['records']]
        observations[label] = result
        print(label, result, flush=True)
        (work/'inspection.json').write_text(json.dumps(observations, indent=2)+'\n')
        return result
    try:
        original = probe.ok(b'\x02\x12')['records'][0][0]
        probe.ok(b'\x02\x11'+directory)
        opened = observe('open_directory', b'\x02\x13')
        if opened['code'] == 0:
            result = observe('read_directory', b'\x02\x14')
            for index, (hexdata, clipped) in enumerate(result['records']):
                data = bytes.fromhex(hexdata)
                assert not clipped
                name = data[1:]
                observe(f'entry_{index}_full', b'\x02\x08'+name+b'\0')
                if len(name) > 127:
                    observe(f'entry_{index}_prefix', b'\x02\x08'+name[:127]+b'\0')
                    observe(f'entry_{index}_short_alias', b'\x02\x08PATTER~1.BIN\0')
    finally:
        try:
            if original is not None:
                probe.ok(b'\x02\x11'+original)
        finally:
            mon.write_mem(0x9000, controls)
    assert ci.wait_desktop_live(mon, 90)
    print(f'Fixture inspection saved: {work}', flush=True)


def cleanup_empty_fixture(ult, mon, work, saved_report):
    """Remove only an empty private directory named by a saved workflow report."""
    report = json.loads(saved_report.read_text())
    directory = report['private_directory'].encode()
    assert re.fullmatch(rb'/Usb0/uos-files-[0-9a-f]{12}', directory)
    assert ci.wait_desktop_live(mon, 90)
    assert bytes(mon.read_mem(0x4122, 0x4123)) == b'\0\0'
    probe = Probe(ult, work)
    controls = bytes(mon.read_mem(0x9000, 0x90ff))
    mon.write_mem(0x9000, b'\0'+b'\xff'*255)
    try:
        stat = probe.command(b'\x02\x08'+directory+b'\0')
        assert not stat['carry'] and not stat['clipped'] and stat['code'] in (0, 82), stat
        if stat['code'] == 0:
            original = probe.ok(b'\x02\x12')['records'][0][0]
            try:
                probe.ok(b'\x02\x11'+directory)
                opened = probe.command(b'\x02\x13')
                assert not opened['carry'] and opened['code'] == 1, 'fixture directory is not empty'
            finally:
                probe.ok(b'\x02\x11'+original)
            probe.ok(b'\x02\x09'+directory)
        assert ci.wait_desktop_live(mon, 90)
    finally:
        mon.write_mem(0x9000, controls)
    report['private_files_removed'] = True
    report['cleanup_after_failure'] = 'verified absent or empty directory removed; desktop live'
    saved_report.write_text(json.dumps(report, indent=2)+'\n')
    print(f'PASS: removed empty private fixture {directory.decode()}', flush=True)


def file_workflow(ult, mon, work, report):
    from hw_ultimate_check import Browser, ascii_to_petscii, build_hashes
    probe = Probe(ult, work)
    original = {}
    settings = bytes(mon.read_mem(0x7350, 0x7358))
    directory = ('/Usb0/uos-files-'+uuid.uuid4().hex[:12]).encode()
    # Exercise commands beyond 255 bytes without the firmware's unsafe
    # >=128-byte component lookup (which can create an inaccessible leaf).
    parents = [directory, directory+b'/'+b'a'*112]
    parents.append(parents[-1]+b'/'+b'b'*112)
    leaf_directory = parents[-1]
    basename = b'pattern-'+b'p'*51+b'.bin'
    source, destination = leaf_directory+b'/'+basename, leaf_directory+b'/copy.bin'
    expected = bytes((i*73+(i//256)*17+(i//65536)*29+11) & 255 for i in range(66053))
    report.update(private_directory=directory.decode(), source_basename_bytes=len(basename),
                  fixture_directories=[p.decode() for p in parents],
                  source_command_bytes=3+len(source), file_bytes=len(expected),
                  expected_sha256=hashlib.sha256(expected).hexdigest(), captures=[])
    (work/'expected.bin').write_bytes(expected)
    output = work/'files-workflow.prg'
    subprocess.run(['64tass', '-a', str(ROOT/'probes/files-workflow.asm'), '-o', str(output)],
                   check=True, capture_output=True)
    code = output.read_bytes()[2:]
    browser = None
    active = False
    created = []
    owned = []
    held_controls = None

    def hold_controls():
        nonlocal held_controls
        assert held_controls is None
        held_controls = bytes(mon.read_mem(0x9000, 0x90ff))
        mon.write_mem(0x9000, b'\0'+b'\xff'*255)

    def restore_controls():
        nonlocal held_controls
        if held_controls is not None:
            mon.write_mem(0x9000, held_controls)
            held_controls = None

    def save():
        (work/'report.json').write_text(json.dumps(report, indent=2)+'\n')

    def run_native(mode):
        assert ci.wait_desktop_live(mon, 60)
        assert bytes(mon.read_mem(0x4122, 0x4123)) == b'\0\0', 'service already owns a file'
        tick = bytes(mon.read_mem(0x033c, 0x033d))
        mon.write_mem(0x5000, code)
        mon.write_mem(0x5500, source+b'\0')
        mon.write_mem(0x5700, destination+b'\0')
        mon.write_mem(0x5f00, tick+bytes([mode])+bytes(7))
        mon.write_mem(0x033c, b'\0\x50')
        print(f'Running native file workflow mode {mode}; leaving UCI I/O quiet for 30 seconds', flush=True)
        time.sleep(30)
        wait_for(lambda: mon.read_mem(0x5f03, 0x5f03) == b'\1', 'native file workflow', 180)
        meta = bytes(mon.read_mem(0x5f03, 0x5f09))
        (work/f'native-{mode}.bin').write_bytes(meta)
        if meta[:3] != b'\1\0\0':
            # Preserve evidence before cleanup commands reuse packet RAM.
            for label, address, length in [('command',0x8080,896), ('packet',0x8800,512),
                                            ('source',0x6000,512), ('state',0x4100,0x800)]:
                (work/f'failed-{mode}-{label}.bin').write_bytes(bytes(mon.read_mem(address,address+length-1)))
            if meta[2] == 0 and bytes(mon.read_mem(0x4122,0x4123)) == b'\0\0':
                path = source if mode == 0 else destination
                diagnostic = {}
                try:
                    probe.ok(b'\x01\x02\x01'+path)
                    try:
                        for label, command in [('info',b'\x01\x07'),('read',b'\x01\x04\0\x02')]:
                            result = probe.command(command)
                            result['records'] = [(data.hex(),clipped) for data,clipped in result['records']]
                            diagnostic[label] = result
                    finally:
                        probe.ok(b'\x01\x03')
                except Exception as error:
                    diagnostic['error'] = str(error)
                (work/f'failed-{mode}-readback.json').write_text(json.dumps(diagnostic,indent=2)+'\n')
        assert meta[:3] == b'\1\0\0', (mode, meta.hex(), bytes(mon.read_mem(0x4124, 0x4143)))
        assert int.from_bytes(meta[3:], 'little') == len(expected), (mode, meta.hex())
        assert bytes(mon.read_mem(0x4122, 0x4123)) == b'\0\0'
        assert bytes(mon.read_mem(0x033c, 0x033d)) == tick
        assert ci.wait_desktop_live(mon, 60)
        report['checks'].append(f'native mode {mode}: {len(expected)} bytes; handles and tick released')
        save()

    def independent_read(path, label):
        data = bytearray()
        probe.ok(b'\x01\x02\x01'+path)
        try:
            while len(data) < len(expected):
                result = probe.command(b'\x01\x04\x00\x10')
                assert not result['carry'] and not result['full'] and not result['clipped'], result
                assert result['code'] == 0 or (result['code'] == 255 and not result['status']), result
                chunk = b''.join(record for record, clipped in result['records'] if not clipped)
                assert len(chunk) == min(4096, len(expected)-len(data)), (label, len(data), len(chunk))
                data.extend(chunk)
        finally:
            probe.ok(b'\x01\x03')
        (work/f'{label}.bin').write_bytes(data)
        assert bytes(data) == expected, f'{label}: complete independent byte comparison differs'
        report['checks'].append(f'{label}: independent raw UCI read matches all {len(data)} bytes')
        save()
        print(f'PASS: {label}, {len(data)} independently read bytes match', flush=True)

    fsyms = {name: lst_symbol('uos-files', name) for name in
             ('view_ready', 'view_page', 'view_count', 'view_error', 'view_eof')}

    def fv(name, size=1):
        address = fsyms[name]
        return int.from_bytes(mon.read_mem(address, address+size-1), 'little')

    def press_view(key, entering=False, leaving=False):
        if entering:
            wait_for(browser.ready, 'browser ready for viewer')
            mon.write_mem(browser.sym['ready'], b'\0')
        else:
            wait_for(lambda: fv('view_ready') == 1 and mon.read_mem(0xc6, 0xc6) == b'\0', 'viewer ready')
        mon.write_mem(fsyms['view_ready'], b'\0')
        ci.inject_keys(mon, bytes([key]))
        time.sleep(0.25)
        if leaving:
            wait_for(browser.ready, 'return from viewer', 90)
        else:
            wait_for(lambda: fv('view_ready') == 1 and mon.read_mem(0xc6, 0xc6) == b'\0', 'viewer page', 90)
            assert fv('view_error') == 0, fv('view_error')

    def capture_view(label, page):
        assert fv('view_page', 4) == page and fv('view_count') == 96
        assert bytes(mon.read_mem(0x7c00, 0x7c5f)) == expected[page:page+96]
        metadata, repeat_meta = {}, {}
        data = read_vdc(mon, work, metadata)
        repeat = read_vdc(mon, work, repeat_meta)
        (work/f'{label}.vdc.bin').write_bytes(data)
        (work/f'{label}.repeat.vdc.bin').write_bytes(repeat)
        assert data[160:1920] == repeat[160:1920], f'{label}: independent VDC captures differ'
        for row in range(12):
            chunk = expected[page+row*8:page+row*8+8]
            text = (f'{page+row*8:08x}: '+chunk.hex()).encode()+b' '+chunk
            # Offsets/hex are generated as lowercase PETSCII. Raw ASCII bytes
            # use the same bounded display conversion as the browser.
            wanted = bytes(map(screen_code, ascii_to_petscii(text))).ljust(80, b' ')
            assert data[(6+row)*80:(7+row)*80] == wanted, (label, row, data[(6+row)*80:(7+row)*80], wanted)
        assert bytes(mon.read_mem(0x7c00, 0x7c5f)) == expected[page:page+96], 'capture changed viewer bytes'
        report['captures'].append({'label':label, 'first':metadata, 'repeat':repeat_meta})
        save()

    try:
        hold_controls()
        original = {target: probe.ok(bytes([target, 0x12]))['records'][0][0] for target in (1, 2)}
        report['original_dos_paths'] = {target: path.decode() for target, path in original.items()}
        report['getcap'] = check_getcap(mon, work)
        immutable = [('begin', 'busy'), ('view_file', 'view_buffer')]
        code_before = {}
        image = (ROOT/'target/uos-files.prg').read_bytes()
        origin = int.from_bytes(image[:2], 'little')
        for start_name, end_name in immutable:
            start, end = lst_symbol('uos-files', start_name), lst_symbol('uos-files', end_name)
            observed = bytes(mon.read_mem(start, end-1))
            assert observed == image[2+start-origin:2+end-origin], 'resident file code differs from build'
            code_before[start_name] = (start, end, observed)
        for parent in parents:
            probe.ok(b'\x02\x16'+parent)
            created.append(parent)
        owned.append(source)
        run_native(0)
        independent_read(source, 'source')
        owned.append(destination)
        run_native(1)
        independent_read(destination, 'copy')
        for target in (1, 2):
            assert probe.ok(bytes([target, 0x12]))['records'][0][0] == original[target]
        probe.ok(b'\x02\x11'+leaf_directory)
        restore_controls()
        active = True
        launch_from_apps(mon, work, quiet_io_seconds=30)
        browser = Browser(mon)
        wait_for(browser.ready, 'browser with private files', 120)
        names = browser.names()
        assert set(names) == {basename, b'copy.bin'}, names
        while names[browser.value('selected')] != basename:
            browser.press(0x11)
        selected = browser.value('selected')
        before_meta = {}
        before = grab(ult, verbose=False, metadata=before_meta)
        (work/'browser-before.vic.bin').write_bytes(before)
        render(before, str(work/'browser-before.png'))
        press_view(ord('V'), entering=True)
        capture_view('viewer-first', 0)
        first_meta = {}
        bitmap = grab(ult, verbose=False, metadata=first_meta)
        (work/'viewer-first.vic.bin').write_bytes(bitmap)
        render(bitmap, str(work/'viewer-first.png'))
        press_view(ord('N'))
        capture_view('viewer-next', 96)
        press_view(ord('B'))
        capture_view('viewer-return', 0)
        press_view(27, leaving=True)
        assert browser.names() == names and browser.value('selected') == selected
        assert bytes(mon.read_mem(0x4122, 0x4123)) == b'\0\0'
        after_meta = {}
        after = grab(ult, verbose=False, metadata=after_meta)
        (work/'browser-after.vic.bin').write_bytes(after)
        render(after, str(work/'browser-after.png'))
        differences = []
        for i, (a, b) in enumerate(zip(before, after)):
            if a != b:
                x, y = (i % 320)//8*8, i//320*8+i%8
                differences.append(dict(offset=i, x=x, y=y, before=a, after=b, clock=x >= 280 and y >= 184))
        (work/'vic-differences.json').write_text(json.dumps(differences, indent=2)+'\n')
        assert all(d['clock'] for d in differences), 'VIC browser pixels changed outside clock'
        report['vic_captures'] = [before_meta, first_meta, after_meta]
        report['vic_roundtrip_changed_bytes'] = len(differences)
        report['checks'].append('desktop viewer: exact bytes/VDC rows, N/B/ESC, full names and selection retained; VIC restored')
        browser.press(27)
        active = False
    finally:
        try:
            if active and browser is not None:
                if not browser.ready():
                    press_view(27, leaving=True)
                browser.press(27)
                active = False
            assert ci.wait_desktop_live(mon, 90), 'desktop required for fixture cleanup'
            if held_controls is None:
                hold_controls()
            # Retry only CLOSE on service-owned uncertain handles before raw
            # cleanup, never replay an OPEN/WRITE. Desktop entry also does this.
            assert bytes(mon.read_mem(0x4122, 0x4123)) == b'\0\0', 'file handle remains owned'
            for target, path in original.items():
                probe.ok(bytes([target, 0x11])+path)
            if created:
                for path in reversed(owned):
                    result = probe.command(b'\x02\x09'+path)
                    missing = result['code'] == 255 and result['status'] == "FILE DOESN'T EXIST"
                    assert not result['carry'] and not result['clipped'] and (result['code'] == 0 or missing), result
                for parent in reversed(created):
                    probe.ok(b'\x02\x09'+parent)
                report['private_files_removed'] = True
            assert bytes(mon.read_mem(0x7350, 0x7358)) == settings
            if 'code_before' in locals():
                for start, end, reference in code_before.values():
                    assert bytes(mon.read_mem(start, end-1)) == reference, 'resident file instructions changed'
                report['resident_file_code_preserved'] = True
            assert ci.wait_desktop_live(mon, 90)
            report['checks'].append('private files removed; both CWDs/settings restored; desktop live')
        finally:
            restore_controls()
            report['read_retries'] = ult.read_retries
            save()
    assert report['build'] == build_hashes()
    report['passed'] = True
    save()
    print(f'HW-FILES PASS; full file copy and desktop viewer; evidence {work}', flush=True)
