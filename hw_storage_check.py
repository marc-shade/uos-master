#!/usr/bin/env python3
"""Boot and verify the storage/VDC changes on the physical C128 + Ultimate.

Mounts a private test disk on drive A, boots uOS, scrolls across a cache
boundary, reads VIC pixels and every visible VDC filename, then returns to
the desktop. Drive B is untouched. On success mounts the distributable
system disk on A and boots it again. Source/build must remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tests"))
import ci_fm as ci
from ci_storage import FileManager, launch, wait_for
from cap_hw_screen import grab, render
from hwlib import desk_tick


class HardwareMonitor:
    def __init__(self, ultimate):
        self.ultimate = ultimate

    def read_mem(self, start, end, bank=0, memspace=0):
        return self.ultimate.read_mem(start, end - start + 1)

    def write_mem(self, start, data, bank=0, memspace=0):
        for i in range(0, len(data), 128):
            self.ultimate.write_mem(start + i, data[i:i + 128])

    def resume(self):
        pass  # DMA reads/writes do not stop the CPU


def read_vdc(mon, work):
    prg = work / "vdc-dump.prg"
    subprocess.run(["64tass", "-a", str(ROOT / "probes/vdc-irqdump.asm"),
                    "-o", str(prg)], check=True, capture_output=True)
    oldirq = mon.read_mem(0x0314, 0x0315)
    assert oldirq != b"\x00\x7c", "previous VDC dump still installed"
    mon.write_mem(0x7c00, prg.read_bytes()[2:])
    mon.write_mem(0x7cf0, oldirq + b"\0")
    mon.write_mem(0x0314, b"\x00\x7c")
    wait_for(lambda: mon.read_mem(0x7cf2, 0x7cf2) != b"\0", "VDC IRQ dump", 10)
    assert mon.read_mem(0x7cf2, 0x7cf2) == b"\x01", "VDC ready timeout"
    assert mon.read_mem(0x0314, 0x0315) == oldirq, "IRQ vector was not restored"
    return bytes(mon.read_mem(0x7400, 0x7bcf))


def screen_code(petscii):
    if 0x40 <= petscii < 0x60:
        return petscii - 0x40
    if 0xc0 <= petscii < 0xff:
        return petscii - 0x80
    return petscii


def quick_check(ult, mon, work, report):
    """Verify the final loader fixes and leave the distributable running."""
    ult.mount((ROOT / "target/ultos.d64").read_bytes(), "a", "d64", "readwrite")
    ult.run_prg((ROOT / "target/uos.prg").read_bytes())
    wait_for(lambda: mon.read_mem(0x033c, 0x033d) == desk_tick().to_bytes(2, "little"),
             "desktop tick vector", 300)
    assert ci.wait_desktop_live(mon, 120)
    launch(mon)
    fm = FileManager(mon)
    prefix = (ROOT / "target/uos-fmgr.prg").read_bytes()[2:18]
    wait_for(lambda: fm.read(ci.APP_START, 16) == prefix, "file-manager LOAD", 180)
    wait_for(fm.ready, "file manager ready", 180)
    fm.goto(12)
    assert fm.names()[12] == b"UOS-CALC"
    vdc = read_vdc(mon, work)
    (work / "vdc-final.bin").write_bytes(vdc)
    names, scroll = fm.names(), fm.value("scroll")
    for row, name in enumerate(names[scroll:scroll + 10]):
        wanted = bytes(map(screen_code, name))
        assert vdc[(4 + row) * 80 + 4:(4 + row) * 80 + 4 + len(wanted)] == wanted
    render(grab(ult, verbose=False), str(work / "file-manager.png"))
    report["checks"].append("final build scrolling and exact VDC filenames")
    print("PASS: final build file manager + both displays", flush=True)

    fm.keys(b"9")
    ci.inject_keys(mon, b"\x1b")
    assert ci.wait_desktop_live(mon, 120)
    launch(mon, b"UOS-CALC")
    calc = (ROOT / "target/uos-calc.prg").read_bytes()[2:18]
    display = ci.lst_symbol("uos-calc", "dispbuf")
    wait_for(lambda: fm.read(ci.APP_START, 16) == calc, "calculator loaded from system disk", 180)
    wait_for(lambda: fm.read(display, 2) == b"0\0", "calculator ready", 180)
    ci.inject_keys(mon, b"1+2=")
    wait_for(lambda: fm.read(display, 2) == b"3\0", "calculator result")
    ci.inject_keys(mon, b"\x1b")
    assert ci.wait_desktop_live(mon, 120)
    report["checks"].append("drive-9 exit restores drive-8 app loading; calculator 1+2=3")
    print("PASS: browsing drive 9 does not break the next app launch", flush=True)

    error = ci.core_symbol("LOADERR")
    mon.write_mem(error, b"\xff")
    launch(mon, b"UOS-MISSING-FILE")
    wait_for(lambda: fm.read(error) == b"\x04", "missing-file error", 180)
    assert ci.wait_desktop_live(mon, 120)
    fillfile = ci.core_symbol("FILLFILE_RT")
    core = (ROOT / "target/uos.prg").read_bytes()
    origin = int.from_bytes(core[:2], "little")
    assert fm.read(fillfile, 16) == core[2 + fillfile - origin:18 + fillfile - origin]
    report["checks"].append("16-character missing app preserves loader and live desktop")
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"HW-QUICK PASS; final build running on C128; evidence {work}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="final loader/display checks on release disk")
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="uos-hardware-storage-"))
    print(f"Hardware evidence: {work}", flush=True)
    ult = ci.cbm.Ultimate()
    mon = HardwareMonitor(ult)
    (work / "drives-before.json").write_text(ult.drives())
    report = {"build": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (ROOT / "target").glob("*.prg")}, "checks": []}
    if args.quick:
        quick_check(ult, mon, work, report)
        return
    disk = work / "test.d64"
    shutil.copyfile(ci.STOCK, disk)
    payload = work / "fixture.prg"
    payload.write_bytes(b"\x00\x50" + bytes(range(256)))
    for i in range(70):
        subprocess.run(["c1541", "-attach", str(disk), "-write", str(payload),
                        f"scroll-{i:02d}"], check=True, capture_output=True)
    ult.mount(disk.read_bytes(), "a", "d64", "readwrite")
    ult.run_prg((ROOT / "target/uos.prg").read_bytes())
    print("Booting the test disk on the C128", flush=True)
    wait_for(lambda: mon.read_mem(0x033c, 0x033d) == desk_tick().to_bytes(2, "little"),
             "desktop tick vector", 300)
    assert ci.wait_desktop_live(mon, 120)
    launch(mon)
    fm = FileManager(mon)
    prefix = (ROOT / "target/uos-fmgr.prg").read_bytes()[2:18]
    wait_for(lambda: fm.read(ci.APP_START, 16) == prefix, "file-manager LOAD", 180)
    wait_for(fm.ready, "file manager ready", 180)
    assert len(fm.names()) == 64 and fm.ordinal() == 0
    report["checks"].append("boot and 64-entry IEC cache")
    print("PASS: real IEC directory scan and input loop", flush=True)

    initial = grab(ult, verbose=False)
    render(initial, str(work / "initial.png"))
    timings = []
    for ordinal in (10, 64, 72, 0):
        started = time.monotonic()
        fm.goto(ordinal)
        timings.append({"ordinal": ordinal, "seconds": round(time.monotonic() - started, 3)})
        vdc = read_vdc(mon, work)
        (work / f"vdc-{ordinal}.bin").write_bytes(vdc)
        names = fm.names()
        scroll = fm.value("scroll")
        for row, name in enumerate(names[scroll:scroll + 10]):
            wanted = bytes(map(screen_code, name))
            got = vdc[(4 + row) * 80 + 4:(4 + row) * 80 + 4 + len(wanted)]
            assert got == wanted, f"VDC row {row} at ordinal {ordinal}: {got!r} != {wanted!r}"
        marker_row = fm.read(ci.FMROW)[0] - scroll + 4
        assert vdc[marker_row * 80 + 2] == 0x3e
        print(f"PASS: entry {ordinal}; all visible VDC filenames + marker read back", flush=True)
    report["checks"].append("scroll across viewport/cache boundaries; exact VDC rows")
    final = grab(ult, verbose=False)
    render(final, str(work / "roundtrip.png"))
    assert initial == final, "VIC bitmap changed after scrolling back to the first entry"
    report["checks"].append("exact VIC bitmap restored after scrolling")
    report["timings"] = timings
    ci.inject_keys(mon, b"\x1b")
    assert ci.wait_desktop_live(mon, 120)
    report["checks"].append("desktop input dispatch restored")
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    ult.mount((ROOT / "target/ultos.d64").read_bytes(), "a", "d64", "readwrite")
    ult.run_prg((ROOT / "target/uos.prg").read_bytes())
    wait_for(lambda: mon.read_mem(0x033c, 0x033d) == desk_tick().to_bytes(2, "little"),
             "release desktop tick vector", 300)
    assert ci.wait_desktop_live(mon, 120)
    print(f"HW-STORAGE PASS; current build running on C128; evidence {work}", flush=True)


if __name__ == "__main__":
    main()
