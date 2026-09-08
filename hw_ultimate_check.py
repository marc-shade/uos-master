#!/usr/bin/env python3
"""Exercise the Ultimate browser on the reference C128 without modifying files.

Boots the distributable on A. Captures an independent directory-packet oracle,
navigates the actual app past ordinal 255, compares complete cached filenames
and VDC text, restores both DOS contexts and leaves the desktop running.
Drive B is not remounted. Physical mouse motion is not injected by this script.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
import urllib.request

from hw_storage_check import ci, HardwareMonitor, ROOT, read_vdc, screen_code, wait_for
from hw_uci_check import Probe
from hwlib import desk_tick, lst_symbol
from ci_storage import launch_from_apps
from cap_hw_screen import grab, render


class ObservingUltimate(ci.cbm.Ultimate):
    """Retry read-only observations; never replay navigation/DMA writes."""
    read_retries = 0

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
                    ('ready', 'count', 'selected', 'base', 'more', 'pathlen', 'nameoff')}

    def read(self, address, size=1):
        return bytes(self.mon.read_mem(address, address+size-1))

    def value(self, name, size=1):
        return int.from_bytes(self.read(self.sym[name], size), 'little')

    def ready(self):
        return self.value('ready') == 1 and self.read(0xc6) == b'\0'

    def press(self, key):
        wait_for(self.ready, 'browser input ready')
        self.mon.write_mem(self.sym['ready'], b'\0')
        ci.inject_keys(self.mon, bytes([key]))
        if key == 27:
            wait_for(lambda: self.value('ready') == 0xff, 'browser exit', 120)
            assert ci.wait_desktop_live(self.mon, 120)
        else:
            time.sleep(0.25)
            wait_for(self.ready, f'browser key {key:#x}', 180)

    def names(self):
        count = self.value('count')
        assert count <= 8
        return [self.read(0x6000+i*512, 512).split(b'\0')[0] for i in range(count)]


def ascii_to_petscii(data):
    return bytes(c & 0xdf if 0x61 <= c <= 0x7a else c | 0x80 if 0x41 <= c <= 0x5a
                 else c if 0x20 <= c <= 0x7e else 0x2e for c in data)


def check_page(browser, expected, work, label):
    got = browser.names()
    assert got == [record[0][1:] for record in expected], (label, got, expected)
    vdc = read_vdc(browser.mon, work)
    (work / f'{label}.vdc.bin').write_bytes(vdc)
    for i, (packet, clipped) in enumerate(expected):
        assert not clipped
        name = packet[1:]
        shown = ascii_to_petscii(name[:74])
        if len(name) > 74:
            shown = shown[:73] + b'>'
        wanted = bytes(map(screen_code, shown))
        assert vdc[(4+i)*80+3:(4+i)*80+3+len(wanted)] == wanted, (label, i, name)
    return [name.decode('utf-8', 'replace') for name in got]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-boot', action='store_true')
    parser.add_argument('--directory', default='/Usb0/c64/#-a/')
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix='uos-hardware-browser-'))
    print(f'Browser hardware evidence: {work}', flush=True)
    report = {'build': build_hashes(), 'checks': [], 'passed': False,
              'dma_observation_quiet_seconds': {'boot':60,'launcher_directory':30,'app_load':30}}
    ult = ObservingUltimate()
    mon = HardwareMonitor(ult)
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
    probe = Probe(ult, work)
    original = {t: probe.ok(bytes([t, 0x12]))['records'][0][0] for t in (1, 2)}
    report['dos_paths_before_hex'] = {t:path.hex() for t,path in original.items()}
    (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    settings = bytes(mon.read_mem(0x7350, 0x7358))
    prefix = (ROOT/'target/uos-ultimate.prg').read_bytes()[2:18]
    active = False
    try:
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
        render(grab(ult, verbose=False), str(work/'first.png'))
        print('PASS: complete first-page names and exact physical VDC rows', flush=True)
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
        assert browser.read(0x7000, browser.value('pathlen', 2)) == b'/'
        names = browser.names()
        index = names.index(b'Usb0')
        for _ in range(index):
            browser.press(0x11)
        browser.press(13)
        assert browser.read(0x7000, browser.value('pathlen', 2)).rstrip(b'/') == b'/Usb0'
        browser.press(ord('U'))
        assert browser.read(0x7000, browser.value('pathlen', 2)) == b'/'
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
