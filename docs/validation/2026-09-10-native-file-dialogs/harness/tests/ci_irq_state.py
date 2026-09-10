#!/usr/bin/env python3
"""Validate the physical diagnostic sampler's stack offsets and restoration."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from py65.devices.mpu6502 import MPU

ROOT = Path(__file__).resolve().parents[1]


def check():
    with tempfile.TemporaryDirectory(prefix='uos-irq-state-') as temp:
        image = Path(temp)/'probe.prg'
        subprocess.run(['64tass','-a',str(ROOT/'probes/irq-state.asm'),'-o',str(image)],
                       check=True,capture_output=True)
        prg = image.read_bytes()
    ram = bytearray((i*17+31)&255 for i in range(65536))
    ram[0x7c00:0x7c00+len(prg)-2] = prg[2:]
    ram[0x7cf0:0x7cf4] = b'\0\x90\0\0'
    ram[0x314:0x316] = b'\0\x7c'
    document = bytes(ram[0x5000:0x6200])
    for i in range(32):
        cpu = MPU(memory=ram,pc=0x7c00)
        original_sp = 255-i*3
        pc, status = 0x5000+i*257, (i*7)&0xcf
        regs = bytes([(i*13)&255,(i*19)&255,(i*23)&255])
        cpu.sp = original_sp
        cpu.stPushWord(pc)
        cpu.stPush(status)
        for r in regs:
            cpu.stPush(r)       # KERNAL A/X/Y saves
        stacked = bytes(ram[0x100+cpu.sp+1:0x200])
        cpu.a,cpu.x,cpu.y = 0x62,0xa3,0x47  # state at the IRQ vector
        cpu.p = 0x85
        for _ in range(200):
            if cpu.pc == 0x9000:
                break
            cpu.step()
        else:
            raise AssertionError('sampler failed to chain to the old IRQ')
        assert (cpu.a,cpu.x,cpu.y,cpu.sp) == (0x62,0xa3,0x47,original_sp-6)
        assert cpu.p & 0xcf == 0x85
        assert bytes(ram[0x100+cpu.sp+1:0x200]) == stacked, 'original IRQ frame changed'
        expected = pc.to_bytes(2,'little')+regs+bytes([status,original_sp])
        assert ram[0x7d00+i*8:0x7d07+i*8] == expected
        assert ram[0x7cf2] == i+1
        assert ram[0x7cf3] == int(i==31)
        assert ram[0x314:0x316] == (b'\0\x90' if i==31 else b'\0\x7c')
        assert bytes(ram[0x5000:0x6200]) == document
    return dict(samples=32,registers_stack_flags_preserved=True,original_irq_restored=True,
                probe_sha256=hashlib.sha256(prg).hexdigest())


if __name__ == '__main__':
    p = argparse.ArgumentParser();p.add_argument('--report',type=Path);args=p.parse_args()
    report = check()
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: IRQ sampler register/stack capture and restoration')
