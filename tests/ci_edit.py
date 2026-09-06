#!/usr/bin/env python3
"""CI for the text editor (uos-edit), x64 headless.

Drives the editor through real paths, within this VICE setup's limit that
SEQ file *data* writes do not persist to the .d64 image (the same gate as
the settings kernal SAVE; the write mechanism itself is proven clean by
probes/seqwrite.asm -> CHKOUT ST=$00). So the load path is checked against
a file pre-placed with c1541, the edit path against the live buffer, and
the save is checked for a clean run (the editor survives and keeps editing);
the saved bytes landing on disk is the hardware gate.

  0 boot
  1 launch uos-edit -> ed_load reads the pre-placed NOTES.T into the buffer
  2 type more text -> it appends to the buffer
  3 F1 save runs cleanly -> the editor is still live and keeps editing
  4 ESC -> back to a live desktop
"""
import os
import struct
import subprocess
import sys
import time

UOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(UOS, "tests/ci_fm.py")).read()
exec(src[:src.index("def main():")])
import shutil

NOTES = b"UOS EDIT TEST\rLINE TWO\r"


def launch(mon, name):
    vec = mon.read_mem(TICK_VEC, TICK_VEC + 1, memspace=0); mon.resume()
    tr = (bytes([0x20, 0x23, 0x08]) + name + b"\x00" + bytes([0x20, 0x26, 0x08])
          + bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
          + bytes([0x4C, 0x00, 0x50]))
    mon.write_mem(TRAMPOLINE, tr); mon.write_mem(TICK_VEC, struct.pack("<H", TRAMPOLINE)); mon.resume()


def wait_bytes(mon, addr, ref, timeout=120):
    dl = time.time() + timeout
    while time.time() < dl:
        got = mon.read_mem(addr, addr + len(ref) - 1, memspace=0); mon.resume()
        if bytes(got) == ref:
            return True
        time.sleep(3)
    return False


def buf(mon, EDLEN, EDBUF, n):
    ln = struct.unpack("<H", bytes(mon.read_mem(EDLEN, EDLEN + 1, memspace=0)))[0]; mon.resume()
    b = bytes(mon.read_mem(EDBUF, EDBUF + n - 1, memspace=0)); mon.resume()
    return ln, b


def main():
    global emu, NAMES_L, NAMES_H, LOADERR
    os.makedirs(WORK, exist_ok=True)
    edit_ref = load_ref(os.path.join(UOS, "target/uos-edit.prg"))
    desk_ref = load_ref(os.path.join(UOS, "target/uos-desktop.prg"))
    DISK = os.path.join(WORK, "ci_edit.d64")
    shutil.copyfile(STOCK, DISK)
    # pre-place NOTES.T as a proper SEQ file (VICE here can read but not write
    # file data; c1541 places it so the load path can be exercised)
    seqsrc = os.path.join(WORK, "notes.seq")
    open(seqsrc, "wb").write(NOTES)
    subprocess.run(["c1541", "-attach", DISK, "-write", seqsrc, "notes.t,s"],
                   check=True, capture_output=True)
    NAMES_L, NAMES_H = parse_lst_symbols()
    LOADERR = core_symbol("LOADERR")
    EDLEN = lst_symbol("uos-edit", "edlen")
    EDBUF = lst_symbol("uos-edit", "edbuf")

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
        print("PASS 0: booted to a live desktop", flush=True)
        passed += 1

        # 1: launch -> ed_load reads the pre-placed NOTES.T
        launch(mon, b"UOS-EDIT")
        assert wait_bytes(mon, APP_START, edit_ref[:16]), "editor never loaded"
        ok = False
        dl = time.time() + 40
        while time.time() < dl:
            ln, b = buf(mon, EDLEN, EDBUF, len(NOTES))
            if ln == len(NOTES) and b == NOTES:
                ok = True
                break
            time.sleep(2)
        assert ok, f"FAIL: ed_load did not read NOTES.T (edlen={ln}, buf={b!r})"
        print(f"PASS 1: ed_load read the pre-placed NOTES.T ({ln} bytes)", flush=True)
        passed += 1

        # 2: type more -> appends
        inject_keys(mon, b"HI")
        want = NOTES + b"HI"
        ok = False
        dl = time.time() + 30
        while time.time() < dl:
            ln, b = buf(mon, EDLEN, EDBUF, len(want))
            if ln == len(want) and b == want:
                ok = True
                break
            time.sleep(2)
        assert ok, f"FAIL: typing did not append (edlen={ln}, buf={b!r})"
        print(f"PASS 2: typed text appended to the loaded buffer (edlen={ln})", flush=True)
        passed += 1

        # 3: F1 save runs cleanly -> editor survives and keeps editing.
        # (The bytes landing on disk is the hardware gate: this VICE setup
        # cannot persist SEQ data writes; probes/seqwrite proves the KERNAL
        # write sequence runs with ST=$00.)
        inject_keys(mon, b"\x85")
        time.sleep(5)
        inject_keys(mon, b"Z")
        want2 = want + b"Z"
        ok = False
        dl = time.time() + 30
        while time.time() < dl:
            ln, b = buf(mon, EDLEN, EDBUF, len(want2))
            if ln == len(want2) and b == want2:
                ok = True
                break
            time.sleep(2)
        assert ok, f"FAIL: editor did not survive F1 save (edlen={ln}, buf={b!r})"
        print("PASS 3: F1 save ran cleanly; editor still editing (data-landing = hw gate)", flush=True)
        passed += 1

        # 4: ESC -> desktop
        inject_keys(mon, b"\x1b")
        assert wait_bytes(mon, DESK_START, desk_ref[:16], timeout=120), "no desktop after ESC"
        assert wait_desktop_live(mon), "desktop tick not live after editor ESC"
        print("PASS 4: ESC returned to a live desktop", flush=True)
        passed += 1

        print(f"CI-EDIT PASS: {passed}/5 editor checks", flush=True)
    finally:
        emu.terminate()
        xv.stop()


main()
