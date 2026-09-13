#!/usr/bin/env python3
"""Execute shipped boot wrappers; reject damaged streams before kernel entry."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from py65.devices.mpu6502 import MPU

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_boot_pack import pack, unpack


def symbols(path):
    return {m[1]:int(m[2],16) for m in re.finditer(r'^(\w+)\s*=\s*\$([0-9a-f]+)$',path.read_text(),re.M)}


class Memory:
    def __init__(self, prg, labels, end):
        self.data = [(i*37+(i>>8)*29+17)&255 for i in range(65536)]
        self.data[0x1c01:0x1c01+len(prg)-2] = prg[2:]
        self.data[0xd505], self.data[0xff00] = 0, 0x0e
        length = labels['boot_file_end']-labels['boot_payload']
        self.allowed = ((0x100,0x200), (0x1300,(labels['decoder_end']+255)&~255),
                        (0x1c01,end), (0x6000,(0x6000+length+255)&~255), (0xff00,0xff01))
        self.writes = set()

    def __getitem__(self, at): return self.data[at]
    def __setitem__(self, at, value):
        assert any(start <= at < end for start,end in self.allowed), ('boot write outside declared regions',hex(at))
        self.writes.add(at); self.data[at] = value


def execute(prg, labels, raw, *, passed, status=0x20, c64=False):
    memory = Memory(prg,labels,0x1c01+len(raw))
    memory.data[0xd505] = 0x40 if c64 else 0
    cpu = MPU(memory=memory,pc=0x1c10);cpu.sp=0xe0;cpu.p=status
    cpu.stPushWord(0x0afe)
    message = bytearray()
    decoded = False
    for steps in range(2500000):
        if cpu.pc == 0x1c10 and decoded:
            assert passed and not message
            assert bytes(memory.data[0x1c01:0x1c01+len(raw)]) == raw
            assert cpu.sp == 0xde
            break
        if cpu.pc == 0x0aff:
            assert not passed
            assert cpu.sp == 0xe0
            assert message == (b'' if c64 else b'\rUOS BOOT ERROR - RELOAD\r')
            break
        if cpu.pc == 0xffd2:
            message.append(cpu.a)
            cpu.pc = cpu.stPopWord()+1
            continue
        if cpu.pc < 0x1c01:
            decoded = True
            assert 0x1300 <= cpu.pc < labels['decoder_end'], hex(cpu.pc)
        else:
            assert not decoded and 0x1c10 <= cpu.pc < labels['decoder_image'], hex(cpu.pc)
        cpu.step()
    else:
        raise AssertionError(('boot did not terminate',hex(cpu.pc)))
    assert cpu.p&0x0c == status&0x0c
    assert memory.data[0xff00] == 0x0e
    if c64:
        assert all(0x100 <= at < 0x200 for at in memory.writes)
    return steps


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    report=dict(passed=False,physical_hardware_io=False,cases=[])
    try:
        for folder in ('native','native/d81','native-desktop','native-desktop/d81'):
            path=ROOT/'target'/folder
            raw=(path/'uos128.prg').read_bytes()[2:]
            prg=(path/'uos128-boot.prg').read_bytes()
            labels=symbols(path/'uos128-boot.sym')
            payload=labels['boot_payload']-0x1c01+2
            assert prg[payload:] == pack(raw) and unpack(prg[payload:],len(raw)) == raw
            for status in (0x20,0x2c):
                steps=execute(prg,labels,raw,passed=True,status=status)
                report['cases'].append(dict(name=folder+' exact kernel and D/I preservation',status=status,instructions=steps,
                    boot_sha256=hashlib.sha256(prg).hexdigest(),kernel_sha256=hashlib.sha256(raw).hexdigest()))
        # Exercise errors in the real decoder, including its nested read/write
        # stack frames. Payload damage cannot choose output addresses or entry.
        cases=[]
        for index in (0,1,127,len(prg[payload:])//2,len(prg[payload:])-2,len(prg[payload:])-1):
            broken=bytearray(prg);broken[payload+index]^=1
            cases.append((f'payload bit flip at {index}',bytes(broken)))
        broken=bytearray(prg);broken[payload]=0
        cases.append(('premature terminator',bytes(broken)))
        broken=bytearray(prg);broken[payload:]=bytes([255,0])*((len(prg)-payload)//2)+bytes((len(prg)-payload)%2)
        cases.append(('run stream exceeds decoded output',bytes(broken)))
        for length in (payload+1,payload+(len(prg)-payload)//2,len(prg)-1):
            cases.append((f'truncated file at {length}',prg[:length]))
        for name,broken in cases:
            steps=execute(broken,labels,raw,passed=False)
            report['cases'].append(dict(name=name,instructions=steps))
        steps=execute(prg,labels,raw,passed=False,c64=True)
        report['cases'].append(dict(name='C64 mode refusal before map or scratch writes',instructions=steps))
        report['passed']=True
    except BaseException as error:
        report['error']=repr(error);raise
    finally:
        args.report.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS:',len(report['cases']),'boot decode and rejection cases',flush=True)


if __name__=='__main__':main()
