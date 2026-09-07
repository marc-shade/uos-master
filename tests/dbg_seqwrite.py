import os, struct, subprocess, sys, time
UOS=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src=open(os.path.join(UOS,"tests/ci_fm.py")).read(); exec(src[:src.index("def main():")])
import shutil
DISK=os.path.join(WORK,"swtest.d64"); os.makedirs(WORK,exist_ok=True); shutil.copyfile(STOCK,DISK)
NAMES_L,NAMES_H=parse_lst_symbols()
code=open(os.path.join(UOS,"probes/seqwrite.bin"),"rb").read()[2:]
xv=cbm.Xvfb(); env=dict(os.environ,DISPLAY=xv.display,__EGL_VENDOR_LIBRARY_FILENAMES=cbm.MESA_EGL)
emu=subprocess.Popen(["x64","-default","-autostart",DISK,"-drive8true","-drive8type","1541","-sounddev","dummy","-jamaction","0","-warp","-autostart-warp","-binarymonitor","-binarymonitoraddress",f"ip4://127.0.0.1:{PORT}"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
try:
    mon=None; dl=time.time()+60
    while time.time()<dl:
        try: mon=Monitor(port=PORT); break
        except OSError: time.sleep(0.25)
    assert wait_desktop_live(mon,300)
    mon.write_mem(0x6000,b"\x00\x00")
    mon.write_mem(0xc000, code)
    ov=mon.read_mem(TICK_VEC,TICK_VEC+1,memspace=0); mon.resume()
    tr=(bytes([0xA2,ov[0],0xA0,ov[1],0x8E,0x3C,0x03,0x8C,0x3D,0x03])+bytes([0x20,0x00,0xc0])+bytes([0x6c,0x3c,0x03]))
    mon.write_mem(TRAMPOLINE,tr); mon.write_mem(TICK_VEC,struct.pack("<H",TRAMPOLINE)); mon.resume()
    for _ in range(20):
        time.sleep(1)
        if mon.read_mem(0x6000,0x6000,memspace=0)[0]==0xa5: mon.resume(); break
        mon.resume()
    st=mon.read_mem(0x6001,0x6001,memspace=0)[0]; mon.resume()
    print("probe done flag=%02x ST-after-CHKOUT=%02x"%(mon.read_mem(0x6000,0x6000,memspace=0)[0],st)); mon.resume()
    print("DIR:\n"+subprocess.run(["c1541","-attach",DISK,"-dir"],capture_output=True,text=True).stdout)
finally:
    emu.terminate(); xv.stop()
