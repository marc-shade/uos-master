import os, subprocess, sys, time, struct, re
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_vdc.py")).read()
exec(src[:src.index("def check_driver_layout():")])
sys.path.insert(0, UOS); import hwlib
xvfb, disp = start_xvfb(); port = free_port()
emu = subprocess.Popen(["x128","-default","-go64","-VDC64KB","-reu","-reusize","512","-autostart",DISK,
    "-drive8true","-drive8type","1541","-sounddev","dummy","-jamaction","0","-warp",
    "-remotemonitor","-remotemonitoraddress",f"ip4://127.0.0.1:{port}"],
    env=dict(os.environ, DISPLAY=disp, **EGL), stdout=open(os.path.join(OUT,"dbg24.log"),"w"), stderr=subprocess.STDOUT)
mon = Mon(port, emu)
NET = {k:0x9100+int(v,16) for k,v in re.findall(r"^(NET_[A-Z]+)\s*=\s*NET_BASE\+\$([0-9a-f]{2})", open(os.path.join(UOS,"src/routines.inc")).read(), re.M)}
try:
    time.sleep(20)
    wait_rows(mon, lambda r: r[2].startswith("desktop"), "desktop", timeout=240)
    r=mon.vdc_rows()
    print("boot row24:", repr(r[24]))
    print("NET_STATE:", mon.peek(NET['NET_STATE'],1).hex(), "NET_YEAR:", mon.peek(NET['NET_YEAR'],2).hex())
    # canned NTP apply + force tick
    import calendar
    utc = calendar.timegm((2026,9,6,17,45,30,0,0,0))
    pkt = bytes(40) + (utc+2208988800).to_bytes(4,"big") + bytes(4)
    mon.poke(0x8800+2, pkt[:24]); mon.poke(0x8800+2+24, pkt[24:])
    mon.poke(0x7352, bytes([0x02,0xf0,0xa5])); mon.poke(NET['NET_STATE'], b"\x00")
    minute = hwlib.lst_symbol("uos-desktop","minute")
    mon.tramp(bytes([0x20, NET['NET_APPLYNTP']&0xff, NET['NET_APPLYNTP']>>8, 0xA9,0xFF, 0x8D, minute&0xff, minute>>8]))
    time.sleep(6)
    r=mon.vdc_rows()
    print("after apply NET_YEAR:", mon.peek(NET['NET_YEAR'],2).hex(), "MON:", mon.peek(NET['NET_MON'],1).hex(), "DAY:", mon.peek(NET['NET_DAY'],1).hex())
    print("after apply row24:", repr(r[24]))
    print("row0:", repr(r[0][58:]))
finally:
    emu.terminate(); xvfb.terminate()
