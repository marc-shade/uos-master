#!/usr/bin/env python3
"""PRD FR-S3 hardware gate: does the settings app's kernal SAVE land on the
REAL disk, and does the boot read it back? (Real C128 + Ultimate II+, DMA.)

Why a round trip instead of "look for UOS-SET in a directory listing": the
shell's and fmgr's list buffers cap at 10 names and this disk already has 10
system files, so an 11th entry is silently dropped — a false negative. The
boot path (VDPREF) LOADs "UOS-SET" into the fixed record at $7350 and applies
the mode byte at $7355, so the byte surviving a reboot IS the proof.

  1. fresh deploy (mount a clean ultos.d64 + run_prg)   -> desktop live
     VDPREF finds no UOS-SET and writes the default mode 2 at $7355
  2. launch settings via the tick trampoline            -> $5000 == settings
     read the mode byte P the PRG image carries; press D until the mode is
     a value != 2 (so it is distinguishable from the "file absent" default)
  3. the D handler SAVEs UOS-SET to the mounted (readwrite) disk; ESC back
  4. REBOOT WITHOUT RE-MOUNTING (run_prg only) so the modified image stays
  5. read $7355 after the desktop is live: == saved mode => SAVE landed and
     LOADed back on real hardware; == 2 => it did not.

Fixes vs hw_validate.py: launch() clobbers $5000 before arming so a stale
resident image (RAM survives a soft reset) can never pass as "loaded".
"""
import importlib.util
import os
import re
import sys
import time

from importlib.machinery import SourceFileLoader
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)
from hwlib import desk_tick, lst_symbol as _lst

UOS = os.path.dirname(os.path.abspath(__file__))
TICK_VEC, T, FLAG = 0x033c, 0x7f00, 0x7fff
KB_BUF, KB_CNT, APP_START = 0x0277, 0xC6, 0x5000
DESK_TICK, MODE = desk_tick(), 0x7355


def prg(n):
    return open(os.path.join(UOS, f"target/{n}.prg"), "rb").read()[2:]


class HW:
    def __init__(self):
        self.u = cbm.Ultimate()
        self.desk = prg("uos-desktop")

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
        """Full image at $1000 AND the entry has registered its vector."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            full = self.rd(0x1000, len(self.desk))
            diffs = sum(1 for i in range(len(self.desk)) if full[i] != self.desk[i])
            if self.vec() == DESK_TICK and diffs < 64:
                return time.time() - t0
            time.sleep(5)
        return None

    def desktop_live(self, timeout=150):
        """Core loop dispatching ticks again (one-shot probe flag)."""
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
        self.wr(APP_START, b"\x00" * 64)          # a stale image must not pass
        orig = self.rd(TICK_VEC, 2)
        code = (bytes([0x20, 0x23, 0x08]) + name + b"\x00"
                + bytes([0x20, 0x26, 0x08])
                + bytes([0xA2, orig[0], 0xA0, orig[1],
                         0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
                + bytes([0x4C, 0x00, 0x50]))
        self.wr(T, code)
        self.wr(TICK_VEC, bytes([T & 0xff, T >> 8]))
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.rd(APP_START, 0x40) == ref[:0x40]:
                return time.time() - t0
            time.sleep(3)
        return None


def main():
    hw = HW()
    settings = prg("uos-settings")
    boot = open(os.path.join(UOS, "target/uos.prg"), "rb").read()

    # ---- 1. fresh deploy ----
    disk = open(os.path.join(UOS, "target/ultos.d64"), "rb").read()
    hw.u.mount(disk, "a", "d64", "readwrite")
    hw.u.run_prg(boot)
    dt = hw.wait_desktop()
    if dt is None:
        print("FAIL: fresh deploy — desktop never live"); return 1
    m0 = hw.rd(MODE, 1)[0]
    print(f"1. fresh deploy: desktop live in {dt:.0f}s; boot-time mode $7355 = {m0} "
          f"(expect 2 = default written when UOS-SET is absent)")

    # ---- 2. settings + cycle to a mode != 2 ----
    dt = hw.launch(b"UOS-SETTINGS", settings)
    if dt is None:
        print("FAIL: settings never landed"); return 1
    time.sleep(8)
    p = hw.rd(MODE, 1)[0]
    print(f"2. settings up in {dt:.0f}s; PRG-image mode byte P = {p}")
    target = (p + 1) % 3
    presses = 1
    if target == 2:                     # indistinguishable from "absent" default
        target = (p + 2) % 3
        presses = 2
    for i in range(presses):
        hw.keys(b"D")
        t0 = time.time()
        want = (p + i + 1) % 3
        while time.time() - t0 < 30 and hw.rd(MODE, 1)[0] != want:
            time.sleep(2)
        cur = hw.rd(MODE, 1)[0]
        print(f"   D #{i+1}: mode -> {cur} (wanted {want}) "
              f"{'ok, SAVE issued' if cur == want else 'MISMATCH'}")
        if cur != want:
            return 1
        time.sleep(15)                  # let the kernal SAVE finish on the 1541
    saved = hw.rd(MODE, 1)[0]
    print(f"   final saved mode = {saved} (must be != 2 to be provable)")

    # ---- 3. ESC back to a live desktop ----
    hw.keys(b"\x1b")
    dt = hw.desktop_live()
    if dt is None:
        print("FAIL: desktop not live after settings ESC"); return 1
    print(f"3. ESC -> desktop live again ({dt:.0f}s incl. reload)")

    # ---- 4. reboot WITHOUT re-mounting ----
    print("4. reboot via run_prg only (mounted image kept) ...")
    hw.u.run_prg(boot)
    dt = hw.wait_desktop()
    if dt is None:
        print("FAIL: reboot — desktop never live"); return 1

    # ---- 5. the verdict ----
    m1 = hw.rd(MODE, 1)[0]
    rec = hw.rd(0x7350, 7)
    print(f"5. after reboot ({dt:.0f}s): $7355 = {m1}; record $7350.. = {rec.hex()}")
    if m1 == saved and saved != 2:
        print(f"PASS: kernal SAVE landed on the real disk and the boot read it back "
              f"(mode {saved} survived the reboot). FR-S3 hardware gate CLOSED.")
        return 0
    print(f"FAIL: expected mode {saved} after reboot, got {m1} "
          f"({'= absent-file default' if m1 == 2 else 'unexpected'}). SAVE did not land.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
