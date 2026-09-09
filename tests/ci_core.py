#!/usr/bin/env python3
"""Exercise the assembled core's public capability ABI with Py65.

Install tests/requirements-uci.txt. This test needs no VICE or local cbm helper.
GETCAP locates resident software entry points; it does not probe peripherals.
"""
import argparse
import hashlib
import json
from pathlib import Path

from py65.devices.mpu6502 import MPU

ROOT = Path(__file__).resolve().parents[1]
GETCAP = 0x082f
EXPECTED = {1: 0xc000, 2: 0xcc00, 3: 0x9c00, 4: 0x082c, 5: 0x0829, 6: 0x4100, 7: 0x4c80}


class Memory:
    def __init__(self, image):
        self.ram = bytearray((i * 37 + 0x53) & 255 for i in range(65536))
        origin = int.from_bytes(image[:2], "little")
        self.ram[origin:origin + len(image) - 2] = image[2:]
        self.reads, self.writes = [], []

    def __getitem__(self, address):
        self.reads.append(address)
        return self.ram[address]

    def __setitem__(self, address, value):
        self.writes.append(address)
        self.ram[address] = value


def check_getcap(image):
    origin = int.from_bytes(image[:2], "little")
    assert origin == 0x0801 and origin + len(image) - 2 <= 0x1000
    mem = Memory(image)
    assert mem.ram[GETCAP] == 0x4c, "GETCAP public slot is not a JMP"
    entry = int.from_bytes(mem.ram[GETCAP + 1:GETCAP + 3], "little")
    assert origin <= entry < origin + len(image) - 2
    calls, longest = 0, 0
    for flags in (0, MPU.CARRY | MPU.DECIMAL | MPU.INTERRUPT | MPU.NEGATIVE | MPU.OVERFLOW):
        for ids in (range(256), range(255, -1, -1)):
            for cap_id in ids:
                cpu = MPU(memory=mem, pc=GETCAP)
                cpu.a, cpu.x, cpu.y = cap_id ^ 0xa5, cap_id, cap_id ^ 0x69
                cpu.p = flags | cpu.UNUSED
                initial_sp = (cap_id * 11 + flags) & 255
                cpu.sp = initial_sp
                cpu.stPushWord(0x02ff)  # RTS returns to $0300
                mem.reads.clear()
                mem.writes.clear()
                for step in range(128):
                    if cpu.pc == 0x0300:
                        break
                    assert origin <= cpu.pc < origin + len(image) - 2, hex(cpu.pc)
                    cpu.step()
                else:
                    raise AssertionError(f"GETCAP({cap_id}) did not return")
                actual = cpu.a | cpu.x << 8
                expected = EXPECTED.get(cap_id, 0)
                assert actual == expected, (
                    f"GETCAP({cap_id}) = ${actual:04x}; expected ${expected:04x}")
                assert cpu.y == cap_id ^ 0x69, f"Y changed for ID {cap_id}"
                assert cpu.sp == initial_sp, f"Unbalanced stack for ID {cap_id}"
                mask = cpu.DECIMAL | cpu.INTERRUPT
                assert cpu.p & mask == flags & mask, "D/I flags changed"
                assert all(0x0100 <= a < 0x0200 for a in mem.writes), (
                    f"GETCAP wrote outside its stack: {mem.writes}")
                assert all(a < 0xd000 for a in mem.reads), "GETCAP probed I/O/ROM"
                calls += 1
                longest = max(longest, step)
    return {"calls": calls, "ids": 256, "longest_instruction_count": longest,
            "checks": ["known entry points and all unknown IDs",
                       "forward/reverse repeated calls with varied A and status flags",
                       "Y, zero page, non-stack RAM and D/I flags preserved",
                       "balanced stack including page wrap; no I/O access"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, default=ROOT / "target/uos.prg")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    image = args.image.read_bytes()
    report = {"core_sha256": hashlib.sha256(image).hexdigest()}
    try:
        report.update(check_getcap(image))
        report["passed"] = True
        print(f"PASS: GETCAP; {report['calls']} calls across all 256 IDs", flush=True)
    except AssertionError as error:
        report.update(passed=False, error=str(error))
        print(f"FAIL: {error}", flush=True)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
