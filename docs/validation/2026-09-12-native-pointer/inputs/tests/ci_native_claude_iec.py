#!/usr/bin/env python3
"""Cold-boot uOS, launch packaged Claude, run the real TCP/PTY bridge, return."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests'), str(ROOT/'apps/claude/host')]
import ci_fm as ci
from native_capture import NativeCapture, wait, expected_screen
from native_capture_transport import PausedViceMonitor
from native_claude_check import landing_screen
from launcher_scene import surface, console
import font
import petscii


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); return sock.getsockname()[1]


def main():
    p = argparse.ArgumentParser(); p.add_argument('--host-exit', action='store_true')
    p.add_argument('--cpu-capture', action='store_true', help='verify settled terminal through the physical IRQ observer')
    p.add_argument('--80col', dest='eighty', action='store_true'); args = p.parse_args()
    if args.cpu_capture and args.host_exit:
        p.error('--cpu-capture requires the stationary fixture without the updating status panel')
    work = Path(tempfile.mkdtemp(prefix='uos-native-claude-iec-', dir='/var/tmp/arc-scratch'))
    print('Native Claude evidence:', work, flush=True)
    disk = work/'suite.d64'; shutil.copyfile(ROOT/'target/native-desktop/uos128.d64', disk)
    hashes = {name: hashlib.sha256((ROOT/'target/native-desktop'/name).read_bytes()).hexdigest()
              for name in ('uos128.prg','uos128.d64','desktop.prg','controls.prg','claude.prg')}
    result = dict(passed=False, physical_hardware_io=False, options=vars(args), images=hashes, events=[])
    labels = {m[2]:int(m[1],16) for m in re.finditer(r'^al ([0-9A-Fa-f]+) \.(\S+)',
              (ROOT/'target/native-desktop/claude.lbl').read_text(), re.M)}
    for name in ('claude.prg','claude.lbl','desktop.prg'):
        shutil.copyfile(ROOT/'target/native-desktop'/name, work/name)
    shutil.copyfile(__file__, work/'run.py')
    xv = ci.cbm.Xvfb(); mon = emu = bridge = None
    emulog = (work/'vice.log').open('w'); hostlog = (work/'bridge.log').open('w')
    try:
        linkport, monport = port(), port()
        fixture = ROOT/'tests/fixtures/claude-session.py'
        host = [sys.executable, '-B', str(ROOT/'apps/claude/run.py'), '--listen', str(linkport),
                '--command', shlex.join([sys.executable,'-B',str(fixture)]), '-v']
        if not args.host_exit: host.append('--no-panel')
        bridge = subprocess.Popen(host, stdout=hostlog, stderr=subprocess.STDOUT)
        # Readiness from the bridge's actual log, without consuming its one connection.
        wait(lambda:'listening on' in (work/'bridge.log').read_text(), 'bridge listening', 15)
        command = ['x128','-default','-80col' if args.eighty else '-40col','-8',str(disk),
            '-drive8true','-drive8type','1541','-VDC16KB','-sounddev','dummy','-jamaction','0','-warp',
            '-acia1','-acia1base','0xDE00','-acia1irq','1','-acia1mode','1','-myaciadev','0',
            '-rsdev1',f'127.0.0.1:{linkport}','-rsdev1baud','38400',
            '-binarymonitor','-binarymonitoraddress',f'ip4://127.0.0.1:{monport}']
        result.update(emulator_command=command, bridge_command=host)
        emu = subprocess.Popen(command, env=dict(os.environ, DISPLAY=xv.display,
            __EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL), stdout=emulog, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+30
        while mon is None:
            assert emu.poll() is None, 'VICE exited'
            try: mon = ci.Monitor(port=monport)
            except OSError:
                if time.monotonic()>deadline: raise
                time.sleep(.1)
        banks = mon.banks(); mon.resume()
        def read(address, count=1, bank=0):
            data = bytes(mon.read_mem(address,address+count-1,bank=bank)); mon.resume(); return data
        def ready(): return read(0x3d12)==b'\1' and read(0xd0,2)==bytes(2)
        def key(value):
            wait(ready,'native readiness',120)
            before = int.from_bytes(read(0x3d13,2),'little')
            mon.write_mem(0x3d12,b'\0'); mon.write_mem(0x34a,bytes([value]));mon.write_mem(0xd0,b'\1');mon.resume()
            wait(lambda:ready() and int.from_bytes(read(0x3d13,2),'little')==(before+1)&65535,
                 f'key {value:02x}',180)
            result['events'].append(value)
        def desktop(label, selected):
            wait(lambda:ready() and read(0xc000,9216,banks['ram00'])==surface(selected),label,180)
            assert read(0,2000,banks['vdc'])==console(80,selected)
            (work/(label+'-surface.bin')).write_bytes(read(0xc000,9216,banks['ram00']))
            (work/(label+'-vdc.bin')).write_bytes(read(0,2000,banks['vdc']))
            assert read(0x3d2f)==bytes([selected])
        desktop('boot-desktop',0)
        original_font = read(0x3000,4096,banks['vdc']); (work/'font-before.bin').write_bytes(original_font)
        original_nmi = read(0x318,2); original_gate = read(0x3d3e,2)
        (work/'nmi-before.bin').write_bytes(original_nmi+original_gate)
        key(ord('A'))
        assert read(0x400,1000,banks['ram00'])==landing_screen(40)
        assert read(0,2000,banks['vdc'])==landing_screen(80)
        print('PASS: packaged app launch page',flush=True)
        key(13)
        def row_text(row, text):
            expected = bytes(petscii.to_screen_code(c) for c in text)
            return read(row*80,len(expected),banks['vdc'])==expected
        wait(lambda:row_text(0,'UOS CLAUDE LINK READY'),'bridge rendered PTY output',90)
        wait(lambda:row_text(2,'Keyboard, glyphs and return test'),'complete initial frame',60)
        assert read(0x318,2)==b'\xf0\x1b'
        assert read(0x3d3e,2)==labels['nmiHandler'].to_bytes(2,'little')
        code = font.CODES['❯']
        expected_glyph = bytes(font.BITMAPS[code])+bytes(8)
        assert read(0x3000+16*code,16,banks['vdc'])==expected_glyph
        key(ord('P')); wait(lambda:row_text(3,'KEY RECEIVED: p'),'PTY keyboard delivery',60)
        key(27); wait(lambda:row_text(4,'ESCAPE RECEIVED'),'Escape delivered to PTY',60)
        previous_rx=int.from_bytes(read(labels['_rxCount'],2),'little')
        key(0x84)
        wait(lambda:int.from_bytes(read(labels['_rxCount'],2),'little')>previous_rx and
             read(labels['_framesSeen'])!=b'\0','HELP received a new frame',60)
        expected=bytearray(b' '*2000)
        for row,text in enumerate(['UOS CLAUDE LINK READY','❯ ✳ ⏺','Keyboard, glyphs and return test',
                                   'KEY RECEIVED: p','ESCAPE RECEIVED']):
            codes=bytes(petscii.to_screen_code(c) for c in text)
            expected[row*80:row*80+len(codes)]=codes
        wait(lambda:read(0,2000,banks['vdc'])==expected,'complete terminal repaint',60)

        if args.cpu_capture:
            # The fixture is now stationary and --no-panel emits no timer
            # updates. This observer borrows the VDC address/selected register;
            # it is not admitted as a concurrent drawing observer.
            time.sleep(.5)
            paused = PausedViceMonitor(mon)
            capture = NativeCapture(paused, work, quiet=.02, kernel_prefix='native-desktop', batch=paused.paused)
            result['cpu_captures'] = capture.records
            result['cpu_capture_batches'] = paused.batches
            assert capture.capture('cpu-session-vdc', mode=1, count=2000) == expected
            assert capture.capture('cpu-session-vic', address=0x400, count=1000) == read(0x400,1000,banks['ram00'])
            assert capture.capture('cpu-session-nmi', address=0x318, count=2) == b'\xf0\x1b'
            assert capture.capture('cpu-session-gate', address=0x3d3e, count=2) == labels['nmiHandler'].to_bytes(2,'little')
            assert all(row['restored'] for row in capture.records)
            print('PASS: settled terminal CPU capture with serial NMI handler installed', flush=True)

        for name, address, count, bank in [('session-vdc',0,2000,banks['vdc']),
                ('session-attrs',0x800,2000,banks['vdc']),('session-vic',0x400,1000,banks['ram00']),
                ('font-during',0x3000,4096,banks['vdc'])]:
            (work/(name+'.bin')).write_bytes(read(address,count,bank))
        counters = {name:int.from_bytes(read(labels[name],size),'little') for name,size in
                    (('_rxCount',2),('_nmiCount',2),('_rxDropped',1),('_rxOverruns',1),('_kbCount',2))}
        result['serial_counters'] = counters
        assert counters['_rxCount']>=3+10*len(list(font.definitions()))
        assert counters['_nmiCount']>=counters['_rxCount']
        assert counters['_rxDropped']==counters['_rxOverruns']==0
        print('PASS: TCP/PTY output, custom glyph, input, Escape, HELP and NMI receive',flush=True)
        # Observe the outcome while Claude still owns its image. A growing
        # desktop may overwrite any freed terminal BSS on its next load.
        entry=labels['_native_video_end']
        error,checkpoint=mon._recv(mon._send(0x12,entry.to_bytes(2,'little')*2+bytes([1,1,4,0,0])))
        assert not error
        checkpoint_id=checkpoint[:4];mon.resume()
        wait(ready,'native ready before closing checkpoint',120)
        before=int.from_bytes(read(0x3d13,2),'little')
        closing_key=ord('Q') if args.host_exit else 0x8c
        mon.write_mem(0x3d12,b'\0');mon.write_mem(0x34a,bytes([closing_key]));mon.write_mem(0xd0,b'\1');mon.resume()
        deadline=time.monotonic()+90
        while True:
            error,checkpoint=mon._recv(mon._send(0x11,checkpoint_id));assert not error
            if int.from_bytes(checkpoint[13:17],'little'):break
            mon.resume();assert time.monotonic()<deadline,'native cleanup checkpoint not reached'
            time.sleep(.1)
        outcome=bytes(mon.read_mem(labels['_closeOutcome'],labels['_closeOutcome'],bank=banks['ram00']))
        (work/'close-outcome.bin').write_bytes(outcome)
        (work/'close-checkpoint.bin').write_bytes(checkpoint)
        result['close_outcome']=outcome[0]
        result['close_observation']=dict(address=labels['_closeOutcome'],cleanup_entry=entry,
            checkpoint_hex=checkpoint.hex(),lifetime='Claude allocation still live; before native_video_end')
        assert outcome==bytes([0 if args.host_exit else 2]),'client missed the shutdown acknowledgement'
        assert bytes(mon.read_mem(0x3d20,0x3d20))==b'\x20'
        assert int.from_bytes(bytes(mon.read_mem(0x3d13,0x3d14)),'little')==(before+1)&65535
        error,_=mon._recv(mon._send(0x13,checkpoint_id));assert not error
        mon.resume();result['events'].append(closing_key)
        desktop('returned-desktop',4)
        after_font = read(0x3000,4096,banks['vdc']); (work/'font-after.bin').write_bytes(after_font)
        assert after_font==original_font
        after_nmi = read(0x318,2)+read(0x3d3e,2)
        (work/'nmi-after.bin').write_bytes(after_nmi)
        assert after_nmi==original_nmi+original_gate
        assert bridge.wait(timeout=25)==0, 'host session did not close cleanly'
        result['host_exit_code'] = bridge.returncode
        key(27)
        assert read(0x400,1000,banks['ram00'])==expected_screen(40,0)
        assert read(0,2000,banks['vdc'])==expected_screen(80,0)
        heap = read(0x3800,512,banks['ram00']); (work/'final-heap.bin').write_bytes(heap)
        assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251)
        assert hashlib.sha256(disk.read_bytes()).hexdigest()==hashes['uos128.d64']
        result['passed'] = True
        print('PASS: original font/NMI restored, desktop selection retained, host reaped and all 426 pages free',flush=True)
    except BaseException as exc:
        result['error'] = repr(exc); raise
    finally:
        if mon:
            try: mon.quit_emulator()
            except (OSError,EOFError): pass
            mon.close()
        for proc in (emu,bridge):
            if proc:
                try: proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try: proc.wait(timeout=25)
                    except subprocess.TimeoutExpired: proc.kill();proc.wait()
        xv.stop();emulog.close();hostlog.close()
        (work/'report.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__': main()
