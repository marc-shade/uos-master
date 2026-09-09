"""Bounded native C128 workspace observations for emulator/hardware tests."""
import hashlib
from pathlib import Path
import subprocess
import time

from hwlib import lst_symbol

ROOT=Path(__file__).resolve().parent


def wait(predicate,label,seconds=30):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.1)
    raise AssertionError(label)


def expected_screen(columns,bank,free=(191,251),slots=32,handle=b'\0'*4,result=0):
    lines=['UOS 128 - NATIVE MEMORY WORKSPACE','',f'SELECTED BANK: {bank}',
           f'FREE 256-BYTE PAGES (HEX) 0/1: {free[0]:02X}/{free[1]:02X}',
           f'FREE HANDLES (HEX): {slots:02X}',f'SELECTED HANDLE: {int.from_bytes(handle,"little"):08X}',
           f'LAST RESULT: {result:02X}','','1/2 SELECT BANK  A ALLOCATE 8K',
           'W FILL  V VERIFY  F RELEASE','C CALCULATOR','00 OK  04 INVALID HANDLE  0A MISMATCH','',
           'NATIVE DESKTOP MIGRATION IN PROGRESS']
    lines+=['']*(25-len(lines))
    assert all(len(line)<=columns for line in lines)
    return bytes(ord(c)-64 if 'A'<=c<='Z' else ord(c) for line in lines for c in line.ljust(columns))


def calculator_screen(columns,result,history,view=0,save_prompt=None,save_status=None):
    lines=['UOS 128 CALCULATOR','',f'RESULT: {result}','','0-9 + - * / =  DEL  C CLEAR',
           'ESC RETURN   S SAVE   N/B HISTORY','','HISTORY (NEWEST FIRST, 32 RETAINED):']
    lines+=history[view:view+8] if history else ['NO RESULTS YET']
    if save_prompt is not None:
        lines+=['','SAVE AS (SEQ FILE ON IEC DISK)','NAME: '+save_prompt,'ENTER SAVE   ESC CANCEL']
    elif save_status is not None:lines+=['',save_status]
    lines+=['']*(25-len(lines))
    return bytes(ord(c)-64 if 'A'<=c<='Z' else ord(c) for line in lines for c in line.ljust(columns))


class NativeCapture:
    def __init__(self,mon,work,quiet=2):
        self.mon,self.work,self.quiet=mon,work,quiet
        assert lst_symbol('native/uos128','native_code_end')<=0x3800
        output=work/'native-read.prg'
        subprocess.run(['64tass','-a',str(ROOT/'probes/native-read.asm'),'-o',str(output)],check=True,capture_output=True)
        self.prg=output.read_bytes()
        assert self.prg[:2]==b'\0\x3e' and len(self.prg)-2<=0x1f0
        self.records=[]

    def read(self,address,count=1):
        data=bytes(self.mon.read_mem(address,address+count-1));self.mon.resume();return data

    def capture(self,label,*,mode=0,bank=0,address=0,count=2000):
        assert mode in (0,1) and bank in (0,1) and 1<=count<=2000 and address+count<=65536
        assert self.read(0x1c13,6)==b'UOS128'
        assert self.read(0x3d11,2)==b'\0\1' and self.read(0xd0)==b'\0','native workspace must be idle'
        oldirq=self.read(0x314,2);assert oldirq!=b'\0\x3e'
        output=self.read(0x1400,2000);scratch=self.read(0x3e00,512)
        metadata=self.read(0x3800,0x600)
        record=dict(label=label,mode=mode,bank=bank,address=address,count=count,
                    probe_sha256=hashlib.sha256(self.prg).hexdigest(),restored=False)
        self.records.append(record)
        try:
            self.mon.write_mem(0x3e00,self.prg[2:])
            command=oldirq+b'\0'+bytes([mode,bank])+address.to_bytes(2,'little')+count.to_bytes(2,'little')+bytes(7)
            self.mon.write_mem(0x3ff0,command)
            self.mon.write_mem(0x314,b'\0\x3e');self.mon.resume()
            time.sleep(self.quiet)
            wait(lambda:self.read(0x3ff2)!=b'\0','native capture complete',20)
            status=self.read(0x3ff2,12)
            record.update(code=status[0],address_resyncs=int.from_bytes(status[7:9],'little'),
                          mode_register=status[9],common_register=status[10],foreground_mmu=status[11])
            assert status[0]==1,record
            assert not status[9]&0x40 and status[10]&15==4 and status[11]==0x0e,record
            result=self.read(0x1400,count)
            (self.work/(label+'.bin')).write_bytes(result)
            return result
        finally:
            wait(lambda:self.read(0x314,2)==oldirq,'native IRQ vector restored',20)
            time.sleep(.1)
            self.mon.write_mem(0x1400,output);self.mon.write_mem(0x3e00,scratch);self.mon.resume()
            assert self.read(0x1400,2000)==output and self.read(0x3e00,512)==scratch
            assert self.read(0x3800,0x600)==metadata,'native heap changed during observation'
            record['restored']=True
