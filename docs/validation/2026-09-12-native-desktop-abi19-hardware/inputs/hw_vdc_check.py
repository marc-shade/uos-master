#!/usr/bin/env python3
"""Hardware regression check for the 80-column companion display.

The Ultimate II+ DMA cannot address VDC RAM, so this pokes the assembled
probes/vdcdump.bin at $7f00, points uOS's once-per-second tick vector at it,
lets it copy the 8563 screen ($0000-$07cf) into main RAM $6000, restores the
vector, and decodes the rows exactly like tests/ci_vdc.py does in x128.

Preconditions: uOS running on the real C128 with the desktop live (run
deploy_hw.py first; drive A must be a 1541 — see ../u2_drive_type.py).
The dump only works while the DESKTOP owns the main loop: apps with a
private KEYIN loop (fmgr/shell/settings) never dispatch the tick.

Exit 0 = header rows + "desktop" row read back from the real VDC.
"""
import importlib.util
import os
import struct
import sys
import time
from importlib.machinery import SourceFileLoader

_l = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
_s = importlib.util.spec_from_loader("cbm", _l)
cbm = importlib.util.module_from_spec(_s)
_l.exec_module(cbm)
UOS = os.path.dirname(os.path.abspath(__file__))
TICK_VEC, TRAMP, DUMP = 0x033C, 0x7F00, 0x6000
VEC0_OFF, VEC1_OFF = 0x50, 0x55          # operand offsets in vdcdump.bin (see .lst)


def decode(cells):
    out = ""
    for c in cells:
        c &= 0x7f
        if 1 <= c <= 0x1a:
            out += chr(c + 96)
        elif 0x41 <= c <= 0x5a or 0x20 <= c <= 0x3f:
            out += chr(c)
        else:
            out += "."
    return out.rstrip()


def main():
    u = cbm.Ultimate()
    vec = u.read_mem(TICK_VEC, 2)
    if vec == b"\x00\x00":
        cbm.die("tick vector is $0000: uOS desktop is not live (run deploy_hw.py)")
    code = bytearray(open(os.path.join(UOS, "probes/vdcdump.bin"), "rb").read()[2:])
    assert code[VEC0_OFF - 1] == 0xA9 and code[VEC1_OFF - 1] == 0xA9, "vdcdump.bin layout changed"
    code[VEC0_OFF], code[VEC1_OFF] = vec[0], vec[1]
    u.write_mem(TRAMP, bytes(code))
    u.write_mem(TICK_VEC, struct.pack("<H", TRAMP))
    for i in range(15):
        time.sleep(2)
        if u.read_mem(TICK_VEC, 2) == vec:
            print(f"dump ran, tick vector restored after {(i + 1) * 2}s")
            break
    else:
        cbm.die(f"dump never ran (vector {u.read_mem(TICK_VEC, 2).hex()}): is the desktop in MAINLOOP?")
    mem = u.read_mem(DUMP, 2000)
    rows = [decode(mem[r * 80:(r + 1) * 80]) for r in range(25)]
    for i, r in enumerate(rows):
        if r:
            print(f"{i:2d}: {r}")
    # the copy is not atomic (the 8563 keeps refreshing), so a few cells can
    # read back blank: check anchors, not whole strings
    ok = rows[0].startswith("UltOS") and rows[1].startswith("ultos") and "apps" in rows[1] \
        and rows[2].startswith("desktop")
    print("raw row0:", mem[:16].hex())
    if not ok:
        cbm.die("FAIL: companion display rows did not read back from the real VDC")
    print("PASS: 80-column companion display verified on the real 8563 (header + desktop row)")


main()
