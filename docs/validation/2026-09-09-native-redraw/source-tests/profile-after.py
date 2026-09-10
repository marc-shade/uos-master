import hashlib,json,sys,time
from pathlib import Path
ROOT=Path('/home/marc/geos128/uos');sys.path[:0]=[str(ROOT/'tests'),str(ROOT)]
from ci_native_editor_ultimate import UltimateEditor
class Counted(UltimateEditor):
 def __init__(self,files):
  self.outputs=[0,0];self.clears=[0,0]
  super().__init__(files)
 def output(self,value):
  screen=self.ram[0xd7]>>7;self.outputs[screen]+=1;self.clears[screen]+=value==0x93
  return super().output(value)
raw=(b'0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n'*1800)[:66053]
e=Counted({b'/SMALL':b'ONE "QUOTED" LINE\r\nTWO\nTHREE\r',b'/LARGE':raw})
report=dict(passed=False,source_commit='working-redraw',images={n:hashlib.sha256((ROOT/'target/native'/n).read_bytes()).hexdigest() for n in ('uos128.prg','editor.prg')},measurements={})
def measure(label,action):
 before=e.instructions;out=list(e.outputs);clears=list(e.clears)
 action()
 report['measurements'][label]=dict(cpu_instructions=e.instructions-before,chrout_calls=[a-b for a,b in zip(e.outputs,out)],screen_clears=[a-b for a,b in zip(e.clears,clears)])
 print(label,report['measurements'][label],flush=True)
e.prompt(0x85,'/SMALL');e.key(0x86)
measure('small-field-ten-characters',lambda:e.type('/Usb0/Note'))
e.check(b'ONE "QUOTED" LINE\r\nTWO\nTHREE\r',0,False,mode=2);e.key(27)
measure('small-insert-character',lambda:e.type('!'));e.key(20)
measure('small-cursor-right',lambda:e.key(0x1d))
e.key(0x87);e.type('Y');e.prompt(0x85,'/LARGE');e.prompt(0x88,'010001')
e.key(0x86);measure('large-field-ten-characters',lambda:e.type('/Usb0/Note'))
e.check(raw,65537,False,mode=2);e.key(27)
measure('large-insert-character',lambda:e.type('!'))
measure('large-backspace-character',lambda:e.key(20))
measure('large-cursor-right',lambda:e.key(0x1d))
e.check(raw,65538,True);e.exit(dirty=True)
assert report['images']=={n:hashlib.sha256((ROOT/'target/native'/n).read_bytes()).hexdigest() for n in ('uos128.prg','editor.prg')}
report['passed']=True
Path('/tmp/native-editor-redraw-current.json').write_text(json.dumps(report,indent=2)+'\n')
