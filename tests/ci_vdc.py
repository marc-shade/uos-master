#!/usr/bin/env python3
"""CI for the 80-column companion display (M1): boots the image in x128
(-go64: C64-mode OS with the 8563 emulated), then reads VDC RAM through the
VICE text monitor (`bank vdc`) and checks what the desktop, file manager and
shell mirror onto the second screen.

Checks:
  A  boot: rows 0-1 carry the header, row 2 says "desktop"
  B  file manager (tick-vector trampoline): row 2 "File manager", row 23 the
     key hint, rows 4.. one directory entry each with the ">" marker on row 0
  C  ESC: back on the desktop, listing rows blanked
  D  shell: row 2 "Command shell", VER -> row 7 "UltOS 0.3", EXIT -> desktop

Run: python3 tests/ci_vdc.py   (exit 0 = all pass)
"""
import os
import re
import socket
import subprocess
import sys
import time

UOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DISK = os.path.join(UOS, "target/ultos.d64")
OUT = os.path.join(UOS, "vdc-emu-out")
os.makedirs(OUT, exist_ok=True)
EGL = {"__EGL_VENDOR_LIBRARY_FILENAMES": "/usr/share/glvnd/egl_vendor.d/50_mesa.json"}
sys.stdout.reconfigure(line_buffering=True)
KB_BUF, KB_CNT, TICK_VEC, TRAMP = 0x0277, 0x00C6, 0x033C, 0x7F00


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_xvfb():
    for n in range(100, 140):
        p = subprocess.Popen(["Xvfb", f":{n}", "-screen", "0", "1400x700x24"],
                             env=dict(os.environ, **EGL),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            if p.poll() is not None:
                break
            if subprocess.run(["xdpyinfo", "-display", f":{n}"], capture_output=True).returncode == 0:
                return p, f":{n}"
            time.sleep(0.25)
        if p.poll() is None:
            p.terminate()
    raise SystemExit("FAIL: no Xvfb display")


class Mon:
    def __init__(self, port, emu):
        self.port, self.emu = port, emu

    def cmd(self, c, wait=1.2):
        for _ in range(80):
            if self.emu.poll() is not None:
                raise SystemExit(f"FAIL: x128 exited rc={self.emu.returncode}")
            try:
                s = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise SystemExit("FAIL: monitor unreachable")
        s.settimeout(wait)
        s.sendall((c + "\n").encode())
        buf = b""
        try:
            while True:
                ch = s.recv(65536)
                if not ch:
                    break
                buf += ch
        except socket.timeout:
            pass
        try:
            s.sendall(b"x\n")
        except OSError:
            pass
        s.close()
        return buf.decode("latin-1", errors="replace")

    def vdc_rows(self):
        """Return 25 strings decoded from VDC screen RAM $0000-$07cf."""
        self.cmd("bank vdc")
        txt = self.cmd("m 0000 07cf", wait=2.5)
        self.cmd("bank cpu")
        mem = {}
        for line in txt.splitlines():
            m = re.search(r">.:([0-9a-fA-F]{4})\s+(.*)$", line)
            if not m:
                continue
            addr = int(m.group(1), 16)
            hexpart = re.split(r"\s{3,}", m.group(2))[0]
            for i, tok in enumerate(re.findall(r"\b[0-9a-fA-F]{2}\b", hexpart)[:16]):
                mem[addr + i] = int(tok, 16)
        rows = []
        for r in range(25):
            s = ""
            for i in range(80):
                c = mem.get(r * 80 + i, 0x20)
                if 1 <= c <= 0x1a:
                    s += chr(c + 96)          # lowercase set: $01.. = a..z
                elif 0x41 <= c <= 0x5a:
                    s += chr(c)               # uppercase glyphs
                elif 0x20 <= c <= 0x3f:
                    s += chr(c)
                else:
                    s += "."
            rows.append(s.rstrip())
        return rows

    def poke(self, addr, data):
        self.cmd("> %04x %s" % (addr, " ".join("%02x" % b for b in data)))

    def peek(self, addr, n):
        txt = self.cmd("m %04x %04x" % (addr, addr + n - 1))
        out = []
        for line in txt.splitlines():
            m = re.search(r">.:([0-9a-fA-F]{4})\s+(.*)$", line)
            if m:
                hexpart = re.split(r"\s{3,}", m.group(2))[0]
                out += [int(t, 16) for t in re.findall(r"\b[0-9a-fA-F]{2}\b", hexpart)[:16]]
        return bytes(out[:n])

    def keys(self, data):
        self.poke(KB_BUF, data + b"\x00" * (10 - len(data)))
        self.poke(KB_CNT, bytes([len(data)]))

    def launch(self, name):
        """One-shot tick-vector trampoline: LOAD_IMM name, APP_LOADER, restore
        the desktop tick, jump to APP_START (same recipe as tests/ci_fm.py)."""
        vec = self.peek(TICK_VEC, 2)
        tramp = (bytes([0x20, 0x23, 0x08]) + name + b"\x00"
                 + bytes([0x20, 0x26, 0x08])
                 + bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
                 + bytes([0x4C, 0x00, 0x50]))
        self.poke(TRAMP, tramp)
        self.poke(TICK_VEC, bytes([TRAMP & 0xff, TRAMP >> 8]))


def wait_rows(mon, pred, what, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        rows = mon.vdc_rows()
        if pred(rows):
            return rows
        time.sleep(3)
    print("---- last VDC rows ----")
    for i, r in enumerate(rows):
        if r:
            print(f"{i:2d}: {r}")
    raise SystemExit(f"FAIL: {what} not seen within {timeout}s")


def show(rows, tag):
    print(f"---- VDC rows ({tag}) ----")
    for i, r in enumerate(rows):
        if r:
            print(f"{i:2d}: {r}")


def main():
    xvfb, disp = start_xvfb()
    port = free_port()
    emu = subprocess.Popen(
        ["x128", "-default", "-go64", "-VDC64KB", "-autostart", DISK,
         "-drive8true", "-drive8type", "1541", "-sounddev", "dummy",
         "-jamaction", "0", "-warp", "-remotemonitor",
         "-remotemonitoraddress", f"ip4://127.0.0.1:{port}"],
        env=dict(os.environ, DISPLAY=disp, **EGL),
        stdout=open(os.path.join(OUT, "ci_vdc_vice.log"), "w"), stderr=subprocess.STDOUT)
    mon = Mon(port, emu)
    passed = 0
    try:
        time.sleep(20)
        rows = wait_rows(mon, lambda r: r[2].startswith("desktop") and "UltOS" in r[0],
                         "boot header + desktop row")
        show(rows, "boot")
        assert "companion display" in rows[0], rows[0]
        assert "ultos menu" in rows[1], rows[1]
        print("PASS A: header rows 0-1 + row 2 'desktop' on the 80-col display")
        passed += 1

        mon.launch(b"UOS-FMGR")
        rows = wait_rows(mon, lambda r: r[2].startswith("File manager") and r[4].startswith("  >"),
                         "file manager rows")
        show(rows, "fmgr")
        assert "device 8" in rows[2], rows[2]
        assert rows[23].startswith("D=del"), rows[23]
        names = [r[4:].strip() for r in rows[4:14] if r.strip()]
        assert len(names) >= 5, names
        assert any("uos" in n.lower() for n in names), names
        print(f"PASS B: file manager mirrored ({len(names)} entries, marker on row 0, hint row)")
        passed += 1

        mon.keys(b"\x1b")
        rows = wait_rows(mon, lambda r: r[2].startswith("desktop") and not any(r[4:14]),
                         "desktop after ESC with blank listing rows")
        print("PASS C: ESC back to the desktop blanked the listing rows")
        passed += 1

        mon.launch(b"UOS-SHELL")
        rows = wait_rows(mon, lambda r: r[2].startswith("Command shell") and r[5].startswith(">"),
                         "shell rows")
        show(rows, "shell")
        assert "UltOS 0.3" in rows[2], rows[2]
        mon.keys(b"VER\x0d")
        rows = wait_rows(mon, lambda r: "UltOS 0.3" in r[7], "VER response on row 7", timeout=60)
        show(rows, "after VER")
        mon.keys(b"EXIT\x0d")
        rows = wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop after EXIT")
        print("PASS D: shell mirrored (header, VER response row 7, EXIT back to desktop)")
        passed += 1
        subprocess.run(["magick", "import", "-display", disp, "-window", "root",
                        os.path.join(OUT, "ci_vdc_final.png")], capture_output=True)
        print(f"CI-VDC PASS: {passed}/4 companion-display checks")
    finally:
        emu.terminate()
        xvfb.terminate()


main()
