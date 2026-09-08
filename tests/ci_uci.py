#!/usr/bin/env python3
"""Run the assembled UCI driver against a register/FIFO model using Py65.

Install tests/requirements-uci.txt. No developer-local cbm helper or VICE
is needed. These protocol/CPU checks complement real cartridge tests.
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import re

from uci_bus import ROOT, UCIBus, load_driver, run_command

DATA, LENGTH, DIRN = 0x8800, 0x913f, 0x9163
TRUNC, PACKET_TRUNC, PACKETS = 0x9167, 0x9168, 0x9169
IMAGE = ROOT / "target/uos-net.prg"


def word(bus, address):
    return int.from_bytes(bus.ram[address:address + 2], "little")


def run(bus, **kwargs):
    load_driver(bus, IMAGE)
    # Canary around the response region: adjacent transport instructions and
    # the entire control table must survive. Driver variables live at its end.
    listing = IMAGE.with_suffix(".lst").read_text(encoding="latin-1")
    match = re.search(r"^[.>]([0-9a-fA-F]+)\s+.*\buci_vars:", listing, re.M)
    assert match, "uci_vars missing from listing"
    code_end = int(match.group(1), 16)
    code = bytes(bus.ram[0x8a00:code_end])
    bus.ram[0x9000:0x9100] = bytes([0xa5]) * 256
    cpu, steps = run_command(bus, load=False, **kwargs)
    assert bus.ram[0x8a00:code_end] == code, "Transport instructions corrupted"
    assert bus.ram[0x9000:0x9100] == bytes([0xa5]) * 256, "Control table corrupted"
    assert not bus.discarded, f"ACK discarded {bus.discarded} unread bytes"
    return cpu, steps


def test_status_and_binary_data():
    payload = b"\0\x80\xff\x03"
    bus = UCIBus([(payload, b"07,NOT READY")])
    cpu, _ = run(bus, command=b"\x04\x29\x01")
    assert cpu.a == 7 and not cpu.p & cpu.CARRY
    assert bytes(bus.ram[DATA:DATA + word(bus, LENGTH)]) == payload
    assert bus.commands == [b"\x04\x29\x01"] and bus.accepted == 1


def test_aggregate_overflow():
    payload = bytes(i & 255 for i in range(896))
    bus = UCIBus([(payload, b"00,OK")])
    cpu, _ = run(bus)
    assert cpu.a == 0 and word(bus, LENGTH) == 510
    assert bus.ram[DATA:DATA + 510] == payload[:510]
    assert bus.ram[TRUNC] == 1 and bus.ram[DATA + 510] == 0


def test_directory_overflow():
    entries = [b"\x10" + f"entry-{i:03d}".encode() for i in range(100)]
    bus = UCIBus([(data, b"00,OK" if i == 99 else b"") for i, data in enumerate(entries)])
    cpu, _ = run(bus, directory=True)
    expected = b""
    count = 0
    for entry in entries:
        if len(expected) + len(entry) > 510:
            break
        expected += entry + b"\0"
        count += 1
    assert cpu.a == 0 and bus.accepted == 100
    assert bus.ram[DIRN] == count and word(bus, LENGTH) == len(expected)
    assert bus.ram[DATA:DATA + len(expected)] == expected
    assert bus.ram[TRUNC] == 1


def test_empty_directory():
    bus = UCIBus([(b"", b"01,DIRECTORY EMPTY")])
    cpu, _ = run(bus, directory=True)
    assert cpu.a == 1 and bus.ram[DIRN] == 0 and word(bus, LENGTH) == 0
    assert not bus.ram[TRUNC]


def collector(items, stop=None):
    def receive(cpu, bus):
        data = bytes(bus.ram[DATA:DATA + word(bus, LENGTH)])
        items.append((data, bus.ram[PACKET_TRUNC]))
        # Exercise the documented callback-clobber contract.
        bus.ram[2:34] = bytes([0xe7]) * 32
        cpu.a = cpu.x = cpu.y = 0xef
        return stop is not None and len(items) == stop
    return receive


def test_stream_large_directory():
    entries = [bytes([0x10 if i % 3 else 0x20]) + f"file-{i:04d}".encode()
               for i in range(1000)]
    bus = UCIBus([(data, b"00,OK" if i == 999 else b"") for i, data in enumerate(entries)])
    items = []
    cpu, _ = run(bus, stream=True, callback=collector(items), directory=True)
    assert items == [(data, 0) for data in entries]
    assert cpu.a == 0 and word(bus, PACKETS) == 1000 and bus.accepted == 1000
    assert not bus.ram[TRUNC] and bus.ram[DIRN] == 0


def test_stream_full_pages():
    pages = [bytes((i * 73 + j) & 255 for i in range(n))
             for j, n in enumerate((512, 512, 1, 0, 256, 510, 511))]
    bus = UCIBus([(data, b"00,OK") for data in pages])
    items = []
    cpu, _ = run(bus, stream=True, callback=collector(items))
    assert cpu.a == 0 and items == [(data, 0) for data in pages]
    assert not bus.ram[TRUNC]


def test_stream_oversized_packet():
    payload = bytes(i & 255 for i in range(600))
    bus = UCIBus([(payload, b""), (b"tail", b"00,OK")])
    items = []
    cpu, _ = run(bus, stream=True, callback=collector(items))
    assert cpu.a == 0 and items == [(payload[:512], 1), (b"tail", 0)]
    assert bus.ram[TRUNC] == 1


def test_long_command():
    command = b"\x01\xf0" + bytes(i & 255 for i in range(894))
    bus = UCIBus([(b"", b"00,OK")])
    cpu, _ = run(bus, command=command, stream=True)
    assert cpu.a == 0 and bus.commands == [command]


def test_invalid_command_lengths():
    for size in (0, 1, 897, 1024):
        bus = UCIBus([(b"", b"00,OK")])
        cpu, _ = run(bus, command=b"x" * size, stream=True)
        assert cpu.a == 0xfc and cpu.p & cpu.CARRY and not bus.commands
    bus = UCIBus()
    cpu, _ = run(bus, command=b"")
    assert cpu.a == 0xfc and cpu.p & cpu.CARRY and not bus.commands


def test_absent_interface():
    bus = UCIBus(present=False)
    cpu, _ = run(bus)
    assert cpu.a == 0xfe and cpu.p & cpu.CARRY and not bus.commands


def test_stream_abort_and_legacy_reuse():
    bus = UCIBus([(b"entry", b"00,OK")] * 10)
    items = []
    cpu, _ = run(bus, stream=True, callback=collector(items, stop=3))
    assert cpu.a == 0xfd and cpu.p & cpu.CARRY
    assert len(items) == 3 and bus.accepted == 2 and bus.aborted == 1
    # Do not reload the driver: NET_CMD must clear the previous app's hook.
    bus.packets = deque([(b"new", b"00,OK")])
    cpu, _ = run_command(bus, command=b"\x01\x12", load=False)
    assert cpu.a == 0 and bus.accepted == 3 and len(items) == 3
    assert bus.ram[DATA:DATA + 3] == b"new" and not bus.ram[TRUNC]


def test_busy_timeout():
    bus = UCIBus([(b"never delivered", b"00,OK")], stuck=True)
    cpu, steps = run(bus)
    assert cpu.a == 0xff and cpu.p & cpu.CARRY and bus.aborted == 1
    assert steps < 20000000


def test_stuck_data_queue_timeout():
    class StuckData(UCIBus):
        def __getitem__(self, address):
            if address == 0xdf1e:
                return 0x5a
            return super().__getitem__(address)
    bus = StuckData([(b"never drained", b"00,OK")])
    cpu, _ = run(bus)
    assert cpu.a == 0xff and cpu.p & cpu.CARRY and bus.aborted == 1


def test_long_status():
    bus = UCIBus([(b"", b"86," + b"X" * 253)])
    cpu, _ = run(bus)
    assert cpu.a == 86 and not cpu.p & cpu.CARRY
    assert bus.ram[0x9142:0x9162] == b"86," + b"X" * 28 + b"\0"


def main():
    global IMAGE
    parser = argparse.ArgumentParser()
    parser.add_argument("--prg", type=Path, default=IMAGE)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    IMAGE = args.prg
    checks = []
    for name, check in list(globals().items()):
        if name.startswith("test_") and callable(check):
            check()
            checks.append(name)
            print(f"PASS: {name}", flush=True)
    report = {"prg_sha256": hashlib.sha256(IMAGE.read_bytes()).hexdigest(),
              "checks": checks}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(f"CI-UCI PASS: {len(checks)} protocol/CPU checks", flush=True)


if __name__ == "__main__":
    main()
