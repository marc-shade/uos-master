import sys,os,socket,subprocess,time,tempfile,json
from pathlib import Path
sys.path[:0]=['/home/marc/geos128/uos','/home/marc/geos128/uos/tests']
import ci_fm as ci
from native_files_check import prepare,NativeFiles
from native_capture import wait
from hwlib import lst_symbol
work=Path(tempfile.mkdtemp(prefix='uos-native-small-trace-'))
disk,fixtures=prepare(work,size=1557)
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
xv=ci.cbm.Xvfb();log=(work/'vice.log').open('w')
p=subprocess.Popen(['x128','-default','-8',str(disk),'-drive8true','-drive8type','1541','-sounddev','dummy','-jamaction','0','-warp','-binarymonitor','-binarymonitoraddress',f'ip4://127.0.0.1:{port}'],env=dict(os.environ,DISPLAY=xv.display,__EGL_VENDOR_LIBRARY_FILENAMES=ci.cbm.MESA_EGL),stdout=log,stderr=subprocess.STDOUT)
report={}
try:
 mon=None
 for _ in range(300):
  try:mon=ci.Monitor(port=port);break
  except OSError:time.sleep(.1)
 assert mon
 client=NativeFiles(mon,work)
 wait(lambda:client.read_ram(0x1c13,6)==b'UOS128' and client.read_ram(0x3d12)==b'\1','boot',60)
 client.key(ord('C'),expected=None)
 byte=lst_symbol('native/uos128','f_byte')
 trace=bytes.fromhex('20b7ff8dfe188a48aeff18ad')+byte.to_bytes(2,'little')+bytes.fromhex('9d0019e8adfe189d0019e88eff1868aaadfe1860')
 addr=lst_symbol('native/uos128','fs_serial')
 assert client.read_ram(addr,3)==bytes.fromhex('20b7ff')
 client.put(0x1800,trace);client.put(addr,bytes.fromhex('200018'))
 if '--acptr' in sys.argv:
  reader=lst_symbol('native/uos128','fs_read_loop');assert client.read_ram(reader,3)==bytes.fromhex('20cfff')
  client.put(reader,bytes.fromhex('20a5ff'))
 for name in ('ZERO','CR','EMPTY','USER','PROGRAM'):
  kind=2 if name=='USER' else 1 if name=='PROGRAM' else 0
  client.open(name.encode(),kind=kind);client.put(0x18ff,b'\0')
  data=client.read(expected=None);count=client.read_ram(0x18ff)[0]
  raw=client.read_ram(0x1900,count)
  report[name]=dict(data=data.hex(),state=client.read_ram(0x3d80,0x64).hex(),trace=[raw[i:i+2].hex() for i in range(0,len(raw),2)])
  print(name,report[name],flush=True)
  client.close()
finally:
 (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 p.terminate();p.wait(timeout=10);xv.stop();log.close();print(work,flush=True)
