#!/usr/bin/env python3
"""Check the native observer through a complete native ROM IRQ frame."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from py65.devices.mpu6502 import MPU
from ci_native_heap import Bus, ROOT
from ci_vdc_capture import CaptureBus


class NativeCaptureBus(Bus):
    def __init__(self, fault=None, present=True):
        super().__init__()
        self.vdc = CaptureBus(fault,present)

    def __getitem__(self,address):
        if address in (0xd600,0xd601) and not self.config & 1:
            return self.vdc[address]
        return super().__getitem__(address)

    def __setitem__(self,address,value):
        if address in (0xd600,0xd601) and not self.config & 1:
            self.vdc[address]=value
        else:
            super().__setitem__(address,value)


def check(prg,mode,bank,start,count,fault=None,present=True):
    bus=NativeCaptureBus(fault,present); ram=bus.ram[0]
    ram[0x3e00:0x3e00+len(prg)-2]=prg[2:]
    ram[0x3ff0:0x3ffb]=b'\0\x0b\0'+bytes([mode,bank])+start.to_bytes(2,'little')+count.to_bytes(2,'little')+b'\0\0'
    ram[0x314:0x316]=b'\0\x3e'
    ram[0xfb:0xff]=b'\x63\x98\x15\xa7'
    bus.vdc.video[:2000]=bytes((i*73+i//251)&255 for i in range(2000))
    bus.vdc.reg[18:20]=b'\x23\x47'
    expected=bytes(bus.vdc.video[:2000] if mode else bus.ram[bank][start:start+count]) if bank<2 else b''
    before=bytes(ram[0x2ff0:0x3000]),bytes(ram[0x37d0:0x3e00]),bytes(ram[0x3000:0x37d0])
    cpu=MPU(memory=bus,pc=0x2500); cpu.sp=0xc0
    cpu.a,cpu.x,cpu.y,cpu.p=0x5a,0x6d,0x90,0x28
    cpu.irq()
    for steps in range(2000000):
        if cpu.pc==0x2500:break
        cpu.step()
    else:raise AssertionError('Native IRQ capture failed to return')
    assert (cpu.a,cpu.x,cpu.y,cpu.sp,cpu.p&0xcf)==(0x5a,0x6d,0x90,0xc0,8)
    assert bus.config==0x0e and ram[0x314:0x316]==b'\0\x0b'
    assert ram[0x3ffb:0x3ffe]==bytes([0xb7,4,0x0e])
    assert ram[0xfb:0xff]==b'\x63\x98\x15\xa7' and ram[0x2aa]==0xbb
    assert bytes(ram[0x2ff0:0x3000])==before[0] and bytes(ram[0x37d0:0x3e00])==before[1]
    result=ram[0x3ff2]; resyncs=int.from_bytes(ram[0x3ff9:0x3ffb],'little')
    if mode>1 or bank>1 or not 1<=count<=2000:
        assert result==4 and bytes(ram[0x3000:0x37d0])==before[2]
    elif mode and not present:assert result==2
    elif mode and fault=='always':assert result==3 and resyncs==3
    else:
        assert result==1 and ram[0x3000:0x3000+count]==expected[:count]
        assert ram[0x3000+count:0x37d0]==before[2][count:]
    if mode==1 and present and 1<=count<=2000:
        assert bus.vdc.reg[18:20]==b'\x23\x47'
    assert not bus.far_writes and ram[0xb10]==1
    return dict(code=result,address_resyncs=resyncs,instructions=steps)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='uos-native-capture-') as folder:
        output=Path(folder)/'probe.prg'
        subprocess.run(['64tass','-a',str(ROOT/'probes/native-read.asm'),'-o',str(output)],check=True,capture_output=True)
        prg=output.read_bytes()
    assert prg[:2]==b'\0\x3e' and len(prg)-2<=0x1f0
    cases={}
    for bank in (0,1):
        for start,count in ((0x4000,2000),(0xcf80,512),(0xe000,2000),(0xfef0,16)):
            cases[f'ram-{bank}-{start:04x}']=check(prg,0,bank,start,count)
    for label,fault,present in [('normal',None,True),('first',0,True),('page-boundary',255,True),
                                ('last',1999,True),('persistent','always',True),('absent',None,False)]:
        cases['vdc-'+label]=check(prg,1,0,0,2000,fault,present)
    for mode,bank,count in ((2,0,1),(0,2,1),(0,0,0),(0,0,2001),(0,0,65535)):
        cases[f'bad-{mode}-{bank}-{count}']=check(prg,mode,bank,0x4000,count)
    report=dict(passed=True,probe_sha256=hashlib.sha256(prg).hexdigest(),cases=cases)
    if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: {len(cases)} native IRQ bank/VDC captures, faults, guards and complete frame restoration',flush=True)


if __name__=='__main__':main()
