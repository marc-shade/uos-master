#!/usr/bin/env python3
"""Debug: boot in x128, launch UOS-SETTINGS via the trampoline, dump VDC rows,
CPU registers, tick vector and the first bytes at $5000."""
import os, sys, time, subprocess
src = open(os.path.join(os.path.dirname(__file__), "ci_vdc.py")).read()
exec(src[:src.index("def main():")])
xvfb, disp = start_xvfb(); port = free_port()
emu = subprocess.Popen(["x128", "-default", "-go64", "-VDC64KB", "-autostart", DISK,
    "-drive8true", "-drive8type", "1541", "-sounddev", "dummy", "-jamaction", "0", "-warp",
    "-remotemonitor", "-remotemonitoraddress", f"ip4://127.0.0.1:{port}"],
    env=dict(os.environ, DISPLAY=disp, **EGL), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
mon = Mon(port, emu)
try:
    time.sleep(20)
    rows = wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop")
    print("desktop up; tick vec", mon.peek(TICK_VEC, 2).hex())
    ref = open(os.path.join(UOS, "target/uos-settings.prg"), "rb").read()[2:]
    if os.environ.get("VIA_SHELL"):
        mon.launch(b"UOS-SHELL")
        wait_rows(mon, lambda r: r[2].startswith("Command shell"), "shell")
        mon.keys(b"EXIT\x0d")
        wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop after EXIT")
        print("shell EXIT done; tick vec", mon.peek(TICK_VEC, 2).hex())
    mon.launch(b"UOS-SETTINGS")
    for i in range(8):
        time.sleep(5)
        got = mon.peek(0x5000, 16)
        rows = mon.vdc_rows()
        print(f"t+{(i+1)*5}s $5000={got.hex()} match={got == ref[:16]} tick={mon.peek(TICK_VEC,2).hex()} rows2-5={[rows[2], rows[4], rows[5]]}")
        if got == ref[:16] and rows[2]:
            break
    print(mon.cmd("r", wait=1.0)[-300:])
    show(mon.vdc_rows(), "final")
    print("VDC_LIVE $cc24 =", mon.peek(0xcc24, 1).hex(), " SETREC", mon.peek(0x7350, 8).hex())
finally:
    emu.terminate(); xvfb.terminate()
