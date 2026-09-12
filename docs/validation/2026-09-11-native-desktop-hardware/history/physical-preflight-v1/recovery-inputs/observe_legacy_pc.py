"""Capture the C64 foreground PC through an IRQ; restore the borrowed page."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
from hw_storage_check import HardwareMonitor,ROOT
from hwlib import desk_tick


def observe(ult):
    work=Path(tempfile.mkdtemp(prefix='uos-desktop-pc-observation-',dir='/var/tmp/arc-scratch'))
    print('Legacy PC observations:',work,flush=True)
    output=work/'legacy-pc.prg'
    subprocess.run(['64tass','-a',str(ROOT/'probes/legacy-pc.asm'),'-o',str(output)],check=True,capture_output=True)
    code=output.read_bytes();assert code[:2]==b'\0\x7e' and len(code)-2<=240
    mon=HardwareMonitor(ult)
    def read(at,count=1):return bytes(mon.read_mem(at,at+count-1))
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and read(0x4122,2)==bytes(2)
    oldirq=read(0x314,2);assert oldirq==b'\x57\x9e'
    saved=read(0x7e00,256);(work/'page-before.bin').write_bytes(saved)
    result=dict(passed=False,physical_hardware_io=True,samples=[],original_irq_hex=oldirq.hex(),
                no_cartridge_commands=True,no_fifo_reads=True,uncertain_writes=ult.uncertain_writes)
    def save():(work/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    try:
        mon.write_mem(0x7e00,code[2:])
        for index in range(8):
            assert read(0x314,2)==oldirq
            mon.write_mem(0x7ef0,oldirq+bytes(14))
            mon.write_mem(0x314,b'\0\x7e')
            deadline=time.monotonic()+10
            while read(0x7ef2)!=b'\1':
                assert time.monotonic()<deadline,'IRQ observer did not finish'
                time.sleep(.1)
            time.sleep(.2)
            assert read(0x314,2)==oldirq
            data=read(0x7ef0,16);(work/f'pc-{index}.bin').write_bytes(data)
            row=dict(index=index,raw_hex=data.hex(),stack=data[3],pc=int.from_bytes(data[4:6],'little'),
                     status=data[6],port_hex=data[7:9].hex(),tick_second=data[9],cia_second=data[10],
                     cia_ports_hex=data[11:13].hex(),uci_state=data[13])
            result['samples'].append(row);save();print(json.dumps(row),flush=True)
            time.sleep(.3)
        result['passed']=True
    finally:
        if read(0x314,2)==oldirq:
            time.sleep(.2);mon.write_mem(0x7e00,saved)
            result['borrowed_page_restored']=read(0x7e00,256)==saved
        else:result['borrowed_page_restored']=False
        save()
    assert result['borrowed_page_restored'] and not ult.uncertain_writes
    print('PASS: eight interrupted PCs captured; original IRQ and borrowed page restored',flush=True)
