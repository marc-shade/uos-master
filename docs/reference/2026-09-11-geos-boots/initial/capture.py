#!/usr/bin/env python3
"""Capture disposable GEOS128 reference boots; never contact physical hardware."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path('/home/marc/geos128/uos')
sys.path.insert(0, str(ROOT / 'tests'))
import ci_fm as ci

SOURCE = Path('/home/marc/geos128/GEOS128.D64')
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
work = Path(tempfile.mkdtemp(prefix='uos-geos-reference-boot-', dir='/var/tmp/arc-scratch'))
shutil.copyfile(__file__, work / 'capture.py')
report = dict(capture_complete=False, physical_hardware_io=False,
              source=str(SOURCE), source_sha256=digest(SOURCE),
              runtime_parity_qualified=False, runs={},
              installed_roms={str(p):digest(p) for p in Path('/usr/share/vice/C128').glob('*.bin')})
print(f'GEOS reference boot evidence: {work}', flush=True)
def save():
    (work / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
save()
try:
    for columns in (80, 40):
        folder = work / str(columns)
        folder.mkdir()
        disk = folder / 'reference.d64'
        shutil.copyfile(SOURCE, disk)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        xv = ci.cbm.Xvfb()
        log = (folder / 'vice.log').open('w')
        command = ['x128', '-default', '-autostart', str(disk),
                   '-drive8true', '-drive8type', '1541',
                   '-80col' if columns == 80 else '+80col',
                   '-VDC16KB', '-sounddev', 'dummy', '-jamaction', '0', '-warp',
                   '-binarymonitor', '-binarymonitoraddress', f'ip4://127.0.0.1:{port}',
                   '-exitscreenshot', str(folder / 'selected-display.png')]
        entry = report['runs'][str(columns)] = dict(command=command,
                    capture_complete=False, vdc_ram_kib=16, captures=[])
        process = None
        mon = None
        try:
            process = subprocess.Popen(command, env=dict(os.environ, DISPLAY=xv.display,
                __EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL), stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 30
            while mon is None:
                assert process.poll() is None, 'x128 exited during startup; see vice.log'
                try: mon = ci.Monitor(port=port)
                except OSError:
                    if time.monotonic() > deadline: raise
                    time.sleep(.1)
            banks = mon.banks()
            entry['banks'] = banks
            mon.resume()
            start = time.monotonic()
            for mark in (30, 60, 90):
                while time.monotonic() - start < mark:
                    assert process.poll() is None, 'x128 exited during reference boot'
                    time.sleep(.2)
                png = folder / f'host-display-{mark:03}.png'
                subprocess.run(['magick', 'import', '-display', xv.display,
                                '-window', 'root', str(png)], check=True, capture_output=True)
                observation = dict(elapsed_seconds=round(time.monotonic()-start,3),
                                   screenshot=png.name, screenshot_sha256=digest(png))
                for name, at, count, bank in (
                    ('mmu', 0xd500, 12, 0), ('vic-registers', 0xd000, 64, 0),
                    ('ram00', 0, 65536, banks['ram00']),
                    ('ram01', 0, 65536, banks['ram01']),
                    ('vdc', 0, 16384, banks['vdc'])):
                    data = b''.join(bytes(mon.read_mem(at+offset,
                        at+offset+min(16384,count-offset)-1, bank=bank))
                        for offset in range(0,count,16384))
                    assert len(data) == count, (name,len(data))
                    output = folder / f'{name}-{mark:03}.bin'
                    output.write_bytes(data)
                    observation[name] = dict(file=output.name, bytes=count, sha256=digest(output))
                mon.resume()
                entry['captures'].append(observation)
                save()
                print(f'Captured GEOS {columns}-column boot at {mark}s; visual interpretation pending', flush=True)
            entry['capture_complete'] = True
        finally:
            if mon:
                try: mon.quit_emulator()
                except (EOFError, OSError): pass
                mon.close()
            if process:
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try: process.wait(timeout=10)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
            xv.stop()
            log.close()
            entry['working_disk_sha256_after'] = digest(disk)
            entry['working_disk_changed'] = entry['working_disk_sha256_after'] != report['source_sha256']
            report['source_unchanged'] = digest(SOURCE) == report['source_sha256']
            assert report['source_unchanged']
            save()
    report['capture_complete'] = True
except BaseException as error:
    report['error'] = repr(error)
    raise
finally:
    save()
print(f'Captured both GEOS reference boots; original disk unchanged; {work}', flush=True)

