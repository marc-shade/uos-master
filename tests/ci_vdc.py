#!/usr/bin/env python3
"""CI for the 80-column companion display (M1): boots the image in x128
(-go64: C64-mode OS with the 8563 emulated), then reads VDC RAM through the
VICE text monitor (`bank vdc`) and checks what the desktop, file manager and
shell mirror onto the second screen.

Checks:
  A  boot: rows 0-1 carry the header, row 2 says "desktop"
  B  file manager (tick-vector trampoline): row 2 "File manager", row 23 the
     key hint, rows 4.. one directory entry each with the ">" marker on row 0
  C  ESC: back on the desktop, listing rows blanked
  D  shell: row 2 "Command shell", VER -> row 7 "UltOS 0.3", EXIT -> desktop
  E  settings: rows 4/5 display mode + background colour, C cycles it, ESC

Run: python3 tests/ci_vdc.py   (exit 0 = all pass)
"""
import os
import re
import socket
import subprocess
import sys
import time

UOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCK = os.path.join(UOS, "target/ultos.d64")
OUT = os.path.join(UOS, "vdc-emu-out")
os.makedirs(OUT, exist_ok=True)
# x128 runs the drive read-write and the settings check SAVEs a record:
# never boot the committed image directly, or it gets a uos-set file
DISK = os.path.join(OUT, "ci_vdc.d64")
import shutil
shutil.copyfile(STOCK, DISK)
EGL = {"__EGL_VENDOR_LIBRARY_FILENAMES": "/usr/share/glvnd/egl_vendor.d/50_mesa.json"}
sys.stdout.reconfigure(line_buffering=True)
KB_BUF, KB_CNT, TICK_VEC, TRAMP = 0x0277, 0x00C6, 0x033C, 0x7F00


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_xvfb():
    for n in range(100, 140):
        p = subprocess.Popen(["Xvfb", f":{n}", "-screen", "0", "1400x700x24"],
                             env=dict(os.environ, **EGL),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            if p.poll() is not None:
                break
            if subprocess.run(["xdpyinfo", "-display", f":{n}"], capture_output=True).returncode == 0:
                return p, f":{n}"
            time.sleep(0.25)
        if p.poll() is None:
            p.terminate()
    raise SystemExit("FAIL: no Xvfb display")


class Mon:
    def __init__(self, port, emu):
        self.port, self.emu = port, emu

    def cmd(self, c, wait=1.2):
        for _ in range(80):
            if self.emu.poll() is not None:
                raise SystemExit(f"FAIL: x128 exited rc={self.emu.returncode}")
            try:
                s = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise SystemExit("FAIL: monitor unreachable")
        s.settimeout(wait)
        s.sendall((c + "\n").encode())
        buf = b""
        try:
            while True:
                ch = s.recv(65536)
                if not ch:
                    break
                buf += ch
        except socket.timeout:
            pass
        try:
            s.sendall(b"x\n")
        except OSError:
            pass
        s.close()
        return buf.decode("latin-1", errors="replace")

    def vdc_rows(self):
        """Return 25 strings decoded from VDC screen RAM $0000-$07cf."""
        self.cmd("bank vdc")
        txt = self.cmd("m 0000 07cf", wait=2.5)
        self.cmd("bank cpu")
        mem = {}
        for line in txt.splitlines():
            m = re.search(r">.:([0-9a-fA-F]{4})\s+(.*)$", line)
            if not m:
                continue
            addr = int(m.group(1), 16)
            hexpart = re.split(r"\s{3,}", m.group(2))[0]
            for i, tok in enumerate(re.findall(r"\b[0-9a-fA-F]{2}\b", hexpart)[:16]):
                mem[addr + i] = int(tok, 16)
        rows = []
        for r in range(25):
            s = ""
            for i in range(80):
                c = mem.get(r * 80 + i, 0x20)
                if 1 <= c <= 0x1a:
                    s += chr(c + 96)          # lowercase set: $01.. = a..z
                elif 0x41 <= c <= 0x5a:
                    s += chr(c)               # uppercase glyphs
                elif 0x20 <= c <= 0x3f:
                    s += chr(c)
                else:
                    s += "."
            rows.append(s.rstrip())
        return rows

    def poke(self, addr, data):
        self.cmd("> %04x %s" % (addr, " ".join("%02x" % b for b in data)))

    def peek(self, addr, n):
        txt = self.cmd("m %04x %04x" % (addr, addr + n - 1))
        out = []
        for line in txt.splitlines():
            m = re.search(r">.:([0-9a-fA-F]{4})\s+(.*)$", line)
            if m:
                hexpart = re.split(r"\s{3,}", m.group(2))[0]
                out += [int(t, 16) for t in re.findall(r"\b[0-9a-fA-F]{2}\b", hexpart)[:16]]
        return bytes(out[:n])

    def keys(self, data):
        self.poke(KB_BUF, data + b"\x00" * (10 - len(data)))
        self.poke(KB_CNT, bytes([len(data)]))

    def launch(self, name):
        """One-shot tick-vector trampoline that launches an app the way the
        desktop menu does: r0 -> name, FILLFILE ($0829), restore the desktop
        tick, jmp LAUNCH_APP ($0832: clears the screen, loads, enters)."""
        vec = self.peek(TICK_VEC, 2)
        straddr = TRAMP + 24
        tramp = (bytes([0xA9, straddr & 0xff, 0x85, 0x02, 0xA9, straddr >> 8, 0x85, 0x03])
                 + bytes([0x20, 0x29, 0x08])
                 + bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
                 + bytes([0x4C, 0x32, 0x08]) + name + b"\x00")
        assert len(tramp) == 24 + len(name) + 1
        self.poke(TRAMP, tramp)
        self.poke(TICK_VEC, bytes([TRAMP & 0xff, TRAMP >> 8]))

    def tramp(self, code):
        """One-shot: restore the desktop tick vector, run `code`, then
        continue into the desktop tick handler."""
        vec = self.peek(TICK_VEC, 2)
        t = (bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
             + code + bytes([0x6C, 0x3C, 0x03]))
        self.poke(TRAMP, t)
        self.poke(TICK_VEC, bytes([TRAMP & 0xff, TRAMP >> 8]))


def wait_rows(mon, pred, what, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        rows = mon.vdc_rows()
        if pred(rows):
            return rows
        time.sleep(3)
    print("---- last VDC rows ----")
    for i, r in enumerate(rows):
        if r:
            print(f"{i:2d}: {r}")
    raise SystemExit(f"FAIL: {what} not seen within {timeout}s")


def show(rows, tag):
    print(f"---- VDC rows ({tag}) ----")
    for i, r in enumerate(rows):
        if r:
            print(f"{i:2d}: {r}")


def check_driver_layout():
    """routines.inc publishes uos-net's jump table and data bytes as fixed
    addresses (the module cannot include routines.inc: duplicate labels);
    prove the assembled module matches, byte for byte, before booting."""
    sys.path.insert(0, UOS)
    import hwlib
    inc = open(os.path.join(UOS, "src/routines.inc")).read()
    base = int(re.search(r"^NET_BASE\s*=\s*\$([0-9a-f]{4})", inc, re.M).group(1), 16)
    want = {m.group(1): base + int(m.group(2), 16)
            for m in re.finditer(r"^(NET_[A-Z]+)\s*=\s*NET_BASE\+\$([0-9a-f]{2})", inc, re.M)}
    prg = open(os.path.join(UOS, "target/uos-net.prg"), "rb").read()
    assert prg[0] | prg[1] << 8 == base, "uos-net load address != NET_BASE"
    img = prg[2:]
    slots = 0
    for name, addr in want.items():
        if addr - base <= 0x1e:
            assert img[addr - base] == 0x4c, f"{name}: no jmp at ${addr:04x}"
            slots += 1
        else:
            got = hwlib.lst_symbol("uos-net", name)
            assert got == addr, f"{name}: routines.inc ${addr:04x} != module ${got:04x}"
    end = base + len(img)
    assert end <= 0x9b00, f"uos-net overruns APP_ID_TBL: ends at ${end:04x}"
    drv = open(os.path.join(UOS, "target/uos-drv1351.prg"), "rb").read()
    assert drv[0] | drv[1] << 8 == 0x9e00 and drv[2 + 9] == 0x4c, "KEYIN_EXT slot"
    assert hwlib.lst_symbol("uos-drv1351", "extseen") == 0x9e0c, "KEY_EXTSEEN"
    print(f"PASS 0: uos-net layout matches routines.inc ({slots} jump slots, "
          f"{len(want) - slots} data labels, ends ${end:04x}); KEYIN_EXT at $9e09")


def main():
    check_driver_layout()
    xvfb, disp = start_xvfb()
    port = free_port()
    emu = subprocess.Popen(
        ["x128", "-default", "-go64", "-VDC64KB", "-reu", "-reusize", "512", "-autostart", DISK,
         "-drive8true", "-drive8type", "1541", "-sounddev", "dummy",
         "-jamaction", "0", "-warp", "-remotemonitor",
         "-remotemonitoraddress", f"ip4://127.0.0.1:{port}"],
        env=dict(os.environ, DISPLAY=disp, **EGL),
        stdout=open(os.path.join(OUT, "ci_vdc_vice.log"), "w"), stderr=subprocess.STDOUT)
    mon = Mon(port, emu)
    passed = 0
    try:
        time.sleep(20)
        rows = wait_rows(mon, lambda r: r[2].startswith("desktop") and "UltOS" in r[0],
                         "boot header + desktop row")
        show(rows, "boot")
        assert "companion display" in rows[0], rows[0]
        assert "ultos menu" in rows[1], rows[1]
        ctr = mon.peek(0x9000, 1)[0]
        assert ctr == 2, f"APP_CTL_CTR after boot = {ctr} (want 2: menu bar + computer icon); it used to be RAM garbage"
        print("PASS A: header rows 0-1 + row 2 'desktop' on the 80-col display; control table = 2 base buttons")
        passed += 1

        mon.launch(b"UOS-FMGR")
        rows = wait_rows(mon, lambda r: r[2].startswith("File manager") and r[4].startswith("  >"),
                         "file manager rows")
        show(rows, "fmgr")
        assert "device 8" in rows[2], rows[2]
        assert rows[23].startswith("D=del"), rows[23]
        names = [r[4:].strip() for r in rows[4:14] if r.strip()]
        assert len(names) >= 5, names
        assert any("uos" in n.lower() for n in names), names
        print(f"PASS B: file manager mirrored ({len(names)} entries, marker on row 0, hint row)")
        passed += 1

        mon.keys(b"\x1b")
        rows = wait_rows(mon, lambda r: r[2].startswith("desktop") and not any(r[4:14]),
                         "desktop after ESC with blank listing rows")
        print("PASS C: ESC back to the desktop blanked the listing rows")
        passed += 1

        mon.launch(b"UOS-SHELL")
        rows = wait_rows(mon, lambda r: r[2].startswith("Command shell") and r[5].startswith(">"),
                         "shell rows")
        show(rows, "shell")
        assert "UltOS 0.3" in rows[2], rows[2]
        mon.keys(b"VER\x0d")
        rows = wait_rows(mon, lambda r: "UltOS 0.3" in r[7], "VER response on row 7", timeout=60)
        show(rows, "after VER")
        mon.keys(b"EXIT\x0d")
        rows = wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop after EXIT")
        print("PASS D: shell mirrored (header, VER response row 7, EXIT back to desktop)")
        passed += 1
        time.sleep(4)   # let the desktop finish re-entering before the next launch

        # E: settings mirrors its two values; C cycles the colour; ESC returns
        mon.launch(b"UOS-SETTINGS")
        rows = wait_rows(mon, lambda r: r[2].startswith("Settings")
                         and r[4].startswith("  display:") and r[5].startswith("  background:"),
                         "settings rows")
        show(rows, "settings")
        col0 = rows[5][14:].strip()
        assert col0, rows[5]
        assert rows[4][14:].strip(), rows[4]
        mon.keys(b"C")
        rows = wait_rows(mon, lambda r: r[5][14:].strip() not in ("", col0),
                         "colour name change after C", timeout=60)
        col1 = rows[5][14:].strip()
        show(rows, "after C")
        mon.keys(b"\x1b")
        wait_rows(mon, lambda r: r[2].startswith("desktop") and not any(r[4:6]),
                  "desktop after settings ESC")
        print(f"PASS E: settings mirrored (mode + colour rows; C: {col0!r} -> {col1!r}; ESC)")
        passed += 1

        # F: the Applications launcher (desktop menu) lists apps on rows 4..
        sys.path.insert(0, UOS)
        import hwlib
        menu_apps = hwlib.lst_symbol("uos-desktop", "MENU_APPS")
        vec = mon.peek(TICK_VEC, 2)
        tramp = (bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
                 + bytes([0x4C, menu_apps & 0xff, menu_apps >> 8]))
        mon.poke(TRAMP, tramp)
        mon.poke(TICK_VEC, bytes([TRAMP & 0xff, TRAMP >> 8]))
        rows = wait_rows(mon, lambda r: r[2].startswith("Applications") and r[4].strip(),
                         "launcher rows")
        show(rows, "launcher")
        apps = [r.strip() for r in rows[4:10] if r.strip()]
        assert any("settings" in a for a in apps) and any("shell" in a for a in apps), apps
        # the launcher's CreateWindow stash/fetch used to DMA over the
        # graphics engine at $c000 (bad last-row math); prove the module is
        # byte-intact after the window opened
        gfx_ref = open(os.path.join(UOS, "target/uos-gfx.prg"), "rb").read()[2:]
        gfx_mem = b"".join(mon.peek(0xc000 + i, min(0x100, len(gfx_ref) - i))
                           for i in range(0, len(gfx_ref), 0x100))
        bad = [i for i, (a, b) in enumerate(zip(gfx_ref, gfx_mem)) if a != b]
        # the engine self-modifies a few counters (COUNTHI at $c29b etc.);
        # corruption looks different: the jump table at $c000 zeroed, hundreds of bytes
        assert not any(i < 0x80 for i in bad) and len(bad) < 64, \
            f"FAIL: gfx module corrupted after launcher: {len(bad)} bytes from ${0xc000 + bad[0]:04x}"
        print(f"PASS F: launcher mirrored ({len(apps)} apps: {apps}); gfx module intact")
        passed += 1
        sym = lambda n: hwlib.lst_symbol("uos-desktop", n)
        mon.tramp(bytes([0x4C, sym("APPS_CANCEL") & 0xff, sym("APPS_CANCEL") >> 8]))
        time.sleep(4)
        def live_slots():
            tbl = mon.peek(0x9001, 250)
            return [(tbl[i], tbl[i + 1]) for i in range(0, 250, 10) if tbl[i] != 0xff]
        ctr, live = mon.peek(0x9000, 1)[0], live_slots()
        assert ctr == 2 and sorted(live) == [(0, 0), (0, 1)], \
            f"after Cancel: CTR={ctr} live={live} (want only the 2 base buttons: the window's close box, rows and Cancel must be freed)"
        print(f"PASS F2: closing the Applications window freed its controls (live slots {live})")
        passed += 1

        # G: the clock mirror. x128 has no command interface at $df1c, so
        # the boot sync must report "no ultimate" and the desktop shows the
        # CIA default 12:00 PM on row 0 col 58 (forced redraw at DESK_START)
        NET = {k: int(v, 16) for k, v in re.findall(r"^(NET_[A-Z]+)\s*=\s*NET_BASE\+\$([0-9a-f]{2})",
                                                    open(os.path.join(UOS, "src/routines.inc")).read(), re.M)}
        NET = {k: 0x9100 + v for k, v in NET.items()}
        NET_DATA = 0x8800
        # (-warp runs the CIA TOD ~10x real time: only the shape is checked)
        rows = wait_rows(mon, lambda r: "no ultimate" in r[0][58:]
                         and re.match(r"\d\d:\d\d [AP]M  no ultimate", r[0][58:]),
                         "clock mirror on row 0", timeout=90)
        show(rows[:1], "clock")
        assert rows[0].startswith("UltOS"), rows[0]
        st = mon.peek(NET['NET_STATE'], 1)[0]
        assert st == 3, f"NET_STATE={st} (want 3 = no ultimate)"
        print(f"PASS G: boot clock sync reported honestly (NET_STATE=3), row 0: {rows[0][58:]!r}")
        passed += 1

        # H: the SNTP conversion, fed a canned reply. 2026-09-06 17:45:30 UTC
        # with the zone -16 quarter-hours (UTC-4) must become 13:45:30 local,
        # Sunday 2026/09/06, land in the CIA TOD as 01:45 PM, and be mirrored
        import calendar
        import datetime
        utc = calendar.timegm((2026, 9, 6, 17, 45, 30, 0, 0, 0))
        pkt = bytes(40) + (utc + 2208988800).to_bytes(4, "big") + bytes(4)
        mon.poke(NET_DATA + 2, pkt[:24])
        mon.poke(NET_DATA + 2 + 24, pkt[24:])
        mon.poke(0x7352, bytes([0x02, 0xf0, 0xa5]))       # record format 2, UTC-4
        mon.poke(NET['NET_STATE'], b"\x00")
        minute = sym("minute")
        mon.tramp(bytes([0x20, NET['NET_APPLYNTP'] & 0xff, NET['NET_APPLYNTP'] >> 8,
                         0xA9, 0xFF, 0x8D, minute & 0xff, minute >> 8]))
        rows = wait_rows(mon, lambda r: re.match(r"01:4\d PM  ntp", r[0][58:]),
                         "synced clock on row 0", timeout=60)
        show(rows[:1], "after NTP apply")
        got = mon.peek(NET['NET_HOUR'], 9)     # hour min sec yearL yearH mon day wday tz
        year = got[3] | got[4] << 8
        wday = (datetime.date(2026, 9, 6).weekday() + 1) % 7
        assert (got[0], got[1], got[2]) == (13, 45, 30), f"time {got[:3]}"
        assert (year, got[5], got[6], got[7]) == (2026, 9, 6, wday), f"date {year}/{got[5]}/{got[6]} wd{got[7]}"
        assert got[8] == 0xf0, f"NET_TZ={got[8]:#x}"
        tod = mon.peek(0xdc0b, 1)[0]; mon.peek(0xdc08, 1)
        todm = mon.peek(0xdc0a, 1)[0]; mon.peek(0xdc08, 1)
        assert tod == 0x81 and 0x45 <= todm <= 0x49, f"CIA TOD hours/min {tod:#x} {todm:#x} (want $81 $45..)"
        print(f"PASS H: NTP reply -> 13:45:30 Sun 2026/09/06 local, CIA TOD $81:$45, row 0: {rows[0][58:]!r}")
        passed += 1

        # I: a zone change shifts the running clock by whole hours (+4 quarters)
        mon.tramp(bytes([0xA9, 0x04, 0x20, NET['NET_TZSHIFT'] & 0xff, NET['NET_TZSHIFT'] >> 8,
                         0xA9, 0xFF, 0x8D, minute & 0xff, minute >> 8]))
        rows = wait_rows(mon, lambda r: re.match(r"02:\d\d PM  ntp", r[0][58:]), "shifted clock on row 0", timeout=60)
        got = mon.peek(NET['NET_HOUR'], 2)
        tz = mon.peek(NET['NET_TZ'], 1)[0]
        assert got[0] == 14 and tz == 0xf4, f"after shift: {got} tz={tz:#x}"
        print(f"PASS I: NET_TZSHIFT +1 h -> 14:{got[1]:02d}, NET_TZ -12, row 0: {rows[0][58:]!r}")
        passed += 1

        # J: the C128 ESC key. The KERNAL never sees it in C64 mode; KEYIN_EXT
        # scans the VIC-IIe extended column. Press the real key through XTest
        # with the file manager open: it must exit, and the sticky flag at
        # $9e0c must prove the ESC matrix line (not the RUN/STOP alias) fired.
        # (the Applications window from F may still be up; its VDC row 2
        # stays "Applications" until a full desktop re-entry, but the tick
        # vector is live, so LAUNCH_APP works regardless of the screen)
        mon.launch(b"UOS-FMGR")
        # its hint row (row 23) proves the fmgr is up and past its scan; the
        # ">" marker column drifts on re-entry, so it is not required here
        wait_rows(mon, lambda r: r[2].startswith("File manager") and r[23].startswith("D=del"),
                  "file manager before ESC")
        time.sleep(2)
        mon.poke(0x9e0c, b"\x00")
        sys.path.insert(0, os.path.dirname(UOS))
        import xtst
        xk = xtst.X(disp)
        xk.pointer_to(700, 300)          # inside the VIC window (Xvfb focus follows the pointer)
        xk.focus_window_named("C128")
        time.sleep(0.5)
        # F9 = the C128 ESC key in VICE's gtk3_sym.vkm (its "Escape" is RUN/STOP).
        # Retry: one synthetic tap can miss the ~1 s KEYIN poll window.
        left = False
        for _ in range(6):
            xk.key("F9", True); time.sleep(0.25); xk.key("F9", False)
            for _ in range(5):
                time.sleep(1)
                if mon.vdc_rows()[2].startswith("desktop"):
                    left = True
                    break
            if left:
                break
        seen = mon.peek(0x9e0c, 1)[0]
        assert left, f"file manager did not leave on the C128 ESC key (KEY_EXTSEEN={seen})"
        assert seen == 1, f"file manager left, but KEY_EXTSEEN={seen}: ESC came from the alias, not the C128 key line"
        print("PASS J: the C128 ESC key (VIC-IIe extended matrix) leaves the file manager; matrix line seen")
        passed += 1
        time.sleep(3)

        # K: settings shows and edits the zone; +/- move it an hour and shift the clock
        mon.launch(b"UOS-SETTINGS")
        rows = wait_rows(mon, lambda r: r[2].startswith("Settings") and r[6].startswith("  time zone:"),
                         "settings zone row")
        show(rows, "settings zone")
        # the saved record still holds the default UTC-4 (check I's
        # NET_TZSHIFT moved the running clock only, not SETREC_TZ)
        assert rows[6][14:].strip() == "utc-04:00", rows[6]
        assert "+/-=zone" in rows[23], rows[23]
        def tod_hour():
            h = mon.peek(0xdc0b, 1)[0]; mon.peek(0xdc08, 1)
            return (h & 0x0f) + 10 * ((h >> 4) & 1) + (12 if h & 0x80 else 0) - (12 if (h & 0x1f) == 0x12 else 0)
        h0 = tod_hour()
        mon.keys(b"+")
        rows = wait_rows(mon, lambda r: r[6][14:].strip() == "utc-03:00", "zone +1 h", timeout=60)
        tz = mon.peek(0x7353, 1)[0]
        hour = mon.peek(NET['NET_HOUR'], 1)[0]
        assert tz == 0xf4 and hour in ((h0 + 1) % 24, (h0 + 2) % 24), f"after +: SETREC_TZ={tz:#x} NET_HOUR={hour} (TOD was {h0})"
        mon.keys(b"-")
        rows = wait_rows(mon, lambda r: r[6][14:].strip() == "utc-04:00", "zone -1 h", timeout=60)
        hour2 = mon.peek(NET['NET_HOUR'], 1)[0]
        assert hour2 in ((hour - 1) % 24, hour % 24), f"after -: NET_HOUR={hour2} (was {hour})"
        mon.keys(b"\x1b")
        wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop after settings")
        print(f"PASS K: settings zone utc-04:00 -> + -> utc-03:00 (clock {hour}h) -> - -> utc-04:00 ({hour2}h); SETREC_TZ persisted")
        passed += 1
        time.sleep(3)

        # L: the Computer window lists the address and the clock source.
        # Re-fire the one-shot tramp until the window shows: a DESK_START
        # re-entry (from K's settings ESC) can re-register APP_TICK over it.
        oc = sym("ON_CLICK_COMPUTER")
        rows = None
        for _ in range(8):
            mon.tramp(bytes([0x4C, oc & 0xff, oc >> 8]))
            for _ in range(5):
                time.sleep(2)
                r = mon.vdc_rows()
                if r[2].startswith("Computer") and r[7].strip().startswith("clock:"):
                    rows = r
                    break
            if rows:
                break
        assert rows, "FAIL: computer window rows never appeared"
        show(rows[:8], "computer")
        assert rows[6].strip() == "ip: none", rows[6]
        assert rows[7].strip() == "clock: ntp", rows[7]
        cl = sym("ON_CLOSE")
        mon.tramp(bytes([0x4C, cl & 0xff, cl >> 8]))
        time.sleep(3)
        ctr, live = mon.peek(0x9000, 1)[0], live_slots()
        assert ctr == 2 and sorted(live) == [(0, 0), (0, 1)], \
            f"after the title-bar close: CTR={ctr} live={live} (the close box (1,0) must be freed)"
        r2 = mon.vdc_rows()[2]
        assert r2.startswith("desktop"), f"80-col row 2 after close: {r2!r}"
        print(f"PASS L: Computer window rows: {rows[6].strip()!r} / {rows[7].strip()!r}; close freed its controls, row 2 back to 'desktop'")
        passed += 1

        subprocess.run(["magick", "import", "-display", disp, "-window", "root",
                        os.path.join(OUT, "ci_vdc_final.png")], capture_output=True)
        print(f"CI-VDC PASS: {passed}/13 companion-display checks")
    finally:
        emu.terminate()
        xvfb.terminate()


main()
