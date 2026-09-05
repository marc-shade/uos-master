#!/usr/bin/env python3
"""Regression proof for the shell key-intake bug (sh_add): load UOS-SHELL
from the desktop, feed E X I T one key at a time, and after each key sample
cmdlen ($46) and cmdbuf. The buffer must accumulate the TYPED CHARACTERS
(45 58 49 54 = "EXIT"); the original sh_add stored the loop index instead
(00 01 02 03), so every command parsed as $00 and nothing ran.
"""
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import re
import time

from importlib.machinery import SourceFileLoader
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)

UOS = os.path.expanduser("~/geos128/uos")
WORK = os.path.join(os.environ.get("TMPDIR", "/tmp"), "uos-ci", "dbg-sx")
PORT = 62844
TICK_VEC = 0x033c
T = 0x7f00  # above every app image; a large LOAD must not clobber this
KB_BUF, KB_CNT = 0x0277, 0xC6
CMDLEN = 0x46


def lst_symbol(module, name):
    """cmdbuf moves whenever the shell source changes — never hardcode it."""
    lst = open(os.path.join(UOS, f"target/{module}.lst"), "rb").read().decode(
        "latin-1", errors="replace")
    m = re.search(r"^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?%s:"
                  % re.escape(name), lst, re.M)
    if not m:
        raise SystemExit(f"FAIL: {name} not found in {module} listing")
    return int(m.group(1), 16)


CMDBUF = lst_symbol("uos-shell", "cmdbuf")
APP_START = 0x5000


class Monitor(cbm.ViceMonitor):
    def write_mem(self, start, data, bank=0, memspace=0):
        body = struct.pack("<BHHBH", 0, start, start + len(data) - 1,
                           memspace, bank) + data
        err, _ = self._recv(self._send(0x02, body))
        if err:
            raise RuntimeError(f"MEM_SET {start:#06x} failed, error {err}")

    def peek(self, start, end):
        got = self.read_mem(start, end, memspace=0)
        self.resume()
        return got


def one_key(mon, ch):
    mon.write_mem(KB_BUF, bytes([ch]) + b"\x00" * 9)
    mon.write_mem(KB_CNT, b"\x01")
    mon.resume()


def main():
    os.makedirs(WORK, exist_ok=True)
    desk = open(os.path.join(UOS, "target/uos-desktop.prg"), "rb").read()[2:]
    shref = open(os.path.join(UOS, "target/uos-shell.prg"), "rb").read()[2:]
    disk = os.path.join(WORK, "dbg.d64")
    shutil.copyfile(os.path.join(UOS, "target/ultos.d64"), disk)

    xv = cbm.Xvfb()
    env = dict(os.environ, DISPLAY=xv.display,
               __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
    emu = subprocess.Popen(
        ["x64", "-default", "-autostart", disk,
         "-drive8true", "-drive8type", "1541",
         "-sounddev", "dummy", "-jamaction", "0",
         "-warp", "-autostart-warp",
         "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{PORT}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    mon = None
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            if emu.poll() is not None:
                raise SystemExit("FAIL: x64 died")
            try:
                mon = Monitor(port=PORT)
                break
            except OSError:
                time.sleep(0.25)

        deadline = time.time() + 300
        while time.time() < deadline:
            if mon.peek(0x1000, 0x103f) == desk[:0x40]:
                break
            time.sleep(2)
        else:
            raise SystemExit("desktop never landed")

        # one-shot trampoline: load UOS-SHELL, restore vector, jmp $5000
        orig = mon.peek(TICK_VEC, TICK_VEC + 1)
        code = (bytes([0x20, 0x23, 0x08]) + b"UOS-SHELL\x00"
                + bytes([0x20, 0x26, 0x08])
                + bytes([0xA2, orig[0], 0xA0, orig[1],
                         0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
                + bytes([0x4C, 0x00, 0x50]))
        mon.write_mem(T, code)
        mon.write_mem(TICK_VEC, struct.pack("<H", T))
        mon.resume()

        deadline = time.time() + 60
        while time.time() < deadline:
            if mon.peek(APP_START, APP_START + 0x3f) == shref[:0x40]:
                break
            time.sleep(2)
        else:
            raise SystemExit("shell never landed")
        print("shell landed; giving refresh/dirscan 10s")
        time.sleep(10)

        def snap(tag):
            cl = mon.peek(CMDLEN, CMDLEN)[0]
            cb = mon.peek(CMDBUF, CMDBUF + 3)
            print(f"  {tag:14s} cmdlen={cl} cmdbuf={cb.hex()}")
            return cl, bytes(cb)

        snap("before keys")
        last = None
        for label, ch in [("E", 0x45), ("X", 0x58), ("I", 0x49), ("T", 0x54)]:
            one_key(mon, ch)
            time.sleep(3)
            last = snap(f"after {label}")
        cl, cb = last
        ok = (cl == 4 and cb == bytes([0x45, 0x58, 0x49, 0x54]))
        print("PASS: cmdbuf holds the typed characters"
              if ok else f"FAIL: cmdbuf={cb.hex()} (expected 45584954)")
        return 0 if ok else 1
    finally:
        if mon:
            try:
                mon.quit_emulator()
            except Exception:
                pass
        emu.terminate()
        xv.stop()


if __name__ == "__main__":
    sys.exit(main())
