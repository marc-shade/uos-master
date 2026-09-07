#!/usr/bin/env python3
"""Screen-fit gallery: boot uOS in x128 (-go64, VDC emulated), open every
screen of the OS through the desktop tick vector (no mouse needed), and
capture the 40-column VIC window and the 80-column VDC window for each.

Output: vdc-emu-out/screens/<name>-vic.png / -vdc.png plus a contact sheet
screens.png. This is the visual gate for "every menu fits on screen".

Screens: desktop, ultos menu open, Applications window, computer window,
file manager, shell (with a DIR listing), settings (with the time zone row).
Apps are launched the way the desktop menu launches them (FILLFILE +
LAUNCH_APP), so the captures show the cleared-screen behaviour.
"""
import os
import subprocess
import sys
import time

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_vdc.py")).read()
exec(src[:src.index("def main():")])           # Mon, start_xvfb, free_port, wait_rows, DISK...
sys.path.insert(0, UOS)
import hwlib  # noqa: E402

SHOTS = os.path.join(OUT, "screens")
os.makedirs(SHOTS, exist_ok=True)
# window geometry on the 1400x700 Xvfb root (x128 opens the VDC window at
# the origin and the VIC window to its right; verified in earlier captures)
VIC = "620x420+400+120"
VDCW = "800x600+0+0"


def shot(disp, name):
    root = os.path.join(SHOTS, f"{name}-root.png")
    subprocess.run(["magick", "import", "-display", disp, "-window", "root", root],
                   check=True, capture_output=True)
    subprocess.run(["magick", root, "-crop", VIC, "+repage", os.path.join(SHOTS, f"{name}-vic.png")],
                   check=True, capture_output=True)
    subprocess.run(["magick", root, "-crop", VDCW, "+repage", "-trim", "+repage",
                    os.path.join(SHOTS, f"{name}-vdc.png")], check=True, capture_output=True)
    print("captured", name)


def tramp_jmp(mon, target):
    """One-shot tick trampoline: restore the desktop tick, jmp target
    (target must end in jmp MAINLOOP, like the desktop's click handlers)."""
    vec = mon.peek(TICK_VEC, 2)
    t = (bytes([0xA2, vec[0], 0xA0, vec[1], 0x8E, 0x3C, 0x03, 0x8C, 0x3D, 0x03])
         + bytes([0x4C, target & 0xff, target >> 8]))
    mon.poke(TRAMP, t)
    mon.poke(TICK_VEC, bytes([TRAMP & 0xff, TRAMP >> 8]))
    time.sleep(6)


def main():
    xvfb, disp = start_xvfb()
    port = free_port()
    emu = subprocess.Popen(
        ["x128", "-default", "-go64", "-VDC64KB", "-reu", "-reusize", "512", "-autostart", DISK,
         "-drive8true", "-drive8type", "1541", "-sounddev", "dummy",
         "-jamaction", "0", "-warp", "-remotemonitor",
         "-remotemonitoraddress", f"ip4://127.0.0.1:{port}"],
        env=dict(os.environ, DISPLAY=disp, **EGL),
        stdout=open(os.path.join(OUT, "screens_vice.log"), "w"), stderr=subprocess.STDOUT)
    mon = Mon(port, emu)
    try:
        time.sleep(20)
        wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop", timeout=240)
        time.sleep(3)
        shot(disp, "01-desktop")

        sym = lambda n: hwlib.lst_symbol("uos-desktop", n)
        tramp_jmp(mon, sym("MNU_ULTOS"))          # opens the ultos popup menu
        shot(disp, "02-ultos-menu")
        tramp_jmp(mon, sym("MENU_APPS"))          # closes the menu, opens Applications
        time.sleep(4)
        shot(disp, "03-applications")
        tramp_jmp(mon, sym("APPS_CANCEL"))
        time.sleep(3)
        tramp_jmp(mon, sym("ON_CLICK_COMPUTER"))
        shot(disp, "04-computer")
        tramp_jmp(mon, sym("ON_CLOSE"))          # close it: apps start from a clean desktop

        for name, key_after, label in (("UOS-FMGR", b"\x1b", "05-file-manager"),
                                       ("UOS-SHELL", None, "06-shell"),
                                       ("UOS-SETTINGS", b"\x1b", "07-settings"),
                                       ("UOS-CALC", b"\x1b", "08-calculator")):
            # apps are launched from a live desktop: the previous app's
            # exit key lands on the desktop first
            mon.launch(name.encode())
            # wait for the app's companion rows to settle (its directory
            # scan runs on the emulated 1541; ESC before that is swallowed)
            last = None
            for _ in range(30):
                time.sleep(4)
                rows = mon.vdc_rows()
                key = tuple(rows[2:14])
                if rows[2].strip() and key == last:
                    break
                last = key
            if name == "UOS-SHELL":
                mon.keys(b"DIR\x0d")
                time.sleep(8)
                shot(disp, label)
                mon.keys(b"EXIT\x0d")
            elif name == "UOS-CALC":
                mon.keys(b"12+34=")      # exercise the display path
                time.sleep(4)
                shot(disp, label)
                mon.keys(key_after)
            else:
                shot(disp, label)
                mon.keys(key_after)
            wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop", timeout=120)
            time.sleep(3)

        # contact sheet of the 40-col screens
        vics = sorted(p for p in os.listdir(SHOTS) if p.endswith("-vic.png"))
        subprocess.run(["magick", "montage", *[os.path.join(SHOTS, p) for p in vics],
                        "-tile", "4x", "-geometry", "+6+6", "-label", "%f",
                        os.path.join(OUT, "screens.png")], capture_output=True)
        print("contact sheet:", os.path.join(OUT, "screens.png"))
    finally:
        emu.terminate()
        xvfb.terminate()


main()
