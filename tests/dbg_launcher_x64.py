#!/usr/bin/env python3
"""Debug: boot, fire MENU_APPS via the tick trampoline, dump VDC rows + $033c."""
import os, sys, time, subprocess
src = open(os.path.join(os.path.dirname(__file__), "ci_vdc.py")).read()
exec(src[:src.index("def main():")])
sys.path.insert(0, UOS); import hwlib
xvfb, disp = start_xvfb(); port = free_port()
emu = subprocess.Popen(["x64", "-default", "-autostart", DISK,
    "-drive8true", "-drive8type", "1541", "-sounddev", "dummy", "-jamaction", "0", "-warp",
    "-remotemonitor", "-remotemonitoraddress", f"ip4://127.0.0.1:{port}"],
    env=dict(os.environ, DISPLAY=disp, **EGL), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
mon = Mon(port, emu)
try:
    time.sleep(20)
    time.sleep(15)
    menu_apps = hwlib.lst_symbol("uos-desktop", "MENU_APPS"); print("MENU_APPS =", hex(menu_apps))
    vec = mon.peek(TICK_VEC, 2); print("vec", vec.hex())
    tramp = (bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03]) + bytes([0x4C, menu_apps & 0xff, menu_apps >> 8]))
    mon.poke(TRAMP, tramp); mon.poke(TICK_VEC, bytes([TRAMP & 0xff, TRAMP >> 8]))
    for i in range(6):
        time.sleep(5)
        print(f"t+{(i+1)*5}s $033c={mon.peek(TICK_VEC,2).hex()} apps_count={mon.peek(hwlib.lst_symbol('uos-desktop','apps_count'),1).hex()}")
        lo=hwlib.lst_symbol("uos-desktop","rowadd_lo"); hi=hwlib.lst_symbol("uos-desktop","rowadd_hi")
        l=mon.peek(lo,6); h=mon.peek(hi,6)
        names=[mon.peek(l[k]|(h[k]<<8),12) for k in range(6)]
        print("   rows:", [n.split(b"\x00")[0] for n in names])
    subprocess.run(["magick","import","-display",disp,"-window","root",os.path.join(OUT,"dbg_launcher.png")],capture_output=True)
    print(mon.cmd("r")[-200:])
finally:
    emu.terminate(); xvfb.terminate()
