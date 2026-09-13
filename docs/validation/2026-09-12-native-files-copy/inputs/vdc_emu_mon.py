#!/usr/bin/env python3
"""Boot uOS in C64 mode under x128 (headless) and interrogate the VDC through
VICE's remote TEXT monitor: register dump + VDC RAM (screen / attrs / font)
so the 80-column path can be debugged without eyes on a monitor.

Usage: vdc_emu_mon.py [out_dir] [boot_wait_s]
"""
import os
import socket
import subprocess
import sys
import time

UOS = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(UOS, "vdc-emu-out")
BOOT = int(sys.argv[2]) if len(sys.argv) > 2 else 45
PORT = 62695
os.makedirs(OUT, exist_ok=True)
sys.stdout.reconfigure(line_buffering=True)   # stream output when piped

EGL = {"__EGL_VENDOR_LIBRARY_FILENAMES": "/usr/share/glvnd/egl_vendor.d/50_mesa.json"}


def start_xvfb():
    """Start Xvfb on the first free display in :94..:99 and VERIFY it answers
    (a stale /tmp/.X11-unix socket makes Xvfb fail silently; the sandbox
    cannot always remove it, so probe instead of assuming)."""
    for n in range(94, 100):
        disp = f":{n}"
        # Xvfb ALSO needs the mesa EGL vendor override on this node: with the
        # NVIDIA libEGL it core-dumps at startup (documented gotcha), so no
        # display ever answers.
        p = subprocess.Popen(["Xvfb", disp, "-screen", "0", "1600x700x24"],
                             env=dict(os.environ, **EGL),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            if subprocess.run(["xdpyinfo", "-display", disp],
                              capture_output=True).returncode == 0:
                return p, disp
            time.sleep(0.25)
        p.terminate()
    raise SystemExit("FAIL: no Xvfb display came up in :94..:99")


xvfb, DISP = start_xvfb()
env = dict(os.environ, DISPLAY=DISP, **EGL)
print(f"Xvfb up on {DISP}")

emu = subprocess.Popen(
    ["x128", "-default", "-go64",
     "-autostart", os.path.join(UOS, "target/ultos.d64"),
     "-drive8true", "-drive8type", "1541",
     "-sounddev", "dummy", "-jamaction", "0", "-warp",
     "-remotemonitor", "-remotemonitoraddress", f"ip4://127.0.0.1:{PORT}"],
    env=env, stdout=open(os.path.join(OUT, "vice.log"), "w"), stderr=subprocess.STDOUT)


def mon(cmd, wait=1.0):
    """Send one text-monitor command; return the reply (the monitor pauses the
    emulator while connected, so each call opens, sends, reads, closes)."""
    for _ in range(40):
        if emu.poll() is not None:
            return f"<x128 exited with {emu.returncode}; see vice.log>"
        try:
            s = socket.create_connection(("127.0.0.1", PORT), timeout=2)
            break
        except OSError:
            time.sleep(0.5)
    else:
        return "<monitor unreachable>"
    s.settimeout(wait)
    s.sendall((cmd + "\n").encode())
    buf = b""
    try:
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    except socket.timeout:
        pass
    try:
        s.sendall(b"x\n")          # resume the emulator on disconnect
    except OSError:
        pass
    s.close()
    return buf.decode("latin-1", errors="replace")


def shot(tag):
    subprocess.run(["magick", "import", "-display", DISP, "-window", "root",
                    os.path.join(OUT, f"root-{tag}.png")], capture_output=True)


try:
    print(f"booting uOS in x128 -go64, waiting {BOOT}s ...")
    time.sleep(BOOT)
    shot("boot")
    print("=== monitor banks available ===")
    print(mon("bank"))
    print("=== VDC registers (memory-mapped $d600 via cpu bank) ===")
    print(mon("m d600 d601"))
    for cmd in ["bank vdc", "m 0000 00a0", "m 0800 0810", "m 3000 3020", "m 2000 2010"]:
        print(f"=== {cmd} ===")
        print(mon(cmd))
    print("=== cpu-side: $02c0/$01 sanity ===")
    print(mon("bank cpu"))
    print(mon("m 0001 0001"))
finally:
    emu.terminate()
    xvfb.terminate()
