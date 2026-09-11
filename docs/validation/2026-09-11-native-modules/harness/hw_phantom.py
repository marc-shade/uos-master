#!/usr/bin/env python3
"""Isolate the phantom-keypress source on the real C128 (Ultimate II+ DMA).

Assumes deploy_hw.py left a clean desktop. Run this with the mouse UNPLUGGED
(the user's A/B counterpart to the earlier mouse-plugged run that flooded the
shell's command line with 16x 'W').

Steps:
  A. Electrical port state at the desktop — SID pot X/Y ($d419/$d41a, how a
     1351 reports position) and CIA1 $dc00/$dc01 (joystick/fire + keyboard
     matrix), sampled several times. A 1351 present + moving changes the pots;
     an empty port reads them differently and stably.
  B. Phantom detection — load the shell, inject NOTHING, watch cmdlen ($46)
     and cmdbuf for ~30 s. Growth with no injection == phantom input reaching
     GETIN. Also watch the raw kernal keyboard buffer count $c6.
  C. Clean-command test — inject exactly "VER\r" once and check the shell's
     response buffer for "0.3". If B is quiet and C responds, the shell works
     on hardware and the earlier flood was external (the mouse).

Prints a verdict. No claim is made that isn't in the printed evidence.
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
TICK_VEC, T = 0x033c, 0x7f00
KB_BUF, KB_CNT, APP_START = 0x0277, 0xC6, 0x5000
DESK_TICK = desk_tick()


def sym(module, name):
    lst = open(os.path.join(UOS, f"target/{module}.lst"), "rb").read().decode(
        "latin-1", errors="replace")
    m = re.search(r"^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?%s:"
                  % re.escape(name), lst, re.M)
    if not m:
        raise SystemExit(f"FAIL: {name} not found in {module}")
    return int(m.group(1), 16)


u = cbm.Ultimate()
shell = open(os.path.join(UOS, "target/uos-shell.prg"), "rb").read()[2:]
CMDBUF = sym("uos-shell", "cmdbuf")
RESP = sym("uos-shell", "respbuf")
CMDLEN = 0x46


def rd(a, n):
    return bytes(u.read_mem(a, n))


def wr(a, d):
    for i in range(0, len(d), 128):
        u.write_mem(a + i, d[i:i + 128])


def vec():
    v = rd(TICK_VEC, 2)
    return v[0] | (v[1] << 8)


def main():
    v = vec()
    print(f"desktop check: $033c=${v:04x} "
          f"({'live' if v == DESK_TICK else 'NOT the desktop — run deploy_hw.py'})")
    if v != DESK_TICK:
        return 1

    # ---- A. electrical port state at the desktop ----
    print("\nA. port/matrix state at the desktop (no app, 6 samples):")
    print("   POTX POTY  DC00 DC01")
    pots = []
    for _ in range(6):
        px, py = rd(0xD419, 1)[0], rd(0xD41A, 1)[0]
        d0, d1 = rd(0xDC00, 1)[0], rd(0xDC01, 1)[0]
        pots.append((px, py))
        print(f"   {px:02x}   {py:02x}    {d0:02x}   {d1:02x}")
        time.sleep(1)
    potspread = max(p[0] for p in pots) - min(p[0] for p in pots)
    print(f"   POTX spread over samples: {potspread} "
          f"(large/jittery => a pot device like a 1351 is present)")

    # ---- B. phantom detection: load shell, inject nothing ----
    print("\nB. shell loaded, NO keys injected — watching for phantom input:")
    orig = rd(TICK_VEC, 2)
    code = (bytes([0x20, 0x23, 0x08]) + b"UOS-SHELL\x00"
            + bytes([0x20, 0x26, 0x08])
            + bytes([0xA2, orig[0], 0xA0, orig[1],
                     0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
            + bytes([0x4C, 0x00, 0x50]))
    wr(T, code)
    wr(TICK_VEC, bytes([T & 0xFF, T >> 8]))
    t0 = time.time()
    while time.time() - t0 < 90:
        if rd(APP_START, 0x40) == shell[:0x40]:
            break
        time.sleep(3)
    else:
        print("   FAIL: shell never landed"); return 1
    print(f"   shell up in {time.time()-t0:.0f}s; sampling cmdlen for 30s "
          f"with zero injection:")
    lens = []
    for _ in range(10):
        cl = rd(CMDLEN, 1)[0]
        cb = rd(CMDBUF, 6).hex()
        kc = rd(KB_CNT, 1)[0]
        lens.append(cl)
        print(f"   cmdlen={cl:3d} cmdbuf={cb} KB_CNT={kc}")
        time.sleep(3)
    grew = lens[-1] > lens[0] or max(lens) > 2
    print(f"   -> phantom input present: {grew} "
          f"(cmdlen {lens[0]} -> {lens[-1]}, peak {max(lens)})")

    # ---- C. clean-command test ----
    print("\nC. injecting exactly 'VER'+RETURN once:")
    # clear the line first in case B caught a stray key
    wr(CMDBUF, b"\x00")
    wr(CMDLEN, b"\x00")
    time.sleep(1)
    wr(KB_BUF, b"VER\x0d" + b"\x00" * 6)
    wr(KB_CNT, bytes([4]))
    ok = False
    t0 = time.time()
    while time.time() - t0 < 30:
        if b"0.3" in rd(RESP, 40):
            ok = True; break
        time.sleep(2)
    print(f"   VER response on hardware: {ok} "
          f"(respbuf={rd(RESP, 12).hex()} cmdlen={rd(CMDLEN,1)[0]} "
          f"cmdbuf={rd(CMDBUF,6).hex()})")

    print("\nVERDICT:")
    if not grew and ok:
        print("  Shell works cleanly on hardware with no phantom input.")
        print("  => the earlier 16x 'W' flood was EXTERNAL to uOS (consistent")
        print("     with a device on control port 1); mouse-out fixes it.")
    elif grew:
        print("  Phantom input STILL present with the mouse unplugged =>")
        print("  NOT the mouse. Suspect a stuck physical key or the DMA-write")
        print("  vs kernal-IRQ race. See the POT/DC0x samples above.")
    else:
        print("  No phantom, but VER did not respond — a separate shell/inject")
        print("  issue on hardware; see cmdbuf/cmdlen above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
