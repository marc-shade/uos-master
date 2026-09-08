#!/usr/bin/env python3
"""Assembled core hit testing and launcher-control registration, with Py65."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from py65.devices.mpu6502 import MPU

ROOT = Path(__file__).resolve().parents[1]


def symbol(module, name):
    text = (ROOT/'target'/f'{module}.lst').read_text(encoding='latin-1')
    m = re.search(r'^[.>]([0-9a-fA-F]+)\s+.*?\b'+re.escape(name)+r':', text, re.M)
    assert m, name
    return int(m.group(1), 16)


def memory():
    ram = bytearray(65536)
    for name in ('uos', 'uos-desktop'):
        prg = (ROOT/'target'/f'{name}.prg').read_bytes()
        addr = int.from_bytes(prg[:2], 'little')
        ram[addr:addr+len(prg)-2] = prg[2:]
    return ram


def test_launcher():
    for count in (6, 0, 1, 2, 3, 4, 5):
        ram = memory()
        ram[0x9000] = 0
        ram[0x9001:0x90fb] = bytes([0xff])*250
        ram[symbol('uos-desktop', 'apps_count')] = count
        # Entry just after draw_rows, before the population count check.
        cpu = MPU(memory=ram, pc=symbol('uos-desktop', '_populate')+3)
        for _ in range(30000):
            if cpu.pc == 0x0811:
                break
            if cpu.pc in (0xc015, 0xc01e):
                ram[2:34] = bytes([0xe7])*32
                cpu.a = cpu.x = cpu.y = 0xe7
                cpu.pc = cpu.stPopWord()+1
            else:
                cpu.step()
        else:
            raise AssertionError('Launcher did not return to input dispatch')
        records = [bytes(ram[0x9001+i*10:0x900b+i*10]) for i in range(25)
                   if ram[0x9001+i*10] != 0xff]
        assert [r[1] for r in records] == list(range(20,20+count))+[29], (
            f'{count} apps: registered control IDs {[r[1] for r in records]}')
        assert ram[0x9000] == len(records)
        for i, record in enumerate(records[:-1]):
            assert int.from_bytes(record[2:4], 'little') == symbol('uos-desktop', f'APPS_LAUNCH_{i+1}')
            assert record[9] <= records[-1][6], 'Application row overlaps Cancel'


def test_hitboxes():
    for x1,x2 in ((72,246),(220,300),(256,319)):
        ram = memory()
        ram[0x9001:0x90fb] = bytes([0xff])*250
        record = bytes([1,25,0x78,0x56,x1&255,x1>>8,80,x2&255,x2>>8,92])
        ram[0x9001+24*10:0x900b+24*10] = record
        for y in (79,80,91,92):
            for x in range(320):
                sx = x+24
                ram[0xd000],ram[0xd010],ram[0xd001] = sx&255,sx>>8,y+50
                cpu = MPU(memory=ram, pc=symbol('uos', 'TESTCLICK'))
                cpu.stPushWord(0x02ff)
                for _ in range(1000):
                    if cpu.pc == 0x0300:
                        break
                    cpu.step()
                else:
                    raise AssertionError('Hit test did not return')
                hit = x1 <= x < x2 and 80 <= y < 92
                assert cpu.a == int(hit), (x1,x2,x,y,cpu.a)
                if hit:
                    assert ram[6] == 1 and ram[8] == 25 and ram[10:12] == b'\x78\x56'


def test_launch_names():
    ram = memory()
    names = [f'UOS-ROW-{i}'.encode() for i in range(1,7)]
    for i, name in enumerate(names,1):
        address = symbol('uos-desktop',f'row{i}')
        ram[address:address+17] = name.ljust(17,b'\0')
    for i, name in enumerate(names,1):
        cpu = MPU(memory=ram,pc=symbol('uos-desktop',f'APPS_LAUNCH_{i}'))
        for _ in range(1000):
            if cpu.pc == 0x0832:
                break
            cpu.step()
        else:
            raise AssertionError(f'Row {i} did not reach LAUNCH_APP')
        address = symbol('uos','file')
        got = bytes(ram[address:address+17]).split(b'\0')[0]
        assert got == name, f'Row {i} launches {got!r}, expected {name!r}'


def test_row_positions():
    ram = memory()
    ram[symbol('uos-desktop','apps_count')] = 6
    cpu = MPU(memory=ram,pc=symbol('uos-desktop','draw_rows'))
    cpu.stPushWord(0x02ff)
    positions = []
    for _ in range(10000):
        if cpu.pc == 0x0300:
            break
        if cpu.pc in (0xc01e,0x0835):
            if cpu.pc == 0xc01e:
                positions.append((int.from_bytes(ram[2:4],'little'),ram[4]))
            ram[2:34] = bytes([0xe7])*32
            cpu.a = cpu.x = cpu.y = 0xe7
            cpu.pc = cpu.stPopWord()+1
        else:
            cpu.step()
    else:
        raise AssertionError('Launcher did not finish drawing its rows')
    assert positions == [(76,82+12*i) for i in range(6)], positions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'build': {n:hashlib.sha256((ROOT/'target'/n).read_bytes()).hexdigest()
                        for n in ('uos.prg','uos-desktop.prg')}, 'checks': {}}
    for fn in (test_launcher,test_hitboxes,test_launch_names,test_row_positions):
        try:
            fn()
            report['checks'][fn.__name__] = {'passed':True}
            print('PASS:',fn.__name__,flush=True)
        except AssertionError as error:
            report['checks'][fn.__name__] = {'passed':False,'error':str(error)}
            print('FAIL:',fn.__name__,error,flush=True)
    if args.report:
        args.report.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if all(c['passed'] for c in report['checks'].values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
