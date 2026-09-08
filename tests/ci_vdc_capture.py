#!/usr/bin/env python3
"""Check the assembled IRQ capture with strict VDC readiness and address drift."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from py65.devices.mpu6502 import MPU
from ci_vdc_protocol import ROOT, VDC


class CaptureBus(VDC):
    def __init__(self, fault=None, present=True):
        super().__init__(present)
        self.fault = fault
        self.reads = 0

    def __getitem__(self, address):
        data_read = address == 0xd601 and self.selected == 31
        value = super().__getitem__(address)
        if data_read:
            if self.fault == 'always' or self.reads == self.fault:
                next_address = self.reg[18] << 8 | self.reg[19]
                self.advance(next_address + 1)
            self.reads += 1
        return value


def check(code, fault=None, present=True):
    bus = CaptureBus(fault, present)
    expected = bytes((i*73 + i//251) & 255 for i in range(2000))
    bus.video[:2000] = expected
    bus.ram[0x7c00:0x7c00+len(code)] = code
    bus.ram[0x7cf0:0x7cf5] = b'\0\x03\0\0\0'
    bus.ram[0x0314:0x0316] = b'\0\x7c'
    bus.ram[0xfb:0xfd] = b'\x91\x82'
    bus.ram[0x73f0:0x7400] = b'\xa5'*16
    bus.ram[0x7bd0:0x7c00] = b'\xb6'*48
    cpu = MPU(memory=bus, pc=0x7c00)
    stack = cpu.sp
    for _ in range(2000000):
        if cpu.pc == 0x0300:
            break
        cpu.step()
    else:
        raise AssertionError('Capture did not restore the IRQ chain')
    result = bus.ram[0x7cf2]
    resyncs = int.from_bytes(bus.ram[0x7cf3:0x7cf5], 'little')
    assert cpu.sp == stack and bus.ram[0xfb:0xfd] == b'\x91\x82'
    assert bus.ram[0x0314:0x0316] == b'\0\x03'
    assert bus.ram[0x73f0:0x7400] == b'\xa5'*16
    assert bus.ram[0x7bd0:0x7c00] == b'\xb6'*48
    if not present:
        assert result == 2 and resyncs == 0 and bus.reads == 0
    elif fault == 'always':
        assert result == 3 and resyncs == 3 and bus.reads == 3
    else:
        assert result == 1 and resyncs == (fault is not None)
        assert bus.ram[0x7400:0x7bd0] == expected
        assert bus.reads == 2000 + resyncs
    return {'code':result, 'address_resyncs':resyncs, 'cycles':cpu.processorCycles}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='uos-vdc-capture-') as temporary:
        output = Path(temporary)/'capture.prg'
        subprocess.run(['64tass','-a',str(ROOT/'probes/vdc-irqdump.asm'),'-o',str(output)],
                       check=True, capture_output=True)
        prg = output.read_bytes()
    assert int.from_bytes(prg[:2], 'little') == 0x7c00 and len(prg)-2 <= 0xf0
    report = {'probe_sha256':hashlib.sha256(prg).hexdigest(), 'checks':{}}
    for label,fault,present in [('normal',None,True),('first',0,True),('early',239,True),
                                ('high-carry',254,True),('page-boundary',255,True),('later',1119,True),
                                ('last',1999,True),('persistent','always',True),
                                ('absent',None,False)]:
        report['checks'][label] = check(prg[2:], fault, present)
        print('PASS:',label,report['checks'][label],flush=True)
    report['passed'] = True
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
