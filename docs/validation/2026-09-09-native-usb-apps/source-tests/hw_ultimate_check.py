#!/usr/bin/env python3
"""Exercise the Ultimate browser on the reference C128.

Boots the distributable on A. Captures an independent directory-packet oracle,
navigates the actual app past ordinal 255, compares complete cached filenames
and VDC text, restores both DOS contexts and leaves the desktop running.
The default navigation check does not modify files or remount drive B.
--drives uses a private scratch D64 on an initially empty B, copies one system
file into it, verifies its complete contents, ejects it and removes the fixture.
Physical mouse motion is not injected by this script.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
import urllib.request
import urllib.parse

from hw_storage_check import ci, HardwareMonitor, ROOT, read_vdc, screen_code, wait_for
from hw_uci_check import Probe
from hwlib import desk_tick, lst_symbol
from ci_storage import FileManager, launch, launch_from_apps
from cap_hw_screen import grab, render


class ObservingUltimate(ci.cbm.Ultimate):
    """Retry read-only observations; never replay navigation/DMA writes."""
    read_retries = 0

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.uncertain_writes=[]

    def write_mem(self,address,data):
        assert len(data)<=128
        try:return super().write_mem(address,data)
        except SystemExit as error:
            self.uncertain_writes.append(dict(address=address,bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),replayed=False))
            raise RuntimeError(f'Host RAM write at ${address:04x} ({len(data)} bytes) failed; acceptance unknown; not replayed') from error

    def read_mem(self, address, length):
        url = f'http://{self.host}/v1/machine:readmem?address={address:04X}&length={length}'
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as response:
                    data = response.read()
                assert len(data) >= length, f'Short RAM observation at {address:#x}'
                return data[:length]
            except OSError as error:
                if attempt == 2:
                    raise RuntimeError(f'RAM observation at {address:#x} failed after three attempts') from error
                self.read_retries += 1
                print(f'Retrying RAM observation at ${address:04x}: {error}', flush=True)
                time.sleep(1)


def build_hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'target').glob('*.prg')) + [ROOT/'target/ultos.d64']}


class Browser:
    def __init__(self, mon):
        self.mon = mon
        self.sym = {name: lst_symbol('uos-ultimate', name) for name in
                    ('ready', 'count', 'selected', 'base', 'more', 'pathlen', 'nameoff',
                     'cache_pages', 'driveview', 'drive_valid', 'drive_count',
                     'drive_selected', 'drive_records', 'drive_locks', 'pending', 'status')}

    def read(self, address, size=1):
        return bytes(self.mon.read_mem(address, address+size-1))

    def value(self, name, size=1):
        return int.from_bytes(self.read(self.sym[name], size), 'little')

    def ready(self):
        return self.value('ready') == 1 and self.read(0xc6) == b'\0'

    def press(self, key):
        wait_for(self.ready, 'browser input ready')
        exit_app = key == 27 and not self.value('driveview')
        self.mon.write_mem(self.sym['ready'], b'\0')
        ci.inject_keys(self.mon, bytes([key]))
        if exit_app:
            wait_for(lambda: self.value('ready') == 0xff, 'browser exit', 120)
            assert ci.wait_desktop_live(self.mon, 120)
        else:
            time.sleep(0.25)
            wait_for(self.ready, f'browser key {key:#x}', 180)

    def names(self):
        count = self.value('count')
        assert count <= 8
        pages = self.read(self.sym['cache_pages'], 8)
        return [self.read(pages[i]*256, 512).split(b'\0')[0] for i in range(count)]


def ascii_to_petscii(data):
    return bytes(c & 0xdf if 0x61 <= c <= 0x7a else c | 0x80 if 0x41 <= c <= 0x5a
                 else c if 0x20 <= c <= 0x60 else 0x2e for c in data)


def check_page(browser, expected, work, label):
    got = browser.names()
    assert got == [record[0][1:] for record in expected], (label, got, expected)
    first_meta, repeat_meta = {}, {}
    vdc = read_vdc(browser.mon, work, first_meta)
    (work / f'{label}.vdc.bin').write_bytes(vdc)
    repeat = read_vdc(browser.mon, work, repeat_meta)
    (work / f'{label}.repeat.vdc.bin').write_bytes(repeat)
    (work / f'{label}.capture.json').write_text(
        json.dumps({'first':first_meta,'repeat':repeat_meta}, indent=2)+'\n')
    # Both independently acquired app areas must agree. Do not retry until a
    # favorable capture appears; clock rows 0/24 may advance between dumps.
    assert vdc[160:1920] == repeat[160:1920], (label, 'VDC captures disagree')
    selected = browser.value('selected')
    for i in range(8):
        wanted = bytearray(b' ' * 80)
        if i < len(expected):
            packet, clipped = expected[i]
            assert not clipped
            name = packet[1:]
            shown = ascii_to_petscii(name[:74])
            if len(name) > 74:
                shown = shown[:73] + b'>'
            wanted[0] = screen_code(ord('>') if i == selected else 32)
            wanted[1] = screen_code(ord('/') if packet[0] & 0x10 else 32)
            wanted[3:3+len(shown)] = bytes(map(screen_code, shown))
        assert vdc[(4+i)*80:(5+i)*80] == wanted, (label, i, 'filename row or blank tail differs')
    # The helper navigates with name details at offset zero. Check all seven
    # complete rows so a shorter selection cannot hide stale trailing text.
    assert browser.value('nameoff', 2) == 0
    detail = ascii_to_petscii(got[selected]) if got else b''
    for i in range(7):
        wanted = bytes(map(screen_code, detail[i*34:(i+1)*34])).ljust(80, b' ')
        assert vdc[(14+i)*80:(15+i)*80] == wanted, (label, i, 'detail row or blank tail differs')
    return [name.decode('utf-8', 'replace') for name in got]


def drive_workflow(ult, mon, work, report):
    def drives():
        data = json.loads(ult.drives())
        assert not data['errors'], data
        return {name: value for record in data['drives'] for name, value in record.items()}

    before = drives()
    (work/'drives-before.json').write_text(json.dumps(before, indent=2)+'\n')
    assert before['a']['bus_id'] == 8 and before['b']['bus_id'] == 9
    assert before['a']['enabled'] and before['b']['enabled']
    assert not before['b']['image_file'], 'Drive workflow requires initially empty B'
    probe = Probe(ult, work)
    original = {t: probe.ok(bytes([t, 0x12]))['records'][0][0] for t in (1, 2)}
    settings = bytes(mon.read_mem(0x7350, 0x7358))
    folder = '/Usb0/uos-drive-'+work.name.rsplit('-', 1)[-1]
    fixture = folder+'/check.d64'
    report.update(drive_workflow=True, fixture=fixture,
                  dos_paths_before_hex={t:p.hex() for t,p in original.items()})
    created_dir = created_image = False
    active = None
    browser = Browser(mon)

    def save():
        (work/'report.json').write_text(json.dumps(report, indent=2)+'\n')

    def status():
        return browser.read(browser.sym['status'], 34).split(b'\0')[0]

    def capture(label):
        first, second = {}, {}
        one, two = read_vdc(mon, work, first), read_vdc(mon, work, second)
        (work/f'{label}.vdc.bin').write_bytes(one)
        (work/f'{label}.repeat.vdc.bin').write_bytes(two)
        assert one[160:1920] == two[160:1920], f'{label}: VDC captures differ'
        report.setdefault('captures', {})[label] = {'first':first, 'repeat':second}
        bitmap = grab(ult, verbose=False)
        (work/f'{label}.vic.bin').write_bytes(bitmap)
        render(bitmap, str(work/f'{label}.png'))
        return one

    def open_browser(through_menu=False):
        nonlocal active
        active = 'browser'
        if through_menu:
            launch_from_apps(mon, work, quiet_io_seconds=30)
        else:
            launch(mon, b'UOS-ULTIMATE')
            time.sleep(30)
        prefix = (ROOT/'target/uos-ultimate.prg').read_bytes()[2:18]
        wait_for(lambda: browser.read(0x5000, 16) == prefix, 'browser LOAD', 180)
        wait_for(browser.ready, 'browser ready', 180)
        assert browser.names() == [b'check.d64']

    def exit_app():
        nonlocal active
        if active == 'browser':
            if browser.value('driveview'):
                browser.press(ord('D'))
            browser.press(27)
        elif active == 'file-manager':
            ci.inject_keys(mon, b'\x1b')
            assert ci.wait_desktop_live(mon, 120)
        active = None

    try:
        probe.ok(b'\x02\x16'+folder.encode())
        created_dir = True
        response = json.loads(ult._expect_ok('PUT', '/v1/files'+urllib.parse.quote(fixture)+
                                             ':create_d64?diskname=uosdrive', what='scratch D64 creation'))
        assert not response['errors'], response
        created_image = True
        report['create_response'] = response
        probe.ok(b'\x02\x11'+folder.encode())
        inventory = probe.ok(b'\x04\x29\x01')['records'][0][0]
        report['inventory_hex'] = inventory.hex()
        open_browser(through_menu=True)
        browser.press(ord('D'))
        assert browser.value('drive_valid') in (1, 2) and browser.value('drive_count') >= 2
        report['capabilities'] = {'valid':browser.value('drive_valid'),
                                  'records_hex':browser.read(browser.sym['drive_records'], 12).hex()}
        for key in (ord('M'), ord('E')):
            browser.press(key)
            assert status() == b'SYSTEM DRIVE PROTECTED' and not browser.value('pending')
            browser.press(13)
            assert drives() == before
        report['checks'].append('system IEC 8 rejects both mount and eject; REST drive state unchanged')
        browser.press(0x11)
        browser.press(ord('M'))
        assert status() == b'MOUNT 09? ENTER=YES ESC=NO'
        screen = capture('mount-confirmation')
        assert b'MOUNT 09?' == status()[:9]
        wanted = bytes(map(screen_code, b'MOUNT 09? ENTER=YES ESC=NO')).ljust(80, b' ')
        assert screen[22*80:23*80] == wanted
        assert drives() == before, 'Media changed before confirmation'
        browser.press(27)
        assert not browser.value('pending') and drives() == before
        browser.press(ord('M'))
        browser.press(13)
        mounted = drives()
        (work/'drives-mounted.json').write_text(json.dumps(mounted, indent=2)+'\n')
        assert mounted['a'] == before['a']
        assert mounted['b']['image_file'] == 'check.d64', mounted['b']
        assert mounted['b']['image_path'].rstrip('/') == folder, mounted['b']
        assert status() == b'DRIVE COMMAND ACCEPTED'
        report['checks'].append('cancel preserves both drives; confirmed browser mount selects the exact private image on B')
        capture('mounted')
        exit_app()
        assert browser.read(0xba) == b'\x08'

        active = 'file-manager'
        launch(mon)
        print('Waiting for File Manager IEC LOAD before DMA observations', flush=True)
        time.sleep(30)
        fm = FileManager(mon)
        fm_prefix = (ROOT/'target/uos-fmgr.prg').read_bytes()[2:18]
        wait_for(lambda: fm.read(0x5000, 16) == fm_prefix, 'File Manager LOAD', 180)
        wait_for(fm.ready, 'File Manager ready', 180)
        fm.goto(fm.names().index(b'UOS-SPRITES'))
        fm.keys(b'BDRIVE-CHECK')
        # No RAM observations while IEC COPY is active, for the same reason
        # that LOAD has quiet windows. Only this scratch destination is written.
        ci.inject_keys(mon, b'\r')
        time.sleep(10)
        wait_for(fm.ready, 'IEC copy finished', 180)
        assert fm.read(fm.symbols['linebuf'], 38).split(b'\0')[0] == b'COPIED TO DEVICE 9'
        ci.inject_keys(mon, b'9')
        time.sleep(10)
        wait_for(fm.ready, 'mounted IEC 9 directory', 180)
        assert fm.names() == [b'DRIVE-CHECK'] and not fm.value('direrror')
        capture('iec-copy')
        report['checks'].append('File Manager loads from system A and copies UOS-SPRITES to mounted IEC 9 as DRIVE-CHECK')
        exit_app()
        assert browser.read(0xba) == b'\x08'

        open_browser()
        browser.press(ord('D'))
        browser.press(0x11)
        browser.press(ord('E'))
        assert status() == b'EJECT 09? ENTER=YES ESC=NO'
        browser.press(13)
        assert drives() == before, 'Eject did not restore the original drive state'
        capture('ejected')
        exit_app()
        # After eject flushes the image, verify every copied byte through the
        # cartridge filesystem, independent of the File Manager's IEC reader.
        probe.ok(b'\x02\x11'+fixture.encode())
        probe.ok(b'\x02\x13')
        entries = probe.ok(b'\x02\x14')['records']
        report['image_directory_hex'] = [packet.hex() for packet, _ in entries]
        assert all(packet and not clipped for packet, clipped in entries)
        # D64 filesystems also emit a volume-label record (attribute $08).
        files = [packet for packet, _ in entries if not packet[0] & 0x08]
        assert len(files) == 1 and files[0][1:] == b'DRIVE-CHECK', entries
        name = files[0][1:]
        report['copied_name_hex'] = name.hex()
        probe.ok(b'\x02\x02\x01'+name)
        try:
            result = probe.command(b'\x02\x04\x00\x04')
            # Dos::get_more_data uses an empty status on successful file
            # reads. Keep this exception specific to READ_DATA; exact bytes
            # and a successful CLOSE below are required independently.
            report['file_read_reply'] = {k:v for k,v in result.items() if k != 'records'}
            assert not result['carry'] and not result['full'] and not result['clipped'], result
            assert (result['code'] == 0 or
                    (result['code'] == 255 and result['status'] == '')), result
            assert all(not clipped for _, clipped in result['records'])
            contents = b''.join(packet for packet, _ in result['records'])
        finally:
            probe.ok(b'\x02\x03')
        (work/'copied.prg').write_bytes(contents)
        expected = (ROOT/'target/uos-sprites.prg').read_bytes()
        assert contents == expected, 'Copied IEC file contents differ'
        report['copied_file'] = {'bytes':len(contents), 'sha256':hashlib.sha256(contents).hexdigest()}
        report['checks'].append('confirmed browser eject restores empty B; every copied byte matches the system PRG')
        assert bytes(mon.read_mem(0x7350, 0x7358)) == settings
        assert probe.ok(b'\x01\x12')['records'][0][0] == original[1]
    except BaseException as error:
        report['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        try:
            exit_app()
            state = drives()
            if state['b']['image_file']:
                path = state['b']['image_path'].rstrip('/')+'/'+state['b']['image_file']
                assert path == fixture, 'Unexpected B media; refusing cleanup eject'
                ult.unmount('b')
            assert drives() == before
            for target, path in original.items():
                probe.ok(bytes([target, 0x11])+path)
            if created_image:
                probe.ok(b'\x02\x09'+fixture.encode())
            if created_dir:
                probe.ok(b'\x02\x09'+folder.encode())
            report['paths_restored'] = report['fixture_removed'] = True
            assert ci.wait_desktop_live(mon, 120)
        except BaseException as error:
            report['cleanup_failure'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            report['read_retries'] = ult.read_retries
            save()
    assert report['build'] == build_hashes()
    report['passed'] = True
    save()
    print(f'HW-DRIVES PASS; desktop live, B empty, private image removed; evidence {work}', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-boot', action='store_true')
    parser.add_argument('--capture-only', action='store_true',
                        help='check eight consecutive VDC captures of the idle desktop')
    parser.add_argument('--directory', default='/Usb0/c64/#-a/')
    parser.add_argument('--drives', action='store_true',
                        help='mount/copy/eject a private D64; requires initially empty drive B')
    parser.add_argument('--files', action='store_true',
                        help='create/copy/read back private binary files, desktop viewer and copy dialog')
    parser.add_argument('--editor', action='store_true',
                        help='shared Open/Save As, private text files and independent byte verification')
    parser.add_argument('--native', action='store_true',
                        help='cold-boot native C128 memory workspace; verify both banks/displays; restore desktop')
    parser.add_argument('--native-files', action='store_true',
                        help='native IEC streams and calculator export on private D64s; independent readback; restore desktop')
    parser.add_argument('--native-files-readback',type=Path,
                        help='resume independent readback of the exact private disks in a completed native test report')
    parser.add_argument('--native-browser',action='store_true',
                        help='native directory browser, renamed-app handoff and byte viewer on a private D64; restore desktop')
    parser.add_argument('--native-browser-readback',type=Path,
                        help='resume independent readback of a completed native browser hardware report')
    parser.add_argument('--native-ultimate',action='store_true',
                        help='native editor with private Ultimate USB files; independent readback; restore desktop')
    parser.add_argument('--native-redraw',action='store_true',
                        help='native editor redraw timings and complete Ultimate file workflow; restore desktop')
    parser.add_argument('--native-usb-apps',action='store_true',
                        help='load USB apps from native browser, verify saves and failures, restore desktop')
    parser.add_argument('--native-usb-apps-reuse',type=Path,
                        help='recheck prior fixtures after the host-input timeout, then restart the complete USB app workflow')
    parser.add_argument('--native-usb-apps-cleanup',type=Path,
                        help='verify/remove the exact private USB app fixtures after the retained-error screen-oracle failure')
    parser.add_argument('--native-ultimate-cleanup',type=Path,
                        help='inspect and remove only a private NOTE fixture from an interrupted pre-boot setup')
    parser.add_argument('--native-editor',action='store_true',
                        help='native banked editor, over-64-KiB edit/save and private D64 readback; restore desktop')
    parser.add_argument('--native-editor-readback',type=Path,
                        help='resume independent readback of a completed native editor hardware report')
    parser.add_argument('--native-editor-restore',type=Path,
                        help='restore saved settings bytes after a failed editor test has already rebooted the legacy desktop')
    parser.add_argument('--editor-exit-diagnose', action='store_true',
                        help='sample an idle editor without changing its code or document')
    parser.add_argument('--editor-inspect', action='store_true',
                        help='record editor/selector RAM without requiring a responsive foreground')
    parser.add_argument('--editor-abort-load', type=Path,
                        help='recover the exact saved editor fixture after a read-only LOAD stall')
    parser.add_argument('--editor-cleanup', type=Path,
                        help='verify and remove the exact private editor fixture in a saved report')
    parser.add_argument('--cleanup-empty-files-fixture', type=Path,
                        help='remove an empty private file-test directory recorded in the supplied report')
    parser.add_argument('--inspect-files-fixture', type=Path,
                        help='record a private failed file-test directory and read-only name lookups')
    parser.add_argument('--files-write-diagnostic', action='store_true',
                        help='compare private raw UCI writes below and at the 512-byte boundary')
    args = parser.parse_args()
    if args.native_usb_apps_reuse:
        from hw_native_ultimate_check import run
        run(ObservingUltimate(timeout=60),usb_apps=True,fixture_report=args.native_usb_apps_reuse)
        return
    if args.native_usb_apps_cleanup:
        from hw_native_usb_apps import cleanup_failed_field_check
        cleanup_failed_field_check(ObservingUltimate(),args.native_usb_apps_cleanup)
        return
    if args.native_usb_apps:
        from hw_native_ultimate_check import run
        run(ObservingUltimate(timeout=60),usb_apps=True)
        return
    if args.native_redraw:
        from hw_native_ultimate_check import run
        run(ObservingUltimate(),redraw=True)
        return
    if args.native_ultimate_cleanup:
        from hw_native_ultimate_check import cleanup_fixture_timeout
        cleanup_fixture_timeout(ObservingUltimate(),args.native_ultimate_cleanup)
        return
    if args.native_ultimate:
        from hw_native_ultimate_check import run
        run(ObservingUltimate())
        return
    if args.native_editor_restore:
        from hw_native_editor_check import restore_record
        restore_record(ObservingUltimate(),args.native_editor_restore)
        return
    if args.native_editor_readback:
        from hw_native_editor_check import readback
        readback(ObservingUltimate(),args.native_editor_readback)
        return
    if args.native_editor:
        from hw_native_editor_check import run
        run(ObservingUltimate())
        return
    if args.native_browser_readback:
        from hw_native_browser_check import readback
        readback(ObservingUltimate(),args.native_browser_readback)
        return
    if args.native_browser:
        from hw_native_browser_check import run
        run(ObservingUltimate())
        return
    if args.native_files_readback:
        from hw_native_files_check import resume_readback
        resume_readback(ObservingUltimate(),args.native_files_readback)
        return
    if args.native_files:
        from hw_native_files_check import run
        run(ObservingUltimate())
        return
    if args.native:
        from hw_native_check import run
        run(ObservingUltimate())
        return
    if (args.editor_exit_diagnose or args.editor_inspect or args.editor_abort_load or args.editor_cleanup) and not args.no_boot:
        parser.error('editor diagnosis/cleanup requires --no-boot')
    work = Path(tempfile.mkdtemp(prefix='uos-hardware-browser-'))
    print(f'Browser hardware evidence: {work}', flush=True)
    report = {'build': build_hashes(), 'checks': [], 'passed': False,
              'reused_running_desktop': args.no_boot,
              'dma_observation_quiet_seconds': {'boot':0 if args.no_boot else 60,
                                                'launcher_directory':30,'app_load':30,
                                                'vdc_capture':2},
              'vdc_captures_per_sample': 2}
    ult = ObservingUltimate()
    mon = HardwareMonitor(ult)
    if args.editor_inspect:
        from hw_editor_check import inspect_editor
        inspect_editor(mon,work)
        return
    if args.editor_exit_diagnose:
        from hw_editor_check import diagnose_exit
        diagnose_exit(ult,mon,work)
        return
    if args.editor_abort_load:
        from hw_editor_check import abort_editor_load
        abort_editor_load(ult,mon,work,args.editor_abort_load)
        return
    if not args.no_boot:
        ult.mount((ROOT/'target/ultos.d64').read_bytes(), 'a', 'd64', 'readwrite')
        ult.run_prg((ROOT/'target/uos.prg').read_bytes())
        # Cartridge RAM observations stop/resume the CPU. Avoid interrupting
        # IEC handshakes while boot modules are loading from the disk image.
        print('Waiting for boot I/O before DMA observations',flush=True)
        time.sleep(60)
    wait_for(lambda: mon.read_mem(0x033c, 0x033d) == desk_tick().to_bytes(2, 'little'),
             'desktop boot', 300)
    assert ci.wait_desktop_live(mon, 120)
    if args.editor_cleanup:
        from hw_editor_check import cleanup_editor_fixture
        cleanup_editor_fixture(ult,mon,work,args.editor_cleanup)
        return
    if args.files_write_diagnostic:
        from hw_files_check import write_diagnostic
        write_diagnostic(ult, mon, work)
        return
    if args.inspect_files_fixture:
        from hw_files_check import inspect_fixture
        inspect_fixture(ult, mon, work, args.inspect_files_fixture)
        return
    if args.cleanup_empty_files_fixture:
        from hw_files_check import cleanup_empty_fixture
        cleanup_empty_fixture(ult, mon, work, args.cleanup_empty_files_fixture)
        return
    if args.files:
        from hw_files_check import file_workflow
        file_workflow(ult, mon, work, report)
        return
    if args.editor:
        from hw_editor_check import editor_workflow
        editor_workflow(ult, mon, work, report)
        return
    if args.drives:
        drive_workflow(ult, mon, work, report)
        return
    if args.capture_only:
        report['capture_only'] = True
        report['captures'] = []
        expected = bytes(map(screen_code, ascii_to_petscii(b'desktop'))).ljust(1760, b' ')
        try:
            footer = None
            for i in range(8):
                metadata = {}
                data = read_vdc(mon, work, metadata)
                (work/f'desktop-{i}.vdc.bin').write_bytes(data)
                report['captures'].append(metadata)
                assert data[160:1920] == expected, f'Desktop capture {i} differs'
                if footer is not None:
                    assert data[1920:] == footer, f'Desktop footer capture {i} differs'
                footer = data[1920:]
                print(f'PASS: capture {i}, address resyncs={metadata["address_resyncs"]}', flush=True)
            assert ci.wait_desktop_live(mon, 120)
            assert report['build'] == build_hashes()
            report['checks'].append('eight exact desktop app areas and stable footer; IRQ chain and desktop remain live')
            report['passed'] = True
        except BaseException as error:
            report['failure'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            report['read_retries'] = ult.read_retries
            (work/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        return
    probe = Probe(ult, work)
    original = {t: probe.ok(bytes([t, 0x12]))['records'][0][0] for t in (1, 2)}
    report['dos_paths_before_hex'] = {t:path.hex() for t,path in original.items()}
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    settings = bytes(mon.read_mem(0x7350, 0x7358))
    prefix = (ROOT/'target/uos-ultimate.prg').read_bytes()[2:18]
    active = False
    try:
        probe.ok(b'\x02\x11/')
        probe.ok(b'\x02\x13')
        root = probe.ok(b'\x02\x14')
        assert 0 < root['count'] < 8, 'Root must exercise clearing unused browser rows'
        expected_root = root['records']
        probe.ok(b'\x02\x11'+args.directory.encode())
        probe.ok(b'\x02\x13')
        first = probe.ok(b'\x02\x14')
        later = probe.ok(b'\x02\x14', skip=256)
        assert first['count'] > 264 and later['count'] == first['count']
        expected_first, expected_later = first['records'][:8], later['records'][:8]
        assert len(expected_first) == len(expected_later) == 8
        report['directory'] = args.directory
        report['directory_packets'] = first['count']
        active = True
        launch_from_apps(mon, work, quiet_io_seconds=30)
        browser = Browser(mon)
        wait_for(lambda: browser.read(0x5000, 16) == prefix, 'browser loaded', 180)
        wait_for(browser.ready, 'initial browser page', 180)
        report['checks'].append('Applications registers six rows; compiled hit-test launches Ultimate at screen x=240')
        report['first_page'] = check_page(browser, expected_first, work, 'first')
        first_bitmap = grab(ult, verbose=False)
        (work/'first.vic.bin').write_bytes(first_bitmap)
        render(first_bitmap, str(work/'first.png'))
        print('PASS: complete first-page names and exact physical VDC rows', flush=True)
        # Exercise an independent clock repaint while this app is active.
        # Invalidate only its cached minute; the actual TOD time is unchanged.
        mon.write_mem(lst_symbol('uos-desktop', 'minute'), b'\xff')
        report['clock_redraw_forced'] = True
        selections = []
        report['selection_seconds'] = selections
        for key, selected in ((0x11, 1), (0x11, 2), (0x91, 1), (0x91, 0)):
            start = time.monotonic()
            browser.press(key)
            elapsed = round(time.monotonic()-start, 3)
            assert browser.value('selected') == selected and browser.value('base', 2) == 0
            label = f'select-{len(selections)+1}-{selected}'
            check_page(browser, expected_first, work, label)
            selections.append({'key': key, 'selected': selected, 'seconds': elapsed})
        returned_bitmap = grab(ult, verbose=False)
        (work/'selection-return.vic.bin').write_bytes(returned_bitmap)
        render(returned_bitmap, str(work/'selection-return.png'))
        # Desktop TICK uses ClrRect 280,191,39,8. Its bitmap-band rounding
        # clears x=280..319, y=184..199, including the lower-right shadow.
        # Compare every other byte and retain all differences before asserting.
        differences = []
        for i, (before, after) in enumerate(zip(first_bitmap, returned_bitmap)):
            if before != after:
                x, y = (i % 320)//8*8, i//320*8 + i%8
                differences.append({'offset':i, 'x':x, 'y':y, 'before':before, 'after':after,
                                    'clock_redraw':x >= 280 and y >= 184})
        outside = [d for d in differences if not d['clock_redraw']]
        (work/'vic-differences.json').write_text(json.dumps(differences, indent=2)+'\n')
        report['vic_roundtrip'] = {'changed_bytes':len(differences),
                                  'differences_outside_clock':len(outside),
                                  'excluded_clock_rectangle':{'x':280,'y':184,'width':40,'height':16}}
        assert not outside, f'Selection round trip left VIC pixels outside the clock: {outside[:8]}'
        report['checks'].append('Down/Down/Up/Up with clock repaint: exact VDC names, selection and details; VIC unchanged outside clock rectangle')
        print(f'PASS: selective navigation and clean erasure; observed seconds {selections}', flush=True)
        timings = []
        report['page_navigation_seconds'] = timings
        for i in range(32):
            start = time.monotonic()
            browser.press(ord('N'))
            assert browser.value('base', 2) == (i+1)*8
            timings.append(round(time.monotonic()-start, 3))
            report['last_ordinal'] = (i+1)*8
            if (i+1) % 8 == 0:
                print(f'Browser reached directory ordinal {(i+1)*8}', flush=True)
        report['later_page'] = check_page(browser, expected_later, work, 'ordinal-256')
        report['page_navigation_seconds'] = timings
        render(grab(ult, verbose=False), str(work/'ordinal-256.png'))
        report['checks'].append('32 Next actions cross ordinal 255; all eight names byte-exact against packet oracle')
        report['checks'].append('exact physical VDC filename rows on first and ordinal-256 pages')
        browser.press(ord('/'))
        assert browser.read(0x7100, browser.value('pathlen', 2)) == b'/'
        report['root_page'] = check_page(browser, expected_root, work, 'root')
        report['checks'].append('Root clears unused list and detail rows, checked against a separate packet oracle')
        names = browser.names()
        index = names.index(b'Usb0')
        for _ in range(index):
            browser.press(0x11)
        browser.press(13)
        assert browser.read(0x7100, browser.value('pathlen', 2)).rstrip(b'/') == b'/Usb0'
        browser.press(ord('U'))
        assert browser.read(0x7100, browser.value('pathlen', 2)) == b'/'
        report['checks'].append('Root, select Usb0, Open and Parent navigate the real filesystem')
        assert bytes(mon.read_mem(0x7350, 0x7358)) == settings
        browser.press(27)
        active = False
        assert probe.ok(b'\x01\x12')['records'][0][0] == original[1]
        report['checks'].append('settings and shell DOS context preserved; ESC returns to live desktop')
    except BaseException as error:
        report['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        try:
            if active and bytes(mon.read_mem(0x5000,0x500f)) == prefix:
                Browser(mon).press(27)
            assert ci.wait_desktop_live(mon, 120)
            for target, path in original.items():
                probe.ok(bytes([target, 0x11])+path)
            assert ci.wait_desktop_live(mon, 120)
            report['paths_restored'] = True
        except BaseException as error:
            report['cleanup_failure'] = f'{type(error).__name__}: {error}'
            raise
        finally:
            report['read_retries'] = ult.read_retries
            (work/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    assert report['build'] == build_hashes()
    report['passed'] = True
    (work/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(f'HW-ULTIMATE PASS; desktop live, DOS paths restored; evidence {work}', flush=True)


if __name__ == '__main__':
    main()
