#!/usr/bin/env python3
"""Debug: drive the COPY action and dump fmgr state around the failure."""
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import time

from importlib.machinery import SourceFileLoader
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(
    importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)

UOS = os.path.expanduser("~/geos128/uos")
WORK = os.path.join(os.environ.get("TMPDIR", "/tmp"), "uos-ci", "dbg")
PORT = 62842
APP_START = 0x5000
KB_BUF, KB_CNT = 0x0277, 0xC6
TRAMPOLINE = 0x6f00
TICK_VEC = 0x033c
FMROW, FMCNT = 0x40, 0x41
import re as _re
def _lst_addr(label):
    lst = open(os.path.join(UOS, "target/uos-fmgr.lst"),
               "rb").read().decode("latin-1", "replace")
    m = _re.search(r"^>([0-9a-fA-F]+)\s+(?:[0-9a-fA-F]{2} ?)+\s*%s:" % label,
                   lst, _re.M)
    if not m:
        raise SystemExit(f"listing: {label} not found")
    return int(m.group(1), 16)
NAMES_L, NAMES_H = _lst_addr("fmnamesL"), _lst_addr("fmnamesH")
try:
    FNBUF2, FNCMD, LINEBUF, ERRTAG = (
        _lst_addr(x) for x in ("fnbuf2", "fncmd", "linebuf", "errtag"))
except SystemExit:
    FNBUF2 = FNCMD = LINEBUF = ERRTAG = 0x6f00
STOCK = os.path.join(UOS, "target/ultos.d64")


class Monitor(cbm.ViceMonitor):
    def write_mem(self, start, data, bank=0, memspace=0):
        body = struct.pack("<BHHBH", 0, start, start + len(data) - 1,
                           memspace, bank) + data
        err, _ = self._recv(self._send(0x02, body))
        assert not err, f"MEM_SET failed {err}"


def rd(mem, addr, n):
    g = mem.read_mem(addr, addr + n - 1, memspace=0)
    mem.resume()
    return g


def keys(mem, k):
    mem.write_mem(KB_BUF, k + b"\x00" * (10 - len(k)))
    mem.write_mem(KB_CNT, bytes([len(k)]))
    mem.resume()


def inject(mem, k):
    mem.write_mem(KB_BUF, k + b"\x00" * (10 - len(k)))
    mem.write_mem(KB_CNT, bytes([len(k)]))
    mem.resume()


def make_trampoline(orig):
    return (bytes([0x20, 0x23, 0x08]) + b"UOS-FMGR\x00"
            + bytes([0x20, 0x26, 0x08])
            + bytes([0xA2, orig[0], 0xA0, orig[1]])
            + bytes([0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
            + bytes([0x4C, 0x00, 0x50]))


def main():
    os.makedirs(WORK, exist_ok=True)
    DISK = os.path.join(WORK, "ci.d64")
    shutil.copyfile(STOCK, DISK)
    xv = cbm.Xvfb()
    env = dict(os.environ, DISPLAY=xv.display,
               __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
    emu = subprocess.Popen(
        ["x64", "-default", "-autostart", DISK, "-drive8true",
         "-drive8type", "1541", "-sounddev", "dummy", "-jamaction", "0",
         "-warp", "-autostart-warp",
         "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{PORT}"],
        stdout=open(os.path.join(WORK,"vice.log"),"w"), env=env)
    mem = None
    try:
        for _ in range(200):
            try:
                mem = Monitor(port=PORT)
                break
            except OSError:
                time.sleep(0.25)
        # wait desktop
        desk = open(os.path.join(UOS, "target/uos-desktop.prg"), "rb").read()[2:]
        for _ in range(100):
            g = rd(mem, 0x1000, 0x20)
            if g == desk[:0x20]:
                break
            time.sleep(2)
        time.sleep(3)
        ov = rd(mem, TICK_VEC, 2)
        mem.write_mem(TRAMPOLINE, make_trampoline(ov))
        mem.write_mem(TICK_VEC, struct.pack("<H", TRAMPOLINE))
        mem.resume()
        fm = open(os.path.join(UOS, "target/uos-fmgr.prg"), "rb").read()[2:]
        for _ in range(100):
            g = rd(mem, 0x5000, 0x20)
            if g == fm[:0x20]:
                break
            time.sleep(2)
        time.sleep(8)   # dirscan + paint

        print("state after launch:")
        print("  row/cnt/state/mode/gllen:", rd(mem, FMROW, 6).hex())
        cnt = rd(mem, FMCNT, 1)[0]
        print("  files:", [rd(mem, (rd(mem, NAMES_L+i,1)[0] |
                     rd(mem, NAMES_H+i,1)[0]<<8), 12).split(b'\x00')[0]
                     for i in range(cnt)])

        def row_of(name):
            for _ in range(30):
                c = rd(mem, FMCNT, 1)[0]
                rows = []
                for i in range(c):
                    a = rd(mem, NAMES_L+i,1)[0] | rd(mem, NAMES_H+i,1)[0] << 8
                    rows.append(rd(mem, a, 16).split(b"\x00")[0])
                import re as _re2
                for i, r in enumerate(rows):
                    norm = bytes(b - 0x80 if 0xC1 <= b <= 0xDA else b
                                 for b in r)
                    if norm.startswith(bytes(b - 0x80 if 0xC1 <= b <= 0xDA
                                             else b for b in name)):
                        return i
                time.sleep(2)
            raise SystemExit("not listed")

        # navigate to UOS-SETTINGS (row 1)
        tgt = row_of(b"C-T")
        print("  target row:", tgt, "current row:", rd(mem, FMROW,1)[0])
        for _ in range(30):
            if rd(mem, FMROW,1)[0] == tgt:
                break
            r = rd(mem, FMROW,1)[0]
            keys(mem, b"\x11" if r < tgt else b"\x91")
            time.sleep(1.5)
        print("  at row:", rd(mem, FMROW,1)[0])

        keys(mem, b"R")
        time.sleep(2)
        print("post-refresh rowi(0x42) should==fmcnt(0x41):",
              rd(mem, 0x41, 2).hex())
        # bitmap bytes under the first list row (y=40..47, x=24..80):
        # bitmap base $a000, row y=40 -> char row 5
        import struct as _s2
        bm = rd(mem, 0xa000 + 8*320 + 3, 12)
        print("bitmap bytes row y64 x24-39:", bm.hex())
        bm0 = rd(mem, 0xb000 + 5*320 + 2, 40)
        print("b000 row0 (y40) x16-55:", bm0.hex())
        bm2 = rd(mem, 0xb000 + 8*320 + 3, 12)
        print("b000 row2 (y64):", bm2.hex())
        # color matrix for rows 5-8 (y40-71), cols 3-5: hires screen at $8400
        print("VIC d011/d018/dd00:", rd(mem, 0xd011, 1).hex(),
              rd(mem, 0xd018, 1).hex(), rd(mem, 0xdd00, 1).hex())
        cl = rd(mem, 0x8400 + 5*40 + 3, 4*(40)+8)
        print("hires screen-matrix bytes rows5-8:", cl[:48].hex())
        print("after C: state/mode/gllen:", rd(mem, 0x44, 3).hex())
        print("  status line:", rd(mem, LINEBUF, 30))
        keys(mem, b"CI-RN")
        time.sleep(2)
        print("after typing: gllen", rd(mem, 0x46,1)[0],
              " fnbuf2:", rd(mem, FNBUF2, 8))
        print("  editor line:", rd(mem, LINEBUF, 30))
        keys(mem, b"\x0d")
        time.sleep(10)
        
        time.sleep(10)
        print("kernal ST $90:", hex(rd(mem, 0x90, 1)[0]))
        print("marker (0x11 src/0x22 dst/0x33 chkin):", hex(rd(mem, 0x49, 1)[0]), "rowi:", rd(mem, 0x42, 1)[0])
        c = rd(mem, 0x41, 1)[0]
        for i in range(c):
            a = rd(mem, NAMES_L+i,1)[0] | rd(mem, NAMES_H+i,1)[0] << 8
            print("  raw row", i, rd(mem, a, 12).hex())
        import struct as _s
        _err, _body = mem._recv(mem._send(0x31, b"\x00"))
        print("regs body (PC at offset?):", _body[:16].hex() if _body else _body)
        print("after RETURN: state", rd(mem, 0x44, 6).hex())
        print("  fncmd:", rd(mem, FNCMD, 32))
        print("  linebuf:", rd(mem, LINEBUF, 40))
        print("  errtag(1=srcopen 2=dstopen):", rd(mem, ERRTAG, 1)[0])
        print("  counts:", rd(mem, FMROW, 2).hex())
        cnt = rd(mem, FMCNT, 1)[0]
        rows = []
        for i in range(cnt):
            a = rd(mem, NAMES_L+i,1)[0] | rd(mem, NAMES_H+i,1)[0] << 8
            rows.append(rd(mem, a, 16).split(b"\x00")[0])
        print("  files:", rows)
        subprocess.run(["magick", "import", "-display", xv.display,
                        "-window", "root", os.path.join(WORK, "dbg.png")],
                       check=True)
    finally:
        if mem:
            try:
                mem.quit_emulator()
            except Exception:
                emu.kill()
        else:
            emu.kill()
        xv.stop()


if __name__ == "__main__":
    main()

def read_regs(mem):
    import struct as _s
    err, body = mem._recv(mem._send(0x31, b"\x00"))  # REGS GET, memspace 0
    mem.resume()
    return body
