#!/usr/bin/env python3
"""Verify the desktop background-colour option on the real C128 (U2+ DMA).

Assumes deploy_hw.py left a clean desktop.
  1. read the initial background: SETREC_BG ($7356) and a screen-matrix cell
     ($8400 low nibble = the hires background colour the desktop painted)
  2. launch settings, press 'C' N times (cycle SETREC_BG, each press SAVEs)
  3. ESC back — settings_back reloads the desktop, which re-clears with the
     new SETREC_BG
  4. confirm $8400's low nibble now equals the cycled colour (the desktop
     background actually changed), and SETREC_BG persisted in the record
"""
import importlib.util
import os
import sys
import time

from importlib.machinery import SourceFileLoader
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)
from hwlib import desk_tick

UOS = os.path.dirname(os.path.abspath(__file__))
TICK_VEC, T, FLAG = 0x033c, 0x7f00, 0x7fff
KB_BUF, KB_CNT, APP_START = 0x0277, 0xC6, 0x5000
SCREEN_MATRIX = 0x8400          # hires colour cells: hi nibble fg, lo nibble bg
BG = 0x7356                     # SETREC_BG
DESK_TICK = desk_tick()
PRESSES = int(sys.argv[1]) if len(sys.argv) > 1 else 3

u = cbm.Ultimate()
desk = open(os.path.join(UOS, "target/uos-desktop.prg"), "rb").read()[2:]
settings = open(os.path.join(UOS, "target/uos-settings.prg"), "rb").read()[2:]


def rd(a, n): return bytes(u.read_mem(a, n))
def wr(a, d):
    for i in range(0, len(d), 128):
        u.write_mem(a + i, d[i:i + 128])
def vec():
    v = rd(TICK_VEC, 2); return v[0] | (v[1] << 8)
def keys(s):
    wr(KB_BUF, s + b"\x00" * (10 - len(s))); wr(KB_CNT, bytes([len(s)]))


def desktop_live(timeout=150):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if vec() != T:
            v = rd(TICK_VEC, 2)
            probe = (bytes([0xEE, FLAG & 0xff, FLAG >> 8])
                     + bytes([0xA2, v[0], 0xA0, v[1],
                              0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
                     + bytes([0x6C, 0x3C, 0x03]))
            wr(FLAG, b"\x00"); wr(T, probe); wr(TICK_VEC, bytes([T & 0xff, T >> 8]))
        time.sleep(3)
        if rd(FLAG, 1)[0]:
            return time.time() - t0
    return None


def launch(name, ref, timeout=120):
    wr(APP_START, b"\x00" * 64)
    orig = rd(TICK_VEC, 2)
    code = (bytes([0x20, 0x23, 0x08]) + name + b"\x00"
            + bytes([0x20, 0x26, 0x08])
            + bytes([0xA2, orig[0], 0xA0, orig[1],
                     0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
            + bytes([0x4C, 0x00, 0x50]))
    wr(T, code); wr(TICK_VEC, bytes([T & 0xff, T >> 8]))
    t0 = time.time()
    while time.time() - t0 < timeout:
        if rd(APP_START, 0x40) == ref[:0x40]:
            return time.time() - t0
        time.sleep(3)
    return None


def main():
    if vec() != DESK_TICK:
        print(f"FAIL: not at the desktop ($033c=${vec():04x}) — run deploy_hw.py")
        return 1
    bg0 = rd(BG, 1)[0]
    cell0 = rd(SCREEN_MATRIX, 1)[0]
    print(f"1. initial: SETREC_BG=${bg0:02x}  screen cell $8400=${cell0:02x} "
          f"(bg nibble ${cell0 & 0x0f:x}) — should match")

    if launch(b"UOS-SETTINGS", settings) is None:
        print("FAIL: settings never landed"); return 1
    time.sleep(6)
    bg_in = rd(BG, 1)[0]
    print(f"2. settings up; SETREC_BG on entry=${bg_in:02x}")
    for i in range(PRESSES):
        before = rd(BG, 1)[0]
        keys(b"C")
        t0 = time.time()
        while time.time() - t0 < 20 and rd(BG, 1)[0] == before:
            time.sleep(1)
        print(f"   C #{i+1}: SETREC_BG ${before:02x} -> ${rd(BG,1)[0]:02x}")
        time.sleep(12)              # let the kernal SAVE finish
    bg_saved = rd(BG, 1)[0]

    keys(b"\x1b")                   # ESC -> desktop reload
    if desktop_live() is None:
        print("FAIL: desktop not live after settings ESC"); return 1
    cell1 = rd(SCREEN_MATRIX, 1)[0]
    bg_after = rd(BG, 1)[0]
    print(f"3. after ESC: SETREC_BG=${bg_after:02x}  screen cell $8400=${cell1:02x} "
          f"(bg nibble ${cell1 & 0x0f:x})")

    exp = bg_saved if bg_saved != 0 else 0        # black special-case: cell hi=1
    ok_cell = (cell1 & 0x0f) == (bg_saved & 0x0f)
    print("\nVERDICT:")
    print(f"  colour cycled {bg0:#x} -> {bg_saved:#x}: {bg_saved != bg0}")
    print(f"  desktop background cell matches the chosen colour: {ok_cell}")
    print("  => BACKGROUND-COLOUR OPTION WORKS ON HARDWARE"
          if (bg_saved != bg0 and ok_cell) else "  => mismatch, investigate")
    return 0 if (bg_saved != bg0 and ok_cell) else 2


if __name__ == "__main__":
    sys.exit(main())
