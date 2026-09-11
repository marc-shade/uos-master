"""Fault-injection hypothesis; does not reproduce the cartridge's initiating fault."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('/home/marc/geos128/uos')
sys.path[:0] = [str(ROOT/'tests'), str(ROOT)]
from ci_native_directory_ultimate import Client, DirectoryDOS
from ci_native_files import RECORDS, CLOSE, STATUS
from ci_native_heap import symbol


class DelayedAbort(DirectoryDOS):
    def __init__(self, entries):
        super().__init__(entries)
        self.open_directory_stuck = False
        self.abort_reads_left = 0
        self.abort_requests = 0
        self.inject_once = True

    def __setitem__(self, address, value):
        if address == 0xdf1c and value == 1 and bytes(self.command)[1] == 0x13 and self.inject_once:
            self.inject_once = False
            self.open_directory_stuck = True
        if address == 0xdf1c and value == 4:
            self.abort_requests += 1
            self.open_directory_stuck = False
            self.abort_reads_left = 100
            return
        super().__setitem__(address, value)

    def __getitem__(self, address):
        if address == 0xdf1c:
            if self.open_directory_stuck:
                return 0x10
            if self.abort_reads_left:
                self.abort_reads_left -= 1
                if self.abort_reads_left == 0:
                    super().__setitem__(0xdf1c, 4)
                return 4
        return super().__getitem__(address)


c = Client([b'\x20NOTE'])
c.ultimate = DelayedAbort([b'\x20NOTE'])
c.m.bus.dos = c.ultimate
c.directory(device=2, expected=0x11, max_steps=6000000)
first = dict(status=c.ram[STATUS], descriptor=bytes(c.ram[RECORDS:RECORDS+16]).hex(),
             timer=bytes(c.ram[symbol('nu_tmo'):symbol('nu_tmo')+3]).hex(),
             active=c.ram[symbol('nd_active')], abort_pending=c.ultimate.abort_reads_left)
assert first['status'] == 0xff and first['timer'] == '000000'
assert first['active'] == 0 and first['abort_pending'] == 100
before = len(c.ultimate.commands)
c.call(CLOSE, 0x15)
second = dict(status=c.ram[STATUS], descriptor=bytes(c.ram[RECORDS:RECORDS+16]).hex(),
              timer=bytes(c.ram[symbol('nu_tmo'):symbol('nu_tmo')+3]).hex(),
              active=c.ram[symbol('nd_active')], abort_pending=c.ultimate.abort_reads_left)
assert second['status'] == 0xe2 and c.ram[RECORDS+3] == 4 and c.ram[RECORDS+7] == 0x15
assert len(c.ultimate.commands) == before and c.ultimate.abort_requests == 1
# Complete the injected external delay, then request cleanup explicitly.
while c.ultimate.abort_reads_left:
    c.ultimate[0xdf1c]
c.call(CLOSE)
assert not c.ram[RECORDS] and c.ultimate.paths[2] == b'/browser'
c.clean()
result = dict(passed=True, hardware_io=False,
    kernel_sha256=hashlib.sha256((ROOT/'target/native/uos128.prg').read_bytes()).hexdigest(),
    injected_fault='OPEN_DIR remains busy until native timeout; abort completion delayed by 100 status reads',
    source_firmware_revision='a01c04e8267a0d916b7203cb34dcf1127f75981d',
    model_limit='Status-read delays are synthetic, not FPGA clocks or measured cartridge timing.',
    after_open=first, after_cleanup_attempt=second, implicit_command_replay=False,
    explicit_close_after_abort_completion_passed=True,
    initiating_physical_failure_proven=False, native_images_changed=False)
Path('/var/tmp/arc-scratch/uos-module-usb-abort-hypothesis.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2), flush=True)
