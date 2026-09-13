#!/usr/bin/env python3
"""HW gate: run the calculator on the real C128 (Ultimate II+).

Flow (all on hardware, reusing deploy_hw.py's proven steps):
  1. mount target/ultos.d64 readwrite on drive A
  2. run_prg target/uos.prg -> the core boots and chain-loads
     gfx/vdc/drv1351/sprites/reu/desktop from the disk (~60 s)
  3. DMA-plant a launch stub in the free $7f00 trampoline area:
     jsr LOAD_IMM("UOS-CALC"); jsr APP_LOADER; jmp $5000 — the same
     inline-name pattern the CI trampoline uses, and the same class of
     LOAD-under-tick that probes/savetest proved on hardware
  4. arm the desktop's polled tick vector $033c at the stub; the next
     desktop tick loads the calculator to $5000 and enters it with the
     full OS resident (gfx engine, KEYIN, VDC companion)
  5. verify over DMA: the app image at $5000 matches the build and
     dispbuf == "0" (the calculator's own display buffer)

A bare probe CANNOT run the calculator: it needs the gfx engine and core
exports, so it must be entered with the OS booted — a standalone jmp to
$5000 lands in an environment with no core and crashes before the
display is drawn.
"""
import importlib.util
import os
import sys
import time
from importlib.machinery import SourceFileLoader

_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hwlib  # noqa: E402
from hwlib import desk_tick, lst_symbol  # noqa: E402

UOS = os.path.dirname(os.path.abspath(__file__))
hwlib.UOS = UOS
CALC = open(os.path.join(UOS, "target/uos-calc.prg"), "rb").read()[2:]
DISBUF = lst_symbol("uos-calc", "dispbuf")
STUB = 0x7f00

# jsr LOAD_IMM ($0823) + inline name + jsr APP_LOADER ($0826) + jmp $5000
LAUNCHER = (bytes([0x20, 0x23, 0x08]) + b"UOS-CALC\x00"
            + bytes([0x20, 0x26, 0x08]) + bytes([0x4c, 0x00, 0x50]))


def main():
    ult = cbm.Ultimate()
    print("U2+ version:", ult.version().strip())

    def rd(a, n=1):
        return bytes(ult.read_mem(a, n))       # cbm: (address, length)

    disk = open(os.path.join(UOS, "target/ultos.d64"), "rb").read()
    ult.mount(disk, "a", "d64", "readwrite")
    print(f"mounted target/ultos.d64 ({len(disk)} B) on drive A, readwrite")

    boot = open(os.path.join(UOS, "target/uos.prg"), "rb").read()
    ult.run_prg(boot)
    print("run_prg target/uos.prg: booting uOS from drive A...")

    deadline = time.time() + 240
    tick = 0
    up = False
    while time.time() < deadline:
        vec = rd(0x033c, 2)
        tick = vec[0] | (vec[1] << 8)
        head = rd(0x1000, 16)
        if tick == desk_tick() and head == open(
                os.path.join(UOS, "target/uos-desktop.prg"), "rb").read()[2:18]:
            up = True
            break
        time.sleep(5)
    if not up:
        print(f"FAIL: desktop not live after boot (tick=${tick:04x}, "
              f"$1000={rd(0x1000, 8).hex()})")
        return 1
    print("uOS desktop live on hardware")

    # plant the launcher in the free trampoline area and arm the tick vector
    ult.write_mem(STUB, LAUNCHER)
    got = rd(STUB, len(LAUNCHER))
    if got != LAUNCHER:
        print(f"FAIL: launcher DMA write verify failed ({got.hex()})")
        return 1
    print(f"launcher planted at ${STUB:04x}; arming tick vector $033c")
    ult.write_mem(0x033c, bytes([STUB & 0xff, STUB >> 8]))

    deadline = time.time() + 90
    while time.time() < deadline:
        head = rd(0x5000, 16)
        disp = rd(DISBUF, 2)
        if head == CALC[:16] and disp == b"0\x00":
            print(f"PASS: calculator live on the real C128 (dispbuf='0', "
                  f"image matches at $5000)")
            return 0
        time.sleep(3)
    print(f"FAIL: calculator not live (head={rd(0x5000, 4).hex()}, "
          f"dispbuf={rd(DISBUF, 2).hex()})")
    return 1


if __name__ == "__main__":
    sys.exit(main())