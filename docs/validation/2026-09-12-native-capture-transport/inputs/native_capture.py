"""Bounded native C128 workspace observations for emulator/hardware tests."""
from contextlib import nullcontext
import hashlib
import json
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


def expected_screen(columns,bank,free=(175,251),slots=32,handle=b'\0'*4,result=0):
    lines=['UOS 128 - NATIVE MEMORY WORKSPACE','',f'SELECTED BANK: {bank}',
           f'FREE 256-BYTE PAGES (HEX) 0/1: {free[0]:02X}/{free[1]:02X}',
           f'FREE HANDLES (HEX): {slots:02X}',f'SELECTED HANDLE: {int.from_bytes(handle,"little"):08X}',
           f'LAST RESULT: {result:02X}','','1/2 SELECT BANK  A ALLOCATE 8K',
           'W FILL  V VERIFY  F RELEASE','C CALCULATOR  B FILES AND APPS','00 OK  04 INVALID HANDLE  0A MISMATCH','',
           'NATIVE DESKTOP MIGRATION IN PROGRESS']
    lines+=['']*(25-len(lines))
    assert all(len(line)<=columns for line in lines)
    return bytes(ord(c)-64 if 'A'<=c<='Z' else ord(c) for line in lines for c in line.ljust(columns))


def calculator_screen(columns,result,history,view=0,save_prompt=None,save_status=None,*,usb=False,save_caret=None,save_view=None):
    from native_field_check import field_cells
    lines=['UOS 128 CALCULATOR','',f'RESULT: {result}','','0-9 + - * / =  DEL  C CLEAR',
           'ESC RETURN   S SAVE   N/B HISTORY','','HISTORY (NEWEST FIRST, 32 RETAINED):']
    lines+=history[view:view+8] if history else ['NO RESULTS YET']
    if save_prompt is not None:
        field_row=len(lines)+2
        lines+=['','SAVE AS (BESIDE USB APP)' if usb else 'SAVE AS (SEQ FILE ON IEC DISK)',
                'NAME: '+' '*19,'ENTER SAVE   ESC CANCEL']
    elif save_status is not None:lines+=['',save_status]
    lines+=['']*(25-len(lines))
    screen=bytearray(ord(c)-64 if 'A'<=c<='Z' else ord(c) for line in lines for c in line.ljust(columns))
    if save_prompt is not None:
        at=field_row*columns+6
        screen[at:at+19]=field_cells(save_prompt,19,save_caret,save_view)
    return bytes(screen)


def verify_boot_layout(capture):
    """Compare the freshly relocated bytes before allocations modify heap state."""
    layout=json.loads((ROOT/'target/native/layout.json').read_text())
    image=(ROOT/'target/native/uos128.prg').read_bytes()
    origin=int.from_bytes(image[:2],'little');size=layout['low_padded_end']-layout['low_start']
    start=2+layout['staging_start']-origin;expected=image[start:start+size]
    assert len(expected)==size and layout['load_end']==origin+len(image)-2
    observed=b''.join(capture.capture(f'resident-initial-{offset:04x}',address=layout['low_start']+offset,count=min(2000,size-offset))
                      for offset in range(0,size,2000))
    assert observed==expected,'cold-boot resident bytes differ from the staged image'
    service_size=layout['service_end']-layout['service_start']
    offset=2+layout['service_start']-origin
    service=b''.join(capture.capture(f'service-initial-{part:04x}',address=layout['service_start']+part,
                                    count=min(2000,service_size-part)) for part in range(0,service_size,2000))
    assert service==image[offset:offset+service_size],'resident Ultimate bytes differ from the boot image'
    return dict(layout=layout,bytes=size,sha256=hashlib.sha256(observed).hexdigest(),cpu_capture_matches_image=True,
                service_bytes=service_size,service_sha256=hashlib.sha256(service).hexdigest(),service_matches_image=True)


class NativeCapture:
    def __init__(self,mon,work,quiet=2,*,kernel_prefix='native',batch=None):
        self.mon,self.work,self.quiet=mon,work,quiet
        self.batch=batch if batch is not None else lambda label:nullcontext()
        self.kernel_prefix=kernel_prefix
        assert lst_symbol(kernel_prefix+'/uos128','native_code_end')<=0x3800
        output=work/'native-read.prg'
        subprocess.run(['64tass','-a',str(ROOT/'probes/native-read.asm'),'-o',str(output)],check=True,capture_output=True)
        self.prg=output.read_bytes()
        assert self.prg[:2]==b'\0\x3e' and len(self.prg)-2<=0x1f0
        self.records=[]

    def read(self,address,count=1):
        data=bytes(self.mon.read_mem(address,address+count-1));self.mon.resume();return data

    def capture(self,label,*,mode=0,bank=0,address=0,count=2000):
        assert mode in (0,1) and bank in (0,1) and 1<=count<=2000 and address+count<=65536
        if mode==0 and bank==0:
            assert all(address+count<=start or address>=end for start,end in ((0x3a00,0x3c00),(0x3e00,0x4000))), 'capture source overlaps borrowed scratch'
        with self.batch(label+'-before'):
            assert self.read(0x1c13,6)==b'UOS128'
            assert self.read(0x3d11,2)==b'\0\1' and self.read(0xd0)==b'\0','native workspace must be idle'
            assert self.read(0x3d91)==b'\0','native file service must be idle before borrowing its buffer'
            oldirq=self.read(0x314,2);assert oldirq!=b'\0\x3e'
            output=self.read(0x3a00,512);scratch=self.read(0x3e00,512)
            metadata=self.read(0x3800,0x600)
            resident=self.read(0x1300,0x900)
        record=dict(label=label,mode=mode,bank=bank,address=address,count=count,
                    probe_sha256=hashlib.sha256(self.prg).hexdigest(),restored=False,
                    output_address=0x3a00,chunk_limit=512,chunks=[],address_resyncs=0)
        self.records.append(record)
        observed_before={'output':(0x3a00,output),'scratch':(0x3e00,scratch),
                         'metadata':(0x3800,metadata),'resident':(0x1300,resident)}
        record['borrower_checks']={}
        for name,(start,before) in observed_before.items():
            filename=f'{label}-borrower-{name}-before.bin'
            (self.work/filename).write_bytes(before)
            record['borrower_checks'][name]=dict(address=start,bytes=len(before),
                before_file=filename,before_sha256=hashlib.sha256(before).hexdigest(),
                source='host observation; not CPU-authoritative metadata')
        result=bytearray()
        try:
            with self.batch(label+'-install'):
                self.mon.write_mem(0x3e00,self.prg[2:])
            for offset in range(0,count,512):
                size=min(512,count-offset)
                command=oldirq+b'\0'+bytes([mode,bank])+(address+offset).to_bytes(2,'little')+size.to_bytes(2,'little')+bytes(7)
                with self.batch(label+f'-command-{offset:04x}'):
                    self.mon.write_mem(0x3ff0,command)
                    self.mon.write_mem(0x314,b'\0\x3e');self.mon.resume()
                time.sleep(self.quiet)
                wait(lambda:self.read(0x3ff2)!=b'\0','native capture chunk complete',20)
                with self.batch(label+f'-result-{offset:04x}'):
                    status=self.read(0x3ff2,12)
                    chunk=dict(address=address+offset,count=size,code=status[0],
                               address_resyncs=int.from_bytes(status[7:9],'little'),
                               mode_register=status[9],common_register=status[10],foreground_mmu=status[11])
                    record['chunks'].append(chunk)
                    record.update({k:chunk[k] for k in ('code','mode_register','common_register','foreground_mmu')})
                    record['address_resyncs']+=chunk['address_resyncs']
                    assert status[0]==1,record
                    assert not status[9]&0x40 and status[10]&15==4 and status[11]==0x0e,record
                    result.extend(self.read(0x3a00,size))
                wait(lambda:self.read(0x314,2)==oldirq,'native IRQ vector restored after chunk',20)
            (self.work/(label+'.bin')).write_bytes(result)
            return bytes(result)
        finally:
            wait(lambda:self.read(0x314,2)==oldirq,'native IRQ vector restored',20)
            time.sleep(.1)
            with self.batch(label+'-restore'):
                self.mon.write_mem(0x3a00,output);self.mon.write_mem(0x3e00,scratch);self.mon.resume()
                for name,(start,before) in observed_before.items():
                    after=self.read(start,len(before))
                    filename=f'{label}-borrower-{name}-after.bin'
                    (self.work/filename).write_bytes(after)
                    differences=[i for i,(left,right) in enumerate(zip(before,after)) if left!=right]
                    record['borrower_checks'][name].update(after_file=filename,
                        after_sha256=hashlib.sha256(after).hexdigest(),matches=after==before,
                        different_offsets=differences,observed_bytes=len(after))
                    message={'output':'native output buffer differs after restoration',
                             'scratch':'native observer scratch differs after restoration',
                             'metadata':'native heap changed during observation',
                             'resident':'resident low kernel changed during observation'}[name]
                    assert after==before,message
            record['restored']=True
