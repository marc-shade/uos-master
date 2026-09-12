#!/usr/bin/env python3
"""Hardware check of the RUN/STOP -> ESC alias in KEYIN_EXT: open the file
manager through the tick vector, drop $03 into the kernal keyboard buffer
over DMA (a real RUN/STOP press lands there the same way), and prove the
desktop owns the main loop again by running the VDC dump (it only executes
from the desktop's MAINLOOP) and reading "desktop" on row 2.
The C128 ESC key itself (extended matrix) needs a finger: KEY_EXTSEEN at
$9e0c is printed so a later read after a real press can confirm it."""
import importlib.util, os, struct, sys, time
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _l)); _l.exec_module(cbm)
UOS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, UOS)
import hwlib
TICK_VEC, TRAMP = 0x033C, 0x7F00
u = cbm.Ultimate()
vec = u.read_mem(TICK_VEC, 2)
assert vec != b"\x00\x00", "desktop not live"
fm = open(os.path.join(UOS, "target/uos-fmgr.prg"), "rb").read()[2:]
straddr = TRAMP + 24
t = (bytes([0xA9, straddr & 0xff, 0x85, 0x02, 0xA9, straddr >> 8, 0x85, 0x03]) + bytes([0x20, 0x29, 0x08])
     + bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03]) + bytes([0x4C, 0x32, 0x08]) + b"UOS-FMGR\x00")
u.write_mem(TRAMP, t)
u.write_mem(TICK_VEC, struct.pack("<H", TRAMP))
for _ in range(40):
    time.sleep(3)
    if u.read_mem(0x5000, 32) == fm[:32] and u.read_mem(TICK_VEC, 2) == vec:
        break
else:
    sys.exit("FAIL: file manager never loaded at $5000")
# its directory scan on the real 1541 takes 10-30 s and does not poll the
# keyboard: wait for the entry count ($41) to settle before pressing
last, stable = None, 0
for _ in range(40):
    time.sleep(3)
    cnt = u.read_mem(0x41, 1)[0]
    stable = stable + 1 if cnt and cnt == last else 0
    last = cnt
    if stable >= 2:
        break
print(f"file manager running at $5000 with {last} entries; KEY_EXTSEEN before =", u.read_mem(0x9e0c, 1).hex())
u.write_mem(0x0277, b"\x03")
u.write_mem(0x00c6, b"\x01")
for _ in range(20):
    time.sleep(2)
    if u.read_mem(0x00c6, 1) == b"\x00":
        break
else:
    sys.exit("FAIL: the kernal buffer still holds the key: nothing is polling KEYIN")
time.sleep(8)            # the desktop reload from the real drive
print("RUN/STOP ($03) consumed; running hw_vdc_check (works only from the desktop main loop)")
r = os.system(f"python3 {os.path.join(UOS, 'hw_vdc_check.py')}")
print("PASS: RUN/STOP alias left the file manager (desktop dispatching)" if r == 0 else "FAIL: desktop not back after RUN/STOP")
sys.exit(0 if r == 0 else 1)
