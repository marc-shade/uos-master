#!/usr/bin/env python3
"""Hardware check for the self-setting clock and the network driver.

Runs against the real C128 + Ultimate II+ (192.168.1.237) after deploy_hw.py.
Compare OS state, the cartridge's running clock and the display with the host:

  1. uos-net's data bytes over DMA: NET_STATE must be 0 (SNTP synced), the
     interface address must be non-empty, and the recorded boot-sync timestamp
     must be recent (no more than 6 hours old or 2 minutes in the future).
  2. the running Ultimate RTC through DOS GET_TIME: two readings must
     advance and agree with the host clock. REST Clock Settings are saved
     configuration fields, not a live RTC reading.
  3. the 80-column display, copied out of VDC RAM with probes/vdcdump.bin
     (as hw_vdc_check.py does): row 0 must carry "HH:MM xM  ntp".

Exit 0 = all three witnesses agree. Retains exact build hashes and results.
"""
import datetime
import importlib.util
import hashlib
import json
import os
import re
import struct
import sys
import time
import tempfile
from pathlib import Path
from importlib.machinery import SourceFileLoader

_l = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
_s = importlib.util.spec_from_loader("cbm", _l)
cbm = importlib.util.module_from_spec(_s)
_l.exec_module(cbm)
UOS = os.path.dirname(os.path.abspath(__file__))
TICK_VEC, TRAMP, DUMP = 0x033C, 0x7F00, 0x6000
VEC0_OFF, VEC1_OFF = 0x50, 0x55

inc = open(os.path.join(UOS, "src/routines.inc")).read()
NET_BASE = int(re.search(r"^NET_BASE\s*=\s*\$([0-9a-f]{4})", inc, re.M).group(1), 16)
NET = {m.group(1): NET_BASE + int(m.group(2), 16)
       for m in re.finditer(r"^(NET_[A-Z]+)\s*=\s*NET_BASE\+\$([0-9a-f]{2})", inc, re.M)}
TAGS = {0: "ntp synced", 1: "no ntp reply", 2: "no network", 3: "no command interface",
        4: "ntp host unresolved/open failed", 0xff: "never attempted"}


def decode(cells):
    out = ""
    for c in cells:
        c &= 0x7f
        if 1 <= c <= 0x1a:
            out += chr(c + 96)
        elif 0x41 <= c <= 0x5a or 0x20 <= c <= 0x3f:
            out += chr(c)
        else:
            out += "."
    return out.rstrip()


def vdc_rows(u):
    vec = u.read_mem(TICK_VEC, 2)
    code = bytearray(open(os.path.join(UOS, "probes/vdcdump.bin"), "rb").read()[2:])
    assert code[VEC0_OFF - 1] == 0xA9 and code[VEC1_OFF - 1] == 0xA9
    code[VEC0_OFF], code[VEC1_OFF] = vec[0], vec[1]
    u.write_mem(TRAMP, bytes(code))
    u.write_mem(TICK_VEC, struct.pack("<H", TRAMP))
    for _ in range(15):
        time.sleep(2)
        if u.read_mem(TICK_VEC, 2) == vec:
            break
    else:
        cbm.die("VDC dump never ran (desktop not in MAINLOOP?)")
    mem = u.read_mem(DUMP, 2000)
    return [decode(mem[r * 80:(r + 1) * 80]) for r in range(25)]


def main():
    u = cbm.Ultimate()
    work = Path(tempfile.mkdtemp(prefix="uos-hardware-clock-"))
    print(f"Clock evidence: {work}", flush=True)
    if u.read_mem(TICK_VEC, 2) == b"\x00\x00":
        cbm.die("tick vector is $0000: uOS desktop is not live (run deploy_hw.py)")
    # 1. the driver's own record of the sync
    blk = u.read_mem(NET["NET_STATE"], 0x42)
    state = blk[0]
    hour, minute, sec = blk[1], blk[2], blk[3]
    year = blk[4] | blk[5] << 8
    mon, day, wday, tz = blk[6], blk[7], blk[8], blk[9]
    tz = tz - 256 if tz > 127 else tz
    ipstr = blk[0x0e:0x1e].split(b"\x00")[0].decode("latin-1")
    stat = blk[0x21:0x42].split(b"\x00")[0].decode("latin-1")
    print(f"NET_STATE={state} ({TAGS.get(state, '?')}) ip={ipstr!r} "
          f"synced local {hour:02d}:{minute:02d}:{sec:02d} {year}/{mon:02d}/{day:02d} wday={wday} "
          f"tz={tz / 4:+.2f} h  last status={stat!r}")
    if state != 0:
        cbm.die(f"FAIL: clock not synced from the network (NET_STATE={state}: {TAGS.get(state, '?')})")
    if not ipstr:
        cbm.die("FAIL: synced but no interface address recorded")
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(minutes=tz * 15)))
    synced = datetime.datetime(year, mon, day, hour, minute, sec, tzinfo=now.tzinfo)
    age = (now - synced).total_seconds()
    print(f"host now {now:%Y-%m-%d %H:%M:%S} in that zone; sync happened {age:.0f}s ago")
    if not (-120 <= age <= 3600 * 6):
        cbm.die(f"FAIL: synced time is {age:.0f}s from this host's clock (allowed -120..21600)")
    # 2. DOS GET_TIME reads the running clock. REST Clock Settings are
    # saved presets; their old 2015 values caused a false frozen-RTC diagnosis.
    from hw_uci_check import Probe
    probe = Probe(u, work)
    runtime = []
    for _ in range(2):
        reply = probe.ok(b"\x01\x26")
        assert not reply["clipped"] and len(reply["records"]) == 1
        runtime.append(reply["records"][0][0].decode("ascii"))
    stamps = [datetime.datetime.strptime(value, "%Y/%m/%d %H:%M:%S").replace(tzinfo=now.tzinfo)
              for value in runtime]
    now = datetime.datetime.now(now.tzinfo)
    drift = (now - stamps[-1]).total_seconds()
    assert stamps[1] > stamps[0], f"Runtime RTC did not advance: {runtime}"
    assert abs(drift) <= 180, f"Runtime RTC differs from host by {drift:.0f}s: {runtime}"
    print(f"Ultimate runtime RTC {runtime[0]} -> {runtime[1]}; host difference {drift:+.0f}s")
    # 3. the 80-column display. The 8563 drops random cells while the DMA
    # copy runs (documented in the driver), so a fresh write can read blank
    # in one snapshot; retry until a stable frame carries the clock.
    m = None
    for _ in range(6):
        rows = vdc_rows(u)
        clk = rows[0][58:]
        m = re.search(r"(\d\d):(\d\d) ([AP])M\s+ntp", clk)
        if m:
            break
        time.sleep(3)
    for i in (0, 1, 2):
        print(f"{i:2d}: {rows[i]}")
    if not m:
        cbm.die(f"FAIL: row 0 never carried the synced clock (last: {clk!r})")
    h12, mm = int(m.group(1)), int(m.group(2))
    h24 = h12 % 12 + (12 if m.group(3) == "P" else 0)
    shown = now.replace(hour=h24, minute=mm, second=0, microsecond=0)
    delta = abs((now - shown).total_seconds())
    if delta > 180:
        cbm.die(f"FAIL: displayed {h24:02d}:{mm:02d} is {delta:.0f}s from the host clock")
    print(f"PASS: clock self-set from the network on the real C128 "
          f"(driver: synced {age:.0f}s ago; Ultimate RTC: advancing and correct; "
          f"80-col row 0: {clk.strip()!r})")

    report = {"build": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in Path(UOS, "target").glob("*.prg")},
              "net_state": state, "ip": ipstr, "synced_time": synced.isoformat(),
              "runtime_rtc_readings": runtime, "rtc_host_difference_seconds": round(drift, 3),
              "vdc_clock": clk.strip(), "checks": ["SNTP and interface address",
              "runtime RTC advances and matches host", "VDC clock matches host"]}
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
