#!/usr/bin/env python3
"""Execute the input logger, actual native GETIN and ROM queue operations."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from py65.devices.mpu6502 import MPU
import ci_native_heap as heap
heap.IMAGE=ROOT/'target/native-desktop/uos128.prg'
from native_input_trace import assemble,decode


class Bus(heap.Bus):
    def __getitem__(self,address):
        if address in (0xd02f,0xdc00,0xdc01,0xdc02,0xdc03) and not self.config&1:
            return {0xd02f:0xff,0xdc00:0x7f,0xdc01:0xef,0xdc02:0xff,0xdc03:0}[address]
        if self.config==0 and 0x4000<=address<0xc000:
            raise AssertionError('executed trace under BASIC mapping')
        return super().__getitem__(address)


def invoke(bus,pc,*,a=0x53,x=0x29,y=0xa6,flags=0x20,inject=None,sp=0xc0):
    cpu=MPU(memory=bus,pc=pc);cpu.sp=sp;cpu.p=flags;cpu.a,cpu.x,cpu.y=a,x,y
    cpu.stPushWord(0xb7f)
    for _ in range(20000):
        if cpu.pc==0xb80:
            assert cpu.sp==sp
            return cpu
        if inject:inject(cpu)
        cpu.step()
    raise AssertionError(('trace did not return',hex(cpu.pc)))


def run(work):
    (trace,gate),original=assemble(work,0xb70)
    def machine():
        bus=Bus();ram=bus.ram[0]
        invoke(bus,0xff8a)  # Install the real ROM default KERNAL vectors.
        ram[0xb70]=0x60  # The original key-check callback returns to its caller.
        ram[0x5000:0x5800]=trace[2:];ram[0x3fc0:0x3fc0+len(gate)-2]=gate[2:]
        ram[0x99]=0;ram[0xd0:0xd6]=bytes([0,0,0,0,88,88]);ram[0x34a:0x354]=bytes(10)
        ram[0x3d12:0x3d16]=bytes([1,0,0,0]);ram[0xa0:0xa3]=bytes.fromhex('010203')
        return bus,ram
    real=int.from_bytes(original[1:],'little')
    cases=[]
    for flags in (0x20,0x29,0x64,0xe8):
        for hold in (0,1):
            left,lr=machine();right,rr=machine()
            for ram in (lr,rr):ram[0xd0]=3;ram[0x34a:0x34d]=b'\x11\x1dA';ram[0x3d13:0x3d15]=b'\xff\x12'
            rr[0x520a]=hold
            before=bytes(rr)
            ordinary=invoke(left,real,flags=flags)
            traced=invoke(right,0x5000,flags=flags)
            assert traced.a==(0 if hold else ordinary.a)
            assert (traced.x,traced.y,traced.p&0x4d)==(ordinary.x,ordinary.y,ordinary.p&0x4d)
            if not hold:assert traced.p&0xcf==ordinary.p&0xcf
            assert lr[:0x100]==rr[:0x100] and lr[0x34a:0x354]==rr[0x34a:0x354]
            assert lr[0x3d00:0x3e00]==rr[0x3d00:0x3e00]
            result=decode(bytes(rr[0x5000:0x5800]));row=result['records'][0]
            assert result['consumed']==1 and result['scans']==0 and row['key']==0x11
            assert row['buffer_count_before']==3 and bytes.fromhex(row['state_after_hex'])[4]==2
            assert row['keys_before']==0x12ff and row['keys_after']==0x1300
            assert row['jiffy_before']==row['jiffy_after']==0x010203
            assert row['buffer_before_hex'].startswith('111d41') and row['buffer_after_hex'].startswith('1d41')
            assert row['mmu_before']==row['mmu_after']==14
            assert not right.io_writes
    bus,ram=machine();ram[0x100a:0x100d]=b'ABC';ram[0xd1]=3
    for value in b'ABC':
        invoke(bus,0x5000)
        assert ram[0x3d15]==value
    rows=decode(bytes(ram[0x5000:0x5800]))['records']
    assert [r['key'] for r in rows]==list(b'ABC')
    assert [r['function_count_before'] for r in rows]==[3,2,1]
    assert [r['function_index_before'] for r in rows]==[0,1,2]
    assert [r['function_byte_before'] for r in rows]==list(b'ABC')
    invoke(bus,0x5000);assert len(decode(bytes(ram[0x5000:0x5800]))['records'])==3
    cases.append('real native/KERNAL normal and function-key consumption; hold/deliver, flags, queue shifts and counter carry')

    for mmu in (0,0x0e):
        for flags in (0x20,0x29,0x64,0xe8):
            bus,ram=machine();bus.config=mmu
            cpu=invoke(bus,0x3fc0,a=0x11,x=2,y=84,flags=flags)
            assert (cpu.a,cpu.x,cpu.y,cpu.p&0xcf,bus.config)==(0x11,2,84,flags&0xcf,mmu)
            row=decode(bytes(ram[0x5000:0x5800]))['records'][0]
            assert (row['type'],row['key'],row['original_x'],row['original_y'],row['mmu_before'])==('scan',17,2,84,mmu)
            assert (row['extended_keyboard_lines'],row['cia1_ddr_a'],row['cia1_ddr_b'])==(255,255,0)
            assert ram[0x3d13:0x3d15]==b'\0\0' and not bus.io_writes
    cases.append('scan gate preserves registers, flags, stack and interrupted 00/0e mapping without consuming input')

    bus,ram=machine();ram[0x520a]=1
    injected=False
    def interleave(cpu):
        nonlocal injected
        if cpu.pc==real and not injected:
            injected=True
            old_config=bus.config;bus.config=0
            invoke(bus,0x3fc0,a=17,x=0,y=84,sp=cpu.sp-16)
            bus.config=old_config
            ram[0xd0]=1;ram[0x34a]=17;ram[0xd4:0xd6]=bytes([84,84])
    invoke(bus,0x5000,inject=interleave)
    rows=decode(bytes(ram[0x5000:0x5800]))['records']
    assert [r['type'] for r in rows]==['scan','consumed']
    assert rows[1]['buffer_count_before']==0 and rows[1]['key']==17
    # Pre-sample may precede the producing IRQ; it is retained rather than
    # rewritten to pretend the two observations were simultaneous.
    first=bytes(ram[0x5300:0x5380])
    for key in range(30):
        ram[0xd0]=1;ram[0x34a]=key+32;invoke(bus,0x5000)
    out=decode(bytes(ram[0x5000:0x5800]))
    assert len(out['records'])==20 and out['overflow']==12
    assert bytes(ram[0x5300:0x5380])==first
    ram[0x5207:0x5209]=b'\xff\xff';ram[0xd0]=1;ram[0x34a]=65;invoke(bus,0x5000)
    assert ram[0x5207:0x5209]==b'\xff\xff'
    cases.append('separate scan/foreground scratch survives producer interleaving; bounded journal retains first records and saturates overflow')
    return cases


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    report=dict(passed=False,physical_hardware_io=False)
    try:
        with tempfile.TemporaryDirectory(prefix='uos-input-cpu-') as work:report['cases']=run(Path(work))
        report['passed']=True;print('PASS:',len(report['cases']),'native input trace groups',flush=True)
    except BaseException as error:report['error']=repr(error);raise
    finally:args.report.write_text(json.dumps(report,indent=2)+'\n')
