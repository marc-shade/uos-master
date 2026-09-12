#!/usr/bin/env python3
import os, struct, subprocess, sys, time
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_fm.py")).read()
exec(src[:src.index("def main():")])
import shutil
DISK=os.path.join(WORK,"dbgpoke.d64"); os.makedirs(WORK,exist_ok=True); shutil.copyfile(STOCK,DISK)
NAMES_L,NAMES_H=parse_lst_symbols()
sym=lambda n: lst_symbol("uos-shell",n)
CMD=sym("cmdbuf"); TOK=sym("tokbuf"); TOK2=sym("tok2buf"); PKA=sym("pkaddr"); PKV=sym("pkval"); PKAL=sym("pkaL"); PKAH=sym("pkaH")
xv=cbm.Xvfb(); env=dict(os.environ,DISPLAY=xv.display,__EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
emu=subprocess.Popen(["x64","-default","-autostart",DISK,"-drive8true","-drive8type","1541","-sounddev","dummy","-jamaction","0","-warp","-autostart-warp","-binarymonitor","-binarymonitoraddress",f"ip4://127.0.0.1:{PORT}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
try:
    mon=None
    dl=time.time()+60
    while time.time()<dl:
        try: mon=Monitor(port=PORT); break
        except OSError: time.sleep(0.25)
    assert wait_desktop_live(mon,300)
    ov=mon.read_mem(TICK_VEC,TICK_VEC+1,memspace=0); mon.resume()
    tr=(bytes([0x20,0x23,0x08])+b"UOS-SHELL\x00"+bytes([0x20,0x26,0x08])+bytes([0xA2,ov[0],0xA0,ov[1],0x8E,0x3C,0x03,0x8C,0x3D,0x03])+bytes([0x4C,0x00,0x50]))
    mon.write_mem(TRAMPOLINE,tr); mon.write_mem(TICK_VEC,struct.pack("<H",TRAMPOLINE)); mon.resume()
    time.sleep(25)
    def rd(a,n): v=bytes(mon.read_mem(a,a+n-1,memspace=0)); mon.resume(); return v
    mon.write_mem(0x02a7,b"\x00"); mon.resume()
    inject_keys(mon,b"POKE 02A7 5A\x0d"); time.sleep(4)
    print("cmdbuf:",rd(CMD,16))
    print("tokbuf:",rd(TOK,8),"tok2buf:",rd(TOK2,8))
    print("pkaddr:",rd(PKA,2).hex(),"pkaL/H:",rd(PKAL,1).hex(),rd(PKAH,1).hex(),"pkval:",rd(PKV,1).hex())
    print("$02a7 =",rd(0x02a7,1).hex(),"cmdlen:",rd(0x46,1).hex())
finally:
    emu.terminate(); xv.stop()
