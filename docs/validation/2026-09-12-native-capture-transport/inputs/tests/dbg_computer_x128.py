#!/usr/bin/env python3
"""Boot x128, fire ON_CLICK_COMPUTER from a CLEAN desktop via Mon.tramp,
dump the VDC rows. Isolates the Computer-window mirror from check L's
post-settings state."""
import os, subprocess, sys, time, re
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_vdc.py")).read()
exec(src[:src.index("def check_driver_layout():")])
sys.path.insert(0, UOS); import hwlib
sym = lambda n: hwlib.lst_symbol("uos-desktop", n)
xvfb, disp = start_xvfb(); port = free_port()
emu = subprocess.Popen(["x128","-default","-go64","-VDC64KB","-reu","-reusize","512","-autostart",DISK,
    "-drive8true","-drive8type","1541","-sounddev","dummy","-jamaction","0","-warp",
    "-remotemonitor","-remotemonitoraddress",f"ip4://127.0.0.1:{port}"],
    env=dict(os.environ, DISPLAY=disp, **EGL), stdout=open(os.path.join(OUT,"dbg_computer_vice.log"),"w"), stderr=subprocess.STDOUT)
mon = Mon(port, emu)
try:
    time.sleep(20)
    wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop", timeout=240)
    print("NET_STATE at boot:", mon.peek(0x9121,1).hex())
    oc = sym("ON_CLICK_COMPUTER"); print("ON_CLICK_COMPUTER =", hex(oc))
    mon.tramp(bytes([0x4C, oc & 0xff, oc >> 8]))
    for k in range(8):
        time.sleep(3)
        r = mon.vdc_rows()
        print(f"t{k}: r2={r[2]!r} r4={r[4]!r} r5={r[5]!r} r6={r[6]!r} r7={r[7]!r}")
        if r[2].startswith("Computer"):
            break
finally:
    emu.terminate(); xvfb.terminate()
