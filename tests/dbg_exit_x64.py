#!/usr/bin/env python3
"""Debug: x64 boot, shell via trampoline, IP/TIME/GET/EXIT, then sample state."""
import os, struct, subprocess, sys, time
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_fm.py")).read()
exec(src[:src.index("def main():")])
import shutil
DISK = os.path.join(WORK, "dbg.d64"); os.makedirs(WORK, exist_ok=True)
shutil.copyfile(STOCK, DISK)
NAMES_L, NAMES_H = parse_lst_symbols()
SH_RESP = lst_symbol("uos-shell", "respbuf"); SH_CMD = lst_symbol("uos-shell", "cmdbuf")
xv = cbm.Xvfb()
env = dict(os.environ, DISPLAY=xv.display, __EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
emu = subprocess.Popen(["x64", "-default", "-autostart", DISK, "-drive8true", "-drive8type", "1541",
    "-sounddev", "dummy", "-jamaction", "0", "-warp", "-autostart-warp",
    "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{PORT}"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
def pc_samples(mon, n=6):
    pcs = []
    for _ in range(n):
        err, body = mon._recv(mon._send(0x31, b"\x00")); mon.resume()
        cnt = struct.unpack("<H", body[0:2])[0]; off = 2
        for _i in range(cnt):
            if body[off + 1] == 3:
                pcs.append(hex(struct.unpack("<H", body[off+2:off+4])[0]))
            off += 1 + body[off]
        time.sleep(0.3)
    return pcs
def state(mon, tag):
    vec = mon.read_mem(0x33c, 0x33d, memspace=0); mon.resume()
    s1 = mon.read_mem(0xdc09, 0xdc09, memspace=0)[0]; mon.resume(); time.sleep(1.5)
    s2 = mon.read_mem(0xdc09, 0xdc09, memspace=0)[0]; mon.resume()
    r16 = mon.read_mem(0x22, 0x22, memspace=0)[0]; mon.resume()
    kb = mon.read_mem(0xc6, 0xc6, memspace=0)[0]; mon.resume()
    cl = mon.read_mem(0x46, 0x46, memspace=0)[0]; mon.resume()
    resp = bytes(mon.read_mem(SH_RESP, SH_RESP + 30, memspace=0)); mon.resume()
    cmd = bytes(mon.read_mem(SH_CMD, SH_CMD + 20, memspace=0)); mon.resume()
    print(f"[{tag}] vec={bytes(vec).hex()} tod_sec={s1:02x}->{s2:02x} r16={r16:02x} kb={kb} cmdlen={cl} cmd={cmd.split(b'\\0')[0]} resp={resp.split(b'\\0')[0]} pc={pc_samples(mon)}", flush=True)
try:
    mon = None
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            mon = Monitor(port=PORT); break
        except OSError:
            time.sleep(0.25)
    assert wait_desktop_live(mon, 300), "desktop never live"
    state(mon, "desktop")
    orig_vec = mon.read_mem(TICK_VEC, TICK_VEC + 1, memspace=0); mon.resume()
    tramp = (bytes([0x20, 0x23, 0x08]) + b"UOS-SHELL\x00" + bytes([0x20, 0x26, 0x08])
             + bytes([0xA2, orig_vec[0], 0xA0, orig_vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03]) + bytes([0x4C, 0x00, 0x50]))
    mon.write_mem(TRAMPOLINE, tramp); mon.write_mem(TICK_VEC, struct.pack("<H", TRAMPOLINE)); mon.resume()
    time.sleep(25)
    state(mon, "shell")
    for verb in (b"IP\x0d", b"TIME\x0d", b"GET 192.168.1.1 /\x0d"):
        inject_keys(mon, verb); time.sleep(8)
        state(mon, verb.decode().strip())
    inject_keys(mon, b"EXIT\x0d"); time.sleep(15)
    state(mon, "after EXIT")
    time.sleep(10)
    state(mon, "after EXIT +10s")
    print("live:", wait_desktop_live(mon, 30))
finally:
    emu.terminate(); xv.stop()
