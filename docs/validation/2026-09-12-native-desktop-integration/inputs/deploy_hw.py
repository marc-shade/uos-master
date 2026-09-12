#!/usr/bin/env python3
"""Deploy uOS to the real C128 (Ultimate II+ at 192.168.1.237) and verify.

    1. mount target/ultos.d64 on drive A (readwrite: the settings app's kernal
       SAVE writes to it — that disk landing is the hardware gate)
    2. POST target/uos.prg to runners:run_prg — RESETS the machine into C64
       mode and runs the boot stub; the core then loads gfx/vdc/drv1351/
       sprites/reu/desktop from the mounted disk (real 1541 speed, ~40 s+)
    3. verify over DMA readmem, memory-side (the desktop is a bitmap, so the
       40-col text RAM says nothing): the desktop image must land at $1000,
       the APP_TICK vector at $033c must be the desktop's, and the pointer
       sprite (VIC $d000/$d001) is read twice so a moving 1351 shows up

Exit 0 = desktop verified on hardware. Uses cbm's verified Ultimate client.
"""
import importlib.util
import os
import sys
import time

from importlib.machinery import SourceFileLoader
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)
from hwlib import desk_tick, lst_symbol as _lst

UOS = os.path.dirname(os.path.abspath(__file__))
DISK = os.path.join(UOS, "target/ultos.d64")
BOOT = os.path.join(UOS, "target/uos.prg")
DESK = open(os.path.join(UOS, "target/uos-desktop.prg"), "rb").read()[2:]


def hexs(b):
    return bytes(b).hex()


def main():
    ult = cbm.Ultimate()
    print("U2+ version:", ult.version())

    disk = open(DISK, "rb").read()
    ult.mount(disk, "a", "d64", "readwrite")
    print(f"mounted {DISK} ({len(disk)} B) on drive A, readwrite")

    boot = open(BOOT, "rb").read()
    ult.run_prg(boot)
    print(f"run_prg {BOOT} ({len(boot)} B): machine reset into C64 mode, "
          f"booting uOS from drive A")

    # Boot chain: real hardware has no warp, and the kernal LOAD streams the
    # desktop into $1000 sequentially over ~30-40 s, so the FIRST bytes match
    # long before the image is complete or the desktop entry has run. Wait
    # for the whole image (only runtime data may differ) AND for the desktop
    # to have registered its APP_TICK vector — that is the entry having run.
    deadline = time.time() + 240
    t0 = time.time()
    up = False
    diffs = []
    tick = 0
    while time.time() < deadline:
        full = bytes(ult.read_mem(0x1000, len(DESK)))
        diffs = [i for i in range(len(DESK)) if full[i] != DESK[i]]
        vec = bytes(ult.read_mem(0x033c, 2))
        tick = vec[0] | (vec[1] << 8)
        if tick == desk_tick() and len(diffs) < 64:
            up = True
            break
        time.sleep(5)
    dt = time.time() - t0
    if not up:
        print(f"FAIL: desktop not live after {dt:.0f}s "
              f"(image diffs={len(diffs)}, $033c=${tick:04x}); "
              f"$1000 now = {hexs(ult.read_mem(0x1000, 16))}")
        print("40-col text RAM (may be bitmap garbage):")
        print(ult.screen())
        return 1
    print(f"PASS: desktop image complete at $1000 and entry ran, {dt:.0f}s "
          f"after run_prg ({len(diffs)} runtime byte(s) differ: "
          f"{[hex(0x1000 + d) for d in diffs[:6]]})")
    print(f"      APP_TICK vector $033c = ${tick:04x} "
          f"({'desktop APP_TICK' if tick == desk_tick() else 'UNEXPECTED'})")
    ctl = ult.read_mem(0x9000, 1)[0]
    print(f"      APP_CTL_CTR $9000 = {ctl} registered controls")

    # pointer sprite: two reads a few seconds apart; a moving mouse changes it
    p1 = bytes(ult.read_mem(0xd000, 2))
    time.sleep(5)
    p2 = bytes(ult.read_mem(0xd000, 2))
    print(f"      sprite0 x/y: {hexs(p1)} -> {hexs(p2)} "
          f"({'moved' if p1 != p2 else 'static'})")
    return 0 if tick == desk_tick() else 2


if __name__ == "__main__":
    sys.exit(main())
