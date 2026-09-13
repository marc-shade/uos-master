#!/usr/bin/env python3
"""Actual VICE 1351 motion/buttons, ROM keyboard, app returns and VIC pixels."""
import ctypes as C
from contextlib import contextmanager
import argparse
import hashlib
import json
import os
import re
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
from native_editor_scene import surface as editor_surface,console as editor_console,RECTS as EDITOR_RECTS
from native_picker_scene import surface as picker_surface,console as picker_console,RECTS as PICKER_RECTS
from native_picker_check import picker_symbol
from native_browser_check import browser_screen,disk_records
from native_controls_check import panel_screen,absent_body
from native_controls_scene import surface as controls_surface,RECTS as CONTROLS_RECTS
from native_files_scene import (browser_surface as files_surface,browser_console as files_console,
    copy_surface as files_copy_surface,copy_console as files_copy_console,RECTS as FILES_RECTS)
from native_claude_check import landing_screen,capture_frame as claude_capture
from native_claude_scene import RECTS as CLAUDE_RECTS
from paint_scene import surface as paint_surface,console as paint_console,RECTS as PAINT_RECTS,MESSAGES as PAINT_MESSAGES
from native_paint_format import encode as paint_encode
from native_vdc_check import capture_frame as vdc_capture,capture_snapshot as vdc_snapshot


class Mouse(Keyboard):
    def __init__(self,display,*,vdc_window=False):
        super().__init__(display)
        self.t.XTestFakeRelativeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_ulong]
        self.t.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        self.x.XWarpPointer.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_int,C.c_int]
        self.x.XGetGeometry.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_int),
            C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_uint)]
        self.x.XRaiseWindow.argtypes=[C.c_void_p,C.c_ulong]
        # Target the requested monitor explicitly; stacking order depends on
        # the initial console. The private X screen must contain its grab center.
        def width(window):
            root=C.c_ulong();x=C.c_int();y=C.c_int();w=C.c_uint();h=C.c_uint();border=C.c_uint();depth=C.c_uint()
            assert self.x.XGetGeometry(self.display,window,C.byref(root),C.byref(x),C.byref(y),C.byref(w),C.byref(h),C.byref(border),C.byref(depth))
            return w.value
        self.window=(max if vdc_window else min)(self.windows,key=lambda row:width(row[0]))[0]
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

    @contextmanager
    def held_key(self,name):
        key=self.x.XKeysymToKeycode(self.display,self.x.XStringToKeysym(name.encode()))
        assert key
        self.t.XTestFakeKeyEvent(self.display,key,1,0);self.x.XFlush(self.display)
        try:yield
        finally:
            self.t.XTestFakeKeyEvent(self.display,key,0,0);self.x.XFlush(self.display)
            time.sleep(.12)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--80col',dest='eighty',action='store_true')
    parser.add_argument('--vdc64',action='store_true')
    parser.add_argument('--boot-frame-only',action='store_true')
    parser.add_argument('--paint-only',action='store_true')
    parser.add_argument('--controls-only',action='store_true')
    parser.add_argument('--files-only',action='store_true')
    parser.add_argument('--editor-only',action='store_true')
    parser.add_argument('--claude-only',action='store_true');args=parser.parse_args()
    assert sum((args.paint_only,args.controls_only,args.files_only,args.editor_only,args.claude_only))<=1
    work=Path(tempfile.mkdtemp(prefix='uos-native-pointer-iec-',dir='/var/tmp/arc-scratch'))
    print('Native pointer VICE:',work,flush=True)
    shutil.copy2(__file__,work/'run.py')
    disk=work/'suite.d64';shutil.copy2(ROOT/'target/native-desktop/uos128.d64',disk)
    data_disk=work/'data-9.d64'
    subprocess.run(['c1541','-format','picker data,09','d64',str(data_disk)],check=True,capture_output=True)
    shutil.copy2(data_disk,work/'initial-data-9.d64')
    image=ROOT/'target/native-desktop'
    report=dict(passed=False,physical_hardware_io=False,options=vars(args),events=[],desktops=[],screens=[],calculator_frames=[],paint_frames=[],controls_frames=[],files_frames=[],editor_frames=[],
        images={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in image.iterdir() if p.suffix in ('.prg','.d64')})
    def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    pointer_app='desktop'
    claude_labels={m[2]:int(m[1],16) for m in re.finditer(r'^al ([0-9A-Fa-f]+) \.(\S+)',(image/'claude.lbl').read_text(),re.M)}
    def symbol(name):
        if pointer_app=='claude':return claude_labels[name]
        if name.startswith('pm_') and pointer_app in ('editor','files'):
            kind,active={'editor':('ed_module_kind',1),'files':('fg_kind',2)}[pointer_app]
            if app_read(lst_symbol('native-desktop/'+pointer_app,kind))==bytes([active]) and app_read(picker_symbol(pointer_app,'fd_active'))==b'\1':
                return picker_symbol(pointer_app,'pgm_'+name[3:])
        return lst_symbol('native-desktop/'+pointer_app,name)
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    xv=ci.cbm.Xvfb(geometry='1920x1200x24');emu=mon=mouse=None;log=(work/'vice.log').open('w')
    report['private_x_display']=xv.display
    report['private_x_geometry']='1920x1200x24'
    try:
        command=['x128','-default','-80col' if args.eighty else '-40col','-8',str(disk),'-drive8true','-drive8type','1541',
            '-9',str(data_disk),'-drive9true','-drive9type','1541',
            '-VDC64KB' if args.vdc64 else '-VDC16KB','-sounddev','dummy','-soundwarpmode','1','-jamaction','0','-warp','-controlport1device','3',
            '-controlport2device','0','+mouse','-binarymonitor','-binarymonitoraddress',f'ip4://127.0.0.1:{port}']
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
        banks=mon.banks();mon.resume();paused=PausedViceMonitor(mon)
        def read(at,n=1,bank=0):
            data=bytes(paused.read_mem(at,at+n-1,bank=bank));paused.resume();return data
        def app_read(at,n=1):
            # ROM IRQ/GETIN can hide high application RAM while ready is set.
            # The checked app allocation lives in physical bank 0 throughout.
            return read(at,n,bank=banks['ram00'])
        def ready():return read(0x3d12)==b'\1' and read(0xd0,2)==bytes(2)
        def value(name):return app_read(symbol(name))[0]
        def position():
            assert symbol('pm_y')==symbol('pm_x')+2
            point=app_read(symbol('pm_x'),3)
            return int.from_bytes(point[:2],'little'),point[2]
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
        report['initial_pointer_state']=app_read(symbol('pm_active'),40).hex();save()
        capture=NativeCapture(paused,work,quiet=.05,kernel_prefix='native-desktop',batch=stable_batch)
        modes=NativeModeCapture(paused,work,quiet=.05,kernel_prefix='native-desktop',batch=stable_batch)
        report.update(captures=capture.records,mode_captures=modes.records,paused_capture_batches=paused.batches)
        report['resident_boot']=verify_running_layout(capture,ROOT,'resident-boot',image_dir=image);save()
        saved_registers=app_read(symbol('pm_saved'),12);saved_init=app_read(symbol('pm_init_saved'))
        saved_keys=capture.capture('keys-before',address=0x1000,count=256)
        saved_callback=read(0x033c,2);report['saved_keycheck']=saved_callback.hex()
        report['saved_sprite_registers']=saved_registers.hex();report['saved_init']=saved_init.hex()
        repeat=read(0xa22)
        with paused.paused('disable-accelerated-repeat'):paused.write_mem(0xa22,b'\x40')
        mouse=Mouse(xv.display,vdc_window=args.eighty);report['private_x_windows']=mouse.windows;save()
        assert len(mouse.windows)==2,'the private X display must contain only this C128 pair'
        resource=b'Mouse'
        error,_=mon._recv(mon._send(0x52,bytes([1,len(resource)])+resource+bytes([4])+bytes([1,0,0,0])))
        mon.resume();assert not error
        report['mouse_enabled_after_boot']=True
        wait(lambda:value('pm_seen')==1,'1351 attached',15)
        time.sleep(1)
        def move_to(tx,ty):
            samples=[]
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                x,y=position();samples.append([x,y])
                if abs(x-tx)<=2 and abs(y-ty)<=2:
                    # Let the foreground finish handling this position before
                    # sending another host delta. Steering again during its
                    # brief N_READY=0 interval can keep the pointer oscillating.
                    wait(ready,'mouse destination idle',60)
                    # Finish the input gesture before taking the first capture.
                    # A single position read can precede queued host deltas.
                    time.sleep(.2)
                    settled=position();samples.append(list(settled))
                    if settled==(x,y) and ready():
                        report.setdefault('mouse_routes',[]).append(dict(app=pointer_app,target=[tx,ty],samples=samples));save()
                        return x,y
                    continue
                mouse.move(max(-12,min(12,(tx-x)*2)),max(-12,min(12,(ty-y)*2)))
            report.setdefault('failed_mouse_routes',[]).append(dict(app=pointer_app,target=[tx,ty],samples=samples));save()
            raise AssertionError(('host mouse failed to reach target',position(),(tx,ty)))
        def desktop(label,selected):
            wait(lambda:header('desktop') and ready() and value('gd_selected')==selected,label,90)
            actual=b''.join(capture.capture(label+f'-surface-{offset:04x}',address=0xc000+offset,count=min(2000,9216-offset)) for offset in range(0,9216,2000))
            (work/(label+'-surface.bin')).write_bytes(actual);assert actual==surface(selected)
            mode=modes.snapshot(label+'-mode');assert mode['vic_sprites']==3 and not mode['cpu_speed']&1
            # Host mouse deltas may still be draining when the large RAM
            # capture begins. Pair the canvas with settled current coordinates.
            for _ in range(20):
                xy=position();time.sleep(.2)
                if position()==xy:break
            else:raise AssertionError('pointer never settled for rendered frame')
            state=app_read(symbol('pm_active'),40);(work/(label+'-state.bin')).write_bytes(state)
            error,raw=mon._recv(mon._send(0x84,bytes([1,0])));mon.resume();assert not error
            (work/(label+'-canvas.bin')).write_bytes(raw)
            rectangle=check_canvas(raw,pixels(selected,*xy))
            def vdc_canvas():
                error,raw=mon._recv(mon._send(0x84,bytes([0,0])));mon.resume();assert not error
                return raw
            vdc=vdc_capture(capture,app_read,vdc_canvas,work,label,selected,color=args.vdc64)
            report['desktops'].append(dict(label=label,selected=selected,position=xy,rectangle=rectangle,mode=mode,vdc=vdc));save()
            if label=='claude-returned':
                subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/'desktop.png')],check=True,capture_output=True)
            print('PASS: complete VIC/VDC graphics and 192000 pixels including both pointers:',label,flush=True)
        def key(name,target):
            before=int.from_bytes(read(0x3d13,2),'little')
            # A short host press can begin and end between emulated keyboard
            # scans under load. Keep it down until the ROM-fed native counter
            # acknowledges it, then release even when an assertion fails.
            with mouse.held_key(name):
                wait(lambda:int.from_bytes(read(0x3d13,2),'little')!=before,
                    name+' sampled by native keyboard',120)
            wait(lambda:header(target) and ready() and int.from_bytes(read(0x3d13,2),'little')!=before,
                name+' reaches '+target,120)
            after=int.from_bytes(read(0x3d13,2),'little')
            assert after==(before+1)&65535,(name,'extra or missing ROM key',before,after)
            report['events'].append(dict(key=name,target=target,keys_before=before,keys_after=after));save()
        def screens(label,oracle):
            for mode,columns,address in ((0,40,0x400),(1,80,0)):
                actual=capture.capture(label+('-vic' if mode==0 else '-vdc'),mode=mode,address=address,count=columns*25)
                assert actual==oracle(columns),(label,columns)
            report['screens'].append(label);save()
        def claude_view(label,*,top=0,focus=0,error=0):
            actual,record=claude_capture(capture,app_read,claude_labels,work,label,
                panel=landing_screen(40,error),top=top,focus=focus)
            assert capture.capture(label+'-vdc',mode=1,count=2000)==landing_screen(80,error)
            xy=position();mode=modes.snapshot(label+'-mode');assert mode['vic_sprites']==3
            error,raw=mon._recv(mon._send(0x84,bytes([1,0])));mon.resume();assert not error
            (work/(label+'-canvas.bin')).write_bytes(raw)
            record.update(position=xy,mode=mode,rectangle=check_canvas(raw,surface_pixels(actual,*xy)))
            report.setdefault('claude_frames',[]).append(record);save()
            subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/(label+'.png'))],check=True,capture_output=True)
            print('PASS: Claude companion, VDC and 64000 mouse pixels:',label,flush=True)
        def claude_click(index):
            x0,y0,x1,y1=CLAUDE_RECTS[index];move_to((x0+x1)//2,(y0+y1)//2)
            before=int.from_bytes(read(0x3d13,2),'little')
            mouse.button(True);wait(lambda:value('pm_arm')==index,'Claude button armed',30)
            mouse.button(False);wait(lambda:ready() and value('pm_buttons')==0,'Claude click completed',120)
            assert int.from_bytes(read(0x3d13,2),'little')==before
            report['events'].append(dict(claude_button=index,keyboard_events_during_click=0));save()
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
        def picker_view(label,entries,*,selected=0,mode=1,device=8,fmt=0):
            wait(lambda:ready() and app_read(picker_symbol(pointer_app,'pg_bitmap'))==b'\1',label,90)
            wait(lambda:value('pm_seen')==1,'picker pointer attached',20)
            def pv(name,count=1):return int.from_bytes(app_read(picker_symbol(pointer_app,name),count),'little')
            assert pv('fd_active')==1 and pv('b_selected',2)==selected and pv('fd_mode')==mode
            assert not pv('b_prompt') and not pv('pg_error')
            expected=dict(selected=selected,mode=mode,device=device,fmt=fmt,focus=pv('pg_focus'))
            entries=[dict(entry,app=False) for entry in entries]
            wanted=picker_surface(entries,**expected)
            actual=b''.join(capture.capture(label+f'-surface-{offset:04x}',address=0xc000+offset,count=min(2000,9216-offset)) for offset in range(0,9216,2000))
            (work/(label+'-surface.bin')).write_bytes(actual);assert actual==wanted,(label,'picker bitmap')
            vdc=capture.capture(label+'-vdc',mode=1,address=0,count=2000)
            assert vdc==picker_console(entries,selected=selected,device=device,fmt=fmt),(label,'picker VDC')
            for _ in range(20):
                xy=position();time.sleep(.2)
                if position()==xy:break
            else:raise AssertionError('picker pointer did not settle')
            display=modes.snapshot(label+'-mode');assert display['vic_sprites']==3
            error,raw=mon._recv(mon._send(0x84,bytes([1,0])));mon.resume();assert not error
            (work/(label+'-canvas.bin')).write_bytes(raw);rectangle=check_canvas(raw,surface_pixels(wanted,*xy))
            report.setdefault('picker_frames',[]).append(dict(label=label,app=pointer_app,expected=expected,
                entries=[dict(name_hex=row['name'].hex(),type=row['type'],blocks=row['blocks'],flags=row.get('flags',128)) for row in entries],
                position=xy,rectangle=rectangle,mode=display));save()
            subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/(label+'.png'))],check=True,capture_output=True)
            print('PASS: shared picker bitmap, VDC and 64000 pointer pixels:',label,flush=True)
        def picker_click(index):
            x0,y0,x1,y1=PICKER_RECTS[index];move_to((x0+x1)//2,(y0+y1)//2)
            before=int.from_bytes(read(0x3d13,2),'little')
            mouse.button(True);wait(lambda:value('pm_arm')==index,'picker button armed',30)
            mouse.button(False);wait(lambda:ready() and value('pm_buttons')==0,'picker click completed',120)
            after=int.from_bytes(read(0x3d13,2),'little');assert after==before
            report['events'].append(dict(picker_button=index,app=pointer_app,keyboard_events_during_click=after-before));save()

        def editor_view(label,data,cursor,*,focus=6,**expected):
            wait(lambda:header('editor') and ready(),label,90)
            state={name:value(name) for name in ('eg_bitmap','eg_error','ed_module_kind','ed_mode','ed_status','ui_selected')}
            assert (state['eg_bitmap'],state['ed_module_kind'],state['ui_selected'])==(1,2,focus),(label,state)
            state['cursor']=int.from_bytes(app_read(symbol('ed_cursor'),3),'little')
            report.setdefault('editor_states',[]).append(dict(label=label,**state));save()
            assert state['cursor']==cursor,(label,state,cursor)
            assert state['ed_mode']==expected.get('mode',0) and state['ed_status']==expected.get('status',0),(label,state)
            kwargs=dict(focus=focus,**expected)
            wanted=editor_surface(data,cursor,**kwargs)
            actual=b''.join(capture.capture(label+f'-surface-{offset:04x}',address=0xc000+offset,count=min(2000,9216-offset)) for offset in range(0,9216,2000))
            (work/(label+'-surface.bin')).write_bytes(actual);assert actual==wanted,(label,'editor bitmap')
            vdc=capture.capture(label+'-vdc',mode=1,address=0,count=2000)
            assert vdc==editor_console(data,cursor,**kwargs),(label,'editor VDC')
            for _ in range(20):
                xy=position();time.sleep(.2)
                if position()==xy:break
            else:raise AssertionError('editor pointer did not settle')
            mode=modes.snapshot(label+'-mode');assert mode['vic_sprites']==3
            error,raw=mon._recv(mon._send(0x84,bytes([1,0])));mon.resume();assert not error
            (work/(label+'-canvas.bin')).write_bytes(raw);rectangle=check_canvas(raw,surface_pixels(wanted,*xy))
            report['editor_frames'].append(dict(label=label,data_hex=data.hex(),cursor=cursor,expected=kwargs,position=xy,rectangle=rectangle,mode=mode));save()
            subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/(label+'.png'))],check=True,capture_output=True)
            print('PASS: graphical editor, VDC and 64000 pointer pixels:',label,flush=True)
        def editor_click(index,point=None):
            x0,y0,x1,y1=EDITOR_RECTS[index]
            move_to(*(point or ((x0+x1)//2,(y0+y1)//2)))
            before=int.from_bytes(read(0x3d13,2),'little')
            mouse.button(True);wait(lambda:value('pm_arm')==index,'editor button armed',30)
            mouse.button(False)
            wait(lambda:ready() and (value('ed_module_kind')!=2 or not value('eg_bitmap') or value('pm_buttons')==0),'editor click ready',120)
            after=int.from_bytes(read(0x3d13,2),'little')
            report['events'].append(dict(editor_button=index,point=point,keyboard_events_during_click=after-before));save();assert after==before
        def controls_view(label,page,focus,notice=0):
            wait(lambda:header('controls') and ready(),label,60)
            state={name:value(name) for name in ('ug_bitmap','ug_error','uc_page','ui_selected','ug_mode','ug_notice')}
            report.setdefault('controls_states',[]).append(dict(label=label,**state));save()
            assert (state['ug_bitmap'],state['uc_page'],state['ui_selected'])==(1,page,focus),state
            assert value('ug_mode')==0 and value('ug_notice')==notice
            body=absent_body(page)
            wanted=controls_surface(body[2:] if page==1 else body,page=page,focus=focus,notice=notice)
            actual=b''.join(capture.capture(label+f'-surface-{offset:04x}',address=0xc000+offset,count=min(2000,9216-offset)) for offset in range(0,9216,2000))
            (work/(label+'-surface.bin')).write_bytes(actual);assert actual==wanted,(label,'Ultimate bitmap')
            vdc=capture.capture(label+'-vdc',mode=1,address=0,count=2000)
            assert vdc==panel_screen(80,body,page=page,focus=focus,notice=notice),(label,'Ultimate VDC')
            for _ in range(20):
                xy=position();time.sleep(.2)
                if position()==xy:break
            else:raise AssertionError('Ultimate pointer did not settle')
            mode=modes.snapshot(label+'-mode');assert mode['vic_sprites']==3
            error,raw=mon._recv(mon._send(0x84,bytes([1,0])));mon.resume();assert not error
            (work/(label+'-canvas.bin')).write_bytes(raw)
            rectangle=check_canvas(raw,surface_pixels(wanted,*xy))
            report['controls_frames'].append(dict(label=label,page=page,focus=focus,notice=notice,position=xy,rectangle=rectangle,mode=mode));save()
            subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/(label+'.png'))],check=True,capture_output=True)
            print('PASS: Ultimate bitmap, VDC and 64000 mouse pixels:',label,flush=True)
        def controls_click(index):
            x0,y0,x1,y1=CONTROLS_RECTS[index]
            move_to((x0+x1)//2,(y0+y1)//2)
            before=int.from_bytes(read(0x3d13,2),'little')
            mouse.button(True);wait(lambda:value('pm_arm')==index,'Ultimate button armed',30)
            mouse.button(False);wait(ready,'Ultimate click ready',60)
            after=int.from_bytes(read(0x3d13,2),'little')
            report['events'].append(dict(controls_button=index,keyboard_events_during_click=after-before));save()
            assert after==before
        def files_state(label):
            with paused.paused(label+'-files-state'):
                state={name:value(name) for name in ('b_selected','b_busy','fg_key','fg_kind','fg_bitmap','fg_error')}
                if state['fg_kind']==1 and state['fg_bitmap']:
                    state.update({name:value(name) for name in ('ui_selected','fv_follow','fv_view','fv_previous_view',
                        'pm_hit','pm_event','pm_arm','pm_buttons')})
                    state['position']=position()
                state.update(ready=read(0x3d12)[0],module_state=read(0x3d1b)[0])
            report.setdefault('files_states',[]).append(dict(label=label,**state));save()
            return state
        def files_view(label,*,selected=0,focus=11,source=None,name=None,**kwargs):
            wait(lambda:header('files') and ready(),label,120)
            state=files_state(label)
            assert value('fg_kind')==1 and value('fg_bitmap')==1
            if state['ui_selected']!=focus:
                (work/(label+'-unexpected-surface.bin')).write_bytes(app_read(0xc000,9216))
                (work/(label+'-unexpected-vdc.bin')).write_bytes(read(0,2000,bank=banks['vdc']))
                raise AssertionError((label,'Files focus',state,focus))
            if source is None:
                entries=disk_records(disk.read_bytes())
                expected=dict(selected=selected,focus=focus,**kwargs)
                wanted=files_surface(entries,**expected);console_wanted=files_console(entries,**expected)
                expected['records']=[dict(e,name=e['name'].hex()) for e in entries]
            else:
                expected=dict(source_device=8,device=8,kind=1,focus=focus);expected.update(kwargs)
                wanted=files_copy_surface(source,name,**expected);console_wanted=files_copy_console(source,name,**expected)
                assert value('fc_source_device')==expected['source_device'] and value('fc_device')==expected['device']
                assert value('fc_length')==len(name) and app_read(symbol('fc_name'),len(name))==name
                for counter in ('copied','verified'):
                    assert int.from_bytes(app_read(symbol('fc_'+counter),4),'little')==kwargs.get(counter,0)
                assert value('fc_status')==kwargs.get('status',0)
                expected.update(source=source.hex(),name=name.hex())
            actual=b''.join(capture.capture(label+f'-surface-{offset:04x}',address=0xc000+offset,
                count=min(2000,9216-offset)) for offset in range(0,9216,2000))
            (work/(label+'-surface.bin')).write_bytes(actual);assert actual==wanted,(label,'Files bitmap')
            vdc=capture.capture(label+'-vdc',mode=1,address=0,count=2000)
            assert vdc==console_wanted,(label,'Files VDC')
            for _ in range(20):
                xy=position();time.sleep(.2)
                if position()==xy:break
            else:raise AssertionError('Files pointer did not settle')
            mode=modes.snapshot(label+'-mode');assert mode['vic_sprites']==3
            error,raw=mon._recv(mon._send(0x84,bytes([1,0])));mon.resume();assert not error
            (work/(label+'-canvas.bin')).write_bytes(raw)
            rectangle=check_canvas(raw,surface_pixels(wanted,*xy))
            report['files_frames'].append(dict(label=label,expected=expected,position=xy,rectangle=rectangle,mode=mode));save()
            subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/(label+'.png'))],check=True,capture_output=True)
            print('PASS: Files bitmap, VDC and 64000 mouse pixels:',label,flush=True)
        def files_click(index):
            x0,y0,x1,y1=FILES_RECTS[index];move_to((x0+x1)//2,(y0+y1)//2)
            before=int.from_bytes(read(0x3d13,2),'little')
            files_state(f'files-button-{index}-before')
            mouse.button(True);wait(lambda:value('pm_arm')==index,'Files button armed',30)
            files_state(f'files-button-{index}-armed')
            mouse.button(False)
            wait(lambda:ready() and (value('fg_kind')!=1 or not value('fg_bitmap') or
                value('pm_buttons')==0 and value('pm_arm')==255),'Files click ready',120)
            files_state(f'files-button-{index}-released')
            after=int.from_bytes(read(0x3d13,2),'little')
            report['events'].append(dict(files_button=index,keyboard_events_during_click=after-before));save()
            assert after==before
        def paint_view(label,document,*,dirty,mode=0,status=0):
            wait(lambda:header('paint') and ready(),label,120)
            assert value('pd_dirty')==dirty and value('pa_mode')==mode and value('pa_status')==status
            name=app_read(symbol('pf_name'),value('pf_length')) if value('pf_length') else b''
            expected=dict(view_x=value('pa_view_x'),view_y=value('pa_view_y'),focus=value('ui_selected'),
                x=int.from_bytes(app_read(symbol('pd_x'),2),'little'),y=value('pd_y'),pen=value('pd_pen'),color=value('pd_color'),
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
            field_view=app_read(symbol('pa_field')+6)[0]
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
                mode=value('pa_mode'),name_length=value('pf_length'),name=app_read(symbol('pf_name'),16).hex())
            report['events'].append(dict(paint_button=index,keyboard_events_during_click=after-before,input_state=state));save()
            assert after==before,state
        # Drain the window grab/warp through real relative input before the
        # first long capture. End in the margin, outside every app button.
        move_to(310,180)
        time.sleep(.5)
        key('Home','desktop')
        desktop('attached',0)
        if args.boot_frame_only:
            subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/'vdc-desktop.png')],check=True,capture_output=True)
            report['passed']=True;save()
            return
        move_to(100,40);desktop('calculator-hover',0)
        key('Down','desktop');desktop('keyboard-selection',1)
        time.sleep(.3);assert value('gd_selected')==1
        mouse.move(4,0);desktop('mouse-resumes',0)
        mouse.button(True);move_to(100,64);mouse.button(False);desktop('cancelled-drag',1)
        paint_document=bytearray(bytes(8192)+b'\x10'*1024)
        ran_apps=set()
        for index,name in enumerate(('calc','editor','files','controls','claude','paint')):
            if args.paint_only and name!='paint':continue
            if args.controls_only and name!='controls':continue
            if args.files_only and name!='files':continue
            if args.editor_only and name!='editor':continue
            if args.claude_only and name!='claude':continue
            ran_apps.add(name)
            move_to(100,40+24*index);desktop(name+'-hover',index)
            snapshot,restore=vdc_snapshot(capture,app_read,work,name+'-close')
            entry=lst_symbol('native-desktop/desktop','vd_restore_registers')
            error,checkpoint=mon._recv(mon._send(0x12,entry.to_bytes(2,'little')*2+bytes([1,1,4,0,0])))
            assert not error
            checkpoint_id=checkpoint[:4];mon.resume()
            before=int.from_bytes(read(0x3d13,2),'little')
            mouse.button(True);assert header('desktop') and value('pm_arm')==index
            mouse.button(False)
            deadline=time.monotonic()+120
            while True:
                error,checkpoint=mon._recv(mon._send(0x11,checkpoint_id));assert not error
                if int.from_bytes(checkpoint[13:17],'little'):break
                mon.resume();assert time.monotonic()<deadline,'VDC restore checkpoint was not reached'
                time.sleep(.1)
            base=restore['base']
            restored=bytes(mon.read_mem(base,base+len(snapshot)-1,bank=banks['vdc']))
            (work/(name+'-restored-vram.bin')).write_bytes(restored)
            (work/(name+'-restore-checkpoint.bin')).write_bytes(checkpoint)
            assert restored==snapshot,'VDC snapshot was not fully restored before app handoff'
            assert bytes(mon.read_mem(0x3d20,0x3d20))==b'\x20'
            restore.update(checkpoint_address=entry,checkpoint_hex=checkpoint.hex(),lifetime='desktop snapshot still owned; VRAM restored before register restoration')
            report.setdefault('vdc_restores',[]).append(restore);save()
            error,_=mon._recv(mon._send(0x13,checkpoint_id));assert not error
            mon.resume()
            wait(lambda:header(name) and ready(),'click opens '+name,120)
            assert int.from_bytes(read(0x3d13,2),'little')==before,'mouse generated a keyboard shortcut'
            if name=='editor':
                pointer_app='editor'
                assert app_read(symbol('pm_saved'),12)==saved_registers and app_read(symbol('pm_init_saved'))==saved_init
                wait(lambda:value('pm_seen')==1,'editor 1351 attached',15)
                move_to(164,172);editor_view('editor-open',b'',0)
                for char in ('c','1','2','8','space','t','e','x','t'):key(char,'editor')
                document=b'C128 TEXT';editor_view('editor-typed',document,len(document),dirty=True)
                editor_click(6,(28,60));editor_view('editor-caret',document,2,dirty=True)
                key('x','editor');document=b'C1X28 TEXT';editor_view('editor-insert',document,3,dirty=True)
                editor_click(2)
                for char in 'guinote':key(char,'editor')
                field=dict(mode=2,field='GUINOTE',field_caret=7,field_view=0,dirty=True)
                editor_view('editor-save-dialog',document,3,focus=11,**field)
                editor_click(14)
                assert value('ed_module_kind')==1 and value('fd_active')==1 and not value('eg_bitmap')
                entries=disk_records(disk.read_bytes())
                for entry in entries:entry['app']=False
                picker_view('editor-destination-picker',entries,mode=2)
                picker_click(18);wait(lambda:value('pm_seen')==1,'editor pointer after picker',15)
                editor_view('editor-picker-return',document,3,focus=11,**field)
                editor_click(12);editor_view('editor-saved',document,3,name='GUINOTE',status=1)
                editor_click(3);key('x','editor')
                editor_view('editor-find',document,3,name='GUINOTE',mode=6,field='X',field_caret=1,field_view=0,focus=11)
                editor_click(12);editor_view('editor-found',document,8,name='GUINOTE',status=13)
                report['editor_saved_hex']=document.hex();save()
            elif name=='calc':
                pointer_app='calc'
                assert app_read(symbol('pm_saved'),12)==saved_registers and app_read(symbol('pm_init_saved'))==saved_init
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
            elif name=='files':
                pointer_app='files'
                assert app_read(symbol('pm_saved'),12)==saved_registers and app_read(symbol('pm_init_saved'))==saved_init
                wait(lambda:value('pm_seen')==1,'Files 1351 attached',15)
                move_to(310,180);key('Home','files');files_view('files-open')
                files_click(7);files_view('files-next-page',selected=8,focus=7)
                files_click(6);files_view('files-previous-page',focus=6)
                entries=disk_records(disk.read_bytes());source=b'EDFIND.PRG'
                chosen=next(i for i,e in enumerate(entries) if e['name'].rstrip(b'\xa0')==source)
                assert chosen<8
                files_click(11+chosen);files_view('files-selected',selected=chosen,focus=11+chosen)
                files_click(10);files_view('files-copy-dialog',source=source,name=source,focus=25)
                for _ in source:key('BackSpace','files')
                for char in 'fscopy':key(char,'files')
                files_view('files-copy-name',source=source,name=b'FSCOPY',focus=25)
                files_click(22)
                assert value('fg_kind')==2 and value('fc_picker_active') and not value('fg_bitmap')
                picker_view('files-copy-picker',entries,mode=2)
                picker_click(18);move_to(310,180)
                for _ in range(28):
                    if value('ui_selected')==25:break
                    key('F10','files')
                else:raise AssertionError('Files field focus unavailable after picker')
                files_view('files-picker-return',source=source,name=b'FSCOPY',focus=25)
                # Keep a separate data disk: the complete suite plus history,
                # an Editor file, this module copy and a Paint image exceed a
                # single D64. Exercise mouse Device and Use Here in the picker.
                files_click(22);picker_click(1)
                key('9','files');key('Return','files')
                picker_view('files-data-picker',[],mode=2,device=9)
                picker_click(17);move_to(310,180)
                for _ in range(28):
                    if value('ui_selected')==25:break
                    key('F10','files')
                else:raise AssertionError('Files field focus unavailable after destination selection')
                files_view('files-data-destination',source=source,name=b'FSCOPY',focus=25,device=9)
                files_click(23)
                copied_source=exact_d64_files((image/'uos128.d64').read_bytes())[source]
                assert copied_source[0]==2
                files_view('files-copy-verified',source=source,name=b'FSCOPY',focus=23,device=9,
                    copied=len(copied_source[1]),verified=len(copied_source[1]),status=1)
                files_click(24);move_to(310,180)
                key('Up','files');key('Down','files')
                files_view('files-copy-return',selected=chosen,focus=11+chosen)
            elif name=='controls':
                pointer_app='controls'
                assert app_read(symbol('pm_saved'),12)==saved_registers and app_read(symbol('pm_init_saved'))==saved_init
                wait(lambda:value('pm_seen')==1,'Ultimate 1351 attached',15)
                move_to(44,40);controls_view('ultimate-open',0,0)
                controls_click(1);controls_view('ultimate-drives',1,1)
                controls_click(8);controls_view('ultimate-missing-drive',1,8,5)
                controls_click(2);controls_view('ultimate-network',2,2)
                controls_click(3);controls_view('ultimate-clock',3,3)
                controls_click(7);controls_view('ultimate-refresh',3,7)
                # Stock GTK symbolic mapping: host F10 is the C128 Tab key.
                controls_click(0);key('F10','controls');controls_view('ultimate-tab',0,1)
                key('Return','controls');controls_view('ultimate-enter',1,1)
            elif name=='claude':
                pointer_app='claude'
                assert app_read(symbol('pm_saved'),12)==saved_registers and app_read(symbol('pm_init_saved'))==saved_init
                wait(lambda:value('pm_seen')==1,'Claude 1351 attached',15)
                move_to(160,170);claude_view('claude-open')
                claude_click(4);claude_view('claude-next-page',top=9,focus=3)
                claude_click(3);claude_view('claude-previous-page',focus=4)
                claude_click(0);claude_view('claude-port-unavailable',top=9,focus=0,error=2)
            elif name=='paint':
                pointer_app='paint'
                assert read(0x033c,2)==symbol('pk_entry').to_bytes(2,'little')
                assert app_read(symbol('pm_saved'),12)==saved_registers and app_read(symbol('pm_init_saved'))==saved_init
                wait(lambda:value('pm_seen')==1,'Paint 1351 attached',15)
                move_to(310,180);paint_view('paint-open',paint_document,dirty=0)
                versions=[]
                for tx,ty,color in ((48,56,1),(88,80,2)):
                    if color!=1:paint_click(7+color)
                    move_to(tx,ty);wait(ready,'Paint brush move',60);time.sleep(.3)
                    x,y=position();assert abs(x-tx)<=2 and abs(y-ty)<=2,('Paint pointer moved after settling',(x,y),(tx,ty))
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
                key('F10','paint');picker_click(1)
                key('9','paint');key('Return','paint')
                picker_view('paint-save-destination',disk_records(data_disk.read_bytes()),mode=2,device=9)
                picker_click(17)
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
                entries=disk_records(data_disk.read_bytes())
                for entry in entries:entry['app']=False
                chosen=next(i for i,entry in enumerate(entries) if entry['name'].rstrip(b'\xa0')==b'PAINTPIC')
                key('Home','paint')
                for _ in range(chosen):key('Down','paint')
                picker_view('paint-file-picker',entries,selected=chosen,device=9)
                picker_click(16);paint_view('paint-loaded',paint_document,dirty=0,status=2)
                report['paint_filtered_line_samples']=int.from_bytes(app_read(symbol('pk_rejects'),2),'little');save()
            else:
                current=bytes(read(0xd000+at)[0] for at in (0,1,2,3,0x10,0x15,0x17,0x1b,0x1c,0x1d,0x27,0x28))
                assert current==saved_registers,(name,'sprite register leak',current.hex(),saved_registers.hex())
                assert read(0xa04)==saved_init,(name,'BASIC sprite hook leak')
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
        # Independently export each created file and preserve every shipped file.
        contents=exact_d64_files(disk.read_bytes())
        before_files=exact_d64_files((image/'uos128.d64').read_bytes())
        if 'editor' in ran_apps:assert contents.pop(b'GUINOTE')==(1,bytes.fromhex(report['editor_saved_hex']))
        if 'calc' in ran_apps:assert contents.pop(b'GUIHIST')==(1,b'42\r')
        data_contents=exact_d64_files(data_disk.read_bytes())
        if 'paint' in ran_apps:assert data_contents.pop(b'PAINTPIC')==(1,paint_encode(paint_document))
        assert exact_d64_files((work/'initial-data-9.d64').read_bytes())=={}
        assert data_contents==({b'FSCOPY':copied_source} if 'files' in ran_apps else {})
        assert contents==before_files
        if 'paint' in ran_apps:
            report['paint_file_sha256']=hashlib.sha256(paint_encode(paint_document)).hexdigest()
            report['paint_destination_device']=9
        if 'calc' in ran_apps:report['calculator_history_export_hex']=b'42\r'.hex()
        if 'files' in ran_apps:
            report['files_copy_sha256']=hashlib.sha256(copied_source[1]).hexdigest()
            report['files_copy_destination_device']=9
        report['system_disk_files_preserved']=True
        report['passed']=True;save()
    except BaseException as error:
        report['error']=repr(error)
        if mon is not None:
            try:
                # Keep one stopped CPU context when diagnosing a timeout. A
                # header alone cannot distinguish a loader from directory I/O.
                with paused.paused('failure-diagnostic'):
                    error_code,registers=mon._recv(mon._send(0x31,b'\0'))
                    assert not error_code
                    report['failure_registers_hex']=registers.hex()
                    report['failure_state']={hex(at):bytes(paused.read_mem(at,at+count-1)).hex()
                        for at,count in ((0xd0,8),(0xa20,16),(0x3d00,256),(0x100,256),(0xdc00,16),(0xdd00,16),(0xd02f,1),(0xd419,2))}
                    for name in ('desktop','calc','editor','files','controls','claude','paint'):
                        if bytes(paused.read_mem(0x3d60,0x3d7f))==(image/(name+'.prg')).read_bytes()[2:34]:
                            data=bytes(paused.read_mem(0x6000,0xbfff,bank=banks['ram00']))
                            (work/('failure-'+name+'-ram.bin')).write_bytes(data)
                            report['failure_app']=name
                            break
            except BaseException as diagnostic:report['diagnostic_error']=repr(diagnostic)
            try:subprocess.run(['magick','import','-display',xv.display,'-window','root',str(work/'failure.png')],check=True,capture_output=True)
            except BaseException as diagnostic:report['screenshot_error']=repr(diagnostic)
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
