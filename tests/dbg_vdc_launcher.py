#!/usr/bin/env python3
"""Debug: boot, fire MENU_APPS via the tick trampoline, dump VDC rows + $033c."""
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
    if os.environ.get("VIA_SETTINGS"):
        mon.launch(b"UOS-SETTINGS")
        wait_rows(mon, lambda r: r[2].startswith("Settings"), "settings")
        mon.keys(b"C"); time.sleep(6)
        mon.keys(b"\x1b")
        wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop after settings")
        time.sleep(4)
    print("kernal open files $98 =", mon.peek(0x98,1).hex(), " LAT $0259.. =", mon.peek(0x0259,10).hex(), " ST $90 =", mon.peek(0x90,1).hex())
    menu_apps = hwlib.lst_symbol("uos-desktop", "MENU_APPS"); print("MENU_APPS =", hex(menu_apps))
    vec = mon.peek(TICK_VEC, 2); print("vec", vec.hex())
    tramp = (bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03]) + bytes([0x4C, menu_apps & 0xff, menu_apps >> 8]))
    mon.poke(TRAMP, tramp); mon.poke(TICK_VEC, bytes([TRAMP & 0xff, TRAMP >> 8]))
    for i in range(6):
        time.sleep(5)
        print(f"t+{(i+1)*5}s $033c={mon.peek(TICK_VEC,2).hex()} apps_count={mon.peek(hwlib.lst_symbol('uos-desktop','apps_count'),1).hex()} $98={mon.peek(0x98,1).hex()} ST={mon.peek(0x90,1).hex()} LAT={mon.peek(0x0259,6).hex()}")
        if i==5:
            show(mon.vdc_rows(), "final")
            mon.cmd("bank vdc"); txt=mon.cmd("m 00f0 0230", wait=2.0); mon.cmd("bank cpu")
            print("\n".join(l for l in txt.splitlines() if l.startswith(">")) )
    subprocess.run(["magick","import","-display",disp,"-window","root",os.path.join(OUT,"dbg_launcher.png")],capture_output=True)
    print(mon.cmd("r")[-200:])
finally:
    emu.terminate(); xvfb.terminate()
