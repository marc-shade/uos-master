#!/usr/bin/env python3
"""Exercise every IRQ delivery point between core banking and the boot DMA.

The actual core and REU code execute. A banked ROM model supplies reset/IRQ
vectors and a minimal RTI handler; the IRQ injection proves vector visibility
and stack balance. At the real delayed-DMA trigger, BASIC must be out and the
8192-byte transfer parameters must be intact. No peripheral firmware is modeled.
"""
import argparse
import hashlib
import json
from pathlib import Path

from py65.devices.mpu6502 import MPU
from ci_desktop import symbol

ROOT = Path(__file__).resolve().parents[1]


class Memory:
    def __init__(self, image, unsafe=False):
        self.ram = bytearray(65536)
        self.ram[0:2] = b'\x2f\x37'
        for data in (image, (ROOT/'target/uos-reu.prg').read_bytes()):
            origin = int.from_bytes(data[:2], 'little')
            self.ram[origin:origin+len(data)-2] = data[2:]
        if unsafe:
            self.ram[symbol('uos', 'setup_banking')+1] = 0x35
        self.dma = 0

    def __getitem__(self, address):
        if self.ram[1] & 2:
            if address == 0xfffd:
                return 0xfc
            if address == 0xfffe:
                return 0x31
            if address == 0xffff:
                return 0xea
            if address == 0xea31:
                return 0x40  # RTI: real KERNAL register handling is separate
        return self.ram[address]

    def __setitem__(self, address, value):
        self.ram[address] = value
        if address == 0xff00 and self.ram[0xdf01] == 0xec:
            assert self.ram[1] & 3 != 3, 'DMA saw BASIC ROM instead of bitmap RAM'
            assert bytes(self.ram[0xdf02:0xdf09]) == b'\0\xa0\0\0\0\0\x20'
            self.dma += 1


def check(image, inject=None, unsafe=False):
    memory = Memory(image, unsafe)
    cpu = MPU(memory=memory, pc=symbol('uos', 'setup_banking'))
    cpu.sp, cpu.p = 0xf0, cpu.UNUSED
    cpu.stPushWord(0x02ff)
    end = symbol('uos', 'VDPREF')
    opportunities = []
    injected = False
    for step in range(1000):
        if cpu.pc == end:
            assert memory.dma == 1
            assert cpu.sp == 0xec, cpu.sp  # test caller frame + JSR VDPREF
            return opportunities, injected
        if not cpu.p & cpu.INTERRUPT:
            assert memory.ram[1] & 2, f'IRQ vectors hidden at ${cpu.pc:04x}'
            opportunities.append(step)
            if inject == step:
                cpu.irq()
                assert cpu.pc == 0xea31
                cpu.step()
                injected = True
        cpu.step()
    raise AssertionError('boot DMA section did not finish')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    image = (ROOT/'target/uos.prg').read_bytes()
    opportunities, _ = check(image)
    for step in opportunities:
        _, injected = check(image, inject=step)
        assert injected
    try:
        check(image, unsafe=True)
    except AssertionError as error:
        assert 'IRQ vectors hidden' in str(error)
        previous_failure = str(error)
    else:
        raise AssertionError('old unsafe banking was not detected')
    report = dict(passed=True, core_sha256=hashlib.sha256(image).hexdigest(),
                  irq_points=len(opportunities), old_banking_rejected=previous_failure,
                  dma_bytes=8192, transfer_parameters_preserved=True)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print('PASS:', report, flush=True)


if __name__ == '__main__':
    main()
