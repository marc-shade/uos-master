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
from ci_native_folders import FolderDOS               # (before GemDOS patches ci_native_ultimate)
import native_gemdesk_scene as scene

ROOT = Path(__file__).resolve().parents[1]
AESVC = (ROOT/'target/native-desktop/aesvc.prg').read_bytes()


class AnyChannel:
    """io.fail_open value that fails every OPEN (an absent or broken drive)."""
    def __eq__(self, other):
        return True


class IdentifiedFolderDOS(FolderDOS):
    """The folder model (directories, DELETE_FILE, FILE_STAT) that also answers
    the DOS target's identify query, which GEMDESK uses to show the USB icon."""
    def respond(self, command):
        if command == bytes([1, 1]):
            return [(b'ULTIMATE DOS', b'00,OK')]
        return super().respond(command)


class GemDOS:
    """Built by the harness as its Ultimate model: IdentifiedFolderDOS with a tree."""
    tree = None

    def __new__(cls, files):
        dos = IdentifiedFolderDOS()
        dos.directories = {path: list(entries) for path, entries in cls.tree.items()}
        dos.paths = {1: b'/', 2: b'/'}
        dos.files.update(files)
        return dos


class Gem(calc.Calculator):
    instruction_limit = 60_000_000
    allow_busy_poll = True
    position = Pointer.position
    frame = Pointer.frame
    poll = Pointer.poll
    move = Pointer.move

    def __init__(self, files, usb=None, fmt=0):
        files = {**files, (8, b'GDDLG.PRG', b'P'): (ROOT/'target/native-desktop/gddlg.prg').read_bytes(),
                 (8, b'GDSET.PRG', b'P'): (ROOT/'target/native-desktop/gdset.prg').read_bytes()}
        extra = {}
        if usb is not None:                 # directories: {path: [attribute+name]}, files: {path: bytes}
            import ci_native_ultimate
            GemDOS.tree = usb['dirs']
            saved, ci_native_ultimate.DOSFiles = ci_native_ultimate.DOSFiles, GemDOS
            extra = dict(ultimate_files=usb['files'])
        try:
            super().__init__('gemdesk', files, loader_name=b'GEMDESK', fmt=fmt,
                             image_prefix='native-desktop', vdc_component=False, **extra)
        finally:
            if usb is not None:
                ci_native_ultimate.DOSFiles = saved
        # Pointer.frame sets bus attributes (button, raster); with a USB model
        # the machine's bus is an UltimateBus wrapper, so use the bus inside it.
        self.bus = getattr(self.m.bus, 'native', self.m.bus)
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


class Relaunch(Gem):
    """GEMDESK started again on the same machine (the AES stays resident), as the
    dispatcher does when a launched program returns to "browse"."""
    def __init__(self, previous):
        from ci_native_files import StreamIEC
        from py65.devices.mpu6502 import MPU
        self._symbol_cache = {}
        self.m, self.ram, self.bus = previous.m, previous.ram, previous.m.bus
        self.image_name, self.image_prefix, self.image = 'gemdesk', 'native-desktop', previous.image
        self.io = StreamIEC(self.m, {k: bytes(v) for k, v in previous.io.files.items()})
        self.io.formats[8] = 0
        self.ram[0x3d21:0x3d23] = bytes([8, 7]); self.ram[0x3d40:0x3d47] = b'GEMDESK'
        self.ram[0x3d9a] = 0     # the launch in between (the Editor) claimed or expired any request
        self.ram[0x3d2c:0x3d2e] = bytes([0, 8])
        self.cpu = MPU(memory=self.m.bus, pc=calc.RUN); self.cpu.sp, self.cpu.p = 0xe0, 0x20
        self.cpu.stPushWord(0xaff)
        self.screens = [bytearray(b' '*1000), bytearray(b' '*2000)]
        self.reverse = [False, False]; self.row = [0, 0]; self.col = [0, 0]; self.keys = []
        self.events = int.from_bytes(self.ram[0x3d13:0x3d15], 'little')   # kernel state
        self.instructions = 0; self.frames = 0
        self.observation_target = None; self.observation_done = False
        self.loop()


def entries_for(files, device=8):
    """Directory records as N_DIRPAGE normalizes them (types 1 SEQ 2 PRG 3 USR)."""
    out = []
    for (dev, name, kind), data in files.items():
        if dev == device:
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
        entries = entries_for(p.io.files)          # the disk as the harness built it
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
        about = b'[1][uOS GEM desktop|AES 1.6 on the C128][OK]'
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
        assert q.ram[0x3d28] == 1 and bytes(q.ram[0x3d40:0x3d46]) == b'EDITOR' and q.ram[0x3d22] == 6
        assert (q.ram[0x3d9a], q.ram[0x3d9b], q.ram[0x3d9c], q.ram[0x3d9d]) == (0x80, 1, 0, 0), 'a staged Editor document'
        assert q.ram[0x3d29] == 8 and q.ram[0x3d34] == 6 and bytes(q.ram[0x3e00:0x3e06]) == b'FILE00'
        done('double-clicking a SEQ file opens it in the Editor as a document (the Files contract)', q)

        back = Relaunch(q)
        window.update(top=0, selected=row)
        back.expect(scene.picture([dict(window)], {1: entries}), 'windows back after the launch')
        done('when the desktop returns, the AES session reopens its windows (rectangle, scroll, selection)', back)
        back.cell(3, g['wy']+entries.index(next(e for e in entries if e['name'] == b'AESVC.PRG')))
        back.frame(down=True); back.frame(down=False)
        back.frame(down=True, exited=True)
        assert back.ram[0x3d28] == 1 and back.ram[0x3d22] == 9 and bytes(back.ram[0x3d40:0x3d49]) == b'AESVC.PRG'
        assert back.ram[0x3d9a] == 0 and back.ram[0x3d21] == 8, 'a program: no document request'
        done('double-clicking a PRG hands it to the dispatcher (device 8) without a document request', back)

        # An unsorted directory, a second drive with a scrolling listing.
        # 'MIKE ' (a trailing space) precedes 'MIKE' on disk; name order puts the
        # shorter name first because the $a0 padding sorts below a space.
        files2 = {(8, b'AESVC.PRG', b'P'): AESVC, (8, b'ZULU', b'S'): bytes(700),
                  (8, b'ALPHA', b'P'): bytes(2600), (8, b'MIKE ', b'P'): bytes(1300), (8, b'MIKE', b'U'): bytes(10),
                  (8, b'ALP', b'S'): bytes(5000), (8, b'BRAVO', b'P'): bytes(700)}
        for i in range(20):
            files2[9, f'NINE{i:02}'.encode(), b'S'] = bytes(300)
        r = Gem(files2)
        disk8 = entries_for(r.io.files)
        disk9 = entries_for(files2, 9)
        w8 = dict(id=1, x=1, y=2, w=28, h=16, title=b'Drive 8', top=0)
        r.cell(35, 3); r.click(double=True)
        r.expect(scene.picture([w8], {1: scene.ordered(disk8, 0)}, selected_icon=0), 'sorted by name')
        done('a drive window lists its directory sorted by name', r,
             order=[e['name'].decode() for e in scene.ordered(disk8, 0)])

        def view(item, label):
            r.key(0x85); r.key(0x1d); r.key(0x1d)          # F1, right, right: the View menu
            for _ in range(item):
                r.key(0x11)
            want = scene.picture([w8], {1: scene.ordered(disk8, VIEW[0])}, selected_icon=0)
            r.expect(scene.scene.menu_draw(want, scene.MENU, open_title=2, hover=item,
                                           flags={(2, VIEW[0]): 1})[0], label+' menu')
            r.key(13)
            VIEW[0] = item
            r.expect(scene.picture([w8], {1: scene.ordered(disk8, item)}, selected_icon=0), label)
        VIEW = [0]
        view(1, 'sorted by type'); view(2, 'sorted by size'); view(3, 'unsorted'); view(0, 'name again')
        done('View sorts by type, size (largest first), directory order and name; the item is checked', r)

        g8 = scene.scene.geometry(dict(kind=scene.KIND, x=1, y=2, w=28, h=16))
        r.cell(3, g8['wy']+2); r.click(); w8['selected'] = 2
        before = scene.picture([w8], {1: scene.ordered(disk8, 0)}, selected_icon=0)
        r.expect(before, 'entry selected')
        r.key(9)                                                   # Ctrl-I: File:Show Info
        r.expect(scene.info_dialog(before, scene.ordered(disk8, 0)[2]), 'show info')
        r.key(27); r.expect(before, 'show info closed')
        done('Show Info (Ctrl-I) opens a dialog for the selected entry; Esc restores the window exactly', r)

        w9 = dict(id=2, x=2, y=3, w=28, h=16, title=b'Drive 9', top=0)
        entries_of = {1: scene.ordered(disk8, 0), 2: scene.ordered(disk9, 0)}
        r.cell(35, 7); r.click(double=True)
        both = scene.picture([w8, w9], entries_of, selected_icon=1)
        r.expect(both, 'drive 9 window')
        done('the Drive 9 icon opens a second, staggered window over the first', r)

        text = b'[1][Drive 9|Files: 20|Blocks used: 40|Blocks free: 624][OK]'   # 664 on a D64
        r.key(9); r.expect(scene.scene.draw(both, text, 1, 1)[0], 'drive info')
        r.key(13); r.expect(both, 'drive info closed')
        done('Show Info on a drive icon: files, blocks used, and blocks free from the drive\'s listing', r, text=text.decode())

        g9 = scene.scene.geometry(dict(kind=scene.KIND, x=2, y=3, w=28, h=16))
        bar = 2+28-1
        r.cell(bar, g9['wy']+g9['wh']-3); r.click()               # the track below the thumb
        w9['top'] = 5
        r.expect(scene.picture([w8, w9], entries_of, selected_icon=1), 'paged down')
        done('a click in the slider track pages down (clamped to the last page)', r)

        track = g9['wh']-3                                          # up arrow, down arrow, size box
        size, pos = scene.slider(20, g9['wh'], 5)
        start, length = scene.scene.thumb(track, size, pos)
        r.cell(bar, g9['wy']+1+start); r.frame(down=True)
        r.cell(bar, g9['wy']+1); r.frame(down=True); r.frame(down=False)
        for _ in range(24):
            r.frame()
        w9['top'] = 0
        r.expect(scene.picture([w8, w9], entries_of, selected_icon=1), 'thumb dragged to the top')
        done('dragging the thumb to the top of the track scrolls to the first entry', r)

        r.cell(1, 12); r.click()                                    # the lower window's visible edge
        r.expect(scene.picture([w9, w8], entries_of, selected_icon=1), 'drive 8 topped')
        done('clicking the lower window tops it', r)

        r.io.fail_open = AnyChannel()
        r.cell(35, 7); r.click(double=True)
        topped = scene.picture([w9, w8], entries_of, selected_icon=1)
        alert = b'[3][Could not read this|drive: error $11][OK]'
        r.expect(scene.scene.draw(topped, alert, 1, 1)[0], 'drive error')
        r.io.fail_open = None
        r.key(13); r.expect(topped, 'drive error closed')
        assert r.ram[0x3d0e] > 0
        done('a drive that cannot be read gives an error alert and opens nothing', r)

        w3 = dict(id=3, x=3, y=4, w=28, h=16, title=b'Drive 8', top=0)
        w4 = dict(id=4, x=4, y=5, w=28, h=16, title=b'Drive 8', top=0)
        entries_of.update({3: entries_of[1], 4: entries_of[1]})
        r.cell(35, 3); r.click(double=True); r.click(double=True)
        four = scene.picture([w9, w8, w3, w4], entries_of, selected_icon=0)
        r.expect(four, 'four windows')
        full = b'[1][Four folder windows|are already open.][OK]'
        r.click(double=True); r.expect(scene.scene.draw(four, full, 1, 1)[0], 'fifth window refused')
        r.key(13); r.expect(four, 'full alert closed')
        done('four folder windows open at once; a fifth is refused with an alert', r)

        # Delete: File:Delete (Ctrl-D) and dragging onto Trash, both confirmed.
        files3 = {(8, b'AESVC.PRG', b'P'): AESVC, (8, b'KEEP', b'S'): bytes(300),
                  (8, b'DOOMED', b'P'): bytes(900), (8, b'LOCKED', b'S'): bytes(50),
                  (8, b'A*B', b'S'): bytes(10), (8, b'OLDNAME', b'U'): bytes(400)}
        d = Gem(files3)
        d.io.locked.add((8, b'LOCKED', b'S'))
        wd = dict(id=1, x=1, y=2, w=28, h=16, title=b'Drive 8', top=0)
        gd = scene.scene.geometry(dict(kind=scene.KIND, x=1, y=2, w=28, h=16))

        def listing():
            return scene.ordered(entries_for({**d.io.files}), 0)

        def shown(selected=None):
            wd['selected'] = selected
            return scene.picture([wd], {1: listing()}, selected_icon=0)

        def row(name):
            return [e['name'] for e in listing()].index(name)

        d.cell(35, 3); d.click(double=True); d.expect(shown(), 'delete fixture')
        locked = next(e for e in listing() if e['name'] == b'LOCKED')
        d.cell(3, gd['wy']+row(b'LOCKED')); d.click(); d.key(9)
        d.expect(scene.info_dialog(shown(row(b'LOCKED')), locked, locked=True), 'locked info')
        d.key(27)
        done('Show Info shows a locked file as read-only (a disabled, checked box)', d)

        d.cell(3, gd['wy']+row(b'OLDNAME')); d.click(); before = shown(row(b'OLDNAME'))
        old = next(e for e in listing() if e['name'] == b'OLDNAME')
        d.key(9); d.key(21)                                       # Ctrl-U clears the name field
        d.expect(scene.info_dialog(before, old, value=b''), 'name cleared')
        for c in b'NEWNAME':
            d.key(c)
        d.expect(scene.info_dialog(before, old, value=b'NEWNAME'), 'name typed')
        d.key(13)
        assert [e for e in d.io.events if e[0] == 'dos'][-1] == ('dos', 8, b'R0:NEWNAME=OLDNAME')
        assert (8, b'NEWNAME', b'U') in d.io.files and (8, b'OLDNAME', b'U') not in d.io.files
        d.expect(shown(), 'renamed and listed again')
        done('Show Info renames: the edited name is sent as R0:NEW=OLD and the drive is listed again', d)

        d.cell(3, gd['wy']+row(b'NEWNAME')); d.click(); before = shown(row(b'NEWNAME'))
        d.key(9); d.key(21)
        for c in b'KEEP':
            d.key(c)
        d.key(13)
        clash = b'[3][Could not rename|NEWNAME|63,FILE EXISTS,00,00][OK]'
        d.expect(scene.scene.draw(before, clash, 1, 1)[0], 'rename clash')
        d.key(13); d.expect(before, 'clash closed')
        assert (8, b'NEWNAME', b'U') in d.io.files and (8, b'KEEP', b'S') in d.io.files
        done('renaming onto an existing name shows the drive\'s refusal and changes nothing', d)

        d.cell(3, gd['wy']+row(b'DOOMED')); d.click()
        before = shown(row(b'DOOMED'))
        ask = b'[2][Delete DOOMED?|This cannot be undone.][Delete|Cancel]'
        mark = len(d.io.events)
        d.key(4); d.expect(scene.scene.draw(before, ask, 2, 2)[0], 'confirm delete')
        d.key(13); d.expect(before, 'delete cancelled')
        assert (8, b'DOOMED', b'P') in d.io.files and not [e for e in d.io.events[mark:] if e[0] == 'dos']
        d.key(4); d.key(9); d.expect(scene.scene.draw(before, ask, 2, 1)[0], 'delete focused')
        d.key(13)
        assert (8, b'DOOMED', b'P') not in d.io.files
        assert [e for e in d.io.events[mark:] if e[0] == 'dos'] == [('dos', 8, b'S0:DOOMED')]
        d.expect(shown(), 'listed again without DOOMED')
        done('Ctrl-D asks first (Cancel is the default), then scratches the file and lists the drive again', d)

        def drag_to_trash(name):
            d.cell(3, gd['wy']+row(name)); d.frame(down=True)
            for _ in range(24):                     # held past the double-click window
                d.frame()
            d.cell(35, 21); d.frame(down=False)
            for _ in range(4):
                d.frame()

        drag_to_trash(b'LOCKED')
        before = shown(row(b'LOCKED'))
        ask = b'[2][Delete LOCKED?|This cannot be undone.][Delete|Cancel]'
        d.expect(scene.scene.draw(before, ask, 2, 2)[0], 'trash confirm')
        d.key(9); d.key(13)
        failed = b'[3][Could not delete|LOCKED|01, FILES SCRATCHED,00,00][OK]'
        d.expect(scene.scene.draw(before, failed, 1, 1)[0], 'locked not deleted')
        d.key(13); d.expect(before, 'failure closed')
        assert (8, b'LOCKED', b'S') in d.io.files
        done('a file dropped on Trash is confirmed; a locked file the drive skips is reported, not hidden', d)

        drag_to_trash(b'KEEP')
        d.key(9); d.key(13)
        assert (8, b'KEEP', b'S') not in d.io.files
        d.expect(shown(), 'dropped on trash')
        done('dragging a row onto Trash deletes it after confirmation', d)

        d.cell(3, gd['wy']+row(b'A*B')); d.click(); before = shown(row(b'A*B'))
        d.key(4)
        refuse = b'[1][This name cannot be|deleted from here.][OK]'
        d.expect(scene.scene.draw(before, refuse, 1, 1)[0], 'pattern name refused')
        d.key(13)
        events = len(d.io.events)
        d.ram[0x3de0] = 8; d.ram[0x3de2] = 1              # the kernel holds drive 8's command channel
        d.cell(3, gd['wy']+row(b'AESVC.PRG')); d.click(); before = shown(row(b'AESVC.PRG'))
        d.key(4); d.key(9); d.key(13)
        busy = b'[3][Could not delete|AESVC.PRG|error $15][OK]'
        d.expect(scene.scene.draw(before, busy, 1, 1)[0], 'channel in use')
        d.key(13)
        assert not [e for e in d.io.events[events:] if e[0] in ('open', 'dos')]
        d.ram[0x3de0] = 0; d.ram[0x3de2] = 0
        d.io.fail_open = AnyChannel()
        d.key(4); d.key(9); d.key(13)
        d.io.fail_open = None
        d.expect(scene.scene.draw(before, busy.replace(b'$15', b'$11'), 1, 1)[0], 'drive error')
        d.key(13); d.expect(before, 'error closed')
        assert (8, b'AESVC.PRG', b'P') in d.io.files
        done('names with DOS pattern characters, a busy command channel and a failed OPEN are refused with alerts', d)

        def prefs():
            d.key(0x85); d.key(0x1d); d.key(0x1d); d.key(0x1d); d.key(13)   # Options:Preferences...
        before = shown(row(b'AESVC.PRG'))
        prefs(); d.expect(scene.prefs_dialog(before, True, 0), 'preferences')
        d.key(32); d.expect(scene.prefs_dialog(before, False, 0), 'confirm unticked')
        d.key(9); d.expect(scene.prefs_dialog(before, False, 0, focus=3), 'tab skips the text')
        d.key(0x91); d.expect(scene.prefs_dialog(before, False, 0, focus=1), 'cursor up')
        d.cell(5+18+2, 6+10); d.click()                             # the Cancel button
        d.expect(before, 'preferences cancelled')
        prefs(); d.expect(scene.prefs_dialog(before, True, 0), 'cancel kept the settings')
        d.key(32)
        d.cell(10, 6+6); d.click()                                  # the Size radio button
        d.expect(scene.prefs_dialog(before, False, 2, focus=5), 'size chosen')
        d.key(13)
        wd['selected'] = None
        d.expect(scene.picture([wd], {1: scene.ordered(entries_for({**d.io.files}), 2)}, selected_icon=0),
                 'sorted by size from preferences')
        done('Preferences: a checkbox, a radio group, Tab and cursor focus; clicking Cancel changes nothing, OK applies the sort order', d)

        by_size = scene.ordered(entries_for({**d.io.files}), 2)
        at = [e['name'] for e in by_size].index(b'NEWNAME')
        d.cell(3, gd['wy']+at); d.click(); d.key(4)
        assert [e for e in d.io.events if e[0] == 'dos'][-1] == ('dos', 8, b'S0:NEWNAME')
        d.expect(scene.picture([wd], {1: scene.ordered(entries_for({**d.io.files}), 2)}, selected_icon=0),
                 'deleted without asking')
        done('with Confirm deletes off, Ctrl-D deletes at once', d)

        by_size = scene.ordered(entries_for({**d.io.files}), 2)
        prefs(); before = scene.picture([wd], {1: by_size}, selected_icon=0)
        d.expect(scene.prefs_dialog(before, False, 2), 'preferences again')
        d.cell(5+12+1, 6+8); d.click()                              # Grey
        d.key(13)
        grey = scene.picture([wd], {1: by_size}, selected_icon=0, color=0x1c)
        d.expect(grey, 'grey desktop')
        done('Preferences: a desktop colour repaints the desktop and its icons', d)

        mark = len(d.io.events)
        d.key(0x85); d.key(0x1d); d.key(0x1d); d.key(0x1d); d.key(0x11); d.key(13)   # Options:Save Desktop
        want = scene.record(0, 2, 0x1c, [dict(dev=8, fmt=0, x=1, y=2, w=28, h=16, top=0)], repeat=d.ram[0x0a22])
        assert bytes(d.io.files[8, b'DESKTOP.INF', b'S']) == want, bytes(d.io.files[8, b'DESKTOP.INF', b'S'])
        assert ('dos', 8, b'S0:DESKTOP.INF') in d.io.events[mark:]
        d.expect(grey, 'saved')
        done('Options:Save Desktop writes DESKTOP.INF (preferences, colour, windows)', d, record=want.hex())

        cold = Gem({k: bytes(v) for k, v in d.io.files.items() if k != (8, b'GEMDESK', b'P')})
        listing_now = scene.ordered(entries_for({**cold.io.files}), 2)
        cold.expect(scene.picture([dict(wd, selected=None)], {1: listing_now}, color=0x1c), 'cold start')
        cold.cell(3, gd['wy']); cold.click(); cold.key(4)                       # confirm is off
        assert [e for e in cold.io.events if e[0] == 'dos'][-1] == ('dos', 8, b'S0:'+listing_now[0]['name'].split(b'\xa0')[0])
        done('a cold start (AES loaded fresh) reads DESKTOP.INF: windows, sort, colour, confirm setting', cold)

        # File:Format on drive 9.
        files4 = {(8, b'AESVC.PRG', b'P'): AESVC, (9, b'OLD1', b'S'): bytes(500),
                  (9, b'OLD2', b'P'): bytes(900)}
        fm = Gem(files4)
        fm.io.locked.add((9, b'OLD1', b'S'))                       # formatting erases locked files too
        w9 = dict(id=1, x=1, y=2, w=28, h=16, title=b'Drive 9', top=0)
        fm.key(ord('9'))                                            # the 9 key opens drive 9
        before = scene.picture([w9], {1: scene.ordered(entries_for(files4, 9), 0)}, selected_icon=1)
        fm.expect(before, 'drive 9 open')

        def format_menu():
            fm.key(0x85); fm.key(0x1d); fm.key(0x11); fm.key(0x11); fm.key(0x11); fm.key(13)
        format_menu()
        fm.expect(scene.format_dialog(before, 2), 'format dialog')
        fm.key(13)                                                  # empty name and ID
        need = b'[1][A disk needs a name|and an ID.][OK]'
        fm.expect(scene.scene.draw(before, need, 1, 1)[0], 'name needed')
        fm.key(13); fm.expect(before, 'need closed')
        format_menu()
        fm.key(0x11); fm.key(32)                                    # drive 9
        fm.expect(scene.format_dialog(before, 3, drive8=False), 'drive 9 chosen')
        fm.key(9)
        for c in b'BLANK':
            fm.key(c)
        fm.key(9)
        for c in b'B1':
            fm.key(c)
        fm.expect(scene.format_dialog(before, 7, drive8=False, name=b'BLANK', ident=b'B1'), 'name and id')
        fm.key(13)
        ask = b'[3][Format drive 9?|Every file on it|will be erased.][Format|Cancel]'
        fm.expect(scene.scene.draw(before, ask, 2, 2)[0], 'format confirm')
        assert not [e for e in fm.io.events if e[0] == 'dos']
        fm.key(9); fm.key(13)
        assert [e for e in fm.io.events if e[0] == 'dos'] == [('dos', 9, b'N0:BLANK,B1')]
        assert not [k for k in fm.io.files if k[0] == 9]
        fm.expect(scene.picture([w9], {1: []}, selected_icon=1), 'formatted and listed again')
        done('the 9 key opens drive 9; File:Format asks for drive, name and ID, confirms, sends N0:NAME,ID and lists the drive again', fm)

        nm = Gem(files4)
        del nm.io.files[8, b'GDDLG.PRG', b'P']                    # the dialog module is missing
        nm.key(ord('9'))
        nm.cell(3, 3); nm.click()                                   # the first entry: Show Info needs one
        nm.key(9)
        missing = b'[3][Could not load GDDLG.PRG.|error $11][OK]'
        shown = scene.picture([dict(w9, selected=0)], {1: scene.ordered(entries_for(nm.io.files, 9), 0)}, selected_icon=1)
        nm.expect(scene.scene.draw(shown, missing, 1, 1)[0], 'module missing')
        nm.key(13); nm.expect(shown, 'desktop goes on')
        done('a missing GDDLG.PRG gives an alert and the desktop goes on', nm)

        big = {(8, b'AESVC.PRG', b'P'): AESVC}
        for i in range(200):                                        # a D81 root holds up to 296
            big[8, f'F{199-i:03}'.encode(), b'S'] = bytes(10)     # directory order is reversed name order
        tr = Gem(big, fmt=2)                                        # the boot drive is a D81
        tr.key(ord('8'))
        kept = scene.ordered(entries_for(tr.io.files)[:195], 0)     # the first 195 on disk, then sorted
        wt = dict(id=1, x=1, y=2, w=28, h=16, title=b'Drive 8', top=0)
        tr.expect(scene.picture([wt], {1: kept}, selected_icon=0), 'first 195 entries')
        done('a directory over 195 entries lists its first 195 (the 16-page snapshot)', tr, first=kept[0]['name'].decode())

        # USB storage (the Ultimate's DOS): icon, folders, parent, launch.
        long = b'A VERY LONG PROGRAM NAME.PRG'
        tree = {b'/': [b'\x10Usb0'],
                b'/Usb0': [b'\x10GAMES', b'\x20CALC.PRG', b'\x20'+long, b'\x20notes.txt'],
                b'/Usb0/GAMES': [b'\x20TETRIS.PRG'],
                b'/shell': [], b'/browser': []}
        us = Gem({(8, b'AESVC.PRG', b'P'): AESVC},
                 usb=dict(dirs=tree, files={b'/Usb0/CALC.PRG': bytes(10)}))
        us.expect(scene.desktop(usb=True), 'usb icon')
        wu = dict(id=1, x=1, y=2, w=28, h=16, title=b'USB /', top=0)
        us.cell(35, 11); us.click(double=True)
        us.expect(scene.picture([wu], {1: scene.usb_entries(tree[b'/'])}, selected_icon=3, usb=True), 'usb root')
        us.cell(3, 3); us.click(double=True)
        wu['title'] = b'USB /Usb0'
        usb0 = scene.ordered(scene.usb_entries(tree[b'/Usb0']), 0)
        us.expect(scene.picture([wu], {1: usb0}, selected_icon=3, usb=True), 'usb0')
        games = [e['name'] for e in usb0].index(b'GAMES')
        us.cell(3, 3+games); us.click(double=True)
        wu['title'] = b'USB /Usb0/GAMES'
        us.expect(scene.picture([wu], {1: scene.usb_entries(tree[b'/Usb0/GAMES'])}, selected_icon=3, usb=True), 'games')
        us.cell(1, 2); us.click()                                   # the close box: up one level
        wu['title'] = b'USB /Usb0'
        us.expect(scene.picture([wu], {1: usb0}, selected_icon=3, usb=True), 'back up')
        done('the USB icon appears when the Ultimate answers; folders open in the window, the close box goes up', us)

        at = [e['name'] for e in usb0].index(long[:16])
        us.cell(3, 3+at); us.click(); us.key(9)                     # Show Info is IEC-only here
        wu['selected'] = at
        shown = scene.picture([wu], {1: usb0}, selected_icon=3, usb=True)
        notusb = b'[1][Not available on USB|storage in the desktop yet.][OK]'
        us.expect(scene.scene.draw(shown, notusb, 1, 1)[0], 'not on usb')
        us.key(13)
        us.cell(3, 3+at)
        us.frame(down=True); us.frame(down=False)
        us.frame(down=True, exited=True)                            # the second press launches
        assert us.ram[0x3d28] == 1 and us.ram[0x3d2c] == 3 and us.ram[0x3d21] == 1
        full = b'/Usb0/'+long
        assert us.ram[0x3d22] == len(full) and bytes(us.ram[0x4e00:0x4e00+len(full)]) == full
        done('a USB file launches with its full path (past 16 characters); Show Info says it is not available on USB', us)

        ud = Gem({(8, b'AESVC.PRG', b'P'): AESVC},
                 usb=dict(dirs=tree, files={b'/Usb0/CALC.PRG': bytes(10)}))
        ud.cell(35, 11); ud.click(double=True); ud.cell(3, 3); ud.click(double=True)
        wd = dict(id=1, x=1, y=2, w=28, h=16, title=b'USB /Usb0', top=0)
        calc_at = [e['name'] for e in usb0].index(b'CALC.PRG')
        ud.cell(3, 3+calc_at); ud.click()
        wd['selected'] = calc_at
        before = scene.picture([wd], {1: usb0}, selected_icon=3, usb=True)
        ask = b'[2][Delete CALC.PRG?|This cannot be undone.][Delete|Cancel]'
        ud.key(4); ud.expect(scene.scene.draw(before, ask, 2, 2)[0], 'usb confirm')
        ud.key(9); ud.key(13)
        dos = ud.ultimate
        assert b'\x20CALC.PRG' not in dos.directories[b'/Usb0'] and dos.last_path == b'/Usb0/CALC.PRG'
        left = scene.ordered(scene.usb_entries(dos.directories[b'/Usb0']), 0)
        wd['selected'] = None
        ud.expect(scene.picture([wd], {1: left}, selected_icon=3, usb=True), 'usb deleted')
        games_at = [e['name'] for e in left].index(b'GAMES')
        ud.cell(3, 3+games_at); ud.click()
        wd['selected'] = games_at
        before = scene.picture([wd], {1: left}, selected_icon=3, usb=True)
        ud.key(4); ud.key(9); ud.key(13)                            # the drive refuses a full folder
        text = bytes(ud.ram[ud.symbol('gm_abuf'):ud.symbol('gm_abuf')+60]).split(b'\0')[0]
        assert text.startswith(b'[3][Could not delete|GAMES|error $'), text
        ud.expect(scene.scene.draw(before, text, 1, 1)[0], 'full folder refused')
        ud.key(13); ud.expect(before, 'refusal closed')
        assert b'\x10GAMES' in dos.directories[b'/Usb0']
        notes = [e['name'] for e in left].index(b'notes.txt')
        ud.cell(3, 3+notes); ud.frame(down=True); ud.frame(down=False); ud.frame(down=True, exited=True)
        assert bytes(ud.ram[0x3d40:0x3d46]) == b'EDITOR' and ud.ram[0x3d9a] == 0x80 and ud.ram[0x3d9b] == 1
        assert (ud.ram[0x3d29], ud.ram[0x3d2a], ud.ram[0x3d2e], ud.ram[0x3d34]) == (1, 3, 5, 9)
        assert bytes(ud.ram[0x4a00:0x4a05]) == b'/Usb0' and bytes(ud.ram[0x3e00:0x3e09]) == b'notes.txt'
        done('Delete on USB: confirmed, DELETE_FILE then FILE_STAT (82) before listing again; a full folder is refused; '
             'a .txt file opens in the Editor with its folder', ud,
             refusal=text.decode())

        # Keyboard mouse and the Control Panel.
        kc = Gem(files4)
        kc.cell(29, 21)                                             # just left of Trash
        start = kc.position
        kc.ram[0xd3] = 8                                            # ALT held (KERNAL SHFLAG)
        kc.key(0x1d); kc.key(0x1d)
        assert kc.position == (start[0]+16, start[1]), (start, kc.position)
        kc.key(13)                                                  # ALT+Return clicks
        kc.ram[0xd3] = 0
        for _ in range(24):
            kc.frame()
        kc.expect(scene.desktop(selected=2), 'trash selected from the keyboard')
        done('ALT+cursor moves the pointer 8 pixels and ALT+Return clicks; the keys are not delivered', kc)

        def slow_double(cx, cy):                                    # presses 12 jiffies apart
            kc.cell(cx, cy); kc.frame(down=True); kc.frame(down=False)
            for _ in range(10):
                kc.frame()
            kc.frame(down=True); kc.frame(down=False)
            for _ in range(24):
                kc.frame()
        slow_double(35, 3)                                          # speed 2 (20 jiffies): a double click
        w8k = dict(id=1, x=1, y=2, w=28, h=16, title=b'Drive 8', top=0)
        kc.expect(scene.picture([w8k], {1: scene.ordered(entries_for(kc.io.files), 0)}, selected_icon=0), 'slow double opens')
        kc.key(23)
        kc.key(0x85); kc.key(0x11); kc.key(13)                      # Desk:Control Panel
        before = scene.desktop(selected=0)
        repeat = kc.ram[0x0a22]
        kc.expect(scene.control_dialog(before, repeat, 2), 'control panel')
        kc.cell(5+21+1, 7+4); kc.click()                            # repeat: None
        kc.cell(5+24+1, 7+6); kc.click()                            # speed 5
        kc.expect(scene.control_dialog(before, 0x40, 4, focus=10), 'none and fastest')
        kc.key(13)
        assert kc.ram[0x0a22] == 0x40
        kc.expect(before, 'control panel closed')
        slow_double(35, 3)                                          # speed 5 (10 jiffies): two clicks
        kc.expect(scene.desktop(selected=0), 'slow double no longer opens')
        done('Control Panel: key repeat goes to the KERNAL, double-click speed to the AES', kc,
             repeat=hex(repeat))
        report['passed'] = True
    finally:
        args.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
