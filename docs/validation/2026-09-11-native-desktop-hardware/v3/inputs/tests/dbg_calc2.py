#!/usr/bin/env python3
"""Debug: rapid state sampling after the first calculator key."""
import os
import struct
import subprocess
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
    global emu
    os.makedirs(WORK, exist_ok=True)
    DISK = os.path.join(WORK, "dbg_calc2.d64")
    shutil.copyfile(STOCK, DISK)
    DISBUF = lst_symbol("uos-calc", "dispbuf")
    Z = {n: zp_symbol("uos-calc", "c_" + n) for n in
         ("acc", "ent", "elen", "pen", "fresh", "err", "tmp", "tmp2", "divs", "rem")}

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
        launch(mon, b"UOS-CALC")
        dl = time.time() + 60
        while time.time() < dl:
            b = bytes(mon.read_mem(APP_START, APP_START + 15, memspace=0)); mon.resume()
            if bytes(b) == open(os.path.join(UOS, "target/uos-calc.prg"), "rb").read()[2:18]:
                break
            time.sleep(2)
        time.sleep(4)

        inject_keys(mon, b"5")
        for i in range(24):
            z = bytes(mon.read_mem(Z["acc"], Z["acc"] + 15, memspace=0)); mon.resume()
            d = bytes(mon.read_mem(DISBUF, DISBUF + 7, memspace=0)); mon.resume()
            sp = bytes(mon.read_mem(0x01, 0x01, memspace=0))[0]; mon.resume()
            acc, ent = struct.unpack("<H", z[0:2])[0], struct.unpack("<H", z[2:4])[0]
            elen, pen, fresh, err = z[4], z[5], z[6], z[7]
            tmp, divs, rem = struct.unpack("<H", z[8:10])[0], struct.unpack("<H", z[11:13])[0], struct.unpack("<H", z[13:15])[0]
            print(f"{i:2d} acc={acc:5d} ent={ent:5d} elen={elen} pen={pen} fresh={fresh} "
                  f"err={err} tmp={tmp:5d} divs={divs:5d} rem={rem:5d} t2={z[10]:3d} "
                  f"sp=${sp:02x} disp={d.split(b'\x00')[0]!r}", flush=True)
            time.sleep(0.15)
    finally:
        emu.terminate()
        xv.stop()


main()