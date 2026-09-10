#!/usr/bin/env python3
"""Execute all real VIC capture wedges and verify host restoration on failure."""
from pathlib import Path
import sys
from unittest.mock import patch
from py65.devices.mpu6502 import MPU

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cap_hw_screen as capture


class Ultimate:
    def __init__(self, fail_part=None):
        self.ram = bytearray((i*13+31) & 255 for i in range(65536))
        self.ram[0x314:0x316] = b'\x31\xea'
        self.original = bytes(self.ram)
        self.part = -1
        self.fail_part = fail_part

    def read_mem(self, start, length):
        if start == capture.STAGE and self.part == self.fail_part:
            self.fail_part = None
            raise OSError('injected bitmap observation failure')
        return bytes(self.ram[start:start+length])

    def write_mem(self, start, data):
        self.ram[start:start+len(data)] = data
        if start == capture.IRQV and data == b'\x40\x03':
            self.part += 1
            cpu = MPU(memory=self.ram, pc=capture.WEDGE)
            cpu.sp = 0xf0
            for step in range(30000):
                if cpu.pc == 0xea31:
                    break
                cpu.step()
            else:
                raise AssertionError('VIC wedge did not return')
            assert cpu.sp == 0xf0
            assert self.ram[1] == self.original[1]
            assert self.ram[0xfb:0xff] == self.original[0xfb:0xff]


def main():
    for fail_part in (None, 0, 2, 3):
        u = Ultimate(fail_part)
        metadata = {}
        with patch.object(capture.time, 'sleep'):
            try:
                data = capture.grab(u, verbose=False, metadata=metadata)
                assert fail_part is None
                assert data == u.original[0xa000:0xbf40]
            except OSError:
                assert fail_part is not None
        assert u.ram[capture.STAGE:capture.STAGE+capture.CHUNK] == u.original[capture.STAGE:capture.STAGE+capture.CHUNK]
        assert u.ram[capture.WEDGE:capture.FLAG+1] == u.original[capture.WEDGE:capture.FLAG+1]
        assert u.ram[0x314:0x316] == u.original[0x314:0x316]
        assert u.ram[0x4100:0x5000] == u.original[0x4100:0x5000]
        assert metadata['work_ram_restored'] and metadata['cassette_restored']
        print(f'PASS: VIC bytes, app/cassette RAM and resident service intact; failure part {fail_part}', flush=True)


if __name__ == '__main__':
    main()
