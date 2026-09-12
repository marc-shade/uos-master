#!/usr/bin/env python3
"""Breakpoint at the launcher row mirror's jsr VDTEXT; report A/X and r9."""
import os, sys, time, subprocess
src = open(os.path.join(os.path.dirname(__file__), "ci_vdc.py")).read()
exec(src[:src.index("def main():")])
sys.path.insert(0, UOS); import hwlib
xvfb, disp = start_xvfb(); port = free_port()
emu = subprocess.Popen(["x128", "-default", "-go64", "-VDC64KB", "-autostart", DISK,
    "-drive8true", "-drive8type", "1541", "-sounddev", "dummy", "-jamaction", "0", "-warp",
    "-remotemonitor", "-remotemonitoraddress", f"ip4://127.0.0.1:{port}"],
    env=dict(os.environ, DISPLAY=disp, **EGL), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
mon = Mon(port, emu)
try:
    time.sleep(20)
    wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop")
    menu_apps = hwlib.lst_symbol("uos-desktop", "MENU_APPS")
    vec = mon.peek(TICK_VEC, 2)
    # breakpoints: draw_rows entry, _drrow, and the mirror's jsr VDTEXT
    for bp in ("2a9a", "2ab4", "2b00"):
        print(mon.cmd(f"break {bp}").strip()[-60:])
    tramp = (bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03]) + bytes([0x4C, menu_apps & 0xff, menu_apps >> 8]))
    mon.poke(TRAMP, tramp); mon.poke(TICK_VEC, bytes([TRAMP & 0xff, TRAMP >> 8]))
    for i in range(8):
        time.sleep(3)
        r = mon.cmd("r", wait=1.0)
        line = [l for l in r.splitlines() if l.startswith(".;")]
        print(f"t+{(i+1)*3}s regs: {line[-1] if line else r.strip()[-80:]}  r9=$14/15: {mon.peek(0x14,2).hex()} apps_count={mon.peek(hwlib.lst_symbol('uos-desktop','apps_count'),1).hex()}")
        if line and any(pc in line[-1] for pc in ("2a9a","2ab4","2b00")):
            print("BREAK HIT:", line[-1]); print(mon.cmd("m 0014 0015").strip()[-60:]); mon.cmd("x")
finally:
    emu.terminate(); xvfb.terminate()
