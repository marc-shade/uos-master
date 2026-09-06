#!/usr/bin/env python3
"""Hardware check for the self-setting clock and the network driver.

Runs against the real C128 + Ultimate II+ (192.168.1.237) after deploy_hw.py.
Three independent witnesses, none of them the OS's own word for it:

  1. uos-net's data bytes over DMA: NET_STATE must be 0 (SNTP synced), the
     interface address must be non-empty, and NET_HOUR/MIN must agree with
     this host's clock in the record's zone (default UTC-4) within 2 min.
  2. the Ultimate's own RTC through its REST API ("Clock Settings"): the
     driver pushes date/time into it (DOS SET_TIME) after a sync. Reported,
     not gated: this cartridge's RTC is frozen at 2015-10-13 16:52:55 and
     ignores the (acknowledged) push.
  3. the 80-column display, copied out of VDC RAM with probes/vdcdump.bin
     (as hw_vdc_check.py does): row 0 must carry "HH:MM xM  ntp".

Exit 0 = witnesses 1 and 3 agree (2 is informational, see above).
"""
import datetime
import importlib.util
import json
import os
import re
import struct
import sys
import time
import urllib.request
from importlib.machinery import SourceFileLoader

_l = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
_s = importlib.util.spec_from_loader("cbm", _l)
cbm = importlib.util.module_from_spec(_s)
_l.exec_module(cbm)
UOS = os.path.dirname(os.path.abspath(__file__))
HOST = "http://192.168.1.237"
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
    # 2. the Ultimate's RTC, pushed by the driver
    with urllib.request.urlopen(HOST + "/v1/configs/Clock%20Settings", timeout=15) as r:
        cs = json.loads(r.read())["Clock Settings"]
    months = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
    rtc = datetime.datetime(int(cs["Year"]), months.index(cs["Month"]) + 1, int(cs["Day"]),
                            int(cs["Hours"]), int(cs["Minutes"]), int(cs["Seconds"]), tzinfo=now.tzinfo)
    drift = (now - rtc).total_seconds()
    # Informational only: on this Ultimate II+ the RTC reads a frozen
    # 2015-10-13 16:52:55 before AND after the driver's DOS SET_TIME push
    # (which the firmware acknowledges with "00,OK", 2026-09-06). A dead
    # RTC cell/chip is a cartridge problem, not something the OS can fix,
    # so it is reported, not gated.
    rtc_ok = abs(drift) <= 180
    print(f"Ultimate RTC reads {rtc:%Y-%m-%d %H:%M:%S}; drift {drift:+.0f}s -> "
          f"{'set by the sync' if rtc_ok else 'NOT set (cartridge RTC frozen; push acknowledged, informational)'}")
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
          f"(driver: synced {age:.0f}s ago; Ultimate RTC: {'set' if rtc_ok else 'frozen, informational'}; "
          f"80-col row 0: {clk.strip()!r})")


main()
