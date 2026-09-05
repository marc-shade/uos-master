#!/usr/bin/env python3
"""Validate the 1351 in control PORT 2 on the real C128 (uOS built with
INIT_MOUSE = $9f03 / install2). Assumes deploy_hw.py left a clean desktop
and the user has the mouse in port 2 and is moving it.

  1. pointer follows the mouse: VIC sprite-0 X/Y ($d000/$d001) sampled over
     a window; movement == the port-2 driver is reading the mouse.
     SID POTX/POTY ($d419/$d41a) and $dc00 pot-select are logged too.
  2. no phantom keys WITH the mouse present: load the shell, inject nothing,
     watch cmdlen ($46) for 30 s (this is what port 1 broke).
  3. keyboard + mouse coexist: inject exactly "VER\\r"; respbuf must show 0.3.
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

UOS = os.path.dirname(os.path.abspath(__file__))
TICK_VEC, T = 0x033c, 0x7f00
KB_BUF, KB_CNT, APP_START = 0x0277, 0xC6, 0x5000
DESK_TICK, CMDLEN = 0x1f2c, 0x46
WATCH = int(sys.argv[1]) if len(sys.argv) > 1 else 60


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
CMDBUF, RESP = sym("uos-shell", "cmdbuf"), sym("uos-shell", "respbuf")


def rd(a, n):
    return bytes(u.read_mem(a, n))


def wr(a, d):
    for i in range(0, len(d), 128):
        u.write_mem(a + i, d[i:i + 128])


def main():
    v = rd(TICK_VEC, 2); v = v[0] | (v[1] << 8)
    print(f"desktop: $033c=${v:04x} ({'live' if v == DESK_TICK else 'NOT desktop'})")
    if v != DESK_TICK:
        return 1

    # ---- 1. pointer follows the mouse ----
    print(f"\n1. watching sprite0 / pots for {WATCH}s — move the mouse (port 2):")
    print("   t    sprX sprY  POTX POTY  DC00")
    pos = []
    t0 = time.time()
    while time.time() - t0 < WATCH:
        sx, sy = rd(0xD000, 1)[0], rd(0xD001, 1)[0]
        px, py = rd(0xD419, 1)[0], rd(0xD41A, 1)[0]
        d0 = rd(0xDC00, 1)[0]
        pos.append((sx, sy))
        print(f"   {time.time()-t0:3.0f}s  {sx:02x}   {sy:02x}    {px:02x}   {py:02x}   {d0:02x}",
              flush=True)
        time.sleep(3)
    distinct = len(set(pos))
    moved = distinct > 1
    print(f"   -> sprite positions seen: {distinct}; pointer {'MOVED' if moved else 'did not move'}")

    # ---- 2. phantom check with the mouse present ----
    print("\n2. shell loaded, no keys injected, mouse present — phantom check:")
    orig = rd(TICK_VEC, 2)
    code = (bytes([0x20, 0x23, 0x08]) + b"UOS-SHELL\x00"
            + bytes([0x20, 0x26, 0x08])
            + bytes([0xA2, orig[0], 0xA0, orig[1],
                     0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
            + bytes([0x4C, 0x00, 0x50]))
    wr(T, code); wr(TICK_VEC, bytes([T & 0xFF, T >> 8]))
    t0 = time.time()
    while time.time() - t0 < 90:
        if rd(APP_START, 0x40) == shell[:0x40]:
            break
        time.sleep(3)
    else:
        print("   FAIL: shell never landed"); return 1
    time.sleep(8)
    wr(CMDBUF, b"\x00"); wr(CMDLEN, b"\x00")   # start from a clean line
    lens = []
    for _ in range(10):
        cl = rd(CMDLEN, 1)[0]
        lens.append(cl)
        print(f"   cmdlen={cl:3d} cmdbuf={rd(CMDBUF, 6).hex()} KB_CNT={rd(KB_CNT,1)[0]}")
        time.sleep(3)
    phantom = max(lens) > 0
    print(f"   -> phantom input with mouse in port 2: {phantom} (peak cmdlen {max(lens)})")

    # ---- 3. keyboard works alongside the mouse ----
    print("\n3. injecting 'VER'+RETURN once:")
    wr(CMDBUF, b"\x00"); wr(CMDLEN, b"\x00"); time.sleep(1)
    wr(KB_BUF, b"VER\x0d" + b"\x00" * 6); wr(KB_CNT, bytes([4]))
    ok = False; t0 = time.time()
    while time.time() - t0 < 30:
        if b"0.3" in rd(RESP, 40):
            ok = True; break
        time.sleep(2)
    print(f"   VER response: {ok} (respbuf={rd(RESP, 12).hex()})")

    print("\nVERDICT:")
    print(f"  pointer follows port-2 mouse : {moved}")
    print(f"  phantom keys with mouse in   : {phantom}")
    print(f"  keyboard (VER) works         : {ok}")
    if moved and not phantom and ok:
        print("  => PORT 2 FIX VERIFIED ON HARDWARE: mouse + keyboard coexist.")
    elif not moved:
        print("  => pointer never moved: mouse not in port 2 / not moved during the"
              " window / driver issue — re-run with the mouse moving.")
    return 0 if (moved and not phantom and ok) else 2


if __name__ == "__main__":
    sys.exit(main())
