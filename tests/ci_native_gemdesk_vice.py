#!/usr/bin/env python3
"""GEMDESK in a real emulated C128 (VICE x128, 1581 true drive emulation):
boot gem.d81, compare the desktop with the CPU-test oracle, open drive 8 from
the keyboard, launch Calculator, leave it, and check the AES session brings
the window and its selection back, then open a SEQ file in the Editor as a
document and return to the desktop."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import ci_fm as ci
import native_gemdesk_scene as scene
from launcher_scene import pointer_shape
from native_capture_transport import PausedViceMonitor

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
from native_editor_scene import surface as editor_surface  # noqa: E402
NOTE = b'GEMDESK opened this SEQ file.\rIt is an Editor document.\r'


def d81_entries(image):
    """Live directory records of a D81 image, as N_DIRPAGE normalizes them."""
    def sector(t, s):
        at = ((t-1)*40+s)*256
        return image[at:at+256]
    out, t, s, seen = [], 40, 3, set()
    while t and (t, s) not in seen:
        seen.add((t, s))
        data = sector(t, s)
        for i in range(8):
            e = data[i*32:i*32+32]
            kind = e[2] & 7
            if e[2] and kind:
                out.append(dict(name=bytes(e[5:21]).rstrip(b'\xa0'), type=kind,
                                blocks=e[30] | e[31] << 8))
        t, s = data[0], data[1]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix='uos-gemdesk-vice-', dir='/var/tmp/arc-scratch'))
    disk = work/'gem.d81'
    shutil.copy2(ROOT/'target/native-desktop/gem.d81', disk)
    (work/'note.seq').write_bytes(NOTE)       # a test-local document on the copy
    subprocess.run(['c1541', '-attach', str(disk), '-write', str(work/'note.seq'), 'note,s'],
                   check=True, capture_output=True)
    entries = d81_entries(disk.read_bytes())
    report = dict(passed=False, physical_hardware_io=False, work=str(work), checks=[],
                  entries=[e['name'].decode('latin-1') for e in entries])
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    xv = ci.cbm.Xvfb(); log = (work/'vice.log').open('w'); mon = None
    command = ['x128', '-default', '-8', str(disk), '-drive8true', '-drive8type', '1581',
               '-sounddev', 'dummy', '-jamaction', '0', '-warp',
               '-binarymonitor', '-binarymonitoraddress', f'ip4://127.0.0.1:{port}']
    report['command'] = command
    emu = subprocess.Popen(command, env=dict(os.environ, DISPLAY=xv.display,
                           __EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL),
                           stdout=log, stderr=subprocess.STDOUT)

    def check(name, **extra):
        report['checks'].append(dict(name=name, **extra))
        args.report.write_text(json.dumps(report, indent=2)+'\n')
        print('PASS:', name, flush=True)

    try:
        deadline = time.monotonic()+30
        while mon is None:
            assert emu.poll() is None
            try: mon = ci.Monitor(port=port)
            except OSError:
                assert time.monotonic() < deadline
                time.sleep(.1)
        banks = mon.banks(); mon.resume(); paused = PausedViceMonitor(mon)

        def read(at, n=1, bank='ram00'):
            result = bytes(paused.read_mem(at, at+n-1, bank=banks[bank])); paused.resume(); return result

        def wait(predicate, label, seconds=300):
            deadline = time.monotonic()+seconds
            while time.monotonic() < deadline:
                if predicate(): return
                assert emu.poll() is None
                time.sleep(.05)
            raise AssertionError(label)

        def ready(): return read(0x3d12) == b'\1' and read(0xd0) == b'\0'

        def key(value):
            wait(ready, 'input ready')
            before = int.from_bytes(read(0x3d13, 2), 'little')
            with paused.paused('key'):
                paused.write_mem(0x3d12, b'\0'); paused.write_mem(0x34a, bytes([value])); paused.write_mem(0xd0, b'\1')
            wait(lambda: int.from_bytes(read(0x3d13, 2), 'little') == before+1 and ready(), f'key {value:#x}')

        def expect(want, label, seconds=120):
            want = bytearray(want)
            want[8000:8128] = pointer_shape(); want[9208:9210] = b'\x7d\x7e'
            want = bytes(want)
            deadline = time.monotonic()+seconds
            while True:                       # redraws finish after the key is consumed
                wait(ready, label)
                got = read(0xc000, 0x2400)
                if got == want: break
                if time.monotonic() > deadline:
                    (work/(label+'-actual.bin')).write_bytes(got); (work/(label+'-expected.bin')).write_bytes(want)
                    raise AssertionError((label, [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b][:12]))
                time.sleep(.2)
            (work/(label+'.surface')).write_bytes(got)

        wait(lambda: read(0x1c13, 6) == b'UOS128' and ready(), 'native boot')
        expect(scene.desktop(), 'desktop')
        check('cold boot of gem.d81: GEMDESK loads AESVC.PRG; the desktop matches the CPU oracle exactly')

        ordered = scene.ordered(entries, 0)
        window = dict(id=1, x=1, y=2, w=28, h=16, title=b'Drive 8', top=0)
        key(ord('8'))
        expect(scene.picture([window], {1: ordered}, selected_icon=0), 'drive-8')
        check('the 8 key opens the boot drive; the listing matches the D81 directory, sorted by name',
              entries=len(entries))

        at = [e['name'] for e in ordered].index(b'CALC')
        for _ in range(at+1):
            key(0x11)
        window['selected'] = at
        g = scene.scene.geometry(dict(kind=scene.KIND, x=1, y=2, w=28, h=16))
        window['top'] = max(0, at-g['wh']+1)
        expect(scene.picture([window], {1: ordered}, selected_icon=0), 'calc-selected')
        key(13)
        wait(lambda: read(0x3d20) == b'\x20' and read(0x3d40, 4) == b'CALC' and ready(), 'Calculator running')
        check('Return launches the selected CALC through the dispatcher')

        key(27)
        expect(scene.picture([window], {1: ordered}), 'back')
        check('leaving Calculator returns to GEMDESK, which reopens the window with its selection')

        note = [e['name'] for e in ordered].index(b'NOTE')
        for _ in range(abs(note-at)):
            key(0x11 if note > at else 0x91)
        window['selected'] = note
        window['top'] = min(window['top'], note)             # the selection scrolls into view
        window['top'] = max(window['top'], note-g['wh']+1)
        expect(scene.picture([window], {1: ordered}), 'note-selected')
        key(13)
        editor = (ROOT/'target/native-desktop/editor.prg').read_bytes()[2:34]
        wait(lambda: read(0x3d60, 32) == editor and ready(), 'Editor running', 120)
        assert read(0x3d9a) == b'\0', 'the Editor claimed the document request'
        want = editor_surface(NOTE, 0, name='NOTE', device=8, dirty=False, field='NOTE', fmt=2,
                              view=0, horizontal=0, selection=None)
        deadline = time.monotonic()+60
        while (got := read(0xc000, 0x2400)) != want:
            if time.monotonic() > deadline:
                (work/'editor-actual.bin').write_bytes(got); (work/'editor-expected.bin').write_bytes(want)
                raise AssertionError(('editor', [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b][:12]))
            time.sleep(.2)
        (work/'editor.surface').write_bytes(got)
        check('Return on a SEQ file opens it in the Editor as a document: the surface matches the Editor oracle')

        key(27)
        expect(scene.picture([window], {1: ordered}), 'back-from-editor')
        check('leaving the Editor returns to GEMDESK with the document still selected')
        report['passed'] = True
    finally:
        args.report.write_text(json.dumps(report, indent=2)+'\n')
        if mon: mon.quit_emulator()
        else: emu.terminate()
        emu.wait(timeout=15); xv.stop(); log.close()


if __name__ == '__main__':
    main()
