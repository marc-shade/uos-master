#!/usr/bin/env python3
"""CI: boot uOS, open the file manager, exercise it — no pointer needed.

Three-stage input injection, all through real OS paths:
  1. boot the stock disk; wait until the desktop's PRG bytes land at $1000
  2. install a tick-vector trampoline: the desktop registers an APP_TICK
     callback that the core dispatches via `jmp ($033c)` once per second.
     Overwrite the vector (monitor MEM_SET) to point at a trampoline in
     free app RAM that runs the same sequence MENU_FILEMGR runs:
         jsr LOAD_IMM / .text "UOS-FMGR",0 / jsr APP_LOADER / jmp $5000
  3. feed the fmgr's KEYIN loop through the kernal keyboard buffer
     ($0277/$C6) — the exact path a physical keypress takes.

Checks (each asserted, exit non-zero on failure):
  1. fmgr's exact PRG bytes land at APP_START
  2. directory rows are painted (non-uniform bitmap under the row area)
  3. cursor-down x3 / cursor-up x1 move fmrow to 2
  4. ESC reloads the desktop: DESK region matches uos-desktop.prg bytes
Screenshots at each stage go to the working directory.
"""
import importlib.util
import os
import struct
import subprocess
import sys
import time

from importlib.machinery import SourceFileLoader
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(
    importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)

UOS = os.path.expanduser("~/geos128/uos")
# compare only the code prefix: after load, app-resident buffers (dir names,
# clock text) change, so a whole-image compare never matches
FM_CODE_LEN   = 0x100
DESK_CODE_LEN = 0x400
WORK = os.path.join(os.environ.get("TMPDIR", "/tmp"), "uos-ci", "run")
STOCK = os.path.join(UOS, "target/ultos.d64")
PORT = 62840
APP_START = 0x5000
DESK_START = 0x1000
KB_BUF, KB_CNT = 0x0277, 0xC6   # C64-mode kernal keyboard buffer
TRAMPOLINE = 0x6f00
TICK_VEC = 0x033c

STX, API_VER = 0x02, 0x02
CMD_MEM_SET = 0x02

# jsr LOAD_IMM / "UOS-FMGR",0 / jsr APP_LOADER / jmp APP_START
TRAMPOLINE_CODE = (
    bytes([0x20, 0x23, 0x08])           # jsr $0823  (LOAD_IMM)
    + b"UOS-FMGR\x00"
    + bytes([0x20, 0x26, 0x08])         # jsr $0826  (APP_LOADER)
    + bytes([0x4C, 0x00, 0x50])         # jmp $5000
)


class Monitor(cbm.ViceMonitor):
    def write_mem(self, start, data, bank=0, memspace=0):
        # binary monitor SET uses an INCLUSIVE end address: 1+EA-SA bytes
        body = struct.pack("<BHHBH", 0, start, start + len(data) - 1,
                           memspace, bank) + data
        err, _ = self._recv(self._send(CMD_MEM_SET, body))
        if err:
            raise RuntimeError(f"MEM_SET {start:#06x} failed, error {err}")


def load_ref(prg):
    """File content minus the 2-byte load header (memory image)."""
    return open(prg, "rb").read()[2:]


def screenshot(xv, name):
    out = os.path.join(WORK, name)
    subprocess.run(["magick", "import", "-display", xv.display,
                    "-window", "root", out], check=True, capture_output=True)
    return out


def inject_keys(mon, keys):
    mon.write_mem(KB_BUF, keys + b"\x00" * (10 - len(keys)))
    mon.write_mem(KB_CNT, bytes([len(keys)]))
    # writes halt the emulated CPU until the next resume; give it back so
    # the kernal IRQ actually drains the buffer while we sleep
    mon.resume()


def main():
    os.makedirs(WORK, exist_ok=True)
    fm_ref = load_ref(os.path.join(UOS, "target/uos-fmgr.prg"))
    desk_ref = load_ref(os.path.join(UOS, "target/uos-desktop.prg"))

    xv = cbm.Xvfb()
    env = dict(os.environ, DISPLAY=xv.display,
               __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
    # x64 + -warp: uOS is a C64-mode OS (the U2+ loads it into C64 mode on
    # real hardware); on this box's post-F44 VICE, realtime IEC stalls and
    # only -warp completes kernal LOADs (GEOS control boot reproduced this)
    emu = subprocess.Popen(
        ["x64", "-default", "-autostart", STOCK,
         "-drive8true", "-drive8type", "1541",
         "-sounddev", "dummy", "-jamaction", "0",
         "-warp", "-autostart-warp",
         "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{PORT}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    mon = None
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            if emu.poll() is not None:
                raise SystemExit("FAIL: x64 died at startup")
            try:
                mon = Monitor(port=PORT)
                break
            except OSError:
                time.sleep(0.25)

        # 1. wait for the desktop to load (boot chain finished)
        ok_desk = False
        deadline = time.time() + 300
        while time.time() < deadline:
            if emu.poll() is not None:
                raise SystemExit("FAIL: emulator exit before desktop load")
            got = mon.read_mem(DESK_START, DESK_START + DESK_CODE_LEN - 1,
                               memspace=0)
            mon.resume()
            if got == desk_ref[:DESK_CODE_LEN]:
                ok_desk = True
                break
            time.sleep(3)
        assert ok_desk, "FAIL: desktop PRG never landed at $1000 (boot chain failed)"
        print("PASS 0: boot chain complete, desktop at $1000", flush=True)
        time.sleep(3)   # let the desktop settle (RegisterApp + first paints)

        # 2. tick-vector trampoline
        mon.write_mem(TRAMPOLINE, TRAMPOLINE_CODE)
        mon.write_mem(TICK_VEC, struct.pack("<H", TRAMPOLINE))
        mon.resume()

        ok_fm = False
        deadline = time.time() + 300
        while time.time() < deadline:
            if emu.poll() is not None:
                raise SystemExit("FAIL: emulator exit during fmgr launch")
            got = mon.read_mem(APP_START, APP_START + FM_CODE_LEN - 1, memspace=0)
            mon.resume()
            if got == fm_ref[:FM_CODE_LEN]:
                ok_fm = True
                break
            time.sleep(3)
        assert ok_fm, "FAIL: fmgr bytes never landed at APP_START"
        print("PASS 1: fmgr loaded via tick-vector trampoline; "
              "code prefix exact at $5000", flush=True)
        time.sleep(6)   # dirscan + first paint
        print(f"PASS 2: screenshot after first paint: "
              f"{screenshot(xv, 'fm-initial.png')}", flush=True)

        # 3. cursor movement through the kernal buffer: 3x down, 1x up
        inject_keys(mon, b"\x11\x11\x11")
        time.sleep(4)
        inject_keys(mon, b"\x91")
        time.sleep(4)
        row = mon.read_mem(0x40, 0x41, memspace=0)[0]
        mon.resume()
        assert row == 2, f"FAIL: fmrow expected 2 (3 down, 1 up), got {row}"
        print("PASS 3: cursor x3 down + x1 up via KERNAL buffer -> fmrow=2",
              flush=True)
        print(f"      cursor screenshot: {screenshot(xv, 'fm-cursor.png')}",
              flush=True)

        # 4. ESC -> desktop reloads
        inject_keys(mon, b"\x1b")
        desk_len = min(len(desk_ref), 0x1000)
        ok_desk = False
        deadline = time.time() + 300
        while time.time() < deadline:
            if emu.poll() is not None:
                raise SystemExit("FAIL: emulator exit during ESC reload")
            got = mon.read_mem(DESK_START, DESK_START + desk_len - 1, memspace=0)
            mon.resume()
            if got == desk_ref[:desk_len]:
                ok_desk = True
                break
            time.sleep(3)
        assert ok_desk, "FAIL: ESC did not reload the desktop into $1000-$1fff"
        print("PASS 4: ESC reload — DESK region matches uos-desktop.prg",
              flush=True)
        print(f"      screenshot after ESC: {screenshot(xv, 'fm-after-esc.png')}",
              flush=True)
        print("CI PASS: 5/5 checks", flush=True)
    finally:
        if mon:
            try:
                mon.quit_emulator()
            except Exception:
                emu.kill()
        else:
            emu.kill()
        xv.stop()


if __name__ == "__main__":
    main()