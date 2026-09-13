#!/usr/bin/env python3
"""Actual VICE 1351 motion/buttons, ROM keyboard, app returns and VIC pixels."""
import ctypes as C
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import ci_fm as ci
from vice_keyboard import Keyboard
from hwlib import lst_symbol
from native_capture import NativeCapture,wait,expected_screen,calculator_screen
from native_capture_transport import PausedViceMonitor
from native_mode_capture import NativeModeCapture
from native_running_layout import verify_running_layout
from launcher_scene import surface,console
from native_pointer_check import pixels,check_canvas
from native_editor_check import editor_screen
from native_browser_check import browser_screen,disk_records
from native_controls_check import panel_screen
from native_claude_check import landing_screen


class Mouse(Keyboard):
    def __init__(self,display):
        super().__init__(display)
        self.t.XTestFakeRelativeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_ulong]
        self.t.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        self.x.XWarpPointer.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_int,C.c_int]
        self.x.XGetGeometry.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_int),
            C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_uint)]
        self.x.XRaiseWindow.argtypes=[C.c_void_p,C.c_ulong]
        # The default console changes X stacking order. Target the narrower
        # VIC window explicitly; a VDC warp can feed unrelated host offsets.
        def width(window):
            root=C.c_ulong();x=C.c_int();y=C.c_int();w=C.c_uint();h=C.c_uint();border=C.c_uint();depth=C.c_uint()
            assert self.x.XGetGeometry(self.display,window,C.byref(root),C.byref(x),C.byref(y),C.byref(w),C.byref(h),C.byref(border),C.byref(depth))
            return w.value
        self.window=min(self.windows,key=lambda row:width(row[0]))[0]
        self.x.XRaiseWindow(self.display,self.window)
        self.x.XSetInputFocus(self.display,self.window,2,0)
        self.x.XWarpPointer(self.display,0,self.window,0,0,0,0,150,150)
        self.x.XFlush(self.display);time.sleep(.3)

    def move(self,dx,dy):
        self.t.XTestFakeRelativeMotionEvent(self.display,dx,dy,0)
        self.x.XFlush(self.display);time.sleep(.12)

    def button(self,down):
        self.t.XTestFakeButtonEvent(self.display,1,int(down),0)
        self.x.XFlush(self.display);time.sleep(.15)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--80col',dest='eighty',action='store_true');args=parser.parse_args()
    work=Path(tempfile.mkdtemp(prefix='uos-native-pointer-iec-',dir='/var/tmp/arc-scratch'))
    print('Native pointer VICE:',work,flush=True)
    shutil.copy2(__file__,work/'run.py')
    disk=work/'suite.d64';shutil.copy2(ROOT/'target/native-desktop/uos128.d64',disk)
    image=ROOT/'target/native-desktop'
    report=dict(passed=False,physical_hardware_io=False,options=vars(args),events=[],desktops=[],screens=[],
        images={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in image.iterdir() if p.suffix in ('.prg','.d64')})
    def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def symbol(name):return lst_symbol('native-desktop/desktop',name)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    xv=ci.cbm.Xvfb();emu=mon=mouse=None;log=(work/'vice.log').open('w')
    try:
        command=['x128','-default','-80col' if args.eighty else '-40col','-8',str(disk),'-drive8true','-drive8type','1541',
            '-VDC16KB','-sounddev','dummy','-jamaction','0','-warp','-controlport1device','3',
            '-controlport2device','0','-mouse','-binarymonitor','-binarymonitoraddress',f'ip4://127.0.0.1:{port}']
        report['command']=command;save()
        emu=subprocess.Popen(command,env=dict(os.environ,DISPLAY=xv.display,
            __EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL),stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+30
        while mon is None:
            assert emu.poll() is None
            try:mon=ci.Monitor(port=port)
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        mon.resume();paused=PausedViceMonitor(mon)
        def read(at,n=1):
            data=bytes(paused.read_mem(at,at+n-1));paused.resume();return data
        def ready():return read(0x3d12)==b'\1' and read(0xd0,2)==bytes(2)
        def value(name):return read(symbol(name))[0]
        def position():return int.from_bytes(read(symbol('pm_x'),2),'little'),value('pm_y')
        def header(name):return read(0x3d60,32)==(image/(name+'.prg')).read_bytes()[2:34]
        wait(lambda:read(0x1c13,6)==b'UOS128' and header('desktop') and ready(),'desktop boot',90)
        report['initial_pointer_state']=read(symbol('pm_active'),40).hex();save()
        wait(lambda:value('pm_seen')==1,'1351 attached',15)
        capture=NativeCapture(paused,work,quiet=.05,kernel_prefix='native-desktop',batch=paused.paused)
        modes=NativeModeCapture(paused,work,quiet=.05,kernel_prefix='native-desktop',batch=paused.paused)
        report.update(captures=capture.records,mode_captures=modes.records,paused_capture_batches=paused.batches)
        report['resident_boot']=verify_running_layout(capture,ROOT,'resident-boot',image_dir=image);save()
        saved_registers=read(symbol('pm_saved'),12);saved_init=read(symbol('pm_init_saved'))
        report['saved_sprite_registers']=saved_registers.hex();report['saved_init']=saved_init.hex()
        repeat=read(0xa22)
        with paused.paused('disable-accelerated-repeat'):paused.write_mem(0xa22,b'\x40')
        mouse=Mouse(xv.display);report['private_x_windows']=mouse.windows;save()
        def move_to(tx,ty):
            for _ in range(80):
                x,y=position()
                if abs(x-tx)<=2 and abs(y-ty)<=2:return x,y
                mouse.move(max(-12,min(12,(tx-x)*2)),max(-12,min(12,(ty-y)*2)))
            raise AssertionError(('host mouse failed to reach target',position(),(tx,ty)))
        def desktop(label,selected):
            wait(lambda:header('desktop') and ready() and value('gd_selected')==selected,label,90)
            xy=position();state=read(symbol('pm_active'),40);(work/(label+'-state.bin')).write_bytes(state)
            actual=b''.join(capture.capture(label+f'-surface-{offset:04x}',address=0xc000+offset,count=min(2000,9216-offset)) for offset in range(0,9216,2000))
            (work/(label+'-surface.bin')).write_bytes(actual);assert actual==surface(selected)
            vdc=capture.capture(label+'-vdc',mode=1,address=0,count=2000);assert vdc==console(80,selected)
            mode=modes.snapshot(label+'-mode');assert mode['vic_sprites']==3 and not mode['cpu_speed']&1
            time.sleep(.15)
            error,raw=mon._recv(mon._send(0x84,bytes([1,0])));mon.resume();assert not error
            (work/(label+'-canvas.bin')).write_bytes(raw)
            rectangle=check_canvas(raw,pixels(selected,*xy))
            report['desktops'].append(dict(label=label,selected=selected,position=xy,rectangle=rectangle,mode=mode));save()
            if label=='claude-returned':
                subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/'desktop.png')],check=True,capture_output=True)
            print('PASS: 64000 VIC pixels including pointer and complete VDC:',label,flush=True)
        def key(name,target):
            before=int.from_bytes(read(0x3d13,2),'little');mouse.press(name)
            wait(lambda:header(target) and ready(),name+' reaches '+target,120)
            assert int.from_bytes(read(0x3d13,2),'little')==before+1,(name,'extra or missing ROM key')
            report['events'].append(dict(key=name,target=target));save()
        def screens(label,oracle):
            for mode,columns,address in ((0,40,0x400),(1,80,0)):
                actual=capture.capture(label+('-vic' if mode==0 else '-vdc'),mode=mode,address=address,count=columns*25)
                assert actual==oracle(columns),(label,columns)
            report['screens'].append(label);save()
        desktop('attached',0)
        move_to(100,40);desktop('calculator-hover',0)
        key('Down','desktop');desktop('keyboard-selection',1)
        time.sleep(.3);assert value('gd_selected')==1
        mouse.move(4,0);desktop('mouse-resumes',0)
        mouse.button(True);move_to(100,64);mouse.button(False);desktop('cancelled-drag',1)
        for index,name in enumerate(('calc','editor','files','controls','claude')):
            move_to(100,40+24*index);desktop(name+'-hover',index)
            before=int.from_bytes(read(0x3d13,2),'little')
            mouse.button(True);assert header('desktop') and value('pm_arm')==index
            mouse.button(False);wait(lambda:header(name) and ready(),'click opens '+name,120)
            assert int.from_bytes(read(0x3d13,2),'little')==before,'mouse generated a keyboard shortcut'
            current=bytes(read(0xd000+at)[0] for at in (0,1,2,3,0x10,0x15,0x17,0x1b,0x1c,0x1d,0x27,0x28))
            assert current==saved_registers,(name,'sprite register leak',current.hex(),saved_registers.hex())
            assert read(0xa04)==saved_init,(name,'BASIC sprite hook leak')
            if name=='calc':screens(name,lambda cols:calculator_screen(cols,'0',[]))
            elif name=='editor':screens(name,lambda cols:editor_screen(cols,b'',0))
            elif name=='files':screens(name,lambda cols:browser_screen(cols,disk_records(disk.read_bytes()),files_app=True))
            elif name=='claude':screens(name,landing_screen)
            # Stock GTK symbolic mapping: host F9 is the C128 Escape key.
            key('F8' if name=='claude' else 'F9','desktop');desktop(name+'-returned',index)
            report['events'].append(dict(mouse_app=name,keyboard_events_during_click=0));save()
        with paused.paused('restore-repeat'):paused.write_mem(0xa22,repeat)
        before=int.from_bytes(read(0x3d13,2),'little');mouse.press('F9')
        wait(lambda:read(0x3d20)==b'\0' and ready(),'workspace exit',60)
        assert int.from_bytes(read(0x3d13,2),'little')==before+1
        screens('workspace',lambda cols:expected_screen(cols,0))
        report['final_mode']=modes.snapshot('workspace-mode');assert report['final_mode']['vic_sprites']==0
        heap=capture.capture('final-heap',address=0x3800,count=0x600)
        assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251)
        assert all(heap[0x400+i*8]==0 for i in range(32))
        report['resident_return']=verify_running_layout(capture,ROOT,'resident-return',image_dir=image)
        report['passed']=True;save()
    except BaseException as error:report['error']=repr(error);raise
    finally:
        if mouse is not None:
            mouse.button(False);mouse.close()
        if mon is not None:
            try:mon.quit_emulator()
            except (OSError,EOFError):pass
            mon.close()
        if emu is not None:
            try:emu.wait(timeout=2)
            except subprocess.TimeoutExpired:emu.terminate();emu.wait(timeout=5)
        xv.stop();log.close()
        report['all_host_processes_terminal']=emu is None or emu.poll() is not None
        report['system_disk_unchanged']=disk.read_bytes()==(image/'uos128.d64').read_bytes()
        save()


if __name__=='__main__':main()
