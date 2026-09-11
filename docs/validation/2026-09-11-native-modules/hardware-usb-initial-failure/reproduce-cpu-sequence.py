from pathlib import Path
import json
import sys
sys.path[:0]=['/home/marc/geos128/uos/tests','/home/marc/geos128/uos']
from ci_native_browser_ultimate import Browser
from ci_native_calc import Calculator,ROOT
from hw_native_usb_apps import app_fixtures,CALCULATOR

folder=b'/Usb0/uos-native-c36f2295116c'
fixtures={b'NOTE.TXT':b'NOTE',b'EMPTY.TXT':b'',b'LARGE.TXT':b'LARGE',**app_fixtures()}
entries=sorted([b'\x10EMPTY FOLDER']+[b'\x20'+name for name in fixtures],
               key=lambda row:(not bool(row[0]&16),row[1:].upper()))
b=Browser(files={folder+b'/'+name:data for name,data in fixtures.items()},directories={folder:entries},trailing_paths=True)
b.dispatch_return();b.path(folder);b.key(9)
assert entries[-1][1:]==CALCULATOR
for _ in range(7):b.key(0x11)
b.check(folder+b'/',entries,selected=7,device=2)
b.image_name='calc';b.key(13);b.type('12+30=SHISTORY');b.key(13)
Calculator.check_screens(b,save_status='HISTORY SAVED AND VERIFIED')
b.image_name='browse';b.key(27)
after=b.ultimate.directories[folder];assert len(after)==9
b.check(folder+b'/',after[8:],base=8,device=2)
b.type('L');b.key(21);b.key(9);b.type((folder+b'/MISSING.PRG').decode());b.key(13)
b.check(folder+b'/',after[8:],base=8,device=2,error='DISK I/O ERROR')
result=dict(passed=True,instructions=b.instructions,events=b.events,commands=[cmd.hex() for cmd in b.ultimate.commands],
            final_base=b.base(),final_page=[entry.hex() for entry in b.page()],
            caveat='Deterministic DOS model; does not reproduce cartridge timing.')
Path('/var/tmp/arc-scratch/uos-module-usb-return-model.json').write_text(json.dumps(result,indent=2)+'\n')
print(result['passed'],result['final_base'],result['final_page'])
