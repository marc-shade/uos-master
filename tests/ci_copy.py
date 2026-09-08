#!/usr/bin/env python3
"""Real IEC copies in both directions; verify every byte and file type.

The source is larger than 16 KiB and is not a multiple of 256. That covers
multi-page channel switching, the old silent size cap, and the last byte.
VICE runs without warp with two true 1541 drives and a 512 KiB REU.
"""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

import ci_fm as ci
from ci_storage import FileManager, launch, wait_for


def main():
    work = Path(tempfile.mkdtemp(prefix="uos-copy-"))
    print(f"Artifacts: {work}", flush=True)
    disk8, disk9 = work / "system.d64", work / "data.d64"
    shutil.copyfile(ci.STOCK, disk8)
    subprocess.run(["c1541", "-format", "data,09", "d64", str(disk9)],
                   check=True, capture_output=True)
    source = b"\x00\x50" + bytes((i * 73 + i // 251) & 255 for i in range(18 * 1024 + 5))
    fixture = work / "source.prg"
    fixture.write_bytes(source)
    subprocess.run(["c1541", "-attach", str(disk8), "-write", str(fixture), "copy-source"],
                   check=True, capture_output=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    xv = ci.cbm.Xvfb()
    env = dict(os.environ, DISPLAY=xv.display,
               __EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL)
    log = (work / "vice.log").open("w")
    emu = subprocess.Popen(
        ["x64", "-default", "-autostart", str(disk8), "-9", str(disk9),
         "-drive8true", "-drive8type", "1541", "-drive9true", "-drive9type", "1541",
         "-reu", "-reusize", "512", "-sounddev", "dummy", "-jamaction", "0",
         "-binarymonitor", "-binarymonitoraddress", f"ip4://127.0.0.1:{port}"],
        env=env, stdout=log, stderr=log)
    mon = None
    try:
        for _ in range(100):
            assert emu.poll() is None, (work / "vice.log").read_text()
            try:
                mon = ci.Monitor(port=port)
                break
            except OSError:
                time.sleep(0.1)
        assert mon is not None
        assert ci.wait_desktop_live(mon, 600), "No live desktop"
        launch(mon)
        fm = FileManager(mon)
        prefix = Path(ci.UOS, "target/uos-fmgr.prg").read_bytes()[2:18]
        wait_for(lambda: fm.read(ci.APP_START, 16) == prefix, "file-manager LOAD", 300)
        wait_for(fm.ready, "directory scan + painting", 300)
        print("PASS: desktop and file manager ready", flush=True)
        fm.goto(fm.names().index(b"COPY-SOURCE"))
        fm.keys(b"BCOPY9\r")
        assert fm.read(fm.symbols["linebuf"], 38).split(b"\0")[0] == b"COPIED TO DEVICE 9"
        fm.keys(b"9")
        assert fm.names() == [b"COPY9"], fm.names()
        assert fm.read(fm.symbols["fmtype"], 3) == b"PRG"
        print("PASS: >16 KiB PRG copied to device 9; type retained", flush=True)

        fm.keys(b"BCOPY-BACK\r")
        assert fm.read(fm.symbols["linebuf"], 38).split(b"\0")[0] == b"COPIED TO DEVICE 8"
        fm.keys(b"8")
        assert b"COPY-BACK" in fm.names()
        print("PASS: reverse copy appears in the live drive-8 listing", flush=True)

        fm.goto(fm.names().index(b"COPY-SOURCE"))
        fm.keys(b"BCOPY9\r")
        assert fm.read(fm.symbols["linebuf"], 38).split(b"\0")[0] == b"COPY FAILED"
        print("PASS: existing destination rejected", flush=True)
        ci.inject_keys(mon, b"\x1b")
        assert ci.wait_desktop_live(mon, 120), "No desktop after copy workflow"
        mon.quit_emulator()
        emu.wait(timeout=20)
        mon.close()
        mon = None

        for disk, name in ((disk9, "copy9"), (disk8, "copy-back")):
            out = work / (name + ".prg")
            subprocess.run(["c1541", "-attach", str(disk), "-read", name, str(out)],
                           check=True, capture_output=True)
            assert out.read_bytes() == source, f"File contents differ: {name}"
            print(f"PASS: {name}: all {len(source)} bytes persisted intact", flush=True)
        print("CI-COPY PASS", flush=True)
    finally:
        if mon is not None:
            mon.close()
        if emu.poll() is None:
            emu.terminate()
            emu.wait(timeout=20)
        xv.stop()
        log.close()


if __name__ == "__main__":
    main()
