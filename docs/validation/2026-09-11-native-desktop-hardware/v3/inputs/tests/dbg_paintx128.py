#!/usr/bin/env python3
"""Debug: gfx state after the fmgr settles — BITMASK, X1/Y1, POINT, and a
real bitmap byte from the list region."""
import os
import time

UOS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(UOS, "tests/ci_vdc.py")).read()
exec(src[:src.index("def main():")])     # Mon, start_xvfb, free_port, wait_rows, DISK, EGL


def main():
    xvfb, disp = start_xvfb()
    port = free_port()
    emu = subprocess.Popen(
        ["x128", "-default", "-go64", "-VDC64KB", "-reu", "-reusize", "512", "-autostart", DISK,
         "-drive8true", "-drive8type", "1541", "-sounddev", "dummy",
         "-jamaction", "0", "-warp", "-remotemonitor",
         "-remotemonitoraddress", f"ip4://127.0.0.1:{port}"],
        env=dict(os.environ, DISPLAY=disp, **EGL),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        mon = Mon(port, emu)
        wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop", timeout=240)
        mon.launch(b"UOS-FMGR")
        time.sleep(15)

        mon.cmd("bank ram")
        print("BITMASK ($c1a4):", " ".join(f"{x:02x}" for x in mon.peek(0xc1a4, 1)), flush=True)
        print("X1 ($02-$03):", " ".join(f"{x:02x}" for x in mon.peek(0x02, 2)), flush=True)
        print("Y1 ($04-$05):", " ".join(f"{x:02x}" for x in mon.peek(0x04, 2)), flush=True)
        print("X2 ($06-$07):", " ".join(f"{x:02x}" for x in mon.peek(0x06, 2)), flush=True)
        print("POINT ($1c-$1d):", " ".join(f"{x:02x}" for x in mon.peek(0x1c, 2)), flush=True)
        # bitmap list region: y=40.., x=30 -> $a000 + 5*320 + 3*8
        for r in (5, 7):
            b = mon.peek(0xa000 + r*320 + 3*8, 16)
            print(f"bitmap row{r} col3-6:", " ".join(f"{x:02x}" for x in b), flush=True)
        # and a REU clear-area probe is not possible via monitor; note BITMASK
    finally:
        emu.terminate()
        xvfb.terminate()


main()