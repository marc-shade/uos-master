#!/usr/bin/env python3
"""Debug: drive the fmgr COPY on x64 (warp, one drive) and read the status
line + memory to see which copy path runs and what it reports."""
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


def main():
    global emu, LBUF, FMCNT
    os.makedirs(WORK, exist_ok=True)
    fm_ref = load_ref(os.path.join(UOS, "target/uos-fmgr.prg"))
    DISK = os.path.join(WORK, "dbg.d64")
    shutil.copyfile(STOCK, DISK)
    LBUF = lst_symbol("uos-fmgr", "linebuf")
    FMCNT = int(open(os.path.join(UOS, "target/uos-fmgr.lst")).read()
                and "0")  # placeholder, unused

    xv = cbm.Xvfb()
    env = dict(os.environ, DISPLAY=xv.display, __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
    emu = subprocess.Popen(
        ["x64", "-default", "-autostart", DISK, "-drive8true", "-drive8type", "1541",
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
        assert wait_desktop_live(mon, 300), "desktop never live"
        launch(mon, b"UOS-FMGR")
        dl = time.time() + 60
        while time.time() < dl:
            b = bytes(mon.read_mem(APP_START, APP_START + 15, memspace=0)); mon.resume()
            if bytes(b) == open(os.path.join(UOS, "target/uos-fmgr.prg"), "rb").read()[2:18]:
                break
            time.sleep(2)
        time.sleep(6)

        def line():
            b = bytes(mon.read_mem(LBUF, LBUF + 38, memspace=0)); mon.resume()
            return b.split(b"\x00")[0]

        print("initial line:", line())
        inject_keys(mon, b"C")
        time.sleep(4)
        print("after C:", line())
        inject_keys(mon, b"CI-CPY\r")
        time.sleep(10)
        print("after RETURN:", line())
        # which path did it take? scratch a marker: list dir
        out = subprocess.run(["c1541", "-attach", DISK, "-list"],
                             capture_output=True).stdout.decode(errors="replace")
        print("dir:", out)
    finally:
        emu.terminate()
        xv.stop()


main()