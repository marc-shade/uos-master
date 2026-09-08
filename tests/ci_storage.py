#!/usr/bin/env python3
"""Exercise real directory streams, viewport pixels, and empty/missing drives.

Runs x64 or x128 with a 512 KiB REU. Uses private disk images and an
ephemeral monitor port. Input is sent through the KERNAL keyboard buffer;
fmready is set by the app only after its scan and painting have finished.
No build may run while this test is reading target PRGs/listings.
"""
import argparse
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import time

import ci_fm as ci


def wait_for(predicate, label, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError(f"Timed out: {label}")


class FileManager:
    def __init__(self, mon):
        self.mon = mon
        self.symbols = {n: ci.lst_symbol("uos-fmgr", n) for n in
                        ("fmnamesL", "fmnamesH", "scroll", "cachebase",
                         "fmready", "direrror", "linebuf", "fmblockL",
                         "fmblockH", "fmtype")}

    def read(self, address, size=1, bank=0):
        data = self.mon.read_mem(address, address + size - 1, bank=bank)
        self.mon.resume()
        return bytes(data)

    def value(self, name):
        return self.read(self.symbols[name])[0]

    def ready(self):
        return (self.value("fmready") == 1 and self.read(ci.KB_CNT)[0] == 0)

    def keys(self, data):
        # More than ten keys would overwrite KERNAL memory. Send one at a
        # time and wait through the resulting paint/scan before proceeding.
        for key in data:
            wait_for(self.ready, "file-manager input ready")
            self.mon.write_mem(self.symbols["fmready"], b"\x00")
            ci.inject_keys(self.mon, bytes([key]))
            wait_for(self.ready, f"key {key:#x} handled")

    def names(self):
        count = self.read(ci.FMCNT)[0]
        assert count <= 64, count
        if not count:
            return []
        lo = self.read(self.symbols["fmnamesL"], count)
        hi = self.read(self.symbols["fmnamesH"], count)
        return [self.read(lo[i] | (hi[i] << 8), 17).split(b"\0")[0]
                for i in range(count)]

    def ordinal(self):
        return (int.from_bytes(self.read(self.symbols["cachebase"], 2), "little")
                + self.read(ci.FMROW)[0])

    def goto(self, ordinal):
        for _ in range(400):
            current = self.ordinal()
            if current == ordinal:
                return
            self.keys(b"\x11" if current < ordinal else b"\x91")
        raise AssertionError(f"Cannot navigate to entry {ordinal}")


def launch(mon, name=b"UOS-FMGR"):
    vec = mon.read_mem(ci.TICK_VEC, ci.TICK_VEC + 1)
    # Same core entry as desktop launches; restore the one-shot tick first.
    addr = ci.TRAMPOLINE + 24
    code = (bytes([0xa9, addr & 255, 0x85, 2, 0xa9, addr >> 8, 0x85, 3,
                   0x20, 0x29, 0x08,
                   0xa2, vec[0], 0xa0, vec[1], 0x8e, 0x3c, 3, 0x8c, 0x3d, 3,
                   0x4c, 0x32, 0x08]) + name + b"\0")
    mon.write_mem(ci.TRAMPOLINE, code)
    mon.write_mem(ci.TICK_VEC, struct.pack("<H", ci.TRAMPOLINE))
    mon.resume()


def check_getcap(mon, work):
    """Call the public ABI from the idle desktop; also used on the real C128."""
    vec = bytes(mon.read_mem(ci.TICK_VEC, ci.TICK_VEC + 1))
    assert vec not in (b"\0\0", b"\0\x50"), "Desktop tick not available"
    mon.resume()
    probe = work / "getcap.prg"
    subprocess.run(["64tass", "-a", str(Path(ci.UOS, "probes/getcap.asm")),
                    "-o", str(probe)], check=True, capture_output=True)
    mon.write_mem(0x5000, probe.read_bytes()[2:])
    mon.write_mem(0x5f00, vec + b"\0")
    mon.write_mem(0x6000, bytes([0xa5]) * 512)
    mon.write_mem(ci.TICK_VEC, b"\0\x50")
    mon.resume()

    def read(address, count):
        value = bytes(mon.read_mem(address, address + count - 1))
        mon.resume()
        return value

    wait_for(lambda: read(0x5f02, 1) == b"\x01", "GETCAP probe", 30)
    data = read(0x6000, 512)
    (work / "getcap.bin").write_bytes(data)
    expected = {1: 0xc000, 2: 0xcc00, 3: 0x9c00, 4: 0x082c, 5: 0x0829}
    values = [data[i] | data[256 + i] << 8 for i in range(256)]
    for i, value in enumerate(values):
        assert value == expected.get(i, 0), f"GETCAP({i}) returned ${value:04x}"
    assert read(ci.TICK_VEC, 2) == vec, "GETCAP probe did not restore desktop tick"
    assert ci.wait_desktop_live(mon, 120), "Desktop stalled after GETCAP probe"
    print("PASS: public GETCAP for all 256 IDs; desktop remains live", flush=True)
    return {"ids": 256, "known_bases": expected, "unknown_result": 0}


def launch_from_apps(mon, work, quiet_io_seconds=0):
    """Open Apps, verify live controls, hit the Ultimate row at screen x=240."""
    def read(address, length):
        data = bytes(mon.read_mem(address,address+length-1))
        mon.resume()
        return data

    def controls():
        data = read(0x9001,250)
        return [data[i:i+10] for i in range(0,250,10) if data[i] != 0xff]

    vec = read(ci.TICK_VEC,2)
    menu = ci.lst_symbol('uos-desktop','MENU_APPS')
    code = bytes([0xa2,vec[0],0xa0,vec[1],0x8e,0x3c,3,0x8c,0x3d,3,
                  0x4c,menu&255,menu>>8])
    mon.write_mem(ci.TRAMPOLINE,code)
    mon.write_mem(ci.TICK_VEC,ci.TRAMPOLINE.to_bytes(2,'little'))
    mon.resume()
    if quiet_io_seconds:
        print('Waiting for IEC directory scan before DMA observations',flush=True)
        time.sleep(quiet_io_seconds)
    wait_for(lambda: any(r[:2] == b'\x01\x1d' for r in controls()),
             'Applications controls',120)
    records = controls()
    ids = [r[1] for r in records if r[0] == 1 and 20 <= r[1] <= 25]
    assert ids == list(range(20,26)), f'Launcher app buttons: {ids}'
    chosen = next(r for r in records if r[:2] == b'\x01\x19')
    assert int.from_bytes(chosen[2:4],'little') == ci.lst_symbol('uos-desktop','APPS_LAUNCH_6')
    (work/'launcher-controls.bin').write_bytes(b''.join(records))
    prg = work/'launch-control.prg'
    subprocess.run(['64tass','-a',str(Path(ci.UOS,'probes/launch-control.asm')),
                    '-o',str(prg)],check=True,capture_output=True)
    mon.write_mem(0x7f00,prg.read_bytes()[2:])
    # 240+24 = 264: the low-byte borrow used to make this row unclickable.
    mon.write_mem(0x7fe0,vec+ci.core_symbol('TESTCLICK').to_bytes(2,'little')+
                  bytes([8,1,chosen[6]+4+50,0,0]))
    load_error = ci.core_symbol('LOADERR')
    mon.write_mem(load_error,b'\xff')
    mon.write_mem(ci.TICK_VEC,b'\0\x7f')
    mon.resume()
    if quiet_io_seconds:
        print('Waiting for IEC app LOAD before DMA observations',flush=True)
        time.sleep(quiet_io_seconds)
    wait_for(lambda: read(0x7fe7,1) == b'\x01','registered launcher hit',120)
    assert read(0x7fe8,1) == b'\x01','Ultimate row was not clickable'
    wait_for(lambda: read(load_error,1) != b'\xff','launcher LOAD started',30)
    filename = read(ci.core_symbol('file'),17).split(b'\0')[0]
    assert filename == b'UOS-ULTIMATE', f'Launcher filename: {filename!r}'
    print('PASS: Apps registers six rows; right-edge hit invokes Ultimate callback',flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--machine", choices=("x64", "x128"), default="x64")
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix=f"uos-storage-{args.machine}-"))
    print(f"Artifacts: {work}", flush=True)
    disk8, disk9 = work / "system.d64", work / "empty.d64"
    shutil.copyfile(ci.STOCK, disk8)
    subprocess.run(["c1541", "-format", "empty,09", "d64", str(disk9)],
                   check=True, capture_output=True)
    payload = work / "fixture.prg"
    system_entries = len(list(Path(ci.UOS, "target").glob("*.prg")))
    payload.write_bytes(b"\x00\x50" + bytes(range(256)) * 2)
    for i in range(70):
        subprocess.run(["c1541", "-attach", str(disk8), "-write", str(payload),
                        f"scroll-{i:02d}"], check=True, capture_output=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    xv = ci.cbm.Xvfb()
    env = dict(os.environ, DISPLAY=xv.display,
               __EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL)
    log = (work / "vice.log").open("w")
    cmd = [args.machine, "-default", "-autostart", str(disk8), "-9", str(disk9),
           "-drive8true", "-drive8type", "1541", "-drive9true", "-drive9type", "1541",
           "-reu", "-reusize", "512", "-sounddev", "dummy", "-jamaction", "0",
           "-warp", "-autostart-warp", "-binarymonitor", "-binarymonitoraddress",
           f"ip4://127.0.0.1:{port}"]
    if args.machine == "x128":
        cmd[2:2] = ["-go64"]
    emu = subprocess.Popen(cmd, env=env, stdout=log, stderr=log)
    mon = None
    try:
        for _ in range(100):
            assert emu.poll() is None, (work / "vice.log").read_text()
            try:
                mon = ci.Monitor(port=port)
                break
            except OSError:
                time.sleep(0.1)
        assert mon is not None, "No VICE monitor"
        assert ci.wait_desktop_live(mon, 300), "No live desktop"
        check_getcap(mon, work)
        prefs = mon.read_mem(0x7350,0x7358); mon.resume()
        launch_from_apps(mon,work)
        browser_ready = ci.lst_symbol('uos-ultimate','ready')
        def browser_state():
            value = mon.read_mem(browser_ready,browser_ready)[0]
            mon.resume()
            return value
        wait_for(lambda: browser_state() == 1,'browser ready after app-row launch')
        assert mon.read_mem(0x7350,0x7358) == prefs
        ci.inject_keys(mon,b'\x1b')
        wait_for(lambda: browser_state() == 0xff,'browser exit')
        assert ci.wait_desktop_live(mon,120)
        launch(mon)
        fm = FileManager(mon)
        prefix = Path(ci.UOS, "target/uos-fmgr.prg").read_bytes()[2:18]
        wait_for(lambda: fm.read(ci.APP_START, 16) == prefix, "file-manager LOAD")
        wait_for(fm.ready, "initial directory painted")
        assert len(fm.names()) == 64
        assert fm.names()[0] == b"UOS"
        assert fm.ordinal() == 0
        # bank 'ram' bypasses BASIC ROM covering the bitmap.
        banks = mon.banks(); mon.resume()
        ram = banks.get("ram", banks.get("ram00", 0))
        initial = fm.read(0xa000, 8000, ram)
        assert any(initial)
        print("PASS: directory cache filled from IEC", flush=True)

        fm.goto(10)
        assert fm.value("scroll") == 1
        fm.goto(72)
        assert int.from_bytes(fm.read(fm.symbols["cachebase"], 2), "little") == 55
        assert fm.names()[fm.read(ci.FMROW)[0]] == f"SCROLL-{72-system_entries:02d}".encode()
        assert fm.read(0xa000, 8000, ram) != initial
        print("PASS: cursor scrolls past both the tenth entry and the cache boundary", flush=True)

        final_ordinal = system_entries + 69
        fm.goto(final_ordinal)
        fm.keys(b"\x11\x11")
        assert fm.ordinal() == final_ordinal
        fm.goto(0)
        fm.keys(b"\x91")
        assert fm.ordinal() == 0 and fm.value("scroll") == 0
        final = fm.read(0xa000, 8000, ram)
        (work / "initial.bitmap").write_bytes(initial)
        (work / "roundtrip.bitmap").write_bytes(final)
        different = [i for i, (a, b) in enumerate(zip(initial, final)) if a != b]
        assert not different, f"stale pixels after round-trip scroll: offsets {different[:32]}"
        print("PASS: top/bottom bounds and exact bitmap restoration", flush=True)

        if args.machine == "x128":
            assert "vdc" in banks, banks
            vdc = fm.read(0, 2000, banks["vdc"])
            assert vdc[4 * 80 + 2] == 0x3e, "VDC selection marker missing"
            assert vdc[4 * 80 + 4:4 * 80 + 7] == b"\x15\x0f\x13", vdc[324:344]
            print("PASS: VDC mirrors the selected directory entry", flush=True)

        fm.keys(b"9")
        assert not fm.names() and fm.ordinal() == 0
        for key in (b"\x11", b"\x91", b"D", b"R", b"C", b"B", b"I", b"\r"):
            fm.keys(key)
            assert fm.read(0x44)[0] == 0, f"empty directory acted on {key!r}"
        assert not fm.names()
        fm.keys(b"8")
        assert len(fm.names()) == 64 and fm.ordinal() == 0
        print("PASS: empty-drive actions are harmless; switching back restores listing", flush=True)

        fm.keys(b"0")  # device 10 has no attached drive
        assert fm.value("direrror") and not fm.names()
        fm.keys(b"8")
        assert not fm.value("direrror") and len(fm.names()) == 64
        print("PASS: absent device returns a read error and recovers", flush=True)

        fm.keys(b"9")
        ci.inject_keys(mon, b"\x1b")
        assert ci.wait_desktop_live(mon, 120), "ESC did not restore a live desktop"
        launch(mon, b"UOS-CALC")
        calc = Path(ci.UOS, "target/uos-calc.prg").read_bytes()[2:18]
        display = ci.lst_symbol("uos-calc", "dispbuf")
        wait_for(lambda: fm.read(ci.APP_START, 16) == calc, "calculator from system disk")
        wait_for(lambda: fm.read(display, 2) == b"0\0", "calculator ready")
        ci.inject_keys(mon, b"1+2=")
        wait_for(lambda: fm.read(display, 2) == b"3\0", "calculator input")
        ci.inject_keys(mon, b"\x1b")
        assert ci.wait_desktop_live(mon, 120)
        print("PASS: leaving drive 9 preserves system-disk app launching", flush=True)
        loaderr = ci.core_symbol("LOADERR")
        mon.write_mem(loaderr, b"\xff")
        launch(mon, b"UOS-MISSING-FILE")  # maximum 16-character filename
        wait_for(lambda: fm.read(loaderr) == b"\x04", "missing-file load error")
        assert ci.wait_desktop_live(mon, 120), "failed load did not restore desktop"
        fillfile = ci.core_symbol("FILLFILE_RT")
        core = Path(ci.UOS, "target/uos.prg").read_bytes()
        origin = int.from_bytes(core[:2], "little")
        assert fm.read(fillfile, 16) == core[2 + fillfile - origin:18 + fillfile - origin]
        print("PASS: failed 16-character app load preserves loader code and desktop", flush=True)
        print("CI-STORAGE PASS", flush=True)
    finally:
        if mon is not None:
            mon.close()
        emu.terminate()
        emu.wait(timeout=15)
        xv.stop()
        log.close()


if __name__ == "__main__":
    main()
