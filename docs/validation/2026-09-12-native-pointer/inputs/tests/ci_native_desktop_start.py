#!/usr/bin/env python3
"""Execute native restart initialization with stale selection and directory state."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import ci_native_heap as heap
from native_display_bus import DisplayBus
from py65.devices.mpu6502 import MPU

parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True)
args=parser.parse_args()
report=dict(passed=False,physical_hardware_io=False,scope='real startup instructions through desktop/workspace dispatch; display and IEC boot verified separately in VICE',cases=[])
heap.Bus=DisplayBus
for prefix in ('native','native-desktop'):
    heap.IMAGE=ROOT/'target'/prefix/'uos128.prg'
    for saved in (2,255):
        machine=heap.Machine();ram=machine.ram
        machine.bus.video[0xd030]=1
        ram[0x3d2f]=saved;ram[0x3d30:0x3d34]=bytes.fromhex('12345678')
        ram[0x3d13:0x3d15]=bytes.fromhex('ffff')
        ram[0xba]=8
        cpu=MPU(memory=machine.bus,pc=heap.symbol('native_start'));cpu.sp=0xf0;cpu.p=0x20
        target=heap.symbol('native_browser' if prefix=='native-desktop' else 'native_draw')
        for steps in range(100000):
            if cpu.pc==target:break
            cpu.step()
        else:raise AssertionError('native restart did not reach dispatch')
        assert cpu.sp==0xf0 and machine.bus.config==0x0e
        assert ram[0x3d2f:0x3d34]==bytes(5)
        assert ram[0x3d13:0x3d15]==bytes(2) and ram[0x3d12]==0
        assert ram[0x3d2e]==1 and ram[0x4a00]==ord('/')
        assert ram[0x3d0e:0x3d11]==bytes([175,251,32])
        assert machine.bus.video[0xd030]==0
        report['cases'].append(dict(kernel=prefix,saved_selection=saved,reset_selection=0,
            browser_position_reset=True,keys_reset=True,free_pages=426,instructions=steps,
            kernel_sha256=hashlib.sha256(heap.IMAGE.read_bytes()).hexdigest()))
report['passed']=True;args.report.write_text(json.dumps(report,indent=2)+'\n')
print('PASS: four native restart cases clear stale selection, browser position and keys with all 426 pages available')
