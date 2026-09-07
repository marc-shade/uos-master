#!/usr/bin/env python3
"""CI for the calculator (uos-calc), x64 headless.

Drives the calculator through the real input path (kernal keyboard buffer)
and gates on the app's own display buffer + accumulator.

  0 boot + launch -> display shows "0"
  1 12+34=        -> "46"
  2 100/7=        -> "14"      (integer division)
  3 65535-1=      -> "65534"   (no wrap at the edge)
  4 300*300=      -> "OVF" and the low-16 product (90000-65536=24464)
  5 5/0=          -> "DIV/0"; C recovers
  6 9 DEL         -> entry backspaced (display returns to the accumulator)
  7 ESC           -> back to a live desktop
"""
import os
import re
import struct
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


def wait_bytes(mon, addr, ref, timeout=120):
    dl = time.time() + timeout
    while time.time() < dl:
        got = bytes(mon.read_mem(addr, addr + len(ref) - 1, memspace=0)); mon.resume()
        if got == ref:
            return True
        time.sleep(3)
    return False


def zp_symbol(module, name):
    """Zero-page EQU (c_acc = $40 form) from a 64tass listing."""
    lst = open(os.path.join(UOS, f"target/{module}.lst"), "rb").read().decode(
        "latin-1", errors="replace")
    m = re.search(r"^=\$?([0-9a-fA-F]{2,4})\s+[^\n]*\b%s\s*=" % re.escape(name), lst, re.M)
    if not m:
        raise SystemExit(f"FAIL: {name} EQU not found in {module} listing")
    return int(m.group(1), 16)


def disp(mon):
    b = bytes(mon.read_mem(DISBUF, DISBUF + 7, memspace=0)); mon.resume()
    return b.split(b"\x00")[0]


def calc(mon, keys, want, note):
    global passed
    inject_keys(mon, keys)
    ok = False
    dl = time.time() + 30
    while time.time() < dl:
        if disp(mon) == want:
            ok = True
            break
        time.sleep(2)
    assert ok, f"FAIL {note}: display={disp(mon)!r} want={want!r}"
    print(f"PASS {note}: display={want!r}", flush=True)
    passed += 1


def main():
    global emu, DISBUF, passed
    os.makedirs(WORK, exist_ok=True)
    calc_ref = load_ref(os.path.join(UOS, "target/uos-calc.prg"))
    desk_ref = load_ref(os.path.join(UOS, "target/uos-desktop.prg"))
    DISK = os.path.join(WORK, "ci_calc.d64")
    shutil.copyfile(STOCK, DISK)
    DISBUF = lst_symbol("uos-calc", "dispbuf")
    C_ACC = zp_symbol("uos-calc", "c_acc")
    C_ERR = zp_symbol("uos-calc", "c_err")

    xv = cbm.Xvfb()
    env = dict(os.environ, DISPLAY=xv.display, __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
    emu = subprocess.Popen(
        ["x64", "-default", "-autostart", DISK, "-drive8true", "-drive8type", "1541",
         "-sounddev", "dummy", "-jamaction", "0", "-warp", "-autostart-warp",
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
        assert wait_desktop_live(mon, 300), "desktop never live"
        print("PASS 0a: booted to a live desktop", flush=True)
        passed += 1

        launch(mon, b"UOS-CALC")
        assert wait_bytes(mon, APP_START, calc_ref[:16]), "calculator never loaded"
        print("PASS 0b: calculator launched", flush=True)
        passed += 1

        time.sleep(3)   # initial c_clear draws "0"
        assert disp(mon) == b"0", f"FAIL: initial display {disp(mon)!r}"
        print("PASS 0c: display starts at 0", flush=True)
        passed += 1

        calc(mon, b"12+34=", b"46", "1 add")
        calc(mon, b"100/7=", b"14", "2 int-div")
        calc(mon, b"65535-1=", b"65534", "3 edge-sub")

        # 4: overflow -> OVF on the display, low 16 bits in the accumulator
        inject_keys(mon, b"300*300=")
        ok = False
        dl = time.time() + 30
        while time.time() < dl:
            if disp(mon) == b"OVF":
                ok = True
                break
            time.sleep(2)
        assert ok, f"FAIL 4 overflow: display={disp(mon)!r}"
        acc = struct.unpack("<H", bytes(mon.read_mem(C_ACC, C_ACC + 1, memspace=0)))[0]
        mon.resume()
        assert acc == 90000 - 65536, f"FAIL 4: low-16 product {acc}"
        print("PASS 4 overflow: OVF shown, low 16 = 24464", flush=True)
        passed += 1

        # 5: division by zero -> DIV/0, then C recovers
        inject_keys(mon, b"C5/0=")
        ok = False
        dl = time.time() + 30
        while time.time() < dl:
            if disp(mon) == b"DIV/0":
                ok = True
                break
            time.sleep(2)
        assert ok, f"FAIL 5 div0: display={disp(mon)!r}"
        err = bytes(mon.read_mem(C_ERR, C_ERR, memspace=0))[0]; mon.resume()
        assert err == 1, f"FAIL 5: err flag {err}"
        inject_keys(mon, b"C")
        ok = False
        dl = time.time() + 30
        while time.time() < dl:
            if disp(mon) == b"0":
                ok = True
                break
            time.sleep(2)
        assert ok, f"FAIL 5 C-clear: display={disp(mon)!r}"
        print("PASS 5 div0: DIV/0 shown, C recovers", flush=True)
        passed += 1

        # 6: DEL backspaces the entry (99 -> 9)
        inject_keys(mon, b"99")
        time.sleep(3)
        inject_keys(mon, b"\x14")
        ok = False
        dl = time.time() + 30
        while time.time() < dl:
            if disp(mon) == b"9":
                ok = True
                break
            time.sleep(2)
        assert ok, f"FAIL 6 backspace: display={disp(mon)!r}"
        print("PASS 6 backspace: 99 -> 9", flush=True)
        passed += 1

        # 7: ESC -> desktop
        inject_keys(mon, b"\x1b")
        assert wait_bytes(mon, DESK_START, desk_ref[:16], timeout=120), "no desktop after ESC"
        assert wait_desktop_live(mon), "desktop tick not live after calculator ESC"
        print("PASS 7: ESC returned to a live desktop", flush=True)
        passed += 1

        print(f"CI-CALC PASS: {passed}/10 calculator checks", flush=True)
    finally:
        emu.terminate()
        xv.stop()


main()