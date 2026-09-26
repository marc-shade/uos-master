#!/usr/bin/env python3
"""GEM desktop (docs/GEM-DESKTOP.md) in the Py65 model: AES load, icons, drive
windows with listings, scrolling, selection, menu, and leaving for the card
launcher. Complete surfaces are compared with tests/native_gemdesk_scene.py."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
from ci_native_pointer import Pointer, heap          # installs the 1351 bus
import ci_native_calc as calc
import ci_native_aes                                   # an owner-30 AES may stay resident
import native_gemdesk_scene as scene

ROOT = Path(__file__).resolve().parents[1]
AESVC = (ROOT/'target/native-desktop/aesvc.prg').read_bytes()


class Gem(calc.Calculator):
    instruction_limit = 60_000_000
    allow_busy_poll = True
    position = Pointer.position
    frame = Pointer.frame
    poll = Pointer.poll
    move = Pointer.move

    def __init__(self, files):
        super().__init__('gemdesk', files, loader_name=b'GEMDESK',
                         image_prefix='native-desktop', vdc_component=False)
        self.bus = self.m.bus
        self.frames = 0

    def key(self, key, exited=False):
        self.observation_target = None
        self.keys.append(key)
        self.loop(exited)
        self.events += 1

    def surface(self):
        return bytes(self.ram[0xc000:0xe400])

    def expect(self, want, label):
        from launcher_scene import pointer_shape
        want = bytearray(want)                 # the 1351 sprite lives in the surface tail
        want[8000:8128] = pointer_shape(); want[9208:9210] = b'\x7d\x7e'
        want = bytes(want)
        got = self.surface()
        assert got == want, (label, [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b][:12])

    def cell(self, cx, cy):
        """Move the pointer to the centre of a cell."""
        self.move(cx*8+4, cy*8+4)

    def click(self, double=False):
        for _ in range(2 if double else 1):
            self.frame(down=True); self.frame(down=False)
        for _ in range(24):          # the double-click window (20 jiffies) closes
            self.frame()


def entries_for(files):
    """Directory records as N_DIRPAGE normalizes them (types 1 SEQ 2 PRG 3 USR)."""
    out = []
    for (dev, name, kind), data in files.items():
        if dev == 8:
            out.append(dict(name=name, type={b'S': 1, b'P': 2, b'U': 3}[kind],
                            blocks=max(1, (len(data)+253)//254)))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    report = dict(passed=False, physical_hardware_io=False, cases=[])

    def done(name, p, **extra):
        report['cases'].append(dict(name=name, frames=p.frames, instructions=p.instructions, **extra))
        args.report.write_text(json.dumps(report, indent=2)+'\n')
        print('PASS:', name, flush=True)

    try:
        files = {(8, b'AESVC.PRG', b'P'): AESVC}
        for i in range(20):                               # 20 entries: the window scrolls
            files[8, f'FILE{i:02}'.encode(), b'S'] = bytes(100+i*200)
        p = Gem(files)
        entries = entries_for({**files, (8, b'GEMDESK', b'P'): p.image})
        p.expect(scene.desktop(), 'startup')
        assert ci_native_aes.resident_aes(p.m) is not None, 'the desktop loaded AESVC.PRG'
        done('startup: AES loaded from the boot folder, menu bar and desktop icons', p)

        p.cell(35, 3); p.click(); p.expect(scene.desktop(selected=0), 'icon selected')
        p.cell(35, 21); p.click(); p.expect(scene.desktop(selected=2), 'trash selected')
        p.cell(20, 15); p.click(); p.expect(scene.desktop(), 'deselected')
        done('clicking icons selects and deselects them', p)

        window = dict(id=1, x=1, y=2, w=28, h=16, title=b'Drive 8', top=0)
        p.cell(35, 3); p.click(double=True)
        p.expect(scene.picture([window], {1: entries}, selected_icon=0), 'drive window')
        done('double-clicking the boot drive opens its listing window', p, entries=len(entries))

        g = scene.scene.geometry(dict(kind=scene.KIND, x=1, y=2, w=28, h=16))
        up_col = 1+28-1
        p.cell(up_col, g['wy']+g['wh']-2); p.click()           # down arrow (the size box has the last cell)
        window['top'] = 1
        p.expect(scene.picture([window], {1: entries}, selected_icon=0), 'scrolled one row')
        p.cell(3, g['wy']+2); p.click()                          # select entry top+2
        window['selected'] = 3
        p.expect(scene.picture([window], {1: entries}, selected_icon=0), 'entry selected')
        p.key(0x11); window['selected'] = 4
        p.expect(scene.picture([window], {1: entries}, selected_icon=0), 'cursor down')
        done('arrows scroll, clicks and cursor keys select rows', p)

        p.key(23)                                                # Ctrl-W: File:Close
        p.expect(scene.desktop(selected=0), 'closed')
        done('File:Close (Ctrl-W) closes the window and frees its listing', p)

        p.key(0x85); p.key(13)                                  # F1, Return: Desk:About
        about = b'[1][uOS GEM desktop|AES 1.4 on the C128][OK]'
        p.expect(scene.scene.draw(scene.desktop(selected=0), about, 1, 1)[0], 'about alert')
        p.key(13)                                               # OK closes the alert
        p.expect(scene.desktop(selected=0), 'about closed')
        done('Desk:About shows an alert and restores the desktop exactly', p)

        p.key(12, exited=True)                                   # Ctrl-L: Options:Launcher
        assert p.ram[0x3d28] == 1 and bytes(p.ram[0x3d40:0x3d45]) == b'CARDS'
        assert p.ram[0x3d22] == 5
        done('Options:Launcher replaces the desktop with the card launcher', p)

        q = Gem(files)
        q.cell(35, 3); q.click(double=True)
        row = entries.index(next(e for e in entries if e['name'] == b'FILE00'))
        g = scene.scene.geometry(dict(kind=scene.KIND, x=1, y=2, w=28, h=16))
        q.cell(3, g['wy']+row)
        q.frame(down=True); q.frame(down=False)
        q.frame(down=True, exited=True)    # the second press is sampled on the settled poll and launches
        assert q.ram[0x3d28] == 1 and bytes(q.ram[0x3d40:0x3d46]) == b'FILE00'
        assert q.ram[0x3d22] == 6 and q.ram[0x3d21] == 8
        done('double-clicking a listed file hands it to the dispatcher (device 8)', q)
        report['passed'] = True
    finally:
        args.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
