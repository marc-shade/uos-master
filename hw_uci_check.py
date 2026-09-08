#!/usr/bin/env python3
"""Verify the assembled UCI transport on the reference C128/Ultimate.

Boots the distributable on A, exercises identification, drive inventory,
long binary echo packets and read-only directory streaming, restores the
original DOS path, then leaves the desktop running. Does not change B.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from hw_storage_check import ci, HardwareMonitor, ROOT, wait_for
from hwlib import desk_tick, lst_symbol


class Probe:
    def __init__(self, ultimate, work):
        self.ultimate = ultimate
        self.mon = HardwareMonitor(ultimate)
        output = work / "uci-stream.prg"
        subprocess.run(["64tass", "-a", str(ROOT / "probes/uci-stream.asm"),
                        "-o", str(output)], check=True, capture_output=True)
        self.code = output.read_bytes()[2:]

    def command(self, data):
        assert 2 <= len(data) <= 896
        assert ci.wait_desktop_live(self.mon, 30), "desktop not dispatching"
        tick = bytes(self.mon.read_mem(0x033c, 0x033d))
        self.mon.write_mem(0x5000, self.code)
        self.mon.write_mem(0x5500, data)
        self.mon.write_mem(0x5f00, tick + len(data).to_bytes(2, "little") + bytes(9))
        self.mon.write_mem(0x033c, b"\x00\x50")
        wait_for(lambda: self.mon.read_mem(0x5f04, 0x5f04) == b"\x01", "UCI tick client", 90)
        meta = bytes(self.mon.read_mem(0x5f04, 0x5f0c))
        result, carry, count, full = meta[1], meta[2], int.from_bytes(meta[3:5], "little"), meta[5]
        end = int.from_bytes(meta[6:8], "little")
        assert 0x6000 <= end <= 0x7c00, f"invalid capture end: {end:#x}"
        raw = bytes(self.mon.read_mem(0x6000, end - 1)) if end > 0x6000 else b""
        records, offset = [], 0
        while offset < len(raw):
            size = int.from_bytes(raw[offset:offset + 2], "little")
            clipped = raw[offset + 2]
            offset += 3
            assert offset + size <= len(raw), "partial capture record"
            records.append((raw[offset:offset + size], clipped))
            offset += size
        assert full or len(records) == count
        status = bytes(self.mon.read_mem(0x9142, 0x9161)).split(b"\0")[0].decode("ascii", "replace")
        assert self.mon.read_mem(0x033c, 0x033d) == tick
        return {"code": result, "carry": carry, "count": count, "full": full,
                "clipped": meta[8], "status": status, "records": records}

    def ok(self, data):
        result = self.command(data)
        assert result["code"] == 0 and not result["carry"], result
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-boot", action="store_true", help="test the current, already booted build")
    parser.add_argument("--rtc-only", action="store_true", help="read the running cartridge RTC through DOS GET_TIME")
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="uos-hardware-uci-"))
    print(f"Hardware UCI evidence: {work}", flush=True)
    report = {"build": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (ROOT / "target").glob("*.prg")}, "checks": []}
    ult = ci.cbm.Ultimate()
    mon = HardwareMonitor(ult)
    if not (args.no_boot or args.rtc_only):
        ult.mount((ROOT / "target/ultos.d64").read_bytes(), "a", "d64", "readwrite")
        ult.run_prg((ROOT / "target/uos.prg").read_bytes())
    wait_for(lambda: mon.read_mem(0x033c, 0x033d) == desk_tick().to_bytes(2, "little"),
             "booted desktop", 300)
    assert ci.wait_desktop_live(mon, 120)
    probe = Probe(ult, work)
    start = 0x8a00
    finish = lst_symbol("uos-net", "uci_vars")
    code_before = bytes(mon.read_mem(start, finish - 1))
    reference = (ROOT / "target/uos-net.prg").read_bytes()
    assert code_before == reference[2:2 + finish - start], "current transport differs from target"
    if args.rtc_only:
        readings = [probe.ok(b"\x01\x26")["records"][0][0].decode("ascii") for _ in range(2)]
        report["runtime_rtc_readings"] = readings
        (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"DOS GET_TIME runtime RTC: {readings}", flush=True)
        return

    for target, title in ((1, "DOS"), (4, "Control")):
        result = probe.ok(bytes([target, 1]))
        identity = result["records"][0][0].decode("ascii", "replace")
        report[title.lower() + "_identity"] = identity
        assert identity.strip() and not result["clipped"]
        print(f"PASS: {title} target identifies as {identity!r}", flush=True)
    inventory = probe.ok(b"\x04\x29\x01")["records"][0][0]
    assert inventory and (len(inventory) - 1) % 3 == 0, inventory.hex()
    report["inventory_raw"] = inventory.hex()
    report["inventory_complete"] = len(inventory) == 1 + inventory[0] * 3
    report["drive_records_received"] = [
        {"type": inventory[i], "iec": inventory[i + 1], "power": inventory[i + 2]}
        for i in range(1, len(inventory), 3)]
    report["checks"].append("DOS/control identification and bounded drive-inventory response")
    if not report["inventory_complete"]:
        print(f"INCOMPLETE: firmware inventory declares {inventory[0]} devices but sends "
              f"{len(report['drive_records_received'])} records ({inventory.hex()})", flush=True)
    else:
        print(f"PASS: complete inventory: {report['drive_records_received']}", flush=True)

    for size in (300, 512, 896):
        command = b"\x01\xf0" + bytes((i * 73 + i // 251) & 255 for i in range(size - 2))
        result = probe.ok(command)
        expected = [(command[:512], int(size > 512))]
        assert result["records"] == expected, f"{size}-byte echo differs"
        assert result["clipped"] == int(size > 512) and result["count"] == 1
        print(f"PASS: {size}-byte binary command/echo; clipped={result['clipped']}", flush=True)
    report["checks"].append("300/512/896-byte binary commands and echo packets; explicit 512-byte receive bound")

    original = probe.ok(b"\x01\x12")["records"][0][0]
    try:
        directories = []
        pending = [b"/", b"/Usb0/", b"/Temp/"]
        for path in pending:
            probe.ok(b"\x01\x11" + path)
            opened = probe.command(b"\x01\x13")
            assert opened["code"] in (0, 1) and not opened["carry"], opened
            if opened["code"] == 1:
                directories.append({"path": path.decode(), "count": 0, "captured_bytes": 0})
                continue
            result = probe.ok(b"\x01\x14")
            assert not result["clipped"] and all(flag == 0 for _, flag in result["records"])
            data_bytes = sum(len(data) for data, _ in result["records"])
            directories.append({"path": path.decode(), "count": result["count"],
                                "captured_bytes": data_bytes, "capture_full": bool(result["full"])})
            print(f"PASS: {path.decode()} streamed {result['count']} entries; captured {data_bytes} bytes", flush=True)
            if data_bytes > 512:
                break
            if path.startswith(b"/Usb0/") and path.count(b"/") < 4:
                # Read-only metadata traversal; do not assume the root itself
                # contains enough entries for the large-directory check.
                for entry, _ in result["records"]:
                    if (entry and entry[0] & 0x10 and not entry[0] & 0x02
                            and entry[1:] not in (b".", b"..")):
                        if len(pending) == 40:
                            break
                        pending.append(path + entry[1:] + b"/")
        assert any(d["captured_bytes"] > 512 for d in directories), "No large directory was exercised"
        report["directories"] = directories
        report["checks"].append("read-only multipart directories exceeding the reply buffer")
    finally:
        probe.ok(b"\x01\x11" + original)

    assert bytes(mon.read_mem(start, finish - 1)) == code_before, "transport instructions changed"
    assert ci.wait_desktop_live(mon, 120)
    report["checks"].append("transport instructions intact; original DOS path and live desktop restored")
    (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"HW-UCI PASS; final build running on C128; evidence {work}", flush=True)


if __name__ == "__main__":
    main()
