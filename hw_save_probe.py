#!/usr/bin/env python3
"""Isolate the FR-S3 SAVE failure WITHOUT a reboot (real C128 + U2+ DMA).

Question: after the settings app's kernal SAVE, is UOS-SET actually on the
mounted disk? The reboot round trip (hw_save_gate.py) can't tell "SAVE never
wrote" from "run_prg discarded the write". This asks the drive directly.

  1. fresh deploy (clean ultos.d64) -> desktop; boot writes default mode 2
  2. launch settings, press D until the mode byte $7355 is != 2 (a value the
     absent-file default can't produce), which also issues the kernal SAVE
  3. ESC back to a live desktop
  4. poke $7355 to a sentinel ($7f), then fire a tick trampoline that does
     LOAD_IMM "UOS-SET" / jsr LOADER  -- the SAME core path the boot uses;
     LOADER loads UOS-SET to its header address ($7350) and latches any
     kernal error at LOADERR
  5. read LOADERR and $7355:
       LOADERR=0 and $7355==saved  -> UOS-SET IS on the drive => SAVE landed,
                                       so the reboot discards writes (cause b)
       LOADERR=$04 (file not found) -> SAVE never wrote (cause a)

No reboot, so the mounted image is never re-fetched; this reads what the
SAVE left on the drive.
"""
import importlib.util
import os
import sys
import time

from importlib.machinery import SourceFileLoader
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)
from hwlib import desk_tick, lst_symbol

UOS = os.path.dirname(os.path.abspath(__file__))
TICK_VEC, T, FLAG = 0x033c, 0x7f00, 0x7fff
KB_BUF, KB_CNT, APP_START = 0x0277, 0xC6, 0x5000
MODE = 0x7355
DESK_TICK = desk_tick()
LOADERR = lst_symbol("uos", "LOADERR")


class HW:
    def __init__(self):
        self.u = cbm.Ultimate()
        self.desk = open(os.path.join(UOS, "target/uos-desktop.prg"), "rb").read()[2:]

    def rd(self, a, n):
        return bytes(self.u.read_mem(a, n))

    def wr(self, a, d):
        for i in range(0, len(d), 128):
            self.u.write_mem(a + i, d[i:i + 128])

    def vec(self):
        v = self.rd(TICK_VEC, 2)
        return v[0] | (v[1] << 8)

    def keys(self, s):
        self.wr(KB_BUF, s + b"\x00" * (10 - len(s)))
        self.wr(KB_CNT, bytes([len(s)]))

    def wait_desktop(self, timeout=240):
        t0 = time.time()
        while time.time() - t0 < timeout:
            full = self.rd(0x1000, len(self.desk))
            diffs = sum(1 for i in range(len(self.desk)) if full[i] != self.desk[i])
            if self.vec() == DESK_TICK and diffs < 64:
                return time.time() - t0
            time.sleep(5)
        return None

    def desktop_live(self, timeout=150):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.vec() != T:
                v = self.rd(TICK_VEC, 2)
                probe = (bytes([0xEE, FLAG & 0xff, FLAG >> 8])
                         + bytes([0xA2, v[0], 0xA0, v[1],
                                  0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
                         + bytes([0x6C, 0x3C, 0x03]))
                self.wr(FLAG, b"\x00"); self.wr(T, probe)
                self.wr(TICK_VEC, bytes([T & 0xff, T >> 8]))
            time.sleep(3)
            if self.rd(FLAG, 1)[0]:
                return time.time() - t0
        return None

    def launch(self, name, ref, timeout=120):
        self.wr(APP_START, b"\x00" * 64)
        orig = self.rd(TICK_VEC, 2)
        code = (bytes([0x20, 0x23, 0x08]) + name + b"\x00"
                + bytes([0x20, 0x26, 0x08])
                + bytes([0xA2, orig[0], 0xA0, orig[1],
                         0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
                + bytes([0x4C, 0x00, 0x50]))
        self.wr(T, code); self.wr(TICK_VEC, bytes([T & 0xff, T >> 8]))
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.rd(APP_START, 0x40) == ref[:0x40]:
                return time.time() - t0
            time.sleep(3)
        return None

    def load_file(self, name, timeout=40):
        """Fire a tick trampoline: LOAD_IMM name / jsr LOADER / flag / restore.
        Returns when the flag at FLAG flips (the trampoline finished)."""
        orig = self.rd(TICK_VEC, 2)
        code = (bytes([0x20, 0x23, 0x08]) + name + b"\x00"     # LOAD_IMM name
                + bytes([0x20, 0x26, 0x08])                      # jsr LOADER
                + bytes([0xEE, FLAG & 0xff, FLAG >> 8])          # inc FLAG (done)
                + bytes([0xA2, orig[0], 0xA0, orig[1],
                         0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])    # restore vec
                + bytes([0x60]))                                 # rts -> main_loop
        self.wr(FLAG, b"\x00")
        self.wr(T, code); self.wr(TICK_VEC, bytes([T & 0xff, T >> 8]))
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.rd(FLAG, 1)[0]:
                return time.time() - t0
            time.sleep(2)
        return None


def main():
    hw = HW()
    settings = open(os.path.join(UOS, "target/uos-settings.prg"), "rb").read()[2:]
    boot = open(os.path.join(UOS, "target/uos.prg"), "rb").read()

    disk = open(os.path.join(UOS, "target/ultos.d64"), "rb").read()
    hw.u.mount(disk, "a", "d64", "readwrite")
    hw.u.run_prg(boot)
    if hw.wait_desktop() is None:
        print("FAIL: fresh deploy — desktop never live"); return 1
    print(f"1. fresh deploy; boot mode $7355 = {hw.rd(MODE,1)[0]} (UOS-SET absent -> 2)")

    if hw.launch(b"UOS-SETTINGS", settings) is None:
        print("FAIL: settings never landed"); return 1
    time.sleep(8)
    p = hw.rd(MODE, 1)[0]
    target = (p + 1) % 3
    presses = 1
    if target == 2:
        target = (p + 2) % 3; presses = 2
    for i in range(presses):
        want = (p + i + 1) % 3
        hw.keys(b"D")
        t0 = time.time()
        while time.time() - t0 < 30 and hw.rd(MODE, 1)[0] != want:
            time.sleep(2)
        if hw.rd(MODE, 1)[0] != want:
            print(f"FAIL: D did not cycle to {want}"); return 1
        time.sleep(15)                         # let the SAVE complete
    saved = hw.rd(MODE, 1)[0]
    print(f"2. settings: saved mode = {saved} (kernal SAVE of UOS-SET issued)")

    hw.keys(b"\x1b")
    if hw.desktop_live() is None:
        print("FAIL: desktop not live after settings ESC"); return 1
    print("3. ESC -> desktop live")

    # 4. poke a sentinel, then LOAD UOS-SET back from the drive (no reboot)
    hw.wr(LOADERR, b"\x00")
    hw.wr(MODE, b"\x7f")
    before = hw.rd(MODE, 1)[0]
    dt = hw.load_file(b"UOS-SET")
    if dt is None:
        print("FAIL: LOAD trampoline never completed"); return 1
    err = hw.rd(LOADERR, 1)[0]
    after = hw.rd(MODE, 1)[0]
    rec = hw.rd(0x7350, 7)
    print(f"4. LOAD \"UOS-SET\" from the drive (no reboot): LOADERR={err:#04x} "
          f"$7355 {before:#04x} -> {after:#04x}; record={rec.hex()}")

    print("\nVERDICT:")
    if err == 0 and after == saved:
        print(f"  UOS-SET IS on the drive (loaded, mode {saved}). The kernal SAVE "
              f"LANDED. => the reboot discards it: run_prg resets the mounted "
              f"U2+ image. Fix is deploy-side (persist/re-mount), not uOS.")
        return 0
    if err == 0x04:
        print("  LOAD returned FILE NOT FOUND => the kernal SAVE never wrote "
              "UOS-SET to the drive. Bug is in the settings SAVE path on HW.")
        return 2
    print(f"  Inconclusive: LOADERR={err:#04x}, mode {before:#04x}->{after:#04x}. "
          f"(err $05=device not present, $1d=load error)")
    return 3


if __name__ == "__main__":
    sys.exit(main())
