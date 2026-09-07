#!/usr/bin/env python3
"""Hardware regression test: the user-selected background colour must survive
a reboot.  Runs on the real C128 + Ultimate II+ (192.168.1.237).

Flow (all on hardware, no emulator):
  1. mount a fresh ultos.d64 read-write (it ships with NO UOS-SET).
  2. run probes/savetest.prg — it LOADs the real UOS-SETTINGS app, sets the
     background to purple ($04) and calls the app's real save_record ($56eb),
     which kernal-SAVEs "UOS-SET" to the mounted disk, then reloads it to
     prove the write landed.
  3. wipe $7356 (SETREC_BG) and the whole colour matrix $8400-$87ff to a $99
     sentinel, so leftover RAM cannot masquerade as a successful load.
  4. reboot uOS from the same mounted image and wait for VDPREF to change the
     $7356 sentinel — proving it read UOS-SET back off the disk — and for
     DESK_START to paint the colour matrix with the saved colour.

Scope note: this exercises a WARM reboot with the image staying mounted. A
full power cycle additionally depends on the U2+ writing the change back to
the SD-card .d64 and auto-mounting it at power-up, which this cannot drive
remotely (it mounts an uploaded image, not an SD file).
"""
import importlib.util, os, subprocess, sys, time, urllib.request
from importlib.machinery import SourceFileLoader
from collections import Counter

UOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = "192.168.1.237"
_l = SourceFileLoader("cbm", os.path.expanduser("~/.claude/skills/commodore-basic/bin/cbm"))
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _l)); _l.exec_module(cbm)

def main():
    # assemble the probe fresh (no committed .prg artifact)
    subprocess.run(["64tass", "-a", "probes/savetest.asm", "-o", "probes/savetest.prg"],
                   cwd=UOS, check=True, capture_output=True)
    u = cbm.Ultimate()
    def rd(a, n=1): return u.read_mem(a, n)
    def wr(a, d):
        d = bytes(d)
        for k in range(0, len(d), 128): u.write_mem(a + k, d[k:k+128])
    def put(ep):
        try:
            urllib.request.urlopen(urllib.request.Request(f"http://{HOST}/v1/"+ep, method="PUT"), timeout=15).read()
        except Exception:
            pass

    # recover the U2+ from any prior stressed state, then mount fresh
    put("drives/a:remove"); time.sleep(2)
    put("machine:reset");   time.sleep(8)
    u.mount(open(f"{UOS}/target/ultos.d64", "rb").read(), "a", "d64", "readwrite"); time.sleep(2)

    # 1+2: save UOS-SET(bg=purple) via the real save_record, verify the write landed
    u.write_mem(0xc800, b"\x00\x00\x00"); u.write_mem(0xc810, b"\x00")
    u.run_prg(open(f"{UOS}/probes/savetest.prg", "rb").read())
    for _ in range(30):
        time.sleep(1)
        if rd(0xc801, 1)[0] == 0xaa: break
    else:
        print("FAIL: savetest never signalled done"); return 1
    status, bg = rd(0xc810, 1)[0], rd(0xc800, 1)[0]
    if not (status == 1 and bg == 4):
        print(f"FAIL: save round-trip did not land (status=${status:02x} bg={bg}, want status=1 bg=4)"); return 1
    print("save: real save_record wrote UOS-SET(bg=4) to the mounted disk and reloaded it")
    time.sleep(3)

    # 3: sentinels
    u.write_mem(0x7356, b"\x99"); wr(0x8400, b"\x99" * 0x400)

    # 4: warm reboot, wait for VDPREF to read UOS-SET back off the disk
    u.run_prg(open(f"{UOS}/target/uos.prg", "rb").read())
    for _ in range(60):
        time.sleep(2)
        if rd(0x7356, 1)[0] != 0x99: break
    time.sleep(4)
    bg2 = rd(0x7356, 1)[0]
    dom = Counter(b & 0x0f for b in rd(0x8400, 0x400)).most_common(1)[0][0]
    if bg2 == 4 and dom == 4:
        print(f"PASS: after reboot VDPREF loaded bg=4 from disk and DESK_START painted it (matrix nibble={dom})")
        return 0
    if bg2 == 0x99:
        print("FAIL: boot did not reach VDPREF/DESK_START (U2+ may need a longer recovery); rerun"); return 1
    print(f"FAIL: colour did not persist (SETREC_BG={bg2}, matrix nibble={dom}; 3=cyan default means the record was not found)")
    return 1

if __name__ == "__main__":
    sys.exit(main())
