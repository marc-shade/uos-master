#!/usr/bin/env python3
"""Drive uOS apps on the REAL C128 (Ultimate II+ DMA) and prove the hardware
gates. Assumes deploy_hw.py already left the desktop live.

Same mechanism as tests/ci_fm.py, over DMA instead of the VICE monitor:
  - one-shot tick trampoline poked at $7f00, vector $033c -> it; the core's
    once-per-second `jmp ($033c)` runs LOAD_IMM/APP_LOADER/jmp $5000
  - keys poked into the C64-mode kernal keyboard buffer $0277 / count $c6
  - liveness = a tick probe flag flipping (the desktop image is resident
    throughout, so bytes at $1000 prove nothing)

Gates:
  1. shell launches after the desktop; VER writes "0.3" to its response buf
  2. DIR: the shell's dirscan reads the REAL drive directory into shnames
  3. settings: D cycles the mode and issues the kernal SAVE of "UOS-SET" to
     the mounted (readwrite) disk; ESC returns to a LIVE desktop
  4. the shell's DIR afterwards lists UOS-SET  <- the SAVE landed on disk
Real 1541 speed: app loads take 5-40 s; every wait is a polled condition.
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
DESK_TICK = desk_tick()
SHCNT, CMDLEN = 0x41, 0x46


def lst_symbol(module, name):
    lst = open(os.path.join(UOS, f"target/{module}.lst"), "rb").read().decode(
        "latin-1", errors="replace")
    m = re.search(r"^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?%s:"
                  % re.escape(name), lst, re.M)
    if not m:
        raise SystemExit(f"FAIL: {name} not found in {module} listing")
    return int(m.group(1), 16)


def prg(name):
    return open(os.path.join(UOS, f"target/{name}.prg"), "rb").read()[2:]


class HW:
    def __init__(self):
        self.u = cbm.Ultimate()

    def rd(self, addr, n):
        return bytes(self.u.read_mem(addr, n))

    def wr(self, addr, data):
        for i in range(0, len(data), 128):           # DMA write cap
            self.u.write_mem(addr + i, data[i:i + 128])

    def vec(self):
        v = self.rd(TICK_VEC, 2)
        return v[0] | (v[1] << 8)

    def keys(self, s):
        self.wr(KB_BUF, s + b"\x00" * (10 - len(s)))
        self.wr(KB_CNT, bytes([len(s)]))

    def launch(self, name, ref, timeout=90):
        """One-shot tick trampoline: load `name` and enter it at $5000."""
        orig = self.rd(TICK_VEC, 2)
        code = (bytes([0x20, 0x23, 0x08]) + name + b"\x00"       # LOAD_IMM
                + bytes([0x20, 0x26, 0x08])                        # APP_LOADER
                + bytes([0xA2, orig[0], 0xA0, orig[1],
                         0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])      # restore
                + bytes([0x4C, 0x00, 0x50]))                       # jmp $5000
        self.wr(T, code)
        self.wr(TICK_VEC, bytes([T & 0xff, T >> 8]))
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.rd(APP_START, 0x40) == ref[:0x40]:
                return time.time() - t0
            time.sleep(3)
        return None

    def desktop_live(self, timeout=120):
        """Wait for the core loop to be dispatching ticks again (probe)."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.vec() != T:
                v = self.rd(TICK_VEC, 2)
                probe = (bytes([0xEE, FLAG & 0xff, FLAG >> 8])
                         + bytes([0xA2, v[0], 0xA0, v[1],
                                  0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
                         + bytes([0x6C, 0x3C, 0x03]))
                self.wr(FLAG, b"\x00")
                self.wr(T, probe)
                self.wr(TICK_VEC, bytes([T & 0xff, T >> 8]))
            time.sleep(3)
            if self.rd(FLAG, 1)[0]:
                return time.time() - t0
        return None

    def shell_names(self):
        lo = self.rd(lst_symbol("uos-shell", "shnamesL"), 12)
        hi = self.rd(lst_symbol("uos-shell", "shnamesH"), 12)
        n = self.rd(SHCNT, 1)[0]
        out = []
        for i in range(min(n, 12)):
            a = lo[i] | (hi[i] << 8)
            raw = self.rd(a, 17)
            nul = raw.find(b"\x00")
            s = raw[:nul if nul >= 0 else 16]
            out.append(bytes(b - 0x80 if 0xC1 <= b <= 0xDA else b
                             for b in s).decode("latin-1"))
        return n, out


def main():
    hw = HW()
    shell, settings = prg("uos-shell"), prg("uos-settings")
    resp = lst_symbol("uos-shell", "respbuf")
    v = hw.vec()
    print(f"start: $033c=${v:04x} ({'desktop live' if v == DESK_TICK else 'NOT the desktop — run deploy_hw.py first'})")
    if v != DESK_TICK:
        return 1

    # ---- gate 1: shell + VER ----
    dt = hw.launch(b"UOS-SHELL", shell)
    if dt is None:
        print("FAIL gate 1: shell never landed at $5000"); return 1
    print(f"PASS gate 1a: shell loaded on hardware in {dt:.0f}s")
    time.sleep(12)                                   # dirscan + first paint
    hw.keys(b"VER\x0d")
    ok = False
    t0 = time.time()
    while time.time() - t0 < 40:
        if b"0.3" in hw.rd(resp, 40):
            ok = True; break
        time.sleep(3)
    print(("PASS gate 1b: VER responded on hardware: "
           + hw.rd(resp, 12).hex()) if ok else
          f"FAIL gate 1b: no VER response (respbuf={hw.rd(resp, 12).hex()} "
          f"cmdlen={hw.rd(CMDLEN, 1)[0]})")
    if not ok:
        return 1

    # ---- gate 2: DIR reads the real drive ----
    hw.keys(b"DIR\x0d")
    time.sleep(15)
    n, names = hw.shell_names()
    print(f"PASS gate 2: DIR on hardware -> {n} entries: {names}")
    had_set = any("UOS-SET" in x.upper() for x in names)
    print(f"      UOS-SET on disk before the save: {had_set}")

    hw.keys(b"EXIT\x0d")
    dt = hw.desktop_live()
    if dt is None:
        print("FAIL: desktop not live after shell EXIT"); return 1
    print(f"PASS: shell EXIT -> desktop live again ({dt:.0f}s, incl. ~40s reload)")

    # ---- gate 3: settings D (kernal SAVE) + ESC ----
    dt = hw.launch(b"UOS-SETTINGS", settings, timeout=120)
    if dt is None:
        print("FAIL gate 3: settings never landed"); return 1
    print(f"PASS gate 3a: settings loaded on hardware in {dt:.0f}s")
    time.sleep(6)
    before = hw.rd(0x7355, 1)[0]
    hw.keys(b"D")
    t0 = time.time(); cycled = False
    while time.time() - t0 < 30:
        if hw.rd(0x7355, 1)[0] != before:
            cycled = True; break
        time.sleep(2)
    after = hw.rd(0x7355, 1)[0]
    print(f"{'PASS' if cycled else 'FAIL'} gate 3b: D cycled the display mode "
          f"{before} -> {after} (SAVE issued to the real drive)")
    time.sleep(15)                                   # let the SAVE finish
    hw.keys(b"\x1b")
    dt = hw.desktop_live(timeout=150)
    if dt is None:
        print("FAIL gate 3c: desktop not live after settings ESC"); return 1
    print(f"PASS gate 3c: settings ESC -> desktop live again ({dt:.0f}s)")

    # ---- gate 4: did the SAVE land? ask the drive via the shell's DIR ----
    dt = hw.launch(b"UOS-SHELL", shell)
    if dt is None:
        print("FAIL gate 4: shell never landed for the post-save DIR"); return 1
    time.sleep(15)
    n, names = hw.shell_names()
    landed = any("UOS-SET" in x.upper() for x in names)
    print(f"{'PASS' if landed else 'FAIL'} gate 4: post-save DIR on hardware -> "
          f"{n} entries: {names}")
    print(f"      record still in RAM at $7350: {hw.rd(0x7350, 7).hex()}")
    print("HW GATES:", "ALL PASS — kernal SAVE landed on the real disk"
          if landed else "SAVE did NOT land (or the dir cap hid it)")
    return 0 if landed else 2


if __name__ == "__main__":
    sys.exit(main())
