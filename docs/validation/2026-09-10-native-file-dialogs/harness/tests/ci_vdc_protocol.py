#!/usr/bin/env python3
"""Require the VDC selected-register ready handshake in assembled driver code."""
import argparse
import hashlib
import json
from pathlib import Path
from py65.devices.mpu6502 import MPU

ROOT = Path(__file__).resolve().parents[1]


class VDC:
    def __init__(self, present=True):
        self.ram = bytearray(65536)
        self.video = bytearray([0xa5])*65536
        self.reg = bytearray(64)
        self.reg[1],self.reg[6],self.reg[28] = 80,25,32
        self.present = present
        self.selected,self.busy,self.ready = 0,0,False
        prg = (ROOT/'target/uos-vdc.prg').read_bytes()
        self.ram[0xcc00:0xcc00+len(prg)-2] = prg[2:]

    def __getitem__(self, a):
        if a == 0xd600:
            if not self.present:
                return 0
            if self.busy:
                self.busy -= 1
                return 0
            self.ready = True
            return 0x80
        if a == 0xd601:
            assert self.ready, f'Read register {self.selected} before ready'
            self.ready,self.busy = False,2
            if self.selected == 31:
                address = self.reg[18]<<8|self.reg[19]
                value = self.video[address]
                self.advance(address)
                return value
            return self.reg[self.selected]
        return self.ram[a]

    def __setitem__(self, a, value):
        if a == 0xd600:
            self.selected,self.busy,self.ready = value&63,3,False
        elif a == 0xd601:
            assert self.ready, f'Write register {self.selected} before ready'
            self.ready,self.busy = False,2
            if self.selected == 31:
                address = self.reg[18]<<8|self.reg[19]
                self.video[address] = value
                self.advance(address)
            else:
                self.reg[self.selected] = value
        else:
            self.ram[a] = value

    def advance(self,address):
        address = (address+1)&65535
        self.reg[18],self.reg[19] = address>>8,address&255

    def call(self, pc, a=0, x=0):
        c = MPU(memory=self,pc=pc)
        c.a,c.x,c.y = a,x,0x69
        c.stPushWord(0x02ff)
        for _ in range(200000):
            if c.pc == 0x0300:
                return c
            c.step()
        raise AssertionError('Driver call did not return')


def check():
    b = VDC()
    c = b.call(0xcc00,x=28)
    assert c.a == 32 and c.x == 28 and c.y == 0x69
    b.call(0xcc03,a=0x46,x=26)
    assert b.reg[26] == 0x46
    b.call(0xcc06,a=0xff,x=2)
    assert b.reg[18:20] == b'\x02\xff'
    b.ram[0xcc24] = 1
    text = b'\xc1\xc4\xc9\xc4\xc1\xd3 \xc3HAMPIONSHIP \xc6OOTBALL (132)'
    want = b'ADIDAS C\x08\x01\x0d\x10\x09\x0f\x0e\x13\x08\x09\x10 F\x0f\x0f\x14\x02\x01\x0c\x0c (132)'
    b.ram[0x6000:0x6000+len(text)+1] = text+b'\0'
    b.ram[0x14:0x16] = b'\0\x60'
    b.call(0xcc1b,a=9,x=3)
    start = 9*80+3
    assert b.video[start:start+len(want)] == want
    assert b.video[start+0x800:start+0x800+len(want)] == bytes([0x81])*len(want)
    assert b.call(0xcc18).a == 1
    absent = VDC(present=False)
    assert absent.call(0xcc18).a == 0


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    r={'driver_sha256':hashlib.sha256((ROOT/'target/uos-vdc.prg').read_bytes()).hexdigest()}
    try:
        check()
        r['passed']=True
        print('PASS: VDC register readiness, string/attributes and absent probe',flush=True)
    except AssertionError as error:
        r.update(passed=False,error=str(error))
        print('FAIL:',error,flush=True)
    if args.report:
        args.report.write_text(json.dumps(r,indent=2)+'\n')
    return 0 if r['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
