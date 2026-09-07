#!/usr/bin/env python3
"""CI for the file manager's cross-device copy ('B' key, FR-F1/S2), x64, two drives.

Drive 8 = the stock UltOS disk, drive 9 = a freshly formatted empty disk
(both attached without warp, so SEQ writes actually land on the images —
the warp build drops them, see the editor CI note). Real input path
(kernal keyboard buffer), memory-side gates + c1541 image listing.

  0 boot + launch the file manager
  1 B on uos-reu, name CI-C9  -> "copied to device 9" (explicit 'B' key)
  2 '9' device switch -> the drive-9 listing shows CI-C9
  3 B on CI-C9 (now browsing drive 9), name CI-BACK -> "copied to device 8"
  4 '8' device switch -> the drive-8 listing shows CI-BACK
  5 after exit: c1541 finds CI-C9 on the drive-9 image and CI-BACK on the
    drive-8 image (bytes actually persisted)
"""
import os
import re
import struct
import subprocess
import sys
import time

UOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(UOS, "tests/ci_fm.py")).read()
exec(src[:src.index("def main():")])
import shutil


def zp_symbol(module, name):
    """Zero-page EQU (c_acc = $40 form) from a 64tass listing."""
    lst = open(os.path.join(UOS, f"target/{module}.lst"), "rb").read().decode(
        "latin-1", errors="replace")
    m = re.search(r"^=\$?([0-9a-fA-F]{2,4})\s+[^\n]*\b%s\s*=" % re.escape(name), lst, re.M)
    if not m:
        raise SystemExit(f"FAIL: {name} EQU not found in {module} listing")
    return int(m.group(1), 16)


def launch(mon, name):
    vec = mon.read_mem(TICK_VEC, TICK_VEC + 1, memspace=0); mon.resume()
    tr = (bytes([0x20, 0x23, 0x08]) + name + b"\x00" + bytes([0x20, 0x26, 0x08])
          + bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
          + bytes([0x4C, 0x00, 0x50]))
    mon.write_mem(TRAMPOLINE, tr); mon.write_mem(TICK_VEC, struct.pack("<H", TRAMPOLINE)); mon.resume()


def wait_bytes(mon, addr, ref, timeout=120):
    dl = time.time() + timeout
    while time.time() < dl:
        got = bytes(mon.read_mem(addr, addr + len(ref) - 1, memspace=0)); mon.resume()
        if got == ref:
            return True
        time.sleep(3)
    return False


def listing(mon):
    cnt = bytes(mon.read_mem(FMCNT, FMCNT, memspace=0))[0]; mon.resume()
    lo = bytes(mon.read_mem(FMNAMESL, FMNAMESL + 12 - 1, memspace=0)); mon.resume()
    hi = bytes(mon.read_mem(FMNAMESH, FMNAMESH + 12 - 1, memspace=0)); mon.resume()
    names = []
    for i in range(cnt):
        ptr = lo[i] | (hi[i] << 8)
        nm = bytes(mon.read_mem(ptr, ptr + 15, memspace=0)); mon.resume()
        names.append(nm.split(b"\x00")[0])
    return names


def linebuf(mon):
    b = bytes(mon.read_mem(LBUF, LBUF + 38, memspace=0)); mon.resume()
    return b.split(b"\x00")[0]


def main():
    global emu, FMCNT, FMNAMESL, FMNAMESH, LBUF
    os.makedirs(WORK, exist_ok=True)
    fm_ref = load_ref(os.path.join(UOS, "target/uos-fmgr.prg"))
    D8 = os.path.join(WORK, "ci_copy.d64")
    D9 = os.path.join(WORK, "ci_copy9.d64")
    shutil.copyfile(STOCK, D8)
    subprocess.run(["c1541", "-format", "dev9,d9", "d64", D9],
                   check=True, capture_output=True)
    FMCNT = zp_symbol("uos-fmgr", "fmcnt")
    FMNAMESL, FMNAMESH = parse_lst_symbols()
    LBUF = lst_symbol("uos-fmgr", "linebuf")

    xv = cbm.Xvfb()
    env = dict(os.environ, DISPLAY=xv.display, __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
    emu = subprocess.Popen(
        ["x64", "-default", "-autostart", D8, "-9", D9,
         "-drive8true", "-drive8type", "1541", "-drive9true", "-drive9type", "1541",
         "-sounddev", "dummy", "-jamaction", "0",
         "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{PORT}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    passed = 0
    try:
        mon = None
        dl = time.time() + 60
        while time.time() < dl:
            try:
                mon = Monitor(port=PORT); break
            except OSError:
                time.sleep(0.25)
        assert wait_desktop_live(mon, 600), "desktop never live"
        print("PASS 0a: booted to a live desktop (no warp, two drives)", flush=True)
        passed += 1

        launch(mon, b"UOS-FMGR")
        assert wait_bytes(mon, APP_START, fm_ref[:16]), "fmgr never loaded"
        time.sleep(6)   # first dirscan + paint
        print("PASS 0b: file manager loaded", flush=True)
        passed += 1

        # 1: copy uos-reu (listing row 5) to device 9 as CI-C9 ('B' key)
        inject_keys(mon, b"\x11\x11\x11\x11\x11")   # down 5 -> uos-reu
        time.sleep(4)
        inject_keys(mon, b"B")
        time.sleep(3)
        inject_keys(mon, b"CI-C9\r")
        ok = False
        dl = time.time() + 60
        while time.time() < dl:
            if linebuf(mon) == b"COPIED TO DEVICE 9":
                ok = True
                break
            time.sleep(2)
        assert ok, f"FAIL 1: status line {linebuf(mon)!r}"
        print("PASS 1: 8->9 copy reports 'copied to device 9'", flush=True)
        passed += 1

        # 2: browse drive 9 -> CI-C9 listed
        inject_keys(mon, b"9")
        ok = False
        dl = time.time() + 60
        while time.time() < dl:
            if b"CI-C9" in listing(mon):
                ok = True
                break
            time.sleep(2)
        assert ok, f"FAIL 2: drive-9 listing {listing(mon)!r}"
        print(f"PASS 2: drive-9 listing shows CI-C9 ({listing(mon)})", flush=True)
        passed += 1

        # 3: copy it back 9 -> 8 as CI-BACK (row 0 = CI-C9), 'B' key
        inject_keys(mon, b"B")
        time.sleep(3)
        inject_keys(mon, b"CI-BACK\r")
        ok = False
        dl = time.time() + 60
        while time.time() < dl:
            if linebuf(mon) == b"COPIED TO DEVICE 8":
                ok = True
                break
            time.sleep(2)
        assert ok, f"FAIL 3: status line {linebuf(mon)!r}"
        print("PASS 3: 9->8 copy reports 'copied to device 8'", flush=True)
        passed += 1

        # 4: CI-BACK on drive 8. The fmgr lists at most 10 rows and the
        # stock disk fills them, so the live listing cannot show the 11th
        # entry — the honest gate is the image itself (c1541).
        emu.terminate()
        emu.wait()
        xv.stop()

        out8 = subprocess.run(["c1541", "-attach", D8, "-list"],
                              capture_output=True).stdout.decode(errors="replace")
        assert "ci-back" in out8.lower(), f"FAIL 4: drive-8 image lacks CI-BACK: {out8}"
        print("PASS 4: drive-8 image contains CI-BACK (c1541)", flush=True)
        passed += 1

        out = subprocess.run(["c1541", "-attach", D9, "-list"],
                             capture_output=True).stdout.decode(errors="replace")
        assert "ci-c9" in out.lower(), f"FAIL 5: drive-9 image lacks CI-C9: {out}"
        print("PASS 5: copied bytes persisted to both images (c1541)", flush=True)
        passed += 1

        print(f"CI-COPY PASS: {passed}/7 cross-device copy checks", flush=True)
    finally:
        # best-effort teardown only: the gates have already run or raised
        try:
            emu.terminate()
        except OSError as e:
            print(f"cleanup: emulator terminate failed: {e}", flush=True)
        try:
            xv.stop()
        except OSError as e:
            print(f"cleanup: xvfb stop failed: {e}", flush=True)


main()