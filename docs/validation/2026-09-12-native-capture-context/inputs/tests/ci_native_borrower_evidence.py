#!/usr/bin/env python3
"""Fault the host readback and require exact retained borrower differences."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_capture import NativeCapture

REGIONS = dict(output=(0x3a00,512,17),scratch=(0x3e00,512,23),
               metadata=(0x3800,1536,1024),resident=(0x1300,2304,43))


class Monitor:
    def __init__(self, fault=None):
        self.ram = bytearray((i*37+83)&255 for i in range(65536))
        self.ram[0x1c13:0x1c19] = b'UOS128'
        self.ram[0x3d11:0x3d13] = b'\0\1'
        self.ram[0xd0] = self.ram[0x3d91] = 0
        self.ram[0x314:0x316] = b'\x65\xfa'
        self.fault = fault; self.completed = self.restoring = self.injected = False

    def read_mem(self, start, end):
        data = bytearray(self.ram[start:end+1])
        if self.fault and self.restoring and not self.injected:
            address, count, offset = REGIONS[self.fault]
            if start == address and len(data) == count:
                data[offset] ^= 0x80
                self.injected = True
        return bytes(data)

    def write_mem(self, start, data):
        self.ram[start:start+len(data)] = data
        if start == 0x314 and data == b'\0\x3e':
            # Only model the host/probe exchange here; CPU instructions are
            # executed separately by the VICE preflight.
            command = self.ram[0x3ff0:0x4000]
            address = int.from_bytes(command[5:7], 'little')
            count = int.from_bytes(command[7:9], 'little')
            self.ram[0x3a00:0x3a00+count] = self.ram[address:address+count]
            self.ram[0x3ff2] = 1
            self.ram[0x3ffb:0x3ffe] = bytes([0x37,4,0x0e])
            self.ram[0x314:0x316] = command[:2]
            self.completed = True
        if start == 0x3e00 and len(data) == 512 and self.completed:
            self.restoring = True

    def resume(self):
        pass


parser = argparse.ArgumentParser()
parser.add_argument('--report', type=Path, required=True)
args = parser.parse_args()
report = dict(passed=False, physical_hardware_io=False, probe_instructions_executed=False, cases=[])
for fault in (None, *REGIONS):
    with tempfile.TemporaryDirectory(prefix='uos-borrower-host-fault-') as temporary:
        work = Path(temporary); mon = Monitor(fault)
        initial = bytes(mon.ram)
        capture = NativeCapture(mon,work,quiet=0)
        try:
            data = capture.capture('sample',address=0x6000,count=32)
        except AssertionError as error:
            assert fault is not None and mon.injected
            message = str(error)
        else:
            assert fault is None and data == initial[0x6000:0x6020]
            message = None
        row = capture.records[0]
        assert row['restored'] == (fault is None)
        assert mon.ram[0x314:0x316] == initial[0x314:0x316]
        # The injected bad read did not alter actual RAM. The observer must
        # still fail and retain what it observed, without treating it as proof
        # of a RAM fault or accepting a subsequent matching reread.
        for name,(address,count,offset) in REGIONS.items():
            assert mon.ram[address:address+count] == initial[address:address+count]
            record = row['borrower_checks'][name]
            before = (work/record['before_file']).read_bytes()
            assert before == initial[address:address+count]
            assert hashlib.sha256(before).hexdigest() == record['before_sha256']
            if 'after_file' in record:
                after = (work/record['after_file']).read_bytes()
                assert hashlib.sha256(after).hexdigest() == record['after_sha256']
                assert record['matches'] == (name != fault)
                assert record['different_offsets'] == ([offset] if name == fault else [])
                assert record['observed_bytes'] == count
                if name == fault:
                    assert after[offset] == before[offset]^0x80
                    assert after[:offset]+after[offset+1:] == before[:offset]+before[offset+1:]
        report['cases'].append(dict(fault=fault,failed=message is not None,error=message,
                                   retained_exact_observations=True,actual_borrowed_ram_restored=True))
report['passed'] = True
args.report.write_text(json.dumps(report,indent=2)+'\n')
print('PASS: good borrower restoration and four injected host-read failures retain exact evidence; no failure accepted')
