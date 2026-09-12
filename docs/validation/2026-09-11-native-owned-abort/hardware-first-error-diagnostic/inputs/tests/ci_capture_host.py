#!/usr/bin/env python3
"""Check host-side VDC capture restores borrowed app RAM on success and failure.

The probe itself executes in ci_vdc_capture.py. This test models its completion
and DMA observation errors to check the host's ownership of filename-cache RAM.
"""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hw_storage_check as capture


class Monitor:
    def __init__(self, code, read_error=False):
        self.ram = bytearray((i*13+7) & 255 for i in range(65536))
        self.ram[0x314:0x316] = b'\x31\xea'
        self.original = bytes(self.ram)
        self.code = code
        self.read_error = read_error
        self.installed = False
        self.screen = bytes((i*11+3) & 255 for i in range(2000))

    def read_mem(self, start, end):
        if start == 0x7400 and end == 0x7bcf and self.read_error:
            self.read_error = False
            raise OSError('injected capture observation error')
        return bytes(self.ram[start:end+1])

    def write_mem(self, start, data):
        if start == 0x7400:
            assert self.ram[0x314:0x316] == b'\x31\xea', 'probe still installed during restore'
        self.ram[start:start+len(data)] = data
        if start == 0x314 and data == b'\x00\x7c':
            self.installed = True
            self.ram[0x7400:0x7bd0] = self.screen
            self.ram[0x7cf2:0x7cf5] = bytes([self.code, 0, 0])
            self.ram[0x314:0x316] = b'\x31\xea'


def main():
    for code, read_error in ((1, False), (2, False), (1, True)):
        mon = Monitor(code, read_error)
        metadata = {}
        with tempfile.TemporaryDirectory(prefix='uos-capture-host-') as directory:
            with patch.object(capture.time, 'sleep'):
                try:
                    data = capture.read_vdc(mon, Path(directory), metadata)
                    assert code == 1 and not read_error
                    assert data == mon.screen
                except (AssertionError, OSError):
                    assert code == 2 or read_error
        assert mon.installed
        assert mon.ram[0x7400:0x7cf5] == mon.original[0x7400:0x7cf5]
        assert mon.ram[0x314:0x316] == mon.original[0x314:0x316]
        assert metadata['work_ram_restored']
        print(f'PASS: RAM/IRQ restored, probe code={code}, observation error={read_error}', flush=True)


if __name__ == '__main__':
    main()
