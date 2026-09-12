#!/usr/bin/env python3
"""Offline faults for acknowledged RAM ranges and bounded paused observations."""
import argparse
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qs, urlsplit

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_capture import NativeCapture
from native_capture_transport import ReceiptUltimate, PausedHardwareMonitor, PausedViceMonitor


class Device(ReceiptUltimate):
    def __init__(self, reply=None, failure=None):
        super().__init__(host='reference.invalid')
        self.reply, self.failure = reply, failure
        self.sent, self.persisted = [], []
        self.ram = bytearray(65536)
        self.stopped = False
        self.record_event = lambda:self.persisted.append(copy.deepcopy(
            dict(writes=self.ram_write_receipts, controls=self.control_requests)))

    def _call(self, method, path, data=None):
        self.sent.append((method, path, data))
        endpoint = urlsplit(path).path
        if endpoint.endswith(':pause'):
            self.stopped = True
        elif endpoint.endswith(':resume'):
            self.stopped = False
        else:
            assert endpoint.endswith(':writemem') and method == 'PUT' and data is None
            query = parse_qs(urlsplit(path).query)
            at = int(query['address'][0],16); value = bytes.fromhex(query['data'][0])
            self.ram[at:at+len(value)] = value
            assert self.persisted[-1]['writes'][-1]['request_started']
            assert not self.persisted[-1]['writes'][-1]['response_received']
            if self.failure == 'write':raise SystemExit('lost write reply after acceptance')
            if self.reply is not None:return self.reply
            return 200,json.dumps(dict(address=f'{at:04X}-{at+len(value)-1:04X}',errors=[])).encode()
        if self.failure == endpoint.rsplit(':',1)[-1]:
            raise SystemExit('lost control reply after acceptance')
        return 200,b'{"errors":[]}'


REGIONS = dict(output=(0x3a00,512,17), scratch=(0x3e00,512,23),
               metadata=(0x3800,1536,1024), resident=(0x1300,2304,43))


class CpuExchange:
    """Only the host protocol is modeled here; VICE executes the real IRQ code."""
    def __init__(self, fault=None):
        self.ram = bytearray((i*37+83)&255 for i in range(65536))
        self.ram[0x1c13:0x1c19] = b'UOS128'
        self.ram[0x3d11:0x3d13] = b'\0\1'
        self.ram[0xd0] = self.ram[0x3d91] = 0
        self.ram[0x314:0x316] = b'\x65\xfa'
        self.fault, self.pending = fault, False
        self.restoring = self.injected = self.stopped = False
        self.starts = self.resumes = self.polls = 0

    def read_mem(self, start, end):
        self.stopped = True
        data = bytearray(self.ram[start:end+1])
        if start == 0x3ff2 and start == end:
            self.polls += 1
            assert not self.pending, 'probe was polled before the CPU was resumed'
        if self.fault and self.restoring and not self.injected:
            at,count,offset = REGIONS[self.fault]
            if start == at and len(data) == count:
                data[offset] ^= 0x80
                self.injected = True
        return bytes(data)

    def write_mem(self, start, data):
        self.stopped = True
        self.ram[start:start+len(data)] = data
        if start == 0x314 and data == b'\0\x3e':
            self.pending = True
        if start == 0x3e00 and len(data) == 512:
            self.restoring = True

    def resume(self):
        self.resumes += 1
        self.stopped = False
        if self.pending:
            command = self.ram[0x3ff0:0x4000]
            address = int.from_bytes(command[5:7],'little')
            count = int.from_bytes(command[7:9],'little')
            self.ram[0x3a00:0x3a00+count] = self.ram[address:address+count]
            self.ram[0x3ff2] = 1
            self.ram[0x3ffb:0x3ffe] = bytes([0x37,4,0x0e])
            self.ram[0x314:0x316] = command[:2]
            self.pending = False
            self.starts += 1


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args()
    report = dict(passed=False, physical_hardware_io=False, probe_instructions_executed=False, cases=[])
    for address,data in ((0,b'\0'),(0x3a80,bytes(range(128))),(0xff80,b'\xff'*128),(0xffff,b'\x81')):
        device = Device();device.write_mem(address,data)
        row = device.ram_write_receipts[0]
        assert len(device.sent) == 1 and row['range_acknowledged'] and not device.uncertain_writes
        assert row['sha256'] == hashlib.sha256(data).hexdigest()
        assert device.ram[address:address+len(data)] == data
        assert device.persisted[-1]['writes'] == device.ram_write_receipts
        report['cases'].append(f'exact range accepted at {address:04x} for {len(data)} bytes')
    for label,reply in (
        ('short range',(200,b'{"address":"3a80-3afe","errors":[]}')),
        ('wrong start',(200,b'{"address":"3a81-3b00","errors":[]}')),
        ('missing range',(200,b'{"errors":[]}')),
        ('wrong type',(200,b'{"address":128,"errors":[]}')),
        ('error body',(200,b'{"address":"3a80-3aff","errors":["bad"]}')),
        ('bad HTTP',(503,b'{"address":"3a80-3aff","errors":[]}')),
        ('non JSON',(200,b'broken')),
        ('non object',(200,b'[]')),
    ):
        device = Device(reply=reply)
        try:device.write_mem(0x3a80,b'\xff'*128)
        except (RuntimeError,ValueError):pass
        else:raise AssertionError(f'{label} accepted')
        row = device.ram_write_receipts[0]
        assert len(device.sent) == len(device.uncertain_writes) == 1
        assert not row['range_acknowledged'] and row['body_hex'] == reply[1].hex()
        assert device.persisted[-1]['writes'] == device.ram_write_receipts
        report['cases'].append(label+' rejected and retained without replay')
    device = Device(failure='write')
    try:device.write_mem(0x3a00,b'\x55')
    except SystemExit:pass
    else:raise AssertionError('lost write reply accepted')
    assert len(device.sent) == len(device.uncertain_writes) == 1
    assert not device.ram_write_receipts[0]['response_received']
    assert device.ram[0x3a00] == 0x55
    report['cases'].append('accepted write with lost reply is retained and not replayed')
    for address,data in ((0,b''),(0,bytes(129)),(-1,b'x'),(65536,b'x'),(65535,b'xx')):
        device = Device()
        try:device.write_mem(address,data)
        except ValueError:pass
        else:raise AssertionError('invalid write sent')
        assert not device.sent and not device.ram_write_receipts
        report['cases'].append(f'invalid range {address}/{len(data)} refused before send')
    device = Device();mon = PausedHardwareMonitor(device)
    with mon.paused('segmented'):
        assert device.stopped
        mon.write_mem(0x3a00,bytes(range(256))*2);mon.resume()
        assert device.stopped
    assert not device.stopped and not mon.in_batch
    assert [r['expected_range'] for r in device.ram_write_receipts] == [
        '3a00-3a7f','3a80-3aff','3b00-3b7f','3b80-3bff']
    assert mon.batches[0]['resume_acknowledged']
    report['cases'].append('512 byte write split into four exact receipts while held paused')
    for failure in ('pause','body','resume'):
        device = Device(failure=failure);mon = PausedHardwareMonitor(device);entered = False
        try:
            with mon.paused(failure):
                entered = True
                if failure == 'body':raise AssertionError('capture read differs')
        except (SystemExit,AssertionError):pass
        else:raise AssertionError('failed batch accepted')
        endpoints = [urlsplit(r[1]).path for r in device.sent]
        assert endpoints == ['/v1/machine:pause','/v1/machine:resume']
        assert entered == (failure != 'pause') and not mon.in_batch and not device.stopped
        assert mon.batches[0]['resume_attempted']
        assert mon.batches[0]['resume_acknowledged'] == (failure != 'resume')
        report['cases'].append(f'{failure} failure retains one pause and one compensating resume')
    device = Device();mon = PausedHardwareMonitor(device)
    with mon.paused('outer'):
        try:
            with mon.paused('inner'):raise AssertionError('nested body ran')
        except RuntimeError:pass
        else:raise AssertionError('nested batch accepted')
        assert mon.in_batch and device.stopped
    assert len(device.sent) == 2 and not device.stopped
    report['cases'].append('nested batch refused without releasing outer pause')
    for paused in (False,True):
        for fault in (None,*REGIONS):
            with tempfile.TemporaryDirectory(prefix='uos-paused-capture-fault-') as temporary:
                work = Path(temporary);cpu = CpuExchange(fault);initial = bytes(cpu.ram)
                mon = PausedViceMonitor(cpu)
                capture = NativeCapture(mon,work,quiet=0,batch=mon.paused if paused else None)
                try:actual = capture.capture('sample',address=0xc7d0,count=2000)
                except AssertionError:
                    assert fault is not None and cpu.injected
                else:
                    assert fault is None and actual == initial[0xc7d0:0xcfa0]
                assert not cpu.stopped and not cpu.pending and not mon.in_batch
                assert cpu.starts == cpu.polls == 4
                row = capture.records[0]
                assert row['restored'] == (fault is None)
                assert cpu.ram[0x314:0x316] == initial[0x314:0x316]
                for name,(address,count,offset) in REGIONS.items():
                    assert cpu.ram[address:address+count] == initial[address:address+count]
                if fault:
                    assert row['borrower_checks'][fault]['different_offsets'] == [REGIONS[fault][2]]
                if paused:
                    assert len(mon.batches) == 11
                    assert all(r['resume_acknowledged'] for r in mon.batches)
                report['cases'].append(f'paused={paused}, fault={fault}: four chunks complete; strict borrower result retained')
    report['passed'] = True
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: {len(report["cases"])} transport/borrower controls; no hardware I/O or probe CPU execution')


if __name__ == '__main__':main()
