import os, struct, subprocess, sys, time
UOS=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src=open(os.path.join(UOS,"tests/ci_fm.py")).read(); exec(src[:src.index("def main():")])
import shutil
DISK=os.path.join(WORK,"db ed.d64".replace(" ","")); os.makedirs(WORK,exist_ok=True); shutil.copyfile(STOCK,DISK)
NAMES_L,NAMES_H=parse_lst_symbols()
edit_ref=load_ref(os.path.join(UOS,"target/uos-edit.prg"))
xv=cbm.Xvfb(); env=dict(os.environ,DISPLAY=xv.display,__EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
emu=subprocess.Popen(["x64","-default","-autostart",DISK,"-drive8true","-drive8type","1541","-sounddev","dummy","-jamaction","0","-binarymonitor","-binarymonitoraddress",f"ip4://127.0.0.1:{PORT}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
def dirlist():
    return subprocess.run(["c1541","-attach",DISK,"-dir"],capture_output=True,text=True).stdout
try:
    mon=None; dl=time.time()+60
    while time.time()<dl:
        try: mon=Monitor(port=PORT); break
        except OSError: time.sleep(0.25)
    assert wait_desktop_live(mon,300)
    ov=mon.read_mem(TICK_VEC,TICK_VEC+1,memspace=0); mon.resume()
    tr=(bytes([0x20,0x23,0x08])+b"UOS-EDIT\x00"+bytes([0x20,0x26,0x08])+bytes([0xA2,ov[0],0xA0,ov[1],0x8E,0x3C,0x03,0x8C,0x3D,0x03])+bytes([0x4C,0x00,0x50]))
    mon.write_mem(TRAMPOLINE,tr); mon.write_mem(TICK_VEC,struct.pack("<H",TRAMPOLINE)); mon.resume()
    for _ in range(40):
        time.sleep(3)
        g=mon.read_mem(APP_START,APP_START+15,memspace=0); mon.resume()
        if bytes(g)==edit_ref[:16]: break
    time.sleep(3)
    inject_keys(mon,b"HI"); time.sleep(3)
    EDLEN=lst_symbol("uos-edit","edlen")
    print("edlen after HI:", struct.unpack("<H",bytes(mon.read_mem(EDLEN,EDLEN+1,memspace=0)))[0]); mon.resume()
    inject_keys(mon,b"\x85"); time.sleep(6)
    print("edlen after F1:", struct.unpack("<H",bytes(mon.read_mem(EDLEN,EDLEN+1,memspace=0)))[0]); mon.resume()
    print("DIR:\n"+dirlist())
finally:
    emu.terminate(); xv.stop()
