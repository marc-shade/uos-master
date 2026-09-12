#!/usr/bin/env python3
"""Execute a native probe inside an outer ROM IRQ that has reached CLI."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode=True
parser=argparse.ArgumentParser()
parser.add_argument('--work',type=Path,required=True)
args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[1]/'inputs'
sys.path[:0]=[str(ROOT/'tests'),str(ROOT)]
from py65.devices.mpu6502 import MPU
from ci_native_capture import NativeCaptureBus

work=args.work
work.mkdir(exist_ok=True)
subprocess.run(['64tass','-a',str(ROOT/'probes/native-read.asm'),'-o',str(work/'probe.prg')],
               check=True,capture_output=True)
prg=(work/'probe.prg').read_bytes()

class Bus(NativeCaptureBus):
    def __init__(self):
        super().__init__()
        self.vic={0xd019:1,0xd030:0}
    def __getitem__(self,at):
        if at in self.vic and not self.config&1:return self.vic[at]
        return super().__getitem__(at)
    def __setitem__(self,at,value):
        if at==0xd019 and not self.config&1:self.vic[at]&=~value
        else:super().__setitem__(at,value)

bus=Bus();ram=bus.ram[0]
ram[0xd8]=255
ram[0x314:0x316]=b'\x65\xfa'
cpu=MPU(memory=bus,pc=0x2500);cpu.sp=0xc0
cpu.a,cpu.x,cpu.y,cpu.p=0x5a,0x6d,0x90,0x28
cpu.irq();outer_trace=[]
for _ in range(200):
    outer_trace.append(dict(pc=cpu.pc,sp=cpu.sp,mmu=bus.config,p=cpu.p))
    if cpu.pc==0xc22a:break
    cpu.step()
else:raise AssertionError('outer ROM IRQ did not reach the instruction after CLI')
assert bus.config==0 and not cpu.p&cpu.INTERRUPT
assert outer_trace[-2]['pc']==0xc229 and outer_trace[-2]['p']&cpu.INTERRUPT
state=(cpu.pc,cpu.sp,cpu.a,cpu.x,cpu.y,cpu.p&0xcf)
outer_stack=bytes(ram[0x100+cpu.sp+1:0x200])
assert ram[0x100+cpu.sp+3]==0x0e  # JSR C024 return word precedes the outer saved MMU
ram[0x3e00:0x3e00+len(prg)-2]=prg[2:]
# A bounded chain handler counts and uses the actual ROM MMU/register/RTI
# restore gateway. The outer ROM IRQ is left paused at its real CLI return.
ram[0x3ff0:0x3ffb]=b'\0\x0b\0\0\0\xd0\xc7\0\2\0\0'
ram[0x314:0x316]=b'\0\x3e'
expected=bytes(ram[0xc7d0:0xc9d0])
cpu.irq();probe_trace=[]
for step in range(200000):
    if cpu.pc in (0xff17,0xff1f,0xff22,0x3e00,0xb00,0xff33):
        probe_trace.append(dict(pc=cpu.pc,sp=cpu.sp,mmu=bus.config,p=cpu.p))
    if cpu.pc==state[0] and cpu.sp==state[1]:break
    cpu.step()
else:raise AssertionError('nested native observer failed to return to the outer ROM IRQ')
assert (cpu.pc,cpu.sp,cpu.a,cpu.x,cpu.y,cpu.p&0xcf)==state
assert bus.config==0 and bytes(ram[0x100+cpu.sp+1:0x200])==outer_stack
assert ram[0x3ff2]==1 and ram[0x3ffb:0x3ffe]==bytes([0xb7,4,0])
assert bytes(ram[0x3a00:0x3c00])==expected
assert ram[0xb10]==1 and ram[0x314:0x316]==b'\0\x0b'
(work/'captured.bin').write_bytes(ram[0x3a00:0x3c00])
(work/'expected.bin').write_bytes(expected)
(work/'outer-stack.bin').write_bytes(outer_stack)
report=dict(passed=True,physical_hardware_io=False,full_c128_emulator=False,
    actual_rom_irq_entry_and_cli_executed=True,induced_nested_irq=True,
    nested_chain_handler='model counter followed by actual native ROM restore gateway',
    outer_rom_irq_resumed_at=cpu.pc,outer_frame_and_registers_preserved=True,
    outer_saved_mmu=14,nested_saved_mmu=ram[0x3ffd],captured_bytes=512,
    captured_sha256=hashlib.sha256(expected).hexdigest(),probe_sha256=hashlib.sha256(prg).hexdigest(),
    rom_sha256=hashlib.sha256(bus.rom).hexdigest(),outer_trace=outer_trace,probe_trace=probe_trace,
    old_host_guard_would_reject=True,physical_failure_cause_proven=False)
(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: real ROM outer IRQ enables nesting at C229; nested probe captures MMU 00 and exact RAM, then restores the outer frame')
