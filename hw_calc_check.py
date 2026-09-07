#!/usr/bin/env python3
"""HW gate: run the calculator on the real C128 (Ultimate II+).

Follows the proven deploy_hw.py flow exactly: mount target/ultos.d64 on
drive A readwrite, then run_prg a boot stub that LOADs UOS-CALC from the
disk (standalone PRG — the tick trampoline does not reliably fire on
hardware) and enters it at $5000. The host verifies over DMA that the app
image landed at $5000 and drew its initial "0" display.

No drive-type switching or drive remove/reset here: that REST dance is
what wedges the U2+ and leaves LOAD with "device not present" ($20).
Drive A's persisted type is 1541 (deploy_hw.py's LOADs prove it).

Typed-key arithmetic still needs a hand on the keyboard — documented
limitation; the arithmetic is emulator-verified by tests/ci_calc.py.
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
from hwlib import lst_symbol  # noqa: E402

UOS = os.path.dirname(os.path.abspath(__file__))
hwlib.UOS = UOS
CALC = open(os.path.join(UOS, "target/uos-calc.prg"), "rb").read()[2:]
DISBUF = lst_symbol("uos-calc", "dispbuf")

subprocess_ok = True
import subprocess  # noqa: E402

subprocess.run(["64tass", "-a", os.path.join(UOS, "probes/hwcalc.asm"),
                "-o", os.path.join(UOS, "probes/hwcalc.prg")], check=True,
               capture_output=True)
PRG = open(os.path.join(UOS, "probes/hwcalc.prg"), "rb").read()

ult = cbm.Ultimate()
print("U2+ version:", ult.version().strip())

disk = open(os.path.join(UOS, "target/ultos.d64"), "rb").read()
ult.mount(disk, "a", "d64", "readwrite")
print(f"mounted target/ultos.d64 ({len(disk)} B) on drive A, readwrite")

ult.run_prg(PRG)
print("hwcalc PRG: LOAD UOS-CALC + jmp $5000; waiting for boot...")

ok = False
dl = time.time() + 180
while time.time() < dl:
    head = bytes(ult.read_mem(0x5000, 0x500f))
    disp = bytes(ult.read_mem(DISBUF, DISBUF + 1))
    if head == CALC[:16] and disp == b"0\x00":
        ok = True
        break
    time.sleep(5)

if not ok:
    err = bytes(ult.read_mem(0x0700, 0x0700))[0]
    print(f"FAIL: calculator not live (head={bytes(ult.read_mem(0x5000, 4)).hex()}, "
          f"LOADERR={err:#x})")
    sys.exit(1)

print(f"PASS: calculator live on the real C128 (dispbuf={disp!r}, "
      f"image matches at $5000)")
sys.exit(0)