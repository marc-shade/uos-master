#!/usr/bin/env python3
"""Actual VICE 1351 motion/buttons, ROM keyboard, app returns and VIC pixels."""
import ctypes as C
from contextlib import contextmanager
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
from native_pointer_check import pixels,surface_pixels,check_canvas
from native_calc_scene import surface as calc_surface, BUTTONS
from native_files_check import exact_d64_files
from native_editor_check import editor_screen
from native_browser_check import browser_screen,disk_records
from native_controls_check import panel_screen
from native_claude_check import landing_screen
from paint_scene import surface as paint_surface,console as paint_console,RECTS as PAINT_RECTS,MESSAGES as PAINT_MESSAGES
from native_paint_format import encode as paint_encode


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
    parser=argparse.ArgumentParser();parser.add_argument('--80col',dest='eighty',action='store_true')
    parser.add_argument('--paint-only',action='store_true');args=parser.parse_args()
    work=Path(tempfile.mkdtemp(prefix='uos-native-pointer-iec-',dir='/var/tmp/arc-scratch'))
    print('Native pointer VICE:',work,flush=True)
    shutil.copy2(__file__,work/'run.py')
    disk=work/'suite.d64';shutil.copy2(ROOT/'target/native-desktop/uos128.d64',disk)
    image=ROOT/'target/native-desktop'
    report=dict(passed=False,physical_hardware_io=False,options=vars(args),events=[],desktops=[],screens=[],calculator_frames=[],paint_frames=[],
        images={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in image.iterdir() if p.suffix in ('.prg','.d64')})
    def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    pointer_app='desktop'
    def symbol(name):return lst_symbol('native-desktop/'+pointer_app,name)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    xv=ci.cbm.Xvfb();emu=mon=mouse=None;log=(work/'vice.log').open('w')
    report['private_x_display']=xv.display
    try:
        command=['x128','-default','-80col' if args.eighty else '-40col','-8',str(disk),'-drive8true','-drive8type','1541',
            '-VDC16KB','-sounddev','dummy','-soundwarpmode','1','-jamaction','0','-warp','-controlport1device','3',
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
        @contextmanager
        def stable_batch(label):
            # N_READY is briefly zero during a foreground pointer sample.
            # Admit an idle snapshot while already paused; never replace a
            # first readback after the observer has touched its scratch.
            if not label.endswith(('-before','-restore')):
                with paused.paused(label):yield
                return
            deadline=time.monotonic()+30;deferred=0
            while True:
                with paused.paused(label):
                    idle=bytes(paused.read_mem(0x3d11,0x3d12))==b'\0\1' and bytes(paused.read_mem(0xd0,0xd0))==b'\0'
                    if idle:
                        report.setdefault('capture_admissions',[]).append(dict(label=label,deferred=deferred))
                        yield
                        return
                deferred+=1
                assert time.monotonic()<deadline,('idle capture admission',label)
                time.sleep(.01)
        wait(lambda:read(0x1c13,6)==b'UOS128' and header('desktop') and ready(),'desktop boot',90)
        report['initial_pointer_state']=read(symbol('pm_active'),40).hex();save()
        capture=NativeCapture(paused,work,quiet=.05,kernel_prefix='native-desktop',batch=stable_batch)
        modes=NativeModeCapture(paused,work,quiet=.05,kernel_prefix='native-desktop',batch=stable_batch)
        report.update(captures=capture.records,mode_captures=modes.records,paused_capture_batches=paused.batches)
        report['resident_boot']=verify_running_layout(capture,ROOT,'resident-boot',image_dir=image);save()
        saved_registers=read(symbol('pm_saved'),12);saved_init=read(symbol('pm_init_saved'))
        saved_keys=capture.capture('keys-before',address=0x1000,count=256)
        saved_callback=read(0x033c,2);report['saved_keycheck']=saved_callback.hex()
        report['saved_sprite_registers']=saved_registers.hex();report['saved_init']=saved_init.hex()
        repeat=read(0xa22)
        with paused.paused('disable-accelerated-repeat'):paused.write_mem(0xa22,b'\x40')
        mouse=Mouse(xv.display);report['private_x_windows']=mouse.windows;save()
        assert len(mouse.windows)==2,'the private X display must contain only this C128 pair'
        wait(lambda:value('pm_seen')==1,'1351 attached',15)
        time.sleep(1)
        def move_to(tx,ty):
            for _ in range(80):
                x,y=position()
                if abs(x-tx)<=2 and abs(y-ty)<=2:return x,y
                mouse.move(max(-12,min(12,(tx-x)*2)),max(-12,min(12,(ty-y)*2)))
            raise AssertionError(('host mouse failed to reach target',position(),(tx,ty)))
        def desktop(label,selected):
            wait(lambda:header('desktop') and ready() and value('gd_selected')==selected,label,90)
            actual=b''.join(capture.capture(label+f'-surface-{offset:04x}',address=0xc000+offset,count=min(2000,9216-offset)) for offset in range(0,9216,2000))
            (work/(label+'-surface.bin')).write_bytes(actual);assert actual==surface(selected)
            vdc=capture.capture(label+'-vdc',mode=1,address=0,count=2000);assert vdc==console(80,selected)
            mode=modes.snapshot(label+'-mode');assert mode['vic_sprites']==3 and not mode['cpu_speed']&1
            # Host mouse deltas may still be draining when the large RAM
            # capture begins. Pair the canvas with settled current coordinates.
            for _ in range(20):
                xy=position();time.sleep(.2)
                if position()==xy:break
            else:raise AssertionError('pointer never settled for rendered frame')
            state=read(symbol('pm_active'),40);(work/(label+'-state.bin')).write_bytes(state)
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
        def calculator_view(label,display,history,selected,*,dialog=False,name='',cursor=0,status=0):
            wait(lambda:header('calc') and ready(),label,60)
            expected=dict(display=display,history=history,selected=selected,dialog=dialog,name=name,cursor=cursor,status=status)
            wanted=calc_surface(**expected)
            actual=b''.join(capture.capture(label+f'-surface-{offset:04x}',address=0xc000+offset,count=min(2000,9216-offset)) for offset in range(0,9216,2000))
            (work/(label+'-surface.bin')).write_bytes(actual);assert actual==wanted,(label,'calculator bitmap')
            messages=[None,'HISTORY SAVED AND VERIFIED','DISK ERROR; FILE MAY BE PARTIAL','FILE EXISTS - CHOOSE ANOTHER NAME']
            vdc=capture.capture(label+'-vdc',mode=1,address=0,count=2000)
            assert vdc==calculator_screen(80,display,history,save_prompt=name if dialog else None,
                save_status=None if dialog else messages[status],save_caret=cursor,save_view=0),(label,'calculator VDC')
            for _ in range(20):
                xy=position();time.sleep(.2)
                if position()==xy:break
            else:raise AssertionError('calculator pointer did not settle')
            mode=modes.snapshot(label+'-mode');assert mode['vic_sprites']==3
            error,raw=mon._recv(mon._send(0x84,bytes([1,0])));mon.resume();assert not error
            (work/(label+'-canvas.bin')).write_bytes(raw)
            rectangle=check_canvas(raw,surface_pixels(wanted,*xy))
            report['calculator_frames'].append(dict(label=label,expected=expected,position=xy,rectangle=rectangle,mode=mode));save()
            subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/(label+'.png'))],check=True,capture_output=True)
            print('PASS: graphical calculator bitmap, VDC and 64000 pointer pixels:',label,flush=True)
        def calc_click(index):
            (x0,y0,x1,y1),_,_=BUTTONS[index]
            move_to((x0+x1)//2,(y0+y1)//2)
            before=int.from_bytes(read(0x3d13,2),'little')
            mouse.button(True);assert value('pm_arm')==index
            mouse.button(False)
            wait(ready,'calculator click ready',60)
            assert int.from_bytes(read(0x3d13,2),'little')==before
            report['events'].append(dict(calculator_button=index,keyboard_events_during_click=0));save()
        def paint_view(label,document,*,dirty,mode=0,status=0):
            wait(lambda:header('paint') and ready(),label,120)
            assert value('pd_dirty')==dirty and value('pa_mode')==mode and value('pa_status')==status
            name=read(symbol('pf_name'),value('pf_length')) if value('pf_length') else b''
            expected=dict(view_x=value('pa_view_x'),view_y=value('pa_view_y'),focus=value('ui_selected'),
                x=int.from_bytes(read(symbol('pd_x'),2),'little'),y=value('pd_y'),pen=value('pd_pen'),color=value('pd_color'),
                dirty=bool(dirty),mode=mode,action=value('pa_action'),name=name.decode('latin1'),caret=value('pa_field_caret'),
                field_view=value('pa_field_view'),device=value('pf_device'),fmt=value('pf_format'))
            wanted=paint_surface(document,message=PAINT_MESSAGES[status],**dict(expected,name=name))
            tag=value('pd_handles');allocation=read(0x3c00+(tag-1)*8,8)
            assert allocation[:2]==bytes([32,1]) and allocation[3]==36
            page=allocation[2]
            observed=b''.join(capture.capture(label+f'-document-{offset:04x}',bank=1,address=page*256+offset,
                count=min(2000,9216-offset)) for offset in range(0,9216,2000))
            assert observed==document,(label,'banked document');(work/(label+'-document.bin')).write_bytes(observed)
            actual=b''.join(capture.capture(label+f'-surface-{offset:04x}',address=0xc000+offset,
                count=min(2000,9216-offset)) for offset in range(0,9216,2000))
            (work/(label+'-surface.bin')).write_bytes(actual);assert actual==wanted,(label,'Paint bitmap')
            vdc=capture.capture(label+'-vdc',mode=1,address=0,count=2000)
            state={k:v for k,v in expected.items() if k not in ('view_x','view_y','field_view')}
            state['name']=name
            field_view=read(symbol('pa_field')+6)[0]
            assert vdc==paint_console(80,bitmap=True,message=status,view=field_view,**state),(label,'Paint VDC')
            for _ in range(20):
                xy=position();time.sleep(.2)
                if position()==xy:break
            else:raise AssertionError('Paint pointer did not settle')
            display=modes.snapshot(label+'-mode');assert display['vic_sprites']==3
            error,raw=mon._recv(mon._send(0x84,bytes([1,0])));mon.resume();assert not error
            (work/(label+'-canvas.bin')).write_bytes(raw)
            rectangle=check_canvas(raw,surface_pixels(wanted,*xy))
            report['paint_frames'].append(dict(label=label,expected=expected,status=status,console_field_view=field_view,
                document_sha256=hashlib.sha256(document).hexdigest(),position=xy,rectangle=rectangle,mode=display));save()
            subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/(label+'.png'))],check=True,capture_output=True)
            print('PASS: complete Paint document, bitmap, VDC and 64000 pointer pixels:',label,flush=True)
        def paint_click(index):
            x0,y0,x1,y1=PAINT_RECTS[index];move_to((x0+x1)//2,(y0+y1)//2)
            before=int.from_bytes(read(0x3d13,2),'little')
            state=dict(before_keys=before,before_keyboard=read(0xd0,5).hex(),key_table=read(0x1000,20).hex())
            mouse.button(True);wait(lambda:value('pm_arm')==index,'Paint button armed',30)
            mouse.button(False);wait(ready,'Paint click ready',120)
            after=int.from_bytes(read(0x3d13,2),'little')
            state.update(after_keys=after,after_keyboard=read(0xd0,5).hex(),last_key=read(0x3d15).hex(),
                mode=value('pa_mode'),name_length=value('pf_length'),name=read(symbol('pf_name'),16).hex())
            report['events'].append(dict(paint_button=index,keyboard_events_during_click=after-before,input_state=state));save()
            assert after==before,state
        # Drain the window grab/warp through real relative input before the
        # first long capture. End in the margin, outside every app button.
        move_to(310,180)
        time.sleep(.5)
        key('Home','desktop')
        desktop('attached',0)
        move_to(100,40);desktop('calculator-hover',0)
        key('Down','desktop');desktop('keyboard-selection',1)
        time.sleep(.3);assert value('gd_selected')==1
        mouse.move(4,0);desktop('mouse-resumes',0)
        mouse.button(True);move_to(100,64);mouse.button(False);desktop('cancelled-drag',1)
        paint_document=bytearray(bytes(8192)+b'\x10'*1024)
        for index,name in enumerate(('calc','editor','files','controls','claude','paint')):
            if args.paint_only and name!='paint':continue
            move_to(100,40+24*index);desktop(name+'-hover',index)
            before=int.from_bytes(read(0x3d13,2),'little')
            mouse.button(True);assert header('desktop') and value('pm_arm')==index
            mouse.button(False);wait(lambda:header(name) and ready(),'click opens '+name,120)
            assert int.from_bytes(read(0x3d13,2),'little')==before,'mouse generated a keyboard shortcut'
            if name=='calc':
                pointer_app='calc'
                assert read(symbol('pm_saved'),12)==saved_registers and read(symbol('pm_init_saved'))==saved_init
                wait(lambda:value('pm_seen')==1,'calculator 1351 attached',15)
                move_to(112,152)
                wait(lambda:value('ui_selected')==14,'calculator equals focus',15)
                calculator_view('calculator-open','0',[],14)
                for button in (8,9,15,10,13,14):calc_click(button)
                calculator_view('calculator-result','42',['42'],14)
                calc_click(17)
                for char in 'guihist':key(char,'calc')
                calculator_view('calculator-save','42',['42'],21,dialog=True,name='GUIHIST',cursor=7)
                calc_click(21)
                wait(lambda:value('save_status')==1,'history saved and verified',60)
                calculator_view('calculator-saved','42',['42'],17,status=1)
                calc_click(17)
                for char in 'cancel':key(char,'calc')
                calc_click(22)
                calculator_view('calculator-cancelled','42',['42'],17)
            elif name=='paint':
                pointer_app='paint'
                assert read(0x033c,2)==symbol('pk_entry').to_bytes(2,'little')
                assert read(symbol('pm_saved'),12)==saved_registers and read(symbol('pm_init_saved'))==saved_init
                wait(lambda:value('pm_seen')==1,'Paint 1351 attached',15)
                move_to(310,180);paint_view('paint-open',paint_document,dirty=0)
                versions=[]
                for tx,ty,color in ((48,56,1),(88,80,2)):
                    if color!=1:paint_click(7+color)
                    move_to(tx,ty);wait(ready,'Paint brush move',60);time.sleep(.3)
                    x,y=position();assert abs(x-tx)<=2 and abs(y-ty)<=2
                    versions.append(bytes(paint_document));xx,yy=x-8,y-32
                    paint_document[yy//8*320+xx//8*8+yy%8]|=128>>(xx%8)
                    paint_document[8192+yy//8*40+xx//8]=color*16
                    before=int.from_bytes(read(0x3d13,2),'little')
                    mouse.button(True);wait(lambda:value('pd_dirty')==1 and ready(),'Paint draws point',60)
                    mouse.button(False);wait(ready,'Paint stroke released',60)
                    after=int.from_bytes(read(0x3d13,2),'little')
                    report['events'].append(dict(paint_point=[xx,yy],color=color,keyboard_events_during_click=after-before,
                        before_keys=before,after_keys=after,last_key=read(0x3d15).hex()));save()
                    assert after==before,report['events'][-1]
                paint_view('paint-drawing',paint_document,dirty=1)
                paint_click(2);paint_view('paint-undo',versions[-1],dirty=1)
                paint_click(2);paint_view('paint-redo',paint_document,dirty=1)
                paint_click(4)
                for char in 'paintpic':key(char,'paint')
                paint_view('paint-save-dialog',paint_document,dirty=1,mode=2)
                paint_click(24);wait(lambda:value('pa_status')==1,'Paint save verified',120)
                paint_view('paint-saved',paint_document,dirty=0,status=1)
                paint_click(4);paint_click(24);assert value('pa_status')==4
                paint_view('paint-collision',paint_document,dirty=0,status=4)
                paint_click(4)
                for char in 'cancel':key(char,'paint')
                paint_click(25);paint_view('paint-cancelled',paint_document,dirty=0)
                paint_click(3);assert value('pd_dirty')==1
                paint_click(5);paint_view('paint-open-confirm',bytes(8192)+b'\x10'*1024,dirty=1,mode=1)
                paint_click(24);assert value('pa_picker_active')==1 and not value('pa_bitmap')
                entries=disk_records(disk.read_bytes())
                for entry in entries:entry['app']=False
                chosen=next(i for i,entry in enumerate(entries) if entry['name'].rstrip(b'\xa0')==b'PAINTPIC')
                key('Home','paint')
                for _ in range(chosen):key('Down','paint')
                screens('paint-file-picker',lambda cols:browser_screen(cols,entries,selected=chosen,picker=True))
                key('Return','paint');paint_view('paint-loaded',paint_document,dirty=0,status=2)
                report['paint_filtered_line_samples']=int.from_bytes(read(symbol('pk_rejects'),2),'little');save()
            else:
                current=bytes(read(0xd000+at)[0] for at in (0,1,2,3,0x10,0x15,0x17,0x1b,0x1c,0x1d,0x27,0x28))
                assert current==saved_registers,(name,'sprite register leak',current.hex(),saved_registers.hex())
                assert read(0xa04)==saved_init,(name,'BASIC sprite hook leak')
            if name=='editor' :screens(name,lambda cols:editor_screen(cols,b'',0))
            elif name=='files':screens(name,lambda cols:browser_screen(cols,disk_records(disk.read_bytes()),files_app=True))
            elif name=='claude':screens(name,landing_screen)
            # Stock GTK symbolic mapping: host F9 is the C128 Escape key.
            key('F8' if name=='claude' else 'F9','desktop')
            pointer_app='desktop'
            desktop(name+'-returned',index)
            assert capture.capture(name+'-keys-restored',address=0x1000,count=256)==saved_keys
            assert read(0x033c,2)==saved_callback
            report['events'].append(dict(mouse_app=name,keyboard_events_during_click=0));save()
        before=int.from_bytes(read(0x3d13,2),'little');mouse.press('F9')
        wait(lambda:read(0x3d20)==b'\0' and ready(),'workspace exit',60)
        assert int.from_bytes(read(0x3d13,2),'little')==before+1
        with paused.paused('restore-repeat'):paused.write_mem(0xa22,repeat)
        assert read(0xa22)==repeat
        screens('workspace',lambda cols:expected_screen(cols,0))
        report['final_mode']=modes.snapshot('workspace-mode');assert report['final_mode']['vic_sprites']==0
        heap=capture.capture('final-page-table',address=0x3800,count=0x200)
        records=capture.capture('final-records',address=0x3c00,count=0x100)
        assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251)
        assert all(records[i*8]==0 for i in range(32))
        report['resident_return']=verify_running_layout(capture,ROOT,'resident-return',image_dir=image)
        # Only the explicitly created history file may differ on this private disk.
        contents=exact_d64_files(disk.read_bytes())
        before_files=exact_d64_files((image/'uos128.d64').read_bytes())
        if not args.paint_only:assert contents.pop(b'GUIHIST')==(1,b'42\r')
        assert contents.pop(b'PAINTPIC')==(1,paint_encode(paint_document))
        assert contents==before_files
        report['paint_file_sha256']=hashlib.sha256(paint_encode(paint_document)).hexdigest()
        if not args.paint_only:report['calculator_history_export_hex']=b'42\r'.hex()
        report['system_disk_files_preserved']=True
        report['passed']=True;save()
    except BaseException as error:
        report['error']=repr(error)
        if mon is not None:
            try:report['failure_state']={hex(at):read(at,count).hex() for at,count in ((0xd0,8),(0xa20,16),(0x3d12,16),(0x3d60,32),(0xdc00,4),(0xd02f,1),(0xd419,2))}
            except BaseException as diagnostic:report['diagnostic_error']=repr(diagnostic)
        raise
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
