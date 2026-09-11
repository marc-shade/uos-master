#!/usr/bin/env python3
"""Debug: fmgr -> ESC -> settings -> RUN/STOP -> shell -> EXIT, then sample."""
import os, socket, struct, subprocess, sys, time
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_fm.py")).read()
exec(src[:src.index("def main():")])
import shutil
_s = socket.socket(); _s.bind(("127.0.0.1", 0)); PORT = _s.getsockname()[1]; _s.close()
DISK = os.path.join(WORK, "dbg2.d64"); os.makedirs(WORK, exist_ok=True)
shutil.copyfile(STOCK, DISK)
NAMES_L, NAMES_H = parse_lst_symbols()
SH_RESP = lst_symbol("uos-shell", "respbuf"); SH_CMD = lst_symbol("uos-shell", "cmdbuf")
xv = cbm.Xvfb()
env = dict(os.environ, DISPLAY=xv.display, __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
emu = subprocess.Popen(["x64", "-default", "-autostart", DISK, "-drive8true", "-drive8type", "1541",
    "-sounddev", "dummy", "-jamaction", "0", "-warp", "-autostart-warp",
    "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{PORT}"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
def pcs(mon, n=8):
    out = []
    for _ in range(n):
        err, body = mon._recv(mon._send(0x31, b"\x00")); mon.resume()
        cnt = struct.unpack("<H", body[0:2])[0]; off = 2
        for _i in range(cnt):
            if body[off + 1] == 3:
                out.append(hex(struct.unpack("<H", body[off+2:off+4])[0]))
            off += 1 + body[off]
        time.sleep(0.3)
    return out
def rd(mon, a, n=1):
    v = bytes(mon.read_mem(a, a + n - 1, memspace=0)); mon.resume(); return v
def launch(mon, name):
    vec = rd(mon, TICK_VEC, 2)
    t = (bytes([0x20, 0x23, 0x08]) + name + b"\x00" + bytes([0x20, 0x26, 0x08])
         + bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03]) + bytes([0x4C, 0x00, 0x50]))
    mon.write_mem(TRAMPOLINE, t); mon.write_mem(TICK_VEC, struct.pack("<H", TRAMPOLINE)); mon.resume()
def state(mon, tag):
    print(f"[{tag}] vec={rd(mon,0x33c,2).hex()} tod={rd(mon,0xdc09).hex()}/{(time.sleep(1.2), rd(mon,0xdc09).hex())[1]} "
          f"r16={rd(mon,0x22).hex()} kb={rd(mon,0xc6)[0]} $98={rd(mon,0x98)[0]} ST={rd(mon,0x90).hex()} $01={rd(mon,1).hex()} pc={pcs(mon)}", flush=True)
try:
    mon = None
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            mon = Monitor(port=PORT); break
        except OSError:
            time.sleep(0.25)
    assert wait_desktop_live(mon, 300), "desktop never live"
    for step, name, key in (("fmgr", b"UOS-FMGR", b"\x1b"), ("settings", b"UOS-SETTINGS", b"\x03"), ("shell", b"UOS-SHELL", None)):
        launch(mon, name); time.sleep(25)
        state(mon, step)
        if key:
            inject_keys(mon, key); time.sleep(8)
            print(step, "exit -> live:", wait_desktop_live(mon, 60), flush=True)
            state(mon, step + " exited")
    inject_keys(mon, b"EXIT\x0d"); time.sleep(15)
    state(mon, "after EXIT")
    print("live:", wait_desktop_live(mon, 60), flush=True)
    state(mon, "final")
finally:
    emu.terminate(); xv.stop()
