#!/usr/bin/env python3
"""Check the native hardware workflow client before allowing it to touch USB."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from py65.devices.mpu6502 import MPU
from ci_files import Client, ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='uos-files-probe-') as directory:
        output = Path(directory)/'probe.prg'
        subprocess.run(['64tass', '-a', str(ROOT/'probes/files-workflow.asm'), '-o', str(output)],
                       check=True, capture_output=True)
        code = output.read_bytes()[2:]
    c = Client()
    expected = bytes((i*73+(i//256)*17+(i//65536)*29+11) & 255 for i in range(66053))
    ram = c.bus.ram
    report = {'checks': [], 'probe_sha256': hashlib.sha256(code).hexdigest()}
    for mode in (0, 1):
        ram[0x5000:0x5000+len(code)] = code
        ram[0x5500:0x5507] = b'source\0'
        ram[0x5700:0x5705] = b'copy\0'
        ram[0x5f00:0x5f0a] = b'\x34\x12'+bytes([mode])+bytes(7)
        cpu = MPU(memory=c.bus, pc=0x5000)
        cpu.stPushWord(0x02ff)
        for steps in range(30000000):
            if cpu.pc == 0x0300:
                break
            if cpu.pc == 0x083b:
                ram[2:34] = bytes([0xe7])*32
                cpu.a = cpu.x = cpu.y = 0xe7
                cpu.pc = cpu.stPopWord()+1
            else:
                cpu.step()
        else:
            raise AssertionError('native file workflow did not return')
        assert ram[0x5f03:0x5f06] == b'\1\0\0', bytes(ram[0x5f03:0x5f0a]).hex()
        assert int.from_bytes(ram[0x5f06:0x5f0a], 'little') == len(expected)
        assert c.bus.files[b'source' if mode == 0 else b'copy'] == expected
        assert c.bus.handles == {1: None, 2: None}
        assert ram[0x33c:0x33e] == b'\x34\x12'
        report['checks'].append(dict(mode=mode, bytes=len(expected), steps=steps))
        print(f'PASS: native workflow mode {mode}, {len(expected)} bytes, tick and handles released', flush=True)
    report['passed'] = True
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
