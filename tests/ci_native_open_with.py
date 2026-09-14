#!/usr/bin/env python3
"""Execute Files -> document app -> Files -> Desktop on one native kernel."""
import argparse
import hashlib
import json
from pathlib import Path
import traceback

from py65.devices.mpu6502 import MPU
from ci_native_calc import Calculator, ROOT
from ci_native_heap import symbol as kernel_symbol
from ci_native_files_gui import GraphicalFiles
from ci_native_editor_gui import GraphicalEditor
from ci_native_paint_gui import GraphicalPaint
from ci_native_paint_files import pattern
from native_paint_format import encode
APP_JUMP=kernel_symbol('app_jump')
NATIVE_DRAW=kernel_symbol('native_draw')


class Suite:
    symbol=Calculator.symbol
    value=Calculator.value

    def __init__(self,files,*,omit=()):
        self.__dict__.update(files.__dict__)
        for app,name in [('editor','EDITOR'),('paint','PAINT'),('files','FILES'),('desktop','BROWSE'),('calc','CALC')]:
            self.io.files[8,name.encode(),b'P']=(ROOT/f'target/native-desktop/{app}.prg').read_bytes()
        for name in ('edpick','edfind','edclip','fspick','fsview','fsopen','vdsvc'):
            self.io.files[8,name.upper().encode()+b'.PRG',b'P']=(ROOT/f'target/native-desktop/{name}.prg').read_bytes()
        for name in omit:self.io.files.pop((8,name,b'P'),None)
        self.cpu=MPU(memory=self.m.bus,pc=kernel_symbol('native_dispatch'))
        self.cpu.sp=0xe0;self.cpu.p=0x20
        self.ram[kernel_symbol('ui_system_device')]=8
        self.ram[kernel_symbol('ui_browser_stage')]=0
        self.entered=[];self.canvases=0;self.steps=0;self.preview_stream=None

    def output(self,value):
        screen=self.ram[0xd7]>>7;row,col=self.row[screen],self.col[screen]
        Calculator.output(self,value)
        if self.image_name=='editor' and value==34:self.ram[0xf4]=1
        chip=self.m.bus
        while not hasattr(chip,'vwrite') and hasattr(chip,'native'):chip=chip.native
        if screen and hasattr(chip,'vwrite'):
            assert not self.value('vd_phase'),'ROM output during VDC ownership'
            if value==0x93:
                for i in range(2000):chip.vwrite(i,32);chip.vwrite(0x800+i,15)
            elif 32<=value<128:
                chip.vwrite(row*80+col,self.screens[1][row*80+col]);chip.vwrite(0x800+row*80+col,15)

    def run(self,expected):
        cpu=self.cpu
        for steps in range(150000000):
            if cpu.pc==APP_JUMP:
                name=bytes(self.ram[0x3d40:0x3d40+self.ram[0x3d22]])
                self.image_name={b'BROWSE':'desktop',b'EDITOR':'editor',b'PAINT':'paint',b'FILES':'files',b'CALC':'calc'}[name]
                self._symbol_cache={}
                if hasattr(self.bus,'video_ram'):self.bus.original=None
                self.entered.append(dict(app=self.image_name,request=self.ram[0x3d9a],kind=self.ram[0x3d9b]))
                print('Entered',self.image_name,'request',self.ram[0x3d9a],flush=True)
            if expected=='workspace' and cpu.pc==NATIVE_DRAW:
                assert self.m.stats()==(175,251,32) and not self.io.handles
                assert not any(self.ram[0x3d9a:0x3d9b]+self.ram[0x3d9d:0x3d9f])
                self.steps+=steps;return
            if cpu.pc==0xffe4 and not self.keys and self.ram[0x3d12]:
                assert self.image_name==expected,(self.image_name,expected,self.entered)
                assert self.ram[0x3d20:0x3d21]==b'\x20' and self.ram[0x3d23]==2
                if self.preview_stream is None:
                    assert not self.io.handles,'ready with an unexpected open file'
                else:
                    assert self.image_name=='files' and self.value('b_preview')==self.value('b_open')==1
                    assert set(self.io.handles)=={122,124},'only the preview data and status channels may remain open'
                    data,status=self.io.handles[122],self.io.handles[124]
                    assert data['key']==self.preview_stream and data['mode']==b'R'
                    assert status['device']==self.preview_stream[0] and status['sa']==15
                self.steps+=steps;return
            if self.io.stub(cpu):continue
            if cpu.pc in (0xffe4,0xffd2,0xff5f,0xfff0):
                if cpu.pc==0xffe4:
                    cpu.a=self.keys.pop(0) if self.keys else 0;cpu.FlagsNZ(cpu.a)
                elif cpu.pc==0xffd2:self.output(cpu.a)
                elif cpu.pc==0xff5f:self.ram[0xd7]^=0x80
                elif cpu.p&1:
                    screen=self.ram[0xd7]>>7;cpu.x,cpu.y=self.row[screen],self.col[screen]
                else:
                    screen=self.ram[0xd7]>>7
                    assert cpu.x<25 and cpu.y<(40,80)[screen]
                    self.row[screen],self.col[screen]=cpu.x,cpu.y
                cpu.pc=(cpu.stPopWord()+1)&65535
            else:cpu.step()
        raise AssertionError(('dispatch did not settle',expected,hex(cpu.pc),self.entered))

    def key(self,key,expected=None):
        before=int.from_bytes(self.ram[0x3d13:0x3d15],'little')
        self.keys.append(key);self.run(expected or self.image_name)
        assert int.from_bytes(self.ram[0x3d13:0x3d15],'little')==(before+1)&65535

    def view(self):
        cls={'files':GraphicalFiles,'editor':GraphicalEditor,'paint':GraphicalPaint}[self.image_name]
        view=object.__new__(cls);view.__dict__.update(self.__dict__)
        view.checked=0
        if self.image_name=='editor':view.symbols={'d_states':view.symbol('d_states')}
        return view

    def check_editor(self,data,**kw):
        self.view().check(data,**kw);self.canvases+=1
        assert not self.ram[0x3d9a]

    def check_files(self,**kw):
        self.view().browser(**kw);self.canvases+=1
        assert not any(self.ram[0x3d9a:0x3d9b]+self.ram[0x3d9d:0x3d9f])

    def finish(self):
        if self.image_name=='files':self.key(27,'desktop')
        assert self.image_name=='desktop'
        self.key(ord('E'),'editor');self.check_editor(b'',cursor=0,dirty=False,name='')
        self.key(27,'desktop');self.key(27,'workspace')


def published(files,kind,name,device,fmt):
    ram=files.ram
    assert ram[0x3d9a]==128 and ram[0x3d9b]==kind and ram[0x3d9d]==1
    assert bytes(ram[0x3d29:0x3d2b])==bytes([device,fmt])
    assert bytes(ram[0x3e00:0x3e00+ram[0x3d34]])==name
    assert ram[0x3d21]==8 and ram[0x3d2c]==0,'app source must remain the boot volume'
    assert bytes(ram[0x3d40:0x3d40+ram[0x3d22]])==(b'EDITOR',b'PAINT')[kind-1]
    assert ram[0x3d28]==1 and files.m.stats()==(175,251,32) and not files.io.handles


def iec_case(fmt):
    raw=(bytes(range(32,127))+b'\r\n')*3+b'\0\xffEND'
    picture=pattern(71);binary=bytes(range(256))*2
    entries={(9,b'FIRST',b'S'):b'FIRST',(9,b'NOTES.TXT',b'U'):raw,
             (9,b'SCENE.TXT',b'P'):encode(picture),(9,b'BINARY',b'S'):binary}
    files=GraphicalFiles(entries,device=9,fmt=fmt)
    files.key(0x11);files.browser(device=9,fmt=fmt,selected=1)
    files.key(13,exited=True);files.restored();published(files,1,b'NOTES.TXT',9,fmt)
    suite=Suite(files);suite.run('editor')
    suite.check_editor(raw,cursor=0,dirty=False,name='NOTES.TXT',status=0)
    assert suite.value('ed_file_type')==2
    suite.key(ord('Z'));suite.check_editor(b'Z'+raw,dirty=True)
    suite.key(26);suite.check_editor(raw,cursor=0,dirty=False,status=27)
    # Model another directory writer moving the first record to the end.
    # A return must find the same raw name, independently of its old ordinal.
    shift=int(fmt==2)
    if shift:
        first=suite.io.files.pop((9,b'FIRST',b'S'))
        suite.io.files[9,b'FIRST',b'S']=first
    suite.key(27,'files');suite.check_files(device=9,fmt=fmt,selected=1-shift)
    suite.key(0x11);suite.key(13,'paint')
    view=suite.view();view.check();assert view.document()==picture and not view.value('pd_dirty')
    assert view.value('pf_type')==1 and view.value('pf_format')==fmt and view.value('pf_device')==9
    suite.canvases+=1
    suite.key(27,'files');suite.check_files(device=9,fmt=fmt,selected=2-shift)
    suite.key(0x11);suite.preview_stream=(9,b'BINARY',b'S');suite.key(13)
    suite.view().preview(b'BINARY',binary[:128]);suite.key(13)
    suite.view().preview(b'BINARY',binary[128:256],offset=128);suite.canvases+=2
    suite.preview_stream=None;suite.key(27);suite.check_files(device=9,fmt=fmt,selected=3-shift)
    suite.finish()
    assert all(bytes(suite.io.files[k])==v for k,v in entries.items())
    return dict(name='IEC geometry '+str(fmt)+' automatic text/picture, Undo, byte viewer and return',
                entered=suite.entered,instructions=suite.steps+files.instructions,canvases=suite.canvases,
                document_sha256=hashlib.sha256(raw).hexdigest(),external_directory_reordered=bool(shift))


def failure_case(kind):
    data=b'SELECTED DOCUMENT'
    files=GraphicalFiles({(9,b'README.TXT',b'S'):data},device=9)
    files.key(5,exited=True);published(files,1,b'README.TXT',9,0)
    omit=(b'EDITOR',) if kind=='app' else ()
    suite=Suite(files,omit=omit)
    if kind=='document':suite.io.files.pop((9,b'README.TXT',b'S'))
    if kind=='wrong-kind':suite.ram[0x3d9b]=2
    if kind=='stale':suite.ram[0x3d9a]=1
    if kind=='files':suite.io.files.pop((8,b'FILES',b'P'))
    suite.run('files' if kind=='app' else 'editor')
    if kind=='app':
        assert suite.value('b_launch_error') and not suite.ram[0x3d9a]
        suite.io.files[8,b'EDITOR',b'P']=(ROOT/'target/native-desktop/editor.prg').read_bytes()
    else:
        suite.check_editor(data if kind=='files' else b'',dirty=False)
        if kind in ('document','wrong-kind'):assert suite.value('ed_status')==2
        suite.key(27,'desktop' if kind=='files' else 'files')
        if kind=='document':suite.check_files(device=9,selected=0)
    suite.finish()
    return dict(name='failure '+kind+' expires request and reaches Desktop',entered=suite.entered,
                instructions=suite.steps+files.instructions,canvases=suite.canvases)


def ultimate_case(context):
    folder=b'/'+b'D'*246;leaf=b'DOC.TXT';path=folder+b'/'+leaf
    assert len(path)==255
    data=b'EXACT ULTIMATE PATH\r\n'+bytes(range(32,127));picture=pattern(143)
    paint_path=folder+b'/CANVAS';usb={path:data,paint_path:encode(picture)}
    directories={b'/':[b'\x10'+folder[1:]],folder:[b'\x20'+leaf,b'\x20CANVAS']}
    files=GraphicalFiles(usb=usb,directories=directories)
    files.type('FFF')
    if context==2:files.key(0x85)
    files.key(13);files.ultimate_browser(folder,directories[folder],device=context)
    files.frame();files.click(28,exited=True);files.restored()
    published(files,1,leaf,context,3)
    suite=Suite(files);suite.run('editor')
    suite.check_editor(data,cursor=0,dirty=False,name=path.decode(),status=0)
    assert suite.value('ed_device')==context and suite.value('ed_format')==3
    suite.key(27,'files')
    suite.view().ultimate_browser(folder,directories[folder],device=context);suite.canvases+=1
    suite.key(0x11);suite.key(16,'paint')
    view=suite.view();view.check();assert view.document()==picture
    assert bytes(suite.ram[view.symbol('pf_name'):view.symbol('pf_name')+view.value('pf_length')])==paint_path
    suite.canvases+=1;suite.key(27,'files')
    suite.view().ultimate_browser(folder,directories[folder],selected=1,device=context);suite.canvases+=1
    suite.finish()
    assert suite.ultimate.handles=={1:None,2:None}
    assert all(bytes(suite.ultimate.files[p])==v for p,v in usb.items())
    return dict(name='Ultimate context '+str(context)+' 255-byte path, mouse Edit, Paint and raw-name return',
                entered=suite.entered,instructions=suite.steps+files.instructions,canvases=suite.canvases,
                path_hex=path.hex(),document_sha256=hashlib.sha256(data).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=('iec0','iec1','iec2','ultimate1','ultimate2','app','document','wrong-kind','stale','files'),required=True)
    parser.add_argument('--vdc-kib',type=int,choices=(16,64))
    parser.add_argument('--reu-kib',type=int,choices=(512,))
    parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    if args.reu_kib:assert args.vdc_kib
    if args.vdc_kib:
        import ci_native_files_gui as files_gui
        from ci_native_vdc_files import Files as GraphicalFiles
        from ci_native_vdc_editor import Editor as GraphicalEditor
        from ci_native_vdc_paint import Paint as GraphicalPaint
        from ci_native_vdc_desktop import VDCBus
        options=dict(size=args.vdc_kib)
        if args.reu_kib:
            from ci_native_reu_calc import CalculatorBus as VDCBus
            options['reu_kib']=args.reu_kib
        files_gui.PointerBus=type('OpenWithBus',(VDCBus,),options)
        GraphicalFiles.instruction_limit=120000000
    report=dict(passed=False,physical_hardware_io=False,cases=[],vdc_kib=args.vdc_kib,reu_kib=args.reu_kib)
    try:
        report['cases']=[iec_case(int(args.case[-1])) if args.case.startswith('iec') else ultimate_case(int(args.case[-1])) if args.case.startswith('ultimate') else failure_case(args.case)]
        report['passed']=True;print('PASS',args.case,flush=True)
    except BaseException:report['error']=traceback.format_exc();raise
    finally:args.report.write_text(json.dumps(report,indent=2)+'\n')
