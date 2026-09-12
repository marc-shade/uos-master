#!/usr/bin/env python3
"""Check real ROM keyboard scan provenance and strict capture rejection in VICE."""
from contextlib import contextmanager
import ctypes as C
from ctypes.util import find_library
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import ci_fm as ci
from native_capture import NativeCapture,wait
from native_capture_transport import PausedViceMonitor
from native_input_trace import InputTrace
from native_running_layout import verify_running_layout
from launcher_scene import surface,console


class Keyboard:
    def __init__(self,display):
        self.x=C.CDLL(find_library('X11'));self.t=C.CDLL(find_library('Xtst'))
        self.x.XOpenDisplay.argtypes=[C.c_char_p];self.x.XOpenDisplay.restype=C.c_void_p
        self.x.XDefaultRootWindow.argtypes=[C.c_void_p];self.x.XDefaultRootWindow.restype=C.c_ulong
        self.x.XQueryTree.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),
                                    C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]
        self.x.XFetchName.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_char_p)]
        self.x.XFree.argtypes=[C.c_void_p]
        self.x.XSetInputFocus.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_ulong]
        self.x.XStringToKeysym.argtypes=[C.c_char_p];self.x.XStringToKeysym.restype=C.c_ulong
        self.x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong];self.x.XKeysymToKeycode.restype=C.c_uint
        self.x.XFlush.argtypes=[C.c_void_p];self.x.XCloseDisplay.argtypes=[C.c_void_p]
        self.t.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        self.display=self.x.XOpenDisplay(display.encode());assert self.display
        root=C.c_ulong();parent=C.c_ulong();children=C.POINTER(C.c_ulong)();count=C.c_uint()
        self.x.XQueryTree(self.display,self.x.XDefaultRootWindow(self.display),C.byref(root),C.byref(parent),C.byref(children),C.byref(count))
        found=[]
        for index in range(count.value):
            name=C.c_char_p()
            if self.x.XFetchName(self.display,children[index],C.byref(name)):
                if name.value and b'C128' in name.value:found.append((children[index],name.value.decode(errors='replace')))
                self.x.XFree(name)
        self.x.XFree(children)
        assert found,'private VICE window not found'
        self.window=found[0][0];self.windows=found
        self.x.XSetInputFocus(self.display,self.window,2,0);self.x.XFlush(self.display)

    def press(self,name):
        key=self.x.XKeysymToKeycode(self.display,self.x.XStringToKeysym(name.encode()))
        assert key
        self.t.XTestFakeKeyEvent(self.display,key,1,0);self.x.XFlush(self.display)
        time.sleep(.06)
        self.t.XTestFakeKeyEvent(self.display,key,0,0);self.x.XFlush(self.display)
        time.sleep(.12)

    def close(self):self.x.XCloseDisplay(self.display)


def main():
    work=Path(tempfile.mkdtemp(prefix='uos-native-input-iec-',dir='/var/tmp/arc-scratch'))
    print('Native input trace VICE:',work,flush=True)
    report=dict(passed=False,physical_hardware_io=False,events=[])
    def save():(work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    xv=ci.cbm.Xvfb();emu=mon=trace=keyboard=None;repeat=None
    log=(work/'vice.log').open('w')
    try:
        command=['x128','-default','-40col','-8',str(ROOT/'target/native-desktop/uos128.d64'),
            '-drive8true','-drive8type','1541','-VDC16KB','-sounddev','dummy','-jamaction','0','-warp',
            '-binarymonitor','-binarymonitoraddress',f'ip4://127.0.0.1:{port}']
        emu=subprocess.Popen(command,env=dict(os.environ,DISPLAY=xv.display,__EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL),stdout=log,stderr=subprocess.STDOUT)
        deadline=time.monotonic()+30
        while mon is None:
            assert emu.poll() is None
            try:mon=ci.Monitor(port=port)
            except OSError:
                if time.monotonic()>deadline:raise
                time.sleep(.1)
        mon.resume();paused=PausedViceMonitor(mon)
        def read(address,count=1):
            raw=bytes(paused.read_mem(address,address+count-1));paused.resume();return raw
        wait(lambda:read(0x1c13,6)==b'UOS128' and read(0x3d12)==b'\1','native desktop boot',90)
        trace=InputTrace(paused,work,paused.paused,report,save,quiet=.2);trace.install()
        # Keep synthetic X key holds to one ROM event despite accelerated time.
        # This fixture-only repeat setting is restored and is not used by the
        # physical diagnostic, which observes the machine's existing policy.
        with paused.paused('fixture-repeat-policy'):
            repeat=read(0xa22);paused.write_mem(0xa22,b'\x40')
        report['fixture_repeat_before']=repeat.hex();save()
        keyboard=Keyboard(xv.display);report['private_x_windows']=keyboard.windows;save()
        trace.phase(1);keyboard.press('Down')
        wait(lambda:int.from_bytes(read(0x520d,2),'little')==1,'real ROM keyboard event consumed',10)
        first=trace.snapshot('input-matrix-down')
        assert [r['type'] for r in first['records']]==['scan','consumed'],first
        assert all(r['key']==17 for r in first['records']),first
        assert read(0x3d2f)==b'\0' and read(0x3d15)==b'\x11'
        print('PASS: X keyboard -> real ROM scan -> native consumption; desktop input held',flush=True)
        trace.phase(2)
        capture=NativeCapture(paused,work,quiet=.05,kernel_prefix='native-desktop',batch=paused.paused)
        report['captures']=capture.records;report['paused_capture_batches']=paused.batches
        capture.capture('trace-quiet-ram',address=0x2500,count=2000);save()
        injected=False
        @contextmanager
        def during(label):
            nonlocal injected
            if label=='trace-input-ram-restore' and not injected:
                injected=True;keyboard.press('Down')
                wait(lambda:int.from_bytes(read(0x520d,2),'little')==2,'second ROM input consumed',10)
            with paused.paused(label):yield
        capture.batch=during
        try:capture.capture('trace-input-ram',address=0x2500,count=2000)
        except AssertionError as error:
            report['expected_capture_error']=str(error)
            assert capture.records[-1]['input_observation']['keys_after']-capture.records[-1]['input_observation']['keys_before']==1
            assert [r['region'] for r in capture.records[-1]['borrower_failures']]==['metadata']
        else:raise AssertionError('input activity was accepted by the strict capture')
        assert not capture.records[-1]['restored'];trace.snapshot('input-during-observer');save()
        print('PASS: scan trace coexists with IRQ observer; changed input still rejects capture',flush=True)
        trace.phase(3)
        with paused.paused('input-direct-buffer'):
            assert read(0xd0,2)==bytes(2)
            paused.write_mem(0x34a,b'P');paused.write_mem(0xd0,b'\1')
        report['events'].append(dict(source='explicit host buffer write',key=ord('P'),phase=3));save()
        wait(lambda:int.from_bytes(read(0x520d,2),'little')==3,'direct buffer input consumed',10)
        last=trace.snapshot('input-direct-buffer-result')
        assert [r['type'] for r in last['records']]==['scan','consumed','scan','consumed','consumed']
        direct=last['records'][-1]
        assert direct['key']==ord('P') and direct['keys_before']==2 and direct['keys_after']==3
        # The stopped CPU may already have taken its pre-sample when the host
        # supplies the byte. Preserve that race instead of inventing a queued
        # byte in the earlier snapshot. No ROM scan produced this fixture key.
        assert direct['buffer_count_before'] in (0,1)
        if direct['buffer_count_before']:assert direct['buffer_before_hex'].startswith('50')
        assert last['overflow']==0 and last['scans']==2 and last['consumed']==3
        assert read(0x3d2f)==b'\0'
        with paused.paused('fixture-repeat-restore'):
            paused.write_mem(0xa22,repeat);assert read(0xa22)==repeat
        repeat=None
        trace.restore();save()
        capture.batch=paused.paused
        report['resident_restored']=verify_running_layout(capture,ROOT,'trace-resident-restored',image_dir=ROOT/'target/native-desktop')
        with paused.paused('normal-key-after-trace'):
            paused.write_mem(0x34a,b'\x11');paused.write_mem(0xd0,b'\1')
        wait(lambda:read(0x3d2f)==b'\1' and read(0x3d12)==b'\1','normal keyboard delivery restored',15)
        banks=mon.banks();mon.resume()
        actual=bytes(mon.read_mem(0xc000,0xe3ff,bank=banks['ram00']));mon.resume()
        assert actual==surface(1);(work/'returned-surface.bin').write_bytes(actual)
        actual=bytes(mon.read_mem(0,1999,bank=banks['vdc']));mon.resume()
        assert actual==console(80,1);(work/'returned-vdc.bin').write_bytes(actual)
        print('PASS: full trace restoration, resident kernel and normal desktop navigation',flush=True)
        from native_input_workflow import run_input_workflow
        shared=work/'shared';shared.mkdir()
        sub=report['shared_workflow']=dict(physical_hardware_io=False)
        def save_shared():(shared/'report.json').write_text(json.dumps(sub,indent=2)+'\n');save()
        observer=NativeCapture(paused,shared,quiet=.05,kernel_prefix='native-desktop',batch=paused.paused)
        sub['captures']=observer.records
        run_input_workflow(paused,observer,shared,ROOT/'target/native-desktop/uos128.d64',sub,save_shared,
                           idle_seconds=.1,pause_batches=2,captures=1)
        assert sub['input_diagnostic']['completed'] and sub['input_trace']['restored']
        assert sub['input_diagnostic']['initial_keys']==sub['input_diagnostic']['final_keys']
        report['passed']=True;print('PASS: complete shared physical diagnostic workflow in VICE',flush=True)
    except BaseException as error:report['error']=repr(error);raise
    finally:
        if repeat is not None and mon is not None:
            try:
                with paused.paused('fixture-repeat-error-restore'):paused.write_mem(0xa22,repeat)
            except BaseException as error:report['repeat_restore_error']=repr(error)
        if trace is not None and trace.installed:
            try:trace.restore()
            except BaseException as error:report['trace_restore_error']=repr(error)
        if keyboard is not None:keyboard.close()
        if mon is not None:
            try:mon.quit_emulator()
            except (EOFError,OSError):pass
            mon.close()
        if emu is not None:
            try:emu.wait(timeout=2)
            except subprocess.TimeoutExpired:emu.terminate();emu.wait(timeout=5)
        xv.stop();log.close();save()


if __name__=='__main__':main()
