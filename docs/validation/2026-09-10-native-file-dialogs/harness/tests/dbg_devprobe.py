#!/usr/bin/env python3
"""Run probes/devprobe.prg in x64 (drive 8 attached) and report how the
serial bus reports an absent device 9 (OPEN vs TALK/TKSA + READST)."""
import os
import shutil
import subprocess
import sys
import time

from importlib.machinery import SourceFileLoader
import importlib.util

UOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(os.environ.get("TMPDIR", "/tmp"), "uos-ci", "devprobe")
STOCK = os.path.join(UOS, "target/ultos.d64")
os.makedirs(WORK, exist_ok=True)
DISK = os.path.join(WORK, "dbg8.d64")
shutil.copyfile(STOCK, DISK)
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)
src = open(os.path.join(UOS, "tests/ci_fm.py")).read()
exec(src[:src.index("def main():")])

xv = cbm.Xvfb()
env = dict(os.environ, DISPLAY=xv.display, __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
p = subprocess.Popen(
    ["x64", "-default", "-autostart", DISK, "-drive8true", "-drive8type", "1541",
     "-sounddev", "dummy", "-jamaction", "0", "-warp", "-autostart-warp",
     "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{PORT}"],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
try:
    mon = None
    dl = time.time() + 60
    while time.time() < dl:
        if p.poll() is not None:
            out, err = p.communicate()
            raise SystemExit(f"x64 exited rc={p.returncode}: "
                             f"{err.decode(errors='replace')[:600]}")
        try:
            mon = Monitor(port=PORT); break
        except OSError:
            time.sleep(0.5)
    assert mon is not None, "monitor never connected"
    time.sleep(2)   # BASIC prompt
    prg = open(os.path.join(UOS, "probes/devprobe.prg"), "rb").read()
    mon.write_mem(0x0801, prg[2:]); mon.resume()
    time.sleep(1)
    # type RUN via the kernal keyboard buffer (C64: $0277/$c6)
    mon.write_mem(0x0277, b"RUN\r")
    mon.write_mem(0x00c6, bytes([4])); mon.resume()
    time.sleep(6)
    r = bytes(mon.read_mem(0x0700, 0x0704, memspace=0)); mon.resume()
    print(f"OPEN carry (A=1+c): {r[0]}  ST after OPEN(9): ${r[1]:02x}  "
          f"kernal $0291 was: ${r[2]:02x}")
    print(f"TALK absent dev9 ST: ${r[3]:02x}   TALK present dev8 ST: ${r[4]:02x}")
finally:
    if p.poll() is None:
        p.terminate()
    xv.stop()