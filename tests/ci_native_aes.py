#!/usr/bin/env python3
"""Persistent AES component (GEM layer step 1): load, survive app exit,
re-attach from a new app, refuse bad images or ranges, and unload fully."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import tempfile

from py65.devices.mpu6502 import MPU
import ci_native_heap as heap
import ci_native_calc
from ci_native_calc import Calculator
from ci_native_files import StreamIEC
from native_banked_bus import BankedBus
import native_aes_scene as scene

ROOT = Path(__file__).resolve().parents[1]
APP = b'AESDEMO.PRG'
AESVC = b'AESVC.PRG'
AE_BASE = 0x9000
AES_OWNER = 30

_released = ci_native_calc.released_stats


def resident_aes(machine):
    """The single owner-30 record, or None; checked against the page tags."""
    ram = machine.ram
    records = [(i, bytes(ram[0x3c00+i*8:0x3c08+i*8])) for i in range(32)]
    aes = [(i, r) for i, r in records if r[0] == AES_OWNER]
    if not aes:
        return None
    assert len(aes) == 1, aes
    slot, record = aes[0]
    assert record[1] == 1 and record[2] == AE_BASE >> 8, record
    pages = record[3]
    assert bytes(ram[0x3900+record[2]:0x3900+record[2]+pages]) == bytes([slot+1])*pages
    return record


def released_with_aes(machine):
    record = resident_aes(machine)
    live = [bytes(machine.ram[0x3c00+i*8:0x3c08+i*8]) for i in range(32)]
    live = [r for r in live if r[0]]
    if record is None:
        return _released(machine)
    assert all(r[0] == AES_OWNER for r in live), live
    return 175, 251-record[3], 31


ci_native_calc.released_stats = released_with_aes


class Demo(Calculator):
    instruction_limit = 12000000

    def __init__(self, output, machine=None, *, corrupt=False, missing=False):
        if machine is None:
            heap.Bus = BankedBus
            machine = heap.Machine()
        self.m = machine
        self.ram = self.m.ram
        self.image_name = 'aes-demo'
        self.image = (output/APP.decode()).read_bytes()
        component = bytearray((output/AESVC.decode()).read_bytes())
        if corrupt:
            component[-1] ^= 1
        self.symbols = {n: int(v, 16) for n, v in re.findall(
            r'^([\w.]+)\s*=\s*\$([\da-fA-F]+)', (output/'parent.sym').read_text(), re.M)}
        self.aes_symbols = {n: int(v, 16) for n, v in re.findall(
            r'^([\w.]+)\s*=\s*\$([\da-fA-F]+)', (output/'aesvc.sym').read_text(), re.M)}
        files = {(8, APP, b'P'): self.image, (8, AESVC, b'P'): bytes(component)}
        if missing:
            del files[8, AESVC, b'P']
        self.io = StreamIEC(self.m, files)
        self.io.formats[8] = 0
        self.ram[0x3d21:0x3d23] = bytes([8, len(APP)])
        self.ram[0x3d40:0x3d40+len(APP)] = APP
        self.ram[0x3d2c:0x3d2e] = bytes([0, 8])
        self.cpu = MPU(memory=self.m.bus, pc=0x1c38)
        self.cpu.sp, self.cpu.p = 0xe0, 0x20
        self.cpu.stPushWord(0xaff)
        self.screens = [bytearray(b' '*1000), bytearray(b' '*2000)]
        self.reverse = [False, False]; self.row = [0, 0]; self.col = [0, 0]; self.keys = []
        # N_KEYS is kernel state and keeps counting across launches.
        self.events = int.from_bytes(self.ram[0x3d13:0x3d15], 'little')
        self.instructions = 0
        self.observation_target = None; self.observation_done = False
        self.loop()

    def symbol(self, name):
        if name == 'cloop':  # the next wait point: alert or event loop, else input
            name = ('demo_alert_loop' if self.alert_open() else
                    'ae_event_wait' if self.ram[self.symbols['demo_waiting']] else 'input_loop')
        return self.symbols[name]

    def alert_open(self):
        return self.m.bus.ram[1][self.aes_symbols['al_active']] == 1

    def surface(self):
        return bytes(self.ram[0xc000:0xe400])

    def data(self, name, length):
        at = self.symbol(name)
        return bytes(self.ram[at:at+length])

    def check(self, *, attaches, apps, loaded, error=0, version=0x0102, choice=0):
        status = self.data('demo_status', 13)
        assert self.value('demo_error') == error, (self.value('demo_error'), error)
        assert self.value('demo_loaded') == loaded
        if error == 0:
            assert status[0:2] == bytes([version >> 8, version & 255])
            assert int.from_bytes(status[4:6], 'little') == attaches
            assert int.from_bytes(status[6:8], 'little') == apps
        lines = ['AES DEMO', f'VERSION (HEX): ${status[0]:02X}{status[1]:02X}',
                 f'ATTACHES (HEX): ${status[5]:02X}{status[4]:02X}',
                 f'APPS (HEX): ${status[7]:02X}{status[6]:02X}',
                 f'LOADED HERE (HEX): ${loaded:02X}', f'ALERT CHOICE (HEX): ${choice:02X}',
                 'EVENT (HEX): '+self.data('ae_ev_result', 7).hex().upper(),
                 'MESSAGE (HEX): '+self.data('ae_ev_result', 15)[7:].hex().upper(),
                 f'LAST ERROR (HEX): ${error:02X}', '',
                 'RETURN: AES STATUS', 'ESC: EXIT, AES STAYS RESIDENT', 'U: UNLOAD AES AND EXIT',
                 'A: AES ALERT OVER THE VIC SURFACE', 'E: WAIT FOR EVENTS  P: POST A MESSAGE']
        for screen, columns in zip(self.screens, (40, 80)):
            expected = bytearray(b' '*(columns*25))
            for row, line in enumerate(lines):
                expected[row*columns:row*columns+len(line)] = bytes(
                    v-64 if 64 <= v < 96 else v for v in line.encode())
            assert screen == expected, (columns, bytes(screen[:columns*10]))

    def bank1(self, offset, length):
        return bytes(self.m.bus.ram[1][AE_BASE+offset:AE_BASE+offset+length])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix='uos-aes-', dir='/var/tmp/arc-scratch'))
    spec = importlib.util.spec_from_file_location('aes_build', ROOT/'examples/native-aes/build.py')
    build = importlib.util.module_from_spec(spec); spec.loader.exec_module(build)
    images = build.build(work)
    component = (work/AESVC.decode()).read_bytes()
    report = dict(passed=False, physical_hardware_io=False, work=str(work), images=images, cases=[])

    def done(name, demo, **extra):
        report['cases'].append(dict(name=name, events=demo.events, instructions=demo.instructions, **extra))
        args.report.write_text(json.dumps(report, indent=2)+'\n')
        print('PASS:', name, flush=True)

    try:
        first = Demo(work)
        first.check(attaches=1, apps=1, loaded=1)
        record = resident_aes(first.m)
        assert record is not None and record[3] == images['images']['AESVC.PRG']['pages']
        # The loaded bytes equal the file image after the executor patches the
        # callback import; the counters live inside the resident image.
        resident = first.bank1(0, len(component)-2)
        expected = bytearray(component[2:])
        callback = first.symbol('ae_callback')
        expected[22:24] = callback.to_bytes(2, 'little')
        assert resident[:22] == bytes(expected[:22]) and resident[22:24] == bytes(expected[22:24])
        first.key(13); first.check(attaches=1, apps=1, loaded=1)
        first.key(27, exited=True)
        assert resident_aes(first.m) is not None, 'AES must survive the app exit'
        done('first app loads AESVC at bank-1 $9000 as owner 30; it survives exit', first,
             pages=record[3])

        second = Demo(work, first.m)
        second.check(attaches=2, apps=2, loaded=0)
        assert second.bank1(22, 2) == callback.to_bytes(2, 'little')
        second.key(13); second.check(attaches=2, apps=2, loaded=0)
        second.key(ord('U'), exited=True)
        assert resident_aes(second.m) is None
        assert second.m.stats() == _released(second.m), 'unload returns every page'
        done('second app attaches without loading, sees persisted counters, unloads fully', second)

        third = Demo(work, second.m)
        third.check(attaches=1, apps=1, loaded=1)
        third.key(27, exited=True)
        machine = third.m
        identity = AE_BASE+32
        machine.bus.ram[1][identity] ^= 0x40          # 'N' -> 0x0e: not an AES
        refused = Demo(work, machine)
        refused.check(attaches=0, apps=0, loaded=0, error=0x10)
        refused.key(27, exited=True)
        assert resident_aes(machine) is not None, 'a refused attach leaves the image alone'
        machine.bus.ram[1][identity] ^= 0x40
        callback_bytes = machine.bus.ram[1][AE_BASE+22:AE_BASE+24]
        machine.bus.ram[1][AE_BASE+22:AE_BASE+24] = bytes(2)  # as a partial load leaves it
        partial = Demo(work, machine)
        partial.check(attaches=0, apps=0, loaded=0, error=0x10)
        partial.key(27, exited=True)
        machine.bus.ram[1][AE_BASE+22:AE_BASE+24] = callback_bytes
        again = Demo(work, machine)
        again.check(attaches=2, apps=2, loaded=0)  # the refused apps never registered
        again.key(ord('U'), exited=True)
        assert resident_aes(machine) is None
        done('wrong identity or zero callback import (partial load) refused with BADIMAGE; restored image re-attaches', again)

        heap.Bus = BankedBus
        blocked_machine = heap.Machine()
        blocked_machine.alloc(1, bank=1, owner=29, page=AE_BASE >> 8)  # real heap reserve
        occupied = Demo(work, blocked_machine)
        occupied.check(attaches=0, apps=0, loaded=0, error=occupied.value('demo_error'))
        assert occupied.value('demo_error') not in (0, 4), occupied.value('demo_error')
        assert resident_aes(blocked_machine) is None
        assert blocked_machine.ram[0x3900+(AE_BASE >> 8)] != 0, 'the other owner keeps its page'
        done('occupied $9000 by another owner: clean allocation refusal, nothing adopted', occupied,
             error=occupied.value('demo_error'))

        for kind, error in (('corrupt', 0x14), ('missing', None)):
            demo = Demo(work, corrupt=kind == 'corrupt', missing=kind == 'missing')
            code = demo.value('demo_error')
            if error is not None:
                assert code == error, code
            else:
                assert code not in (0, 4), code
            demo.check(attaches=0, apps=0, loaded=0, error=code)
            assert resident_aes(demo.m) is None
            demo.key(27, exited=True)
            done(f'{kind} AESVC.PRG refused; no resident image', demo, error=code)
        alert_cases(work, report, done)
        event_cases(work, report, done)
        report['passed'] = True
    finally:
        args.report.write_text(json.dumps(report, indent=2)+'\n')


ALERT = b'[3][Delete NOTES.TXT?|This cannot be undone.][Delete|Cancel]'
BLANK = bytes(8192)+b'\x16'*1024


def alert_cases(work, report, done):
    from native_display_bus import DisplayBus  # VIC/CIA state N_VSHOW requires
    heap.Bus = DisplayBus
    demo = Demo(work, heap.Machine())
    demo.check(attaches=1, apps=1, loaded=1)
    aes = demo.aes_symbols

    def reply():
        return bytes(demo.ram[0x3a00:0x3a06])

    def expect(focus, before=BLANK):
        want, geo = scene.draw(before, ALERT, 2, focus)
        got = demo.surface()
        assert got == want, [(i, a, b) for i, (a, b) in enumerate(zip(got, want)) if a != b][:12]
        return geo

    def saved_pages():
        return [bytes(demo.ram[0x3c00+i*8:0x3c08+i*8]) for i in range(32)
                if demo.ram[0x3c00+i*8] == AES_OWNER and demo.ram[0x3c02+i*8] != AE_BASE >> 8]

    demo.key(ord('A'))
    assert demo.alert_open()
    geo = expect(2)
    assert reply()[:2] == bytes([0, 2]) and reply()[2:] == scene.dirty_rows(geo['y'], geo['h'])
    assert len(saved_pages()) == 1, 'one owner-30 save-under allocation while open'
    for key, focus in ((9, 1), (9, 2), (0x9d, 1), (0x9d, 2), (0x1d, 1), (ord('x'), 1)):
        demo.key(key); expect(focus)
        rows = scene.dirty_rows(geo['button_y'], 2) if key != ord('x') else bytes(4)
        assert reply() == bytes([0, focus])+rows, (key, reply())
    demo.key(13)
    assert not demo.alert_open() and demo.surface() == BLANK, 'exact restoration'
    assert reply()[:2] == bytes([1, 1]) and not saved_pages()
    demo.check(attaches=1, apps=1, loaded=1, choice=1)
    done('keyboard alert: exact frame, Tab/cursor focus with row masks, Return, exact restore', demo,
         alert=dict(x=geo['x'], y=geo['y'], w=geo['w'], h=geo['h']))

    for keys, choice in (([ord('2')], 2), ([ord('1')], 1), ([27], 2), ([13], 2)):
        demo.key(ord('A')); expect(2)
        for key in keys:
            demo.key(key)
        assert not demo.alert_open() and demo.surface() == BLANK
        demo.check(attaches=1, apps=1, loaded=1, choice=choice)
    done('digits choose directly, Escape chooses Cancel, Return takes the default', demo)

    def point(x, y, down):
        at = demo.symbol('ae_pointer_x')
        demo.ram[at:at+2] = x.to_bytes(2, 'little')
        demo.ram[demo.symbol('ae_pointer_y')] = y
        demo.ram[demo.symbol('ae_pointer_buttons')] = down
        demo.key(0xff)

    demo.key(ord('A')); expect(2)
    delete_x = geo['button_x'][0]*8+12; bar_y = geo['button_y']*8+8
    point(delete_x, bar_y, 1); expect(1)            # press arms and focuses Delete
    point(20, 20, 0); expect(1)                     # release elsewhere: nothing chosen
    assert demo.alert_open()
    point(delete_x, bar_y, 1); point(delete_x+8, bar_y+4, 0)
    assert not demo.alert_open() and demo.surface() == BLANK
    demo.check(attaches=1, apps=1, loaded=1, choice=1)
    done('1351-style press/release on the same button chooses it; release elsewhere does not', demo)

    # A drawn surface underneath must come back byte for byte.
    pattern = bytes((i*37+11) & 255 for i in range(8192))+bytes((i*7) & 255 for i in range(1024))
    demo.ram[0xc000:0xe400] = pattern
    demo.key(ord('A')); expect(2, pattern)
    demo.key(27)
    assert demo.surface() == pattern
    done('arbitrary pixels and colours under the alert are restored exactly', demo)

    at = demo.symbol('demo_alert')
    original = bytes(demo.ram[at:at+len(ALERT)+1])
    for bad in (b'[3][a|b|c|d|e|f][OK]', b'[4][x][OK]', b'[1][x][]', b'[1][x][A|B|C|D]',
                b'[1]['+b'W'*31+b'][OK]', b'[1][x][OK]junk', b'[1][x][ELEVENCHARS]'):
        assert scene.parse(bad) is None
        demo.ram[at:at+len(bad)+1] = bad+b'\0'
        demo.key(ord('A'))
        assert not demo.alert_open() and not saved_pages() and demo.surface() == pattern
        demo.check(attaches=1, apps=1, loaded=1, choice=2, error=1)
    too_big = b'[1][' + b'|'.join([b'W'*30]*5) + b'][OK]'
    assert scene.parse(too_big) is not None and scene.layout(*scene.parse(too_big)) is None
    demo.ram[at:at+len(too_big)+1] = too_big+b'\0'
    demo.key(ord('A')); assert not demo.alert_open() and not saved_pages()
    demo.ram[at:at+len(original)] = original
    done('malformed strings and alerts over 250 cells are refused before any surface change', demo)
    demo.key(27, exited=True)


def event_cases(work, report, done):
    heap.Bus = BankedBus
    demo = Demo(work, heap.Machine())
    demo.check(attaches=1, apps=1, loaded=1)

    def waiting():
        return demo.ram[demo.symbol('demo_waiting')] == 1

    def resume():
        """Run one more pass of the wait loop without a key (time/pointer moved)."""
        demo.observation_target = None
        demo.keys.append(0)
        demo.loop()

    def jiffy(value):
        demo.ram[0xa0:0xa3] = value.to_bytes(3, 'big')

    def pointer(x, y, buttons):
        at = demo.symbol('ae_pointer_x')
        demo.ram[at:at+2] = x.to_bytes(2, 'little')
        demo.ram[demo.symbol('ae_pointer_y')] = y
        demo.ram[demo.symbol('ae_pointer_buttons')] = buttons

    def params(mask, clicks=1, bmask=1, bstate=1, m1=(0, 0, 0, 0, 0), m2=(0, 0, 0, 0, 0), timer=0):
        at = demo.symbol('ae_ev_params')
        demo.ram[at:at+16] = bytes([mask, clicks, bmask, bstate, *m1, *m2]) + timer.to_bytes(2, 'little')

    def result():
        return demo.data('ae_ev_result', 15)

    jiffy(1000); pointer(0, 0, 0)
    demo.key(ord('E')); assert waiting()
    demo.key(ord('Z')); assert not waiting()
    assert result()[:2] == bytes([1, 0x5a]) and result()[6] == 0
    demo.check(attaches=1, apps=1, loaded=1)
    done('keyboard event returns the key', demo)

    jiffy(0x01fff0)                         # crosses a 16-bit carry during the wait
    demo.key(ord('E')); assert waiting()
    jiffy(0x01fff0+59); resume(); assert waiting()
    jiffy(0x01fff0+60); resume(); assert not waiting() and result()[0] == 32
    done('timer fires at exactly 60 jiffies, not 59, across a carry', demo)

    params(2)
    demo.key(ord('E')); assert waiting()
    pointer(40, 30, 1); resume(); assert not waiting()
    assert result()[0] == 2 and result()[6] == 1 and result()[2:6] == bytes([40, 0, 30, 1])
    demo.key(ord('E')); assert not waiting() and result()[0] == 2, 'GEM: state already matches'
    pointer(40, 30, 0)
    done('button press fires one click; an already-matching state fires at once', demo)

    params(2, clicks=2)
    jiffy(5000); demo.key(ord('E'))
    pointer(0, 0, 1); resume(); assert waiting()
    pointer(0, 0, 0); jiffy(5010); resume(); assert waiting()
    pointer(0, 0, 1); jiffy(5019); resume(); assert not waiting()
    assert result()[0] == 2 and result()[6] == 2
    pointer(0, 0, 0)
    jiffy(6000); demo.key(ord('E'))
    pointer(0, 0, 1); resume(); pointer(0, 0, 0); jiffy(6019); resume(); assert waiting()
    jiffy(6020); resume(); assert not waiting() and result()[6] == 1
    done('double-click inside the 20-jiffy window; the window closing reports one click', demo)

    params(4|8, m1=(0, 10, 10, 5, 5), m2=(1, 0, 0, 4, 4))
    pointer(8, 8, 0); demo.key(ord('E')); assert waiting()           # in rect 2, outside rect 1
    pointer(12*8, 14*8+7, 0); resume(); assert not waiting()          # enters 1 and leaves 2
    assert result()[0] == 4|8
    params(4, m1=(0, 10, 10, 5, 5))
    pointer(15*8, 12*8, 0); demo.key(ord('E')); assert waiting()      # x == 10+5 is outside
    pointer(14*8+7, 10*8, 0); resume(); assert not waiting() and result()[0] == 4
    done('rectangle enter/leave with half-open cell bounds', demo)

    params(16|32, timer=1000)
    jiffy(0); demo.key(ord('P')); demo.key(ord('E'))
    assert not waiting() and result()[0] == 16 and result()[7:] == bytes([41, 0, 7, 0, 1, 2, 3, 4])
    demo.key(ord('E')); assert waiting()
    jiffy(1000); resume(); assert not waiting() and result()[0] == 32
    for n in range(16):
        demo.key(ord('P')); assert demo.value('demo_error') == 0, n
    demo.key(ord('P')); assert demo.value('demo_error') == 2, 'N_NOMEM when 16 are queued'
    done('messages queue in order, deliver once, and refuse a 17th', demo)

    demo.key(27, exited=True)
    other = Demo(work, demo.m)
    other.check(attaches=2, apps=2, loaded=0)
    at = other.symbol('ae_ev_params')
    other.ram[at:at+16] = bytes([16|32, 1, 1, 1]+[0]*10) + (5).to_bytes(2, 'little')
    other.ram[0xa0:0xa3] = bytes(3)
    other.key(ord('E'))
    other.ram[0xa0:0xa3] = (5).to_bytes(3, 'big')
    other.observation_target = None; other.keys.append(0); other.loop()
    assert other.data('ae_ev_result', 1)[0] == 32, 'the previous app\'s messages were discarded'
    other.key(ord('U'), exited=True)
    done('a new app attaching finds an empty queue', other)


if __name__ == '__main__':
    main()
