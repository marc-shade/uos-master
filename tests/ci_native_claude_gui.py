#!/usr/bin/env python3
"""Loaded Claude frame, real pointer code and interrupt-driven terminal lifecycle."""
import argparse
import hashlib
import json
from pathlib import Path

from ci_native_pointer import Pointer, PointerBus, heap
from ci_native_claude import Client, TerminalMachine
from native_claude_scene import surface, RECTS
from native_claude_check import landing_screen
from py65.devices.mpu6502 import MPU

ROOT = Path(__file__).resolve().parents[1]


class GraphicalClient(Client):
    frame = Pointer.frame
    move = Pointer.move
    position = Pointer.position
    poll = Pointer.poll

    def __init__(self, **options):
        super().__init__(**options)
        self.bus = self.chip.parent
        self.frames = self.checked = 0

    def settle(self):
        for _ in range(40):
            top = self.value('cg_top')
            if not self.value('cg_controls_dirty') and not any(self.ram[self.symbol('cg_dirty')+top:self.symbol('cg_dirty')+top+16]):return
            self.poll()
        raise AssertionError('graphical companion did not settle')

    def check(self):
        self.settle()
        assert self.value('cg_bitmap') == 1 and not self.value('cg_error')
        assert self.value('cg_keys_owned') == 1 and self.value('pm_active') == 1
        assert bytes(self.ram[0x33c:0x33e]) == self.symbol('pk_entry').to_bytes(2,'little')
        want = surface(bytes(self.ram[0x400:0x7e8]),bytes(self.chip.colors[:1000]),
            bytes(self.chip.video[0x3000:0x4000]), live=self.value('cg_live'),menu=self.value('cg_menu'),
            top=self.value('cg_top'),focus=self.value('cg_focus'))
        actual = bytes(self.ram[0xc000:0xe400])
        assert actual == want, ('Claude surface',[(i,a,b) for i,(a,b) in enumerate(zip(actual,want)) if a != b][:20])
        self.checked += 1

    def click(self, index, *, exited=False):
        before = self.events
        x0,y0,x1,y1 = RECTS[index]
        self.move((x0+x1)//2,(y0+y1)//2)
        self.frame(down=True)
        self.frame(down=False,exited=exited)
        assert int.from_bytes(self.ram[0x3d13:0x3d15],'little') == before

    def restored(self):
        for address in (0xd000,0xd001,0xd002,0xd003,0xd010,0xd015,0xd017,0xd01b,0xd01c,0xd01d,0xd027,0xd028,0xdc00,0xdc02,0xdc03,0xd02f):
            assert self.bus.video[address] == self.bus.initial[address], hex(address)
        assert self.ram[0xa04] == self.bus.init_status
        assert not self.value('pm_active') and not self.value('cg_keys_owned')
        assert not self.ram[heap.symbol('v_tag')]
        assert bytes(self.ram[0x33c:0x33e]) == bytes(self.ram[self.symbol('cg_saved_callback'):self.symbol('cg_saved_callback')+2])
        assert self.m.stats() == (175,251,32)


def run(selected="all"):
    cases = []
    def done(name,c):
        cases.append(dict(name=name,frames=c.frames,keys=c.events,complete_surfaces=c.checked))
        print('PASS:',name,flush=True)

    if selected in ("all","core"):
        c = GraphicalClient();c.check()
        assert c.chip.video[:2000] == landing_screen(80)
        c.frame();c.click(4);c.check();assert c.value('cg_top') == 9
        c.click(3);c.check();assert c.value('cg_top') == 0
        c.click(2,exited=True);c.restored();assert not c.chip.serial_writes
        done('mouse launch page, both complete panel pages, Desktop and ownership restoration',c)

        for options in ({'present':False},{'busy':True}):
            c = GraphicalClient(**options);c.frame();c.click(0);c.check()
            assert c.value('cg_top') == 9 and not c.chip.serial_writes
            assert c.chip.video[:2000] == landing_screen(80,2 if 'present' in options else 1)
            c.key(27,exited=True);c.restored()
        done('busy and absent ports preserve ownership and show their entire error',c)

        c = GraphicalClient();c.frame();c.click(0);c.check()
        assert c.value('cg_live') == 1 and c.chip.sent == b'\0\1'
        # Every screen code, raw color and bottom row remains observable. Incoming
        # glyphs immediately change the companion's glyphs as well as the terminal.
        panel = bytearray(b' '*1000)
        for row in range(25):
            payload = bytes((row*40+col)&255 for col in range(40))
            panel[row*40:(row+1)*40] = payload
            c.feed(bytes([7,row,row&15,40])+payload+b'\5')
        assert bytes(c.ram[0x400:0x7e8]) == panel
        c.check();c.click(4);c.check()
        c.feed(bytes([10,255])+bytes([1,2,4,8,16,32,64,128])+b'\5');c.check()
        c.click(3);c.check()
        c.click(1);assert c.chip.sent[-2:] == b'\0\1'
        c.click(2);c.check();assert c.value('cg_live') == 2
        c.feed(bytes([9,0x5a]),exited=True);c.restored()
        assert c.value('_closeOutcome') == 2 and not c.value('_rxDropped') and not c.value('_rxOverruns')
        done('mouse Connect/Repaint/acknowledged Desktop, all 256 panel codes and live custom glyphs',c)

        c = GraphicalClient();c.key(9);c.check();assert c.value('cg_focus') == 2
        c.key(9);c.check();assert c.value('cg_focus') == 4
        c.key(13);c.check();assert c.value('cg_top') == 9
        c.key(0x9d);c.key(0x9d);c.key(13);c.check();assert c.value('cg_live') == 1
        for code in (9,13,27,0x85,0x89,0x86,0x8a,0x87,0x8b,0x88,0x11,0x91,0x1d,0x9d,3):
            c.key(code);assert c.chip.sent[-1] == code
        c.key(255);c.check();assert c.value('cg_menu') == 1
        before = bytes(c.chip.sent)
        c.key(9);c.key(9);c.key(13);c.check();assert c.value('cg_top') == 0
        c.key(27);c.check();assert c.value('cg_menu') == 0 and bytes(c.chip.sent) == before
        c.key(0x84);assert c.chip.sent[-2:] == b'\0\1'
        c.close();c.restored()
        done('keyboard controls and both panel pages preserve the complete terminal key stream',c)

    if selected in ("all","input"):
        c = GraphicalClient();c.check()
        # Invoke the ROM-visible callback with the scan's real A/X/Y contract.
        # Modifier release after enqueue cannot change the already decoded event.
        at = c.symbol('pk_next');saved = bytes(c.ram[at:at+2])
        stack = bytes(c.ram[0x100:0x200]);c.ram[at:at+2] = b'\0\x0b'
        for modifiers in range(32):
            for code in (0x84,0x85,0x41):
                cpu = MPU(memory=c.chip,pc=c.symbol('pk_entry'));cpu.sp=0xe0;cpu.p=0x30
                cpu.a=code;cpu.x=modifiers;cpu.y=64;cpu.stPushWord(0xaff)
                for _ in range(100):
                    if cpu.pc == 0xb00:break
                    cpu.step()
                assert (cpu.pc,cpu.a,cpu.x,cpu.y,cpu.p,cpu.sp) == (0xb00,255 if code==0x84 and modifiers&4 else code,modifiers,64,0x30,0xde)
        c.ram[at:at+2]=saved;c.ram[0x100:0x200]=stack
        c.key(27,exited=True);c.restored()
        done('Ctrl+Help is decoded in the owned ROM-visible filter; 96 modifier/key combinations',c)

    if selected in ("all","stream"):
        c = GraphicalClient();c.key(13);c.check()
        # A glyph update leaves visible companion rows pending. Begin the next
        # burst at an actual RAM-store mapping inside one of those redraws.
        prologue=bytes([10,255])+bytes(range(8))+b'\5'
        c.feed(prologue)
        data = bytearray([1,14])
        for row in range(25):
            data += bytes([7,row,row&15,40])+bytes([row+32])*40
            data += bytes([2,row,0,14,80])+bytes([row+65])*80
        data += bytes([5])
        normal_step = c.cpu.step
        schedule = dict(at=0,credits=192-len(prologue),tx=len(c.chip.sent),due=c.cpu.processorCycles+260,
                        nested=False,peak=0,transfers=0,maps=set())
        def paced_step():
            normal_step()
            if schedule['nested']:return
            # The unmodified bridge window is 192 bytes, replenished in 64-byte
            # credits. Arrival spacing models 38,400 baud at the VIC's 1 MHz.
            while len(c.chip.sent)-schedule['tx'] >= 2:
                pair = c.chip.sent[schedule['tx']:schedule['tx']+2];schedule['tx'] += 2
                assert pair == b'\0\3',pair
                schedule['credits'] += 64
            if schedule['at']==0:
                if c.chip.config!=0x3f or not c.ram[0x3d11]:return
            elif c.cpu.processorCycles < schedule['due']:return
            schedule['due'] = c.cpu.processorCycles+260
            if not schedule['credits'] or schedule['at'] == len(data):return
            if c.ram[0x3d11]:schedule['transfers'] += 1
            schedule['maps'].add(c.chip.config)
            schedule['nested']=True
            try:c.nmi(data[schedule['at']])
            finally:schedule['nested']=False
            schedule['at']+=1;schedule['credits']-=1
            pending=(c.value('_rxHead')-c.value('_rxTail'))&255
            schedule['peak']=max(schedule['peak'],pending)
        c.cpu.step = paced_step
        try:
            for _ in range(12000):
                c.poll()
                if schedule['at'] == len(data) and c.value('_rxHead') == c.value('_rxTail'):break
            else:raise AssertionError('paced terminal stream did not drain')
        finally:c.cpu.step = normal_step
        c.check()
        assert c.chip.video[:2000] == b''.join(bytes([row+65])*80 for row in range(25))
        assert bytes(c.ram[0x400:0x7e8]) == b''.join(bytes([row+32])*40 for row in range(25))
        assert schedule['transfers'] > 0 and 0x3f in schedule['maps'],schedule
        assert not c.value('_rxDropped') and not c.value('_rxOverruns')
        assert schedule['peak']<=192
        c.close();c.restored()
        done('paced 38400-baud output interrupts live bitmap transfers without losing terminal or panel bytes',c)
        cases[-1].update(bytes_received=len(data),peak_ring=schedule['peak'],interrupts_during_transfers=schedule['transfers'],interrupted_maps=sorted(schedule['maps']))

    if selected in ("all","fallback"):
        original_bus = heap.Bus
        class Occupied(PointerBus):
            def __init__(self):
                super().__init__();self.ram[0][0xd8]=1  # unsupported active BASIC graphics
        heap.Bus = Occupied
        try:
            c=GraphicalClient();assert c.value('cg_bitmap') == 0
            assert not c.value('cg_keys_owned') and not c.value('pm_active')
            c.key(13);c.feed(bytes([1,14,5]));c.close()
            assert c.m.stats() == (175,251,32)
        finally:heap.Bus = original_bus
        done('refused display retains text terminal and serial cleanup without installing mouse ownership',c)

        import ci_native_claude as terminal
        original_machine=terminal.TerminalMachine
        class Fragmented(original_machine):
            def __init__(self):
                super().__init__()
                self.obstacle=self.alloc(36,0,77,page=0xc0)
                self.foreign=bytes(self.ram[0xc000:0xe400])
        terminal.TerminalMachine=Fragmented
        try:
            c=GraphicalClient();assert not c.value('cg_bitmap') and c.value('cg_error')==2
            c.key(13)
            assert bytes(c.ram[0xc000:0xe400])==c.m.foreign
            assert not c.value('cg_keys_owned') and not c.value('pm_active')
            c.m.select(c.m.obstacle,77)
            stack=bytes(c.ram[0x100:0x200]);c.m.invoke('free');c.ram[0x100:0x200]=stack
            c.close()
        finally:terminal.TerminalMachine=original_machine
        done('foreign surface allocation is preserved during a text fallback session',c)

        c=GraphicalClient(tx=False);c.key(13,exited=True);c.restored()
        assert not c.chip.sent and (c.chip.command,c.chip.control)==(2,0x1e)
        done('transmitter timeout restores graphical input, display, font and all app pages',c)

        c=GraphicalClient();c.frame();c.move(50,16);c.frame(down=True)
        c.key(9);c.frame(down=False);c.check()
        assert c.value('cg_live') == 0 and not c.chip.serial_writes
        c.key(27,exited=True);c.restored()
        done('keyboard input cancels a held Connect gesture',c)
    return cases


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--case',choices=('all','core','input','stream','fallback'),default='all');args = parser.parse_args()
    report = dict(passed=False,physical_hardware_io=False,
        images={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (ROOT/'target/native-desktop/claude.prg',heap.IMAGE)})
    try:
        report['cases'] = run(args.case);report['passed'] = True
    except BaseException as exc:
        report['error'] = repr(exc);raise
    finally:args.report.write_text(json.dumps(report,indent=2)+'\n')
