#!/usr/bin/env python3
"""Debug: boot the CI disk and dump the settings-record region."""
import importlib.util
import os
import struct
import subprocess
import time

from importlib.machinery import SourceFileLoader
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(
    importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)

WORK = os.path.join(os.environ.get("TMPDIR", "/tmp"), "uos-ci", "run")
DISK = os.path.join(WORK, "ci.d64")
PORT = 62848

xv = cbm.Xvfb()
env = dict(os.environ, DISPLAY=xv.display,
           __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
emu = subprocess.Popen(
    ["x64", "-default", "-autostart", DISK, "-drive8true",
     "-drive8type", "1541", "-sounddev", "dummy", "-jamaction", "0",
     "-warp", "-autostart-warp", "-binarymonitor",
     "-binarymonitoraddress", f"ip4://127.0.0.1:{PORT}"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
mem = None
for _ in range(160):
    try:
        mem = cbm.ViceMonitor(port=PORT)
        break
    except OSError:
        time.sleep(0.25)

def rd(a, n):
    g = mem.read_mem(a, a + n - 1, memspace=0)
    mem.resume()
    return g

# wait for the desktop code at $1000
desk = open(os.path.expanduser("~/geos128/uos/target/uos-desktop.prg"),
            "rb").read()[2:]
for _ in range(120):
    g = rd(0x1000, 0x20)
    if g == desk[:0x20]:
        break
    time.sleep(2)
time.sleep(3)
print("record region:", rd(0x5800, 8).hex())
print("mode at $5805:", rd(0x5805, 1).hex())
mem.quit_emulator()
xv.stop()