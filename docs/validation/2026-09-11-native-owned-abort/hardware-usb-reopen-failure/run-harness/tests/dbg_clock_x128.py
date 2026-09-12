#!/usr/bin/env python3
"""Debug: boot x128, dump the desktop's time/vdtime/minute bytes and VDC row 0."""
import os, subprocess, sys, time
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_vdc.py")).read()
exec(src[:src.index("def check_driver_layout():")])
sys.path.insert(0, UOS)
import hwlib
sym = lambda n: hwlib.lst_symbol("uos-desktop", n)
xvfb, disp = start_xvfb()
port = free_port()
emu = subprocess.Popen(["x128", "-default", "-go64", "-VDC64KB", "-reu", "-reusize", "512", "-autostart", DISK,
     "-drive8true", "-drive8type", "1541", "-sounddev", "dummy", "-jamaction", "0", "-warp",
     "-remotemonitor", "-remotemonitoraddress", f"ip4://127.0.0.1:{port}"],
    env=dict(os.environ, DISPLAY=disp, **EGL), stdout=open(os.path.join(OUT, "dbg_clock_vice.log"), "w"), stderr=subprocess.STDOUT)
mon = Mon(port, emu)
try:
    time.sleep(20)
    rows = wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop", timeout=240)
    for i in range(3):
        t = mon.peek(sym("time"), 10); v = mon.peek(sym("vdtime"), 24); m = mon.peek(sym("minute"), 1)
        st = mon.peek(0x9121, 1); tod = mon.peek(0xdc08, 4); r16 = mon.peek(0x22, 1); vec = mon.peek(0x33c, 2)
        print(f"t{i}: time={t.hex()} vdtime={v.hex()} minute={m.hex()} NET_STATE={st.hex()} tod={tod.hex()} r16={r16.hex()} vec={vec.hex()}")
        print("row0:", repr(mon.vdc_rows()[0]))
        time.sleep(5)
    mon.poke(sym("minute"), b"\xff")
    time.sleep(4)
    t = mon.peek(sym("time"), 10); v = mon.peek(sym("vdtime"), 24)
    print(f"forced: time={t.hex()} vdtime={v.hex()}")
    print("row0:", repr(mon.vdc_rows()[0]))
finally:
    emu.terminate(); xvfb.terminate()
