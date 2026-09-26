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


class AnyChannel:
    """io.fail_open value that fails every OPEN (an absent or broken drive)."""
    def __eq__(self, other):
        return True


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

        # An unsorted directory, a second drive with a scrolling listing.
        # 'MIKE ' (a trailing space) precedes 'MIKE' on disk; name order puts the
        # shorter name first because the $a0 padding sorts below a space.
        files2 = {(8, b'AESVC.PRG', b'P'): AESVC, (8, b'ZULU', b'S'): bytes(700),
                  (8, b'ALPHA', b'P'): bytes(2600), (8, b'MIKE ', b'P'): bytes(1300), (8, b'MIKE', b'U'): bytes(10),
                  (8, b'ALP', b'S'): bytes(5000), (8, b'BRAVO', b'P'): bytes(700)}
        for i in range(20):
            files2[9, f'NINE{i:02}'.encode(), b'S'] = bytes(300)
        r = Gem(files2)
        disk8 = entries_for({**files2, (8, b'GEMDESK', b'P'): r.image})
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

        text = b'[1][Drive 9|Files: 20|Blocks used: 40][OK]'
        r.key(9); r.expect(scene.scene.draw(both, text, 1, 1)[0], 'drive info')
        r.key(13); r.expect(both, 'drive info closed')
        done('Show Info on a drive icon counts its files and blocks', r, text=text.decode())

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
        d.cell(5+18+2, 7+7); d.click()                              # the Cancel button
        d.expect(before, 'preferences cancelled')
        prefs(); d.expect(scene.prefs_dialog(before, True, 0), 'cancel kept the settings')
        d.key(32)
        d.cell(10, 7+6); d.click()                                  # the Size radio button
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
        report['passed'] = True
    finally:
        args.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
