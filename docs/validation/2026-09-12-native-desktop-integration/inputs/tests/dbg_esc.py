#!/usr/bin/env python3
"""Probe: does the core's esc_to_desk path kill the main loop?

Hypothesis (session 2026-09-05): esc_to_desk ends `jmp DESK_START` at
main-loop stack base; the reloaded desktop's final RTS then pops an empty
stack, the PC flies into garbage, and the core loop (with its once-per-
second `jmp ($033c)` TICK dispatch) never runs again.  This is why the
PASS-10 shell trampoline never fires: nothing dispatches it.

Design: a tick PROBE (inc a flag, restore vector, continue into the real
handler) installed at the pristine desktop must fire (CONTROL).  After an
injected ESC the same probe must fire again (TREATMENT) IF the fix holds.
Regression gate: exit 0 = fix holds (tick alive after ESC), exit 1 = the
stack-underflow regressed (tick dead).  The bug this guards: DESK_START
must reset the stack (ldx #$ff / txs) and end in `jmp MAINLOOP`, never RTS.
"""
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import time

from importlib.machinery import SourceFileLoader
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)

UOS = os.path.expanduser("~/geos128/uos")
WORK = os.path.join(os.environ.get("TMPDIR", "/tmp"), "uos-ci", "dbg-esc")
PORT = 62842
TICK_VEC = 0x033c
PROBE = 0x7f00
FLAG = 0x7fff
KB_BUF, KB_CNT = 0x0277, 0xC6


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

    def regs(self):
        err, body = self._recv(self._send(0x31, b"\x00"))
        self.resume()
        n = struct.unpack("<H", body[0:2])[0]
        out, off = {}, 2
        for _ in range(n):
            size = body[off]
            rid = body[off + 1]
            val = struct.unpack("<H", body[off + 2:off + 4])[0]
            out[rid] = val
            off += 1 + size
        return out  # VICE 6502 ids: 0=A 1=X 2=Y 3=PC 4=SP 5=FLAGS


def install_probe(mon):
    vec = mon.peek(TICK_VEC, TICK_VEC + 1)
    probe = (bytes([0xEE, 0xFF, 0x7F])            # inc $6fff
             + bytes([0xA2, vec[0], 0xA0, vec[1]])  # ldx/ldy #orig
             + bytes([0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])  # restore vec
             + bytes([0x6C, 0x3C, 0x03]))         # jmp ($033c) -> real handler
    mon.write_mem(FLAG, b"\x00")
    mon.write_mem(PROBE, probe)
    mon.write_mem(TICK_VEC, struct.pack("<H", PROBE))
    mon.resume()
    return vec


def probe_fired(mon, secs):
    deadline = time.time() + secs
    while time.time() < deadline:
        if mon.peek(FLAG, FLAG)[0]:
            return True
        time.sleep(1)
    return False


def sample_pc(mon, n, gap=0.5):
    out = []
    for _ in range(n):
        out.append(mon.regs().get(3))
        time.sleep(gap)
    return out


def main():
    os.makedirs(WORK, exist_ok=True)
    desk_ref = open(os.path.join(UOS, "target/uos-desktop.prg"), "rb").read()[2:]
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
                raise SystemExit("FAIL: x64 died at startup")
            try:
                mon = Monitor(port=PORT)
                break
            except OSError:
                time.sleep(0.25)

        deadline = time.time() + 300
        up = False
        while time.time() < deadline:
            if mon.peek(0x1000, 0x103f) == desk_ref[:0x40]:
                up = True
                break
            time.sleep(2)
        assert up, "desktop never landed at $1000"
        print("boot: desktop at $1000")
        print("PC samples pre-ESC :", [hex(p) for p in sample_pc(mon, 5)])

        vec = install_probe(mon)
        ctl = probe_fired(mon, 20)
        print(f"CONTROL  tick-probe fired at pristine desktop: {ctl} "
              f"(orig vec {vec.hex()})")
        assert ctl, "control failed: tick probe did not fire at a healthy desktop"

        mon.write_mem(KB_BUF, b"\x1b" + b"\x00" * 9)
        mon.write_mem(KB_CNT, b"\x01")
        mon.resume()
        print("ESC injected; waiting out the desktop reload...")
        time.sleep(25)
        redesk = mon.peek(0x1000, 0x103f) == desk_ref[:0x40]
        print(f"desktop bytes intact after ESC: {redesk}")
        print("PC samples post-ESC:", [hex(p) for p in sample_pc(mon, 10)])

        vec = install_probe(mon)
        trt = probe_fired(mon, 20)
        print(f"TREATMENT tick-probe fired after core-ESC reload: {trt} "
              f"(vec before probe {vec.hex()})")
        if trt:
            print("PASS: tick dispatch alive after core ESC reload — the "
                  "esc_to_desk stack-underflow fix holds")
            return 0
        print("FAIL: tick dead after ESC — esc_to_desk left the main loop "
              "on an empty stack (regression of the DESK_START txs+MAINLOOP fix)")
        return 1
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
