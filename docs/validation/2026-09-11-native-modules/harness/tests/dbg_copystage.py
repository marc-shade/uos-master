#!/usr/bin/env python3
"""Debug: two-drive fmgr copy with stage latches ($0700-0702) + state dump."""
import os
import struct
import subprocess
import sys
import time

UOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(UOS, "tests/ci_fm.py")).read()
exec(src[:src.index("def main():")])
import shutil


def launch(mon, name):
    vec = mon.read_mem(TICK_VEC, TICK_VEC + 1, memspace=0); mon.resume()
    tr = (bytes([0x20, 0x23, 0x08]) + name + b"\x00" + bytes([0x20, 0x26, 0x08])
          + bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
          + bytes([0x4C, 0x00, 0x50]))
    mon.write_mem(TRAMPOLINE, tr); mon.write_mem(TICK_VEC, struct.pack("<H", TRAMPOLINE)); mon.resume()


def zp_symbol(module, name):
    lst = open(os.path.join(UOS, f"target/{module}.lst"), "rb").read().decode(
        "latin-1", errors="replace")
    m = re.search(r"^=\$?([0-9a-fA-F]{2,4})\s+[^\n]*\b%s\s*=" % re.escape(name), lst, re.M)
    if not m:
        raise SystemExit(f"FAIL: {name} EQU not found in {module} listing")
    return int(m.group(1), 16)


def main():
    global emu, LBUF, FMNAMESL
    os.makedirs(WORK, exist_ok=True)
    fm_prg = open(os.path.join(UOS, "target/uos-fmgr.prg"), "rb").read()[2:]
    D8 = os.path.join(WORK, "dbg8c.d64")
    D9 = os.path.join(WORK, "dbg9c.d64")
    shutil.copyfile(STOCK, D8)
    subprocess.run(["c1541", "-format", "dev9,d9", "d64", D9],
                   check=True, capture_output=True)
    LBUF = lst_symbol("uos-fmgr", "linebuf")
    FMNAMESL = lst_symbol("uos-fmgr", "fmnamesL")
    CDST = zp_symbol("uos-fmgr", "cdst")
    FMCNT_A = zp_symbol("uos-fmgr", "fmcnt")
    STATE_A = zp_symbol("uos-fmgr", "state")
    MODE_A = zp_symbol("uos-fmgr", "mode")

    xv = cbm.Xvfb()
    env = dict(os.environ, DISPLAY=xv.display, __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
    emu = subprocess.Popen(
        ["x64", "-default", "-autostart", D8, "-9", D9,
         "-drive8true", "-drive8type", "1541", "-drive9true", "-drive9type", "1541",
         "-sounddev", "dummy", "-jamaction", "0", "-warp", "-autostart-warp",
         "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{PORT}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    try:
        mon = None
        dl = time.time() + 60
        while time.time() < dl:
            try:
                mon = Monitor(port=PORT); break
            except OSError:
                time.sleep(0.25)
        assert wait_desktop_live(mon, 400), "desktop never live"
        launch(mon, b"UOS-FMGR")
        dl = time.time() + 90
        while time.time() < dl:
            b = bytes(mon.read_mem(APP_START, APP_START + 15, memspace=0)); mon.resume()
            if bytes(b) == fm_prg[:16]:
                break
            time.sleep(2)
        time.sleep(6)

        inject_keys(mon, b"\x11\x11\x11\x11\x11")
        time.sleep(4)
        inject_keys(mon, b"B")
        time.sleep(4)
        inject_keys(mon, b"CI-C9\r")
        time.sleep(15)

        l = bytes(mon.read_mem(LBUF, LBUF + 38, memspace=0)); mon.resume()
        print("linebuf:", l.split(b"\x00")[0])
        print("latches: src_st=$%02x dst_st=$%02x quotes=%d" % (
            bytes(mon.read_mem(0x0700, 0x0700, memspace=0))[0],
            bytes(mon.read_mem(0x0701, 0x0701, memspace=0))[0],
            bytes(mon.read_mem(0x0702, 0x0702, memspace=0))[0]))
        mon.resume()
        print("cdst:", bytes(mon.read_mem(CDST, CDST, memspace=0))[0],
              " state:", bytes(mon.read_mem(STATE_A, STATE_A, memspace=0))[0],
              " mode:", bytes(mon.read_mem(MODE_A, MODE_A, memspace=0))[0])
        mon.resume()
    finally:
        emu.terminate()
        xv.stop()


main()