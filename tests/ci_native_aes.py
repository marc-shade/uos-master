#!/usr/bin/env python3
"""Persistent AES component (GEM layer step 1): load, survive app exit,
re-attach from a new app, refuse bad images or ranges, and unload fully."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import tempfile

from py65.devices.mpu6502 import MPU
import ci_native_heap as heap
import ci_native_calc
from ci_native_calc import Calculator
from ci_native_files import StreamIEC
from native_banked_bus import BankedBus

ROOT = Path(__file__).resolve().parents[1]
APP = b'AESDEMO.PRG'
AESVC = b'AESVC.PRG'
AE_BASE = 0x9000
AES_OWNER = 30

_released = ci_native_calc.released_stats


def resident_aes(machine):
    """The single owner-30 record, or None; checked against the page tags."""
    ram = machine.ram
    records = [(i, bytes(ram[0x3c00+i*8:0x3c08+i*8])) for i in range(32)]
    aes = [(i, r) for i, r in records if r[0] == AES_OWNER]
    if not aes:
        return None
    assert len(aes) == 1, aes
    slot, record = aes[0]
    assert record[1] == 1 and record[2] == AE_BASE >> 8, record
    pages = record[3]
    assert bytes(ram[0x3900+record[2]:0x3900+record[2]+pages]) == bytes([slot+1])*pages
    return record


def released_with_aes(machine):
    record = resident_aes(machine)
    live = [bytes(machine.ram[0x3c00+i*8:0x3c08+i*8]) for i in range(32)]
    live = [r for r in live if r[0]]
    if record is None:
        return _released(machine)
    assert all(r[0] == AES_OWNER for r in live), live
    return 175, 251-record[3], 31


ci_native_calc.released_stats = released_with_aes


class Demo(Calculator):
    instruction_limit = 12000000

    def __init__(self, output, machine=None, *, corrupt=False, missing=False):
        if machine is None:
            heap.Bus = BankedBus
            machine = heap.Machine()
        self.m = machine
        self.ram = self.m.ram
        self.image_name = 'aes-demo'
        self.image = (output/APP.decode()).read_bytes()
        component = bytearray((output/AESVC.decode()).read_bytes())
        if corrupt:
            component[-1] ^= 1
        self.symbols = {n: int(v, 16) for n, v in re.findall(
            r'^([\w.]+)\s*=\s*\$([\da-fA-F]+)', (output/'parent.sym').read_text(), re.M)}
        files = {(8, APP, b'P'): self.image, (8, AESVC, b'P'): bytes(component)}
        if missing:
            del files[8, AESVC, b'P']
        self.io = StreamIEC(self.m, files)
        self.io.formats[8] = 0
        self.ram[0x3d21:0x3d23] = bytes([8, len(APP)])
        self.ram[0x3d40:0x3d40+len(APP)] = APP
        self.ram[0x3d2c:0x3d2e] = bytes([0, 8])
        self.cpu = MPU(memory=self.m.bus, pc=0x1c38)
        self.cpu.sp, self.cpu.p = 0xe0, 0x20
        self.cpu.stPushWord(0xaff)
        self.screens = [bytearray(b' '*1000), bytearray(b' '*2000)]
        self.reverse = [False, False]; self.row = [0, 0]; self.col = [0, 0]; self.keys = []
        # N_KEYS is kernel state and keeps counting across launches.
        self.events = int.from_bytes(self.ram[0x3d13:0x3d15], 'little')
        self.instructions = 0
        self.observation_target = None; self.observation_done = False
        self.loop()

    def symbol(self, name):
        return self.symbols['input_loop' if name == 'cloop' else name]

    def data(self, name, length):
        at = self.symbol(name)
        return bytes(self.ram[at:at+length])

    def check(self, *, attaches, apps, loaded, error=0, version=0x0100):
        status = self.data('demo_status', 13)
        assert self.value('demo_error') == error, (self.value('demo_error'), error)
        assert self.value('demo_loaded') == loaded
        if error == 0:
            assert status[0:2] == bytes([version >> 8, version & 255])
            assert int.from_bytes(status[4:6], 'little') == attaches
            assert int.from_bytes(status[6:8], 'little') == apps
        lines = ['AES DEMO', f'VERSION (HEX): ${status[0]:02X}{status[1]:02X}',
                 f'ATTACHES (HEX): ${status[5]:02X}{status[4]:02X}',
                 f'APPS (HEX): ${status[7]:02X}{status[6]:02X}',
                 f'LOADED HERE (HEX): ${loaded:02X}', f'LAST ERROR (HEX): ${error:02X}', '',
                 'RETURN: AES STATUS', 'ESC: EXIT, AES STAYS RESIDENT', 'U: UNLOAD AES AND EXIT']
        for screen, columns in zip(self.screens, (40, 80)):
            expected = bytearray(b' '*(columns*25))
            for row, line in enumerate(lines):
                expected[row*columns:row*columns+len(line)] = bytes(
                    v-64 if 64 <= v < 96 else v for v in line.encode())
            assert screen == expected, (columns, bytes(screen[:columns*10]))

    def bank1(self, offset, length):
        return bytes(self.m.bus.ram[1][AE_BASE+offset:AE_BASE+offset+length])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix='uos-aes-', dir='/var/tmp/arc-scratch'))
    spec = importlib.util.spec_from_file_location('aes_build', ROOT/'examples/native-aes/build.py')
    build = importlib.util.module_from_spec(spec); spec.loader.exec_module(build)
    images = build.build(work)
    component = (work/AESVC.decode()).read_bytes()
    report = dict(passed=False, physical_hardware_io=False, work=str(work), images=images, cases=[])

    def done(name, demo, **extra):
        report['cases'].append(dict(name=name, events=demo.events, instructions=demo.instructions, **extra))
        args.report.write_text(json.dumps(report, indent=2)+'\n')
        print('PASS:', name, flush=True)

    try:
        first = Demo(work)
        first.check(attaches=1, apps=1, loaded=1)
        record = resident_aes(first.m)
        assert record is not None and record[3] == images['images']['AESVC.PRG']['pages']
        # The loaded bytes equal the file image after the executor patches the
        # callback import; the counters live inside the resident image.
        resident = first.bank1(0, len(component)-2)
        expected = bytearray(component[2:])
        callback = first.symbol('ae_callback')
        expected[22:24] = callback.to_bytes(2, 'little')
        assert resident[:22] == bytes(expected[:22]) and resident[22:24] == bytes(expected[22:24])
        first.key(13); first.check(attaches=1, apps=1, loaded=1)
        first.key(27, exited=True)
        assert resident_aes(first.m) is not None, 'AES must survive the app exit'
        done('first app loads AESVC at bank-1 $9000 as owner 30; it survives exit', first,
             pages=record[3])

        second = Demo(work, first.m)
        second.check(attaches=2, apps=2, loaded=0)
        assert second.bank1(22, 2) == callback.to_bytes(2, 'little')
        second.key(13); second.check(attaches=2, apps=2, loaded=0)
        second.key(ord('U'), exited=True)
        assert resident_aes(second.m) is None
        assert second.m.stats() == _released(second.m), 'unload returns every page'
        done('second app attaches without loading, sees persisted counters, unloads fully', second)

        third = Demo(work, second.m)
        third.check(attaches=1, apps=1, loaded=1)
        third.key(27, exited=True)
        machine = third.m
        identity = AE_BASE+32
        machine.bus.ram[1][identity] ^= 0x40          # 'N' -> 0x0e: not an AES
        refused = Demo(work, machine)
        refused.check(attaches=0, apps=0, loaded=0, error=0x10)
        refused.key(27, exited=True)
        assert resident_aes(machine) is not None, 'a refused attach leaves the image alone'
        machine.bus.ram[1][identity] ^= 0x40
        callback_bytes = machine.bus.ram[1][AE_BASE+22:AE_BASE+24]
        machine.bus.ram[1][AE_BASE+22:AE_BASE+24] = bytes(2)  # as a partial load leaves it
        partial = Demo(work, machine)
        partial.check(attaches=0, apps=0, loaded=0, error=0x10)
        partial.key(27, exited=True)
        machine.bus.ram[1][AE_BASE+22:AE_BASE+24] = callback_bytes
        again = Demo(work, machine)
        again.check(attaches=2, apps=2, loaded=0)  # the refused apps never registered
        again.key(ord('U'), exited=True)
        assert resident_aes(machine) is None
        done('wrong identity or zero callback import (partial load) refused with BADIMAGE; restored image re-attaches', again)

        heap.Bus = BankedBus
        blocked_machine = heap.Machine()
        blocked_machine.alloc(1, bank=1, owner=29, page=AE_BASE >> 8)  # real heap reserve
        occupied = Demo(work, blocked_machine)
        occupied.check(attaches=0, apps=0, loaded=0, error=occupied.value('demo_error'))
        assert occupied.value('demo_error') not in (0, 4), occupied.value('demo_error')
        assert resident_aes(blocked_machine) is None
        assert blocked_machine.ram[0x3900+(AE_BASE >> 8)] != 0, 'the other owner keeps its page'
        done('occupied $9000 by another owner: clean allocation refusal, nothing adopted', occupied,
             error=occupied.value('demo_error'))

        for kind, error in (('corrupt', 0x14), ('missing', None)):
            demo = Demo(work, corrupt=kind == 'corrupt', missing=kind == 'missing')
            code = demo.value('demo_error')
            if error is not None:
                assert code == error, code
            else:
                assert code not in (0, 4), code
            demo.check(attaches=0, apps=0, loaded=0, error=code)
            assert resident_aes(demo.m) is None
            demo.key(27, exited=True)
            done(f'{kind} AESVC.PRG refused; no resident image', demo, error=code)
        report['passed'] = True
    finally:
        args.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
