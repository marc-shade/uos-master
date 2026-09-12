#!/usr/bin/env python3
"""Cold boot the graphical dispatcher and operate actual native apps in VICE."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
import ci_fm as ci
from native_capture import expected_screen, calculator_screen, wait
from native_capture import NativeCapture
from native_running_layout import verify_running_layout
from native_editor_check import editor_screen
from native_browser_check import disk_records, browser_screen
from launcher_scene import surface, console

parser = argparse.ArgumentParser()
parser.add_argument('--missing-calc', action='store_true')
parser.add_argument('--80col', dest='eighty', action='store_true')
parser.add_argument('--desktop-boot', action='store_true')
parser.add_argument('--missing-desktop', action='store_true')
parser.add_argument('--cpu-observation', action='store_true')
parser.add_argument('--running-layout', action='store_true')
parser.add_argument('--hardware-sequence', action='store_true')
parser.add_argument('--transport-sequence', action='store_true')
parser.add_argument('--nested-irq', action='store_true')
parser.add_argument('--input-during-capture', action='store_true')
args = parser.parse_args()
assert not args.missing_desktop or (args.desktop_boot and not args.missing_calc)
work = Path(tempfile.mkdtemp(prefix='uos-native-desktop-iec-', dir='/var/tmp/arc-scratch'))
print('Native desktop evidence:', work, flush=True)
disk = work/'desktop.d64'
shutil.copyfile(ROOT/'target/native-desktop'/('uos128.d64' if args.desktop_boot else 'workspace.d64'), disk)
if args.missing_calc:
    subprocess.run(['c1541','-attach',str(disk),'-delete','calc'],check=True,capture_output=True)
if args.missing_desktop:
    subprocess.run(['c1541','-attach',str(disk),'-delete','browse'],check=True,capture_output=True)
for name in ('desktop.prg','desktop.lst','desktop.sym','files.prg','files.lst'):
    shutil.copyfile(ROOT/'target/native-desktop'/name,work/name)
shutil.copyfile(__file__,work/'run.py')
shutil.copyfile(ROOT/'launcher_scene.py',work/'launcher_scene.py')
sha = lambda data: hashlib.sha256(data).hexdigest()
record = dict(passed=False, physical_hardware_io=False, options=vars(args),
              disk_sha256=sha(disk.read_bytes()), events=[], desktops=[], screens=[], observations=[])
syms = {m[1]:int(m[2],16) for m in re.finditer(r'^(\w+)\s*=\s*\$([0-9a-f]+)',(ROOT/'target/native-desktop/desktop.sym').read_text(),re.M)}
kernel_prefix='native-desktop' if args.desktop_boot else 'native'
kernel_dir=ROOT/'target'/kernel_prefix
for name in ('uos128.prg','uos128.sym','uos128.lst'):
    shutil.copyfile(kernel_dir/name,work/name)
record['kernel_sha256']=sha((kernel_dir/'uos128.prg').read_bytes())
ksyms = {m[1]:int(m[2],16) for m in re.finditer(r'^(\w+)\s*=\s*\$([0-9a-f]+)',(kernel_dir/'uos128.sym').read_text(),re.M)}
records = disk_records(disk.read_bytes())
with socket.socket() as sock:
    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
xv=ci.cbm.Xvfb();process=None;mon=None
log=(work/'vice.log').open('w')
try:
    command=['x128','-default','-80col' if args.eighty else '-40col','-8',str(disk),
             '-drive8true','-drive8type','1541','-VDC16KB','-sounddev','dummy','-jamaction','0',
             '-warp','-binarymonitor','-binarymonitoraddress',f'ip4://127.0.0.1:{port}']
    record['command']=command
    process=subprocess.Popen(command,env=dict(os.environ,DISPLAY=xv.display,
        __EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL),stdout=log,stderr=subprocess.STDOUT)
    deadline=time.monotonic()+30
    while mon is None:
        assert process.poll() is None,'x128 exited'
        try:mon=ci.Monitor(port=port)
        except OSError:
            if time.monotonic()>deadline:raise
            time.sleep(.1)
    banks=mon.banks();record['banks']=banks;mon.resume()
    def read(at,count=1,bank=0):
        data=bytes(mon.read_mem(at,at+count-1,bank=bank));mon.resume();return data
    def ready():return read(0x3d12)==b'\1' and read(0xd0,2)==bytes(2)
    def key(value):
        wait(ready,'native input readiness',120)
        before=int.from_bytes(read(0x3d13,2),'little');start=time.monotonic()
        mon.write_mem(0x3d12,b'\0');mon.write_mem(0x34a,bytes([value]));mon.write_mem(0xd0,b'\1');mon.resume()
        wait(lambda:ready() and int.from_bytes(read(0x3d13,2),'little')==(before+1)&65535,
             f'desktop/app key {value:02x}',180)
        record['events'].append(dict(key=value,elapsed_seconds=round(time.monotonic()-start,3)))
    def observation(label):
        data={}
        for name,at,count,bank in [('app',0x3d20,16,0),('heap',0x3800,0x600,banks['ram00']),
            ('vic',0xd000,64,0),('port',0,2,0),('text',0xd7,2,0),('jiffy',0xa0,3,0),
            ('display_tag',ksyms['v_tag'],1,0),('keys',0x3d12,4,0)]:
            raw=read(at,count,bank);(work/f'{label}-{name}.bin').write_bytes(raw);data[name]=raw.hex()
        record['observations'].append(dict(label=label,**data))
        return data
    def screens(label,oracle):
        for columns,at,bank in ((40,0x400,banks['ram00']),(80,0,banks['vdc'])):
            data=read(at,columns*25,bank);(work/f'{label}-{columns}.bin').write_bytes(data)
            assert data==oracle(columns),(label,columns,'complete screen mismatch')
        record['screens'].append(label)
        print('PASS: both text screens:',label,flush=True)
    def desktop(label,selected=0,error=0,fallback=False):
        state=read(syms['gd_selected'],8)
        assert state[:4]==bytes([selected,int(not fallback),2 if fallback else 0,error]),(label,state.hex())
        assert read(0x3d2f)==bytes([selected]),(label,'saved desktop selection')
        text=read(0,2000,banks['vdc']);(work/f'{label}-80.bin').write_bytes(text)
        assert text==console(80,selected,error,fallback),(label,'VDC desktop')
        obs=observation(label)
        if fallback:
            data=read(0x400,1000,banks['ram00']);(work/f'{label}-40.bin').write_bytes(data)
            assert data==console(40,selected,error,True)
            assert obs['display_tag']=='00' and obs['port']=='2f73'
            record['desktops'].append(dict(label=label,selected=selected,error=error,fallback=True))
            print('PASS: desktop text fallback:',label,flush=True)
            return
        expected=surface(selected,error)
        actual=read(0xc000,9216,banks['ram00']);(work/f'{label}-surface.bin').write_bytes(actual)
        assert actual==expected,(label,'complete surface mismatch')
        assert obs['port']=='2f75' and obs['display_tag']!='00'
        # Both bitmap bytes and the emulator's actual palette-index pixels agree.
        expected_rows=[]
        for y in range(200):
            row=bytearray()
            for x in range(320):
                color=expected[8192+y//8*40+x//8]
                ink=expected[y//8*320+x//8*8+y%8]&(128>>(x%8))
                row.append(color>>4 if ink else color&15)
            expected_rows.append(bytes(row))
        # Let a complete displayed frame follow the foreground's ready flag.
        time.sleep(.15)
        err,raw=mon._recv(mon._send(0x84,bytes([1,0])));mon.resume();assert not err
        (work/f'{label}-display-get.bin').write_bytes(raw)
        fields,=struct.unpack_from('<I',raw)
        width,height,xoff,yoff,innerw,innerh,bpp=struct.unpack_from('<6HB',raw,4)
        length,=struct.unpack_from('<I',raw,4+fields);pixels=raw[8+fields:]
        assert fields>=13 and bpp==8 and length==width*height and length-len(pixels) in (0,4)
        matches=[]
        for y in range(height-199):
            row=pixels[y*width:(y+1)*width];x=row.find(expected_rows[0])
            while x>=0:
                if all(pixels[(y+dy)*width+x:(y+dy)*width+x+320]==wanted for dy,wanted in enumerate(expected_rows)):
                    matches.append([x,y,320,200])
                x=row.find(expected_rows[0],x+1)
        assert len(matches)==1,(label,'rendered bitmap mismatch',matches)
        record['desktops'].append(dict(label=label,selected=selected,error=error,fallback=False,
            bytes=9216,pixels=64000,rectangle=matches[0],missing_canvas_tail_bytes=length-len(pixels)))
        print('PASS: desktop surface, pixels and VDC controls:',label,flush=True)
    wait(lambda:read(0x1c13,6)==b'UOS128' and ready(),'native workspace boot',60)
    if args.input_during_capture:
        assert args.desktop_boot
        from native_input_capture_vice import run_input_capture
        desktop('before-input-control')
        run_input_capture(mon,work,record,key)
        desktop('after-input-control',selected=2)
        record['passed']=True
        sys.exit(0)
    if args.nested_irq:
        assert args.desktop_boot and not args.missing_calc and not args.missing_desktop
        from native_nested_irq_vice import run_nested_irq
        desktop('before-nested-irqs')
        run_nested_irq(mon,work,record,syms['gd_loop'])
        desktop('after-nested-irqs')
        record['passed']=True
        sys.exit(0)
    if args.hardware_sequence or args.transport_sequence:
        assert args.desktop_boot and not args.missing_calc and not args.missing_desktop
        from hw_native_desktop_check import run_native_workflow
        from native_capture_transport import PausedViceMonitor
        sequence_mon=PausedViceMonitor(mon)
        if args.transport_sequence:
            from native_transport_workflow import run_transport_workflow as run_native_workflow
        capture=NativeCapture(sequence_mon,work,quiet=.1,kernel_prefix=kernel_prefix,
                              batch=sequence_mon.paused)
        sub=dict(physical_hardware_io=False,events=[],desktops=[],screens=[],captures=capture.records,
                 paused_capture_batches=sequence_mon.batches)
        record['hardware_sequence']=sub
        def save_sequence():
            (work/'hardware-sequence.json').write_text(json.dumps(sub,indent=2)+'\n')
        run_native_workflow(sequence_mon,capture,work,disk,sub,save_sequence,key_quiet=.1,key_poll=.1,kernel_prefix=kernel_prefix)
        assert sub['native_checks_passed']
        observation('final')
        record['passed']=True
        print(f'PASS: shared {"focused capture" if args.transport_sequence else "hardware native"} sequence under VICE; no physical machine I/O',flush=True)
        sys.exit(0)
    if args.missing_desktop:
        screens('missing-desktop-workspace',lambda columns:expected_screen(columns,0,result=0x11))
        key(ord('C'));screens('fallback-calculator',lambda columns:calculator_screen(columns,'0',[]))
        key(27);screens('fallback-calculator-return',lambda columns:expected_screen(columns,0))
        final=observation('final')
        assert final['display_tag']=='00' and final['port']=='2f73'
        assert sha(disk.read_bytes())==record['disk_sha256']
        record['passed']=True
        print('PASS: missing desktop boots usable workspace and calculator',flush=True)
        sys.exit(0)
    if not args.desktop_boot:
        screens('workspace-boot',lambda columns:expected_screen(columns,0))
        key(ord('B'))
    if args.cpu_observation or args.running_layout:
        capture=NativeCapture(mon,work,quiet=.1,kernel_prefix=kernel_prefix)
        record['captures']=capture.records
    desktop('desktop-initial')
    if args.running_layout:
        record['resident_boot']=verify_running_layout(capture,ROOT,'resident-boot',image_dir=kernel_dir)
    if args.cpu_observation:
        before=observation('before-cpu-observation')
        observed=b''.join(capture.capture(f'cpu-surface-{offset:04x}',address=0xc000+offset,
                        count=min(2000,9216-offset)) for offset in range(0,9216,2000))
        (work/'cpu-surface.bin').write_bytes(observed)
        assert observed==surface()
        assert capture.capture('cpu-vdc',mode=1,address=0,count=2000)==console(80)
        after=observation('after-cpu-observation')
        for field in ('app','heap','port','text','display_tag','keys'):
            assert before[field]==after[field],('observer changed foreground state',field)
        for address in (0x11,0x15,0x16,0x18,0x1a):
            mask=0x7f if address==0x11 else 255
            assert bytes.fromhex(before['vic'])[address]&mask==bytes.fromhex(after['vic'])[address]&mask
        assert before['jiffy']!=after['jiffy']
        desktop('desktop-after-cpu-observation')
        key(27);screens('workspace-returned',lambda columns:expected_screen(columns,0))
        if args.running_layout:
            record['resident_return']=verify_running_layout(capture,ROOT,'resident-return',image_dir=kernel_dir)
        final=observation('final')
        assert final['display_tag']=='00' and final['port']=='2f73'
        record['passed']=True
        print('PASS: full CPU-captured bitmap/VDC under graphics; observer and app cleanup restore all state',flush=True)
        sys.exit(0)
    subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/'desktop-initial.png')],check=True,capture_output=True)
    before=read(0xa0,3);time.sleep(.2);assert read(0xa0,3)!=before
    if args.missing_calc:
        key(ord('C'));desktop('missing-app-recovered',error=0x11)
        key(ord('F'));screens('files-after-missing',lambda columns:browser_screen(columns,records))
        key(27);desktop('desktop-after-files',2)
    else:
        for index,(value,selected) in enumerate([(0x11,1),(9,2),(0x1d,0),(0x9d,2),(0x13,0)]):
            key(value);desktop(f'selection-{index}',selected)
        key(13)
        assert read(ksyms['v_tag'])==b'\0' and read(0x38c0,36)==bytes(36)
        screens('calculator-new',lambda columns:calculator_screen(columns,'0',[]))
        for value in b'12+30=':key(value)
        screens('calculator-result',lambda columns:calculator_screen(columns,'42',['42']))
        key(27);desktop('desktop-after-calculator')
        key(ord('E'));screens('editor-new',lambda columns:editor_screen(columns,b'',0))
        document=b'Native desktop'
        for value in document:key(value)
        screens('editor-typed',lambda columns:editor_screen(columns,document,len(document),dirty=True))
        key(27);screens('editor-discard-prompt',lambda columns:editor_screen(columns,document,len(document),dirty=True,mode=5))
        key(ord('N'));screens('editor-kept',lambda columns:editor_screen(columns,document,len(document),dirty=True))
        key(27);key(ord('Y'));desktop('desktop-after-editor',1)
        key(ord('F'));screens('files',lambda columns:browser_screen(columns,records))
        key(27);desktop('desktop-after-files',2)
    key(27);screens('workspace-returned',lambda columns:expected_screen(columns,0))
    key(ord('B'));desktop('desktop-after-workspace',2);key(27)
    if not args.missing_calc:
        key(ord('A'));handle=read(0x3d04,4)
        occupied=read(0xc000,9216,banks['ram00'])
        key(ord('B'));desktop('occupied-surface-fallback',2,fallback=True)
        assert read(0xc000,9216,banks['ram00'])==occupied
        key(9);desktop('fallback-selection',0,fallback=True)
        key(27);screens('workspace-owner-retained',lambda columns:expected_screen(columns,0,(143,251),31,handle))
        key(ord('F'));screens('workspace-all-free',lambda columns:expected_screen(columns,0))
        key(ord('B'));desktop('desktop-after-obstacle-release');key(27)
    if args.running_layout:
        record['resident_return']=verify_running_layout(capture,ROOT,'resident-return',image_dir=kernel_dir)
    final=observation('final')
    assert final['display_tag']=='00' and final['port']=='2f73'
    assert read(0x3d20,1)==b'\0' and read(0x3d23,1)==b'\0'
    assert sha(disk.read_bytes())==record['disk_sha256']
    record['passed']=True
except Exception as error:
    record['error']=str(error)
    raise
finally:
    if mon:
        try:mon.quit_emulator()
        except (EOFError,OSError):pass
        mon.close()
    if process:
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
    xv.stop();log.close()
    (work/'report.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS: interactive native desktop dispatcher workflow',flush=True)
