#!/usr/bin/env python3
"""Debug: launch uos-calc on x64, inject single keys, watch the state."""
import os
import struct
import subprocess
import sys
import time

UOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(UOS, "tests/ci_fm.py")).read()
exec(src[:src.index("def main():")])
import shutil


def launch(mon, name):
    vec = mon.read_mem(TICK_VEC, TICK_VEC + 1, memspace=0); mon.resume()
    tr = (bytes([0x20, 0x23, 0x08]) + name + b"\x00" + bytes([0x20, 0x26, 0x08])
          + bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
          + bytes([0x4C, 0x00, 0x50]))
    mon.write_mem(TRAMPOLINE, tr); mon.write_mem(TICK_VEC, struct.pack("<H", TRAMPOLINE)); mon.resume()


def zp_symbol(module, name):
    lst = open(os.path.join(UOS, f"target/{module}.lst"), "rb").read().decode(
        "latin-1", errors="replace")
    m = re.search(r"^=\$?([0-9a-fA-F]{2,4})\s+[^\n]*\b%s\s*=" % re.escape(name), lst, re.M)
    if not m:
        raise SystemExit(f"FAIL: {name} EQU not found in {module} listing")
    return int(m.group(1), 16)


def main():
    global emu
    os.makedirs(WORK, exist_ok=True)
    DISK = os.path.join(WORK, "dbg_calc.d64")
    shutil.copyfile(STOCK, DISK)
    DISBUF = lst_symbol("uos-calc", "dispbuf")
    Z = {n: zp_symbol("uos-calc", "c_" + n) for n in
         ("acc", "ent", "elen", "pen", "fresh", "err", "tmp", "tmp2", "opkey")}
    print("ZP:", {k: hex(v) for k, v in Z.items()})

    xv = cbm.Xvfb()
    env = dict(os.environ, DISPLAY=xv.display, __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
    emu = subprocess.Popen(
        ["x64", "-default", "-autostart", DISK, "-drive8true", "-drive8type", "1541",
         "-sounddev", "dummy", "-jamaction", "0", "-warp", "-autostart-warp",
         "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{PORT}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    try:
        mon = None
        dl = time.time() + 60
        while time.time() < dl:
            try:
                mon = Monitor(port=PORT); break
            except OSError:
                time.sleep(0.25)
        assert wait_desktop_live(mon, 300), "desktop never live"
        launch(mon, b"UOS-CALC")
        dl = time.time() + 60
        while time.time() < dl:
            b = bytes(mon.read_mem(APP_START, APP_START + 15, memspace=0)); mon.resume()
            if bytes(b) == open(os.path.join(UOS, "target/uos-calc.prg"), "rb").read()[2:18]:
                break
            time.sleep(2)
        time.sleep(4)

        def state():
            acc = struct.unpack("<H", bytes(mon.read_mem(Z["acc"], Z["acc"] + 1, memspace=0)))[0]
            ent = struct.unpack("<H", bytes(mon.read_mem(Z["ent"], Z["ent"] + 1, memspace=0)))[0]
            elen = bytes(mon.read_mem(Z["elen"], Z["elen"], memspace=0))[0]
            pen = bytes(mon.read_mem(Z["pen"], Z["pen"], memspace=0))[0]
            fresh = bytes(mon.read_mem(Z["fresh"], Z["fresh"], memspace=0))[0]
            err = bytes(mon.read_mem(Z["err"], Z["err"], memspace=0))[0]
            disp = bytes(mon.read_mem(DISBUF, DISBUF + 7, memspace=0)); mon.resume()
            return (f"acc={acc} ent={ent} elen={elen} pen={chr(pen) if pen else 0} "
                    f"fresh={fresh} err={err} disp={disp!r}")

        # IRQ-clobber test: write a sentinel to $4a, wait, read it back
        mon.write_mem(Z["tmp2"], b"\xaa"); mon.resume()
        time.sleep(2)
        x = bytes(mon.read_mem(Z["tmp2"], Z["tmp2"], memspace=0))[0]
        print("IRQ sentinel @tmp2: wrote aa, read", hex(x), flush=True)
        # where is the CPU? sample PC 5x
        pcs = []
        for _s in range(5):
            err, body = mon._recv(mon._send(0x31, b"\x00")); mon.resume()
            n = struct.unpack("<H", body[0:2])[0]; off = 2
            pc = None
            for _i in range(n):
                if body[off + 1] == 3:
                    pc = struct.unpack("<H", body[off+2:off+4])[0]
                off += 1 + body[off]
            pcs.append(hex(pc) if pc else "?")
            time.sleep(0.3)
        print("PC samples:", pcs, flush=True)
        print("initial:", state())
        inject_keys(mon, b"5")
        time.sleep(4)
        t2 = bytes(mon.read_mem(Z["tmp2"], Z["tmp2"], memspace=0))[0]
        print("after '5':", state(), " tmp2(byte)=", t2)
        pcs2 = []
        for _s in range(6):
            err, body = mon._recv(mon._send(0x31, b"\x00")); mon.resume()
            n = struct.unpack("<H", body[0:2])[0]; off = 2
            pc = None
            for _i in range(n):
                if body[off + 1] == 3:
                    pc = struct.unpack("<H", body[off+2:off+4])[0]
                off += 1 + body[off]
            pcs2.append(hex(pc) if pc else "?")
            time.sleep(0.3)
        print("PC after '5':", pcs2, flush=True)
        inject_keys(mon, b"7")
        time.sleep(4)
        zp = bytes(mon.read_mem(0x40, 0x4f, memspace=0)); mon.resume()
        print("after '7':", state(), " ZP40-4f:", zp.hex(), flush=True)
        r = mon.regs() if hasattr(mon, "regs") else None
        if r:
            print("regs:", {k: hex(v) for k, v in r.items()} if isinstance(r, dict) else r, flush=True)
        inject_keys(mon, b"+")
        time.sleep(4)
        print("after '+':", state())
    finally:
        emu.terminate()
        xv.stop()


main()