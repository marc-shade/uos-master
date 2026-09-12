"""Temporary, bounded keyboard evidence; never an app qualification bypass."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from native_capture import ROOT, wait

BASE, SIZE, GATE, GATE_SIZE = 0x5000, 0x800, 0x3fc0, 0x30
KEYIN, KEYCHECK = 0x1c3b, 0x033c


def assemble(work, old_keycheck=0xc000):
    symbols = {m[1]: int(m[2],16) for m in re.finditer(r'^(\w+)\s*=\s*\$([0-9a-f]+)',
        (ROOT/'target/native-desktop/uos128.sym').read_text(),re.M)}
    result = []
    for name, var, value in (('native-input-trace','KEYIN_TARGET',symbols['native_keyin']),
                              ('native-input-gate','KEYCHECK_TARGET',old_keycheck)):
        output = work/(name+'.prg')
        subprocess.run(['64tass','-a','-D',f'{var}=${value:04x}',str(ROOT/'probes'/(name+'.asm')),
                        '-o',str(output)],check=True,capture_output=True)
        result.append(output.read_bytes())
    assert result[0][:2] == b'\0\x50' and len(result[0])-2 == SIZE
    assert result[1][:2] == b'\xc0\x3f' and len(result[1])-2 <= GATE_SIZE
    return result, bytes([0x4c])+symbols['native_keyin'].to_bytes(2,'little')


def decode(raw):
    assert len(raw) == SIZE and raw[0x200:0x206] == b'UIT1\x01\x14'
    count = raw[0x206]; assert count <= 20
    result = dict(records=[], overflow=int.from_bytes(raw[0x207:0x209],'little'),
        phase=raw[0x209], hold=raw[0x20a], scans=int.from_bytes(raw[0x20b:0x20d],'little'),
        consumed=int.from_bytes(raw[0x20d:0x20f],'little'))
    for index in range(count):
        data = raw[0x300+64*index:0x340+64*index]
        assert data[0] in (1,2)
        row = dict(index=index, type='scan' if data[0]==1 else 'consumed', key=data[1],
            phase=data[2], entry_flags=data[3], mmu_before=data[5],
            jiffy_before=int.from_bytes(data[7:10],'big'), state_before_hex=data[13:23].hex(),
            buffer_before_hex=data[23:33].hex(), function_byte_before=data[53],
            keys_before=int.from_bytes(data[55:57],'little'), last_key_before=data[59],
            cia1_port_a=data[61],cia1_port_b=data[62],shift_flags=data[63])
        row.update(buffer_count_before=data[17],function_count_before=data[18],
                   function_index_before=data[19],scan_index_before=data[21],last_scan_index_before=data[22])
        if data[0] == 1:
            row.update(original_x=data[4], original_y=data[6],extended_keyboard_lines=data[10],
                       cia1_ddr_a=data[11],cia1_ddr_b=data[12])
        else:
            row.update(return_flags=data[4],mmu_after=data[6],jiffy_after=int.from_bytes(data[10:13],'big'),
                state_after_hex=data[33:43].hex(),buffer_after_hex=data[43:53].hex(),
                function_byte_after=data[54],keys_after=int.from_bytes(data[57:59],'little'),last_key_after=data[60])
        result['records'].append(row)
    return result


class InputTrace:
    def __init__(self, mon, work, batch, report, save, *, quiet=2):
        self.mon,self.work,self.batch,self.report,self.save,self.quiet = mon,work,batch,report,save,quiet
        self.backups={};self.installed=False;self.hooks_started=False
        self.row=report['input_trace']=dict(installed=False,restored=False,held_input=True,
            snapshots=[],batches=[],reserved_by_heap=False,
            lease='Temporary free pages under exclusive idle-desktop diagnostic; allocation map must remain unchanged')

    def read(self, address, count):
        data=bytes(self.mon.read_mem(address,address+count-1));self.mon.resume();return data

    @contextmanager
    def timed_batch(self,label):
        row=dict(label=label,start=time.monotonic());self.row['batches'].append(row);self.save()
        try:
            with self.batch(label):yield
        finally:row['finish']=time.monotonic();self.save()

    def install(self):
        previous=self.read(KEYCHECK,2)
        assert int.from_bytes(previous,'little')>=0xc000, 'native ROM keyboard hook required'
        (prg,gate),expected=assemble(self.work,int.from_bytes(previous,'little'))
        capture=self.work/'native-read.prg'
        subprocess.run(['64tass','-a',str(ROOT/'probes/native-read.asm'),'-o',str(capture)],check=True,capture_output=True)
        assert len(capture.read_bytes())-2 <= GATE-0x3e00, 'observer overlaps input mapping gate'
        with self.timed_batch('input-trace-install'):
            assert self.read(0x1c13,6)==b'UOS128'
            assert self.read(0x3d11,2)==b'\0\1' and self.read(0xd0,2)==b'\0\0'
            assert self.read(0x3d20,1)==b'\x20' and self.read(0x3d23,1)==b'\x02'
            assert self.read(0x3d91,1)==b'\0' and self.read(0x99,1)==b'\0'
            assert self.read(0x3d60,32)==(ROOT/'target/native-desktop/desktop.prg').read_bytes()[2:34]
            assert self.read(0x3850,8)==bytes(8), 'trace pages are already allocated'
            assert self.read(KEYIN,3)==expected and self.read(KEYCHECK,2)==previous
            for name,address,count in [('pages',BASE,SIZE),('gate',GATE,GATE_SIZE),
                                        ('keyin',KEYIN,3),('keycheck',KEYCHECK,2),('ownership',0x3800,512)]:
                data=self.read(address,count);self.backups[name]=data
                (self.work/('input-trace-'+name+'-before.bin')).write_bytes(data)
            self.installed=True
            self.mon.write_mem(BASE,prg[2:]);self.mon.write_mem(GATE,gate[2:])
            assert self.read(BASE,SIZE)==prg[2:] and self.read(GATE,len(gate)-2)==gate[2:]
            self.hooks_started=True
            self.mon.write_mem(KEYCHECK,GATE.to_bytes(2,'little'))
            self.mon.write_mem(KEYIN,b'\x4c\0\x50')
            assert self.read(KEYCHECK,2)==b'\xc0\x3f' and self.read(KEYIN,3)==b'\x4c\0\x50'
            self.row.update(installed=True,prg_sha256=hashlib.sha256(prg).hexdigest(),
                            gate_sha256=hashlib.sha256(gate).hexdigest(),original_keycheck=previous.hex())
            self.save()

    def phase(self, value):
        with self.timed_batch(f'input-trace-phase-{value}'):
            self.mon.write_mem(0x5209,bytes([value]))
            assert self.read(0x5209,1)==bytes([value])

    def snapshot(self,label):
        with self.timed_batch(label):
            raw=self.read(BASE,SIZE)
            result=dict(label=label,file=label+'.bin',sha256=hashlib.sha256(raw).hexdigest(),time=time.monotonic())
            (self.work/result['file']).write_bytes(raw)
            self.row['snapshots'].append(result);self.save()
            try:result.update(decode(raw))
            except BaseException as error:
                result['decode_error']=dict(type=type(error).__name__,message=str(error));self.save();raise
            self.save()
            assert self.read(0x3800,512)==self.backups['ownership'], 'allocation occurred during diagnostic lease'
            return result

    def restore(self):
        if not self.installed:return
        observation_error=None
        if self.hooks_started:
            try:self.snapshot('input-trace-final')
            except BaseException as error:
                observation_error=error
                self.row['final_observation_error']=dict(type=type(error).__name__,message=str(error));self.save()
            with self.timed_batch('input-trace-detach'):
                self.mon.write_mem(KEYIN,self.backups['keyin'])
                self.mon.write_mem(KEYCHECK,self.backups['keycheck'])
                assert self.read(KEYIN,3)==self.backups['keyin'] and self.read(KEYCHECK,2)==self.backups['keycheck']
            # Existing calls must return before their borrowed code is restored.
            # GETIN is bounded with keyboard input, and the trace has no waits.
            time.sleep(self.quiet)
        with self.timed_batch('input-trace-restore'):
            assert self.read(0x3800,512)==self.backups['ownership'], 'trace pages acquired by an app'
            self.mon.write_mem(GATE,self.backups['gate']);self.mon.write_mem(BASE,self.backups['pages'])
            for name,address in [('gate',GATE),('pages',BASE),('keyin',KEYIN),('keycheck',KEYCHECK)]:
                data=self.read(address,len(self.backups[name]))
                (self.work/('input-trace-'+name+'-after.bin')).write_bytes(data)
                assert data==self.backups[name], ('input diagnostic restoration differs',name)
        self.row['restored']=True;self.save();self.installed=False
        if observation_error is not None:raise observation_error
