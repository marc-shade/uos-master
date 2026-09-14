#!/usr/bin/env python3
"""Execute Ultimate folder creation, exact UI frames and failure recovery."""
import argparse
import hashlib
import json
from pathlib import Path
import posixpath

import ci_native_files_gui as gui
from ci_native_directory_ultimate import DirectoryDOS
from ci_native_vdc_files import Files as VDCFiles, VDCBus
from native_browser_check import screen_bytes
from native_field_check import field_cells
from native_files_scene import surface

CAPTURES = None
CAPTURE_COUNT = 0


class FolderDOS(DirectoryDOS):
    """Model directory state separately from the native code and FIFO driver."""
    def __init__(self):
        super().__init__()
        self.refuse_create = None
        self.last_path = None

    def respond(self, command):
        context, op = command[:2]
        if op not in (8, 0x16):
            return super().respond(command)
        assert context in (1, 2)
        raw = command[2:]
        if op == 8:
            assert raw.endswith(b'\0') and b'\0' not in raw[:-1], command
            raw = raw[:-1]
        assert raw.startswith(b'/') and 1 <= len(raw) <= 255 and b'\0' not in raw
        path = posixpath.normpath(raw)
        existing = next((p for p in (*self.directories, *self.files)
                         if p.upper() == path.upper()), None)
        if op == 8:
            if existing is None:
                return [(b'', b'88,FILE NOT FOUND')]
            attr = 0x10 if existing in self.directories else 0x20
            return [(bytes(11)+bytes([attr])+posixpath.basename(existing)[:63], b'00,OK')]
        self.last_path = raw
        if self.refuse_create:
            return [(b'', self.refuse_create)]
        if existing is not None:
            return [(b'', b'FILE EXISTS')]
        parent, leaf = posixpath.split(path)
        if parent not in self.directories:
            return [(b'', b'NO PATH')]
        self.directories[path] = []
        self.directories[parent].append(b'\x10'+leaf)
        self.directories[parent].sort(key=lambda v: (not v[0] & 16, v[1:].upper()))
        return [(b'', b'00,OK')]


MESSAGES = (
    'NEW FOLDER; EXISTING NAMES ARE KEPT',
    'USE A VALID NAME OF 1-127 BYTES',
    'COMPLETE PATH EXCEEDS 255 BYTES',
    'FOLDER CREATED AND CHECKED',
    'CREATE FAILED; BACK REFRESHES',
    'RESULT UNKNOWN; BACK REFRESHES',
    'CLOSE DIRECTORY FAILED; BACK RETRIES',
)


def fixture(*, size=None, path=b'/Usb0', entries=(), context=1):
    old = gui.PointerBus
    if size:
        gui.PointerBus = type('FolderVDC', (VDCBus,), dict(size=size))
    try:
        cls = VDCFiles if size else gui.GraphicalFiles
        p = cls({(9,b'ORIGINAL',b'S'):b'KEEP'}, directories={b'/Usb0':[]})
    finally:
        gui.PointerBus = old
    dos = FolderDOS()
    dos.directories[path] = list(entries)
    p.ultimate = dos
    p.m.bus.dos = dos
    p.type('FFF')
    if context == 2:
        p.key(0x85)
    if bytes(p.ram[0x4a00:0x4a00+p.ram[0x3d2e]]) != path:
        p.ram[0x4a00:0x4a00+len(path)]=path
        p.ram[0x3d2e]=len(path);p.ram[0x3d34]=0
        p.key(ord('R'))
    p.checked_folders = 0
    return p


def dialog(p, name=b'', *, result=0, sent=False, caret=None, path=b'/Usb0', context=1):
    global CAPTURE_COUNT
    assert p.value('fm_active') == 1 and p.value('fm_sent') == sent
    assert p.value('fm_result') == result
    assert p.data('fm_name', p.value('fm_length')) == name
    assert p.ram[0x3d1b] == 3, 'modal module must remain resident until it returns'
    state = p.data('fm_state', 8)
    if caret is None:
        caret = len(name)
    assert state[1] == caret
    lines = ['']*25
    lines[0] = 'FOLDER NAME IN CURRENT DIRECTORY'
    lines[1] = path[-37:].decode('ascii').upper()
    lines[2] = 'DOS: '+str(context)
    lines[9] = MESSAGES[result]
    if p.value('fm_error'):
        lines[10] = f"ERROR: {p.value('fm_error'):02X}  DOS: {p.value('fm_dos'):02X}"
        lines[11] = p.data('fm_status',32).split(b'\0')[0].decode('ascii').upper()
    body = bytearray(screen_bytes(40, lines))
    body[280:318] = field_cells(name,38,caret,state[5])
    rows = gui.ascii_rows(body)
    assert p.data('fv_body',1000) == b''.join(rows), ('complete folder text',
        [(i,a,b) for i,(a,b) in enumerate(zip(p.data('fv_body',1000),b''.join(rows))) if a!=b][:25])
    expected = surface(rows,view=7,focus=p.value('ui_selected'),
                       caret=caret-state[5]+1,folder_sent=sent)
    actual = bytes(p.ram[0xc000:0xe400])
    assert actual == expected, ('complete folder bitmap', [(i,a,b) for i,(a,b)
                                 in enumerate(zip(actual,expected)) if a != b][:12])
    if isinstance(p,VDCFiles):
        p.mirror()
    else:
        # The fallback prints the shared, uppercase bitmap text. Stored
        # filename bytes retain their original case independently of display.
        body=bytearray(v-64 if 64<=v<96 else v-32 if 96<=v<128 else v
                       for v in b''.join(rows))
        if p.value('ui_selected')==25:
            body[280+caret-state[5]+1]|=128
        wanted = bytearray(screen_bytes(80, ['']*25))
        for row in range(13):
            wanted[row*80:row*80+40] = body[row*40:row*40+40]
        expected_console=p.footer(wanted)
        assert p.screens[1] == expected_console, ('complete VDC text fallback',
            [(i,a,b) for i,(a,b) in enumerate(zip(p.screens[1],expected_console)) if a!=b][:25],
            len(p.screens[1]),len(expected_console))
    if CAPTURES is not None:
        prefix=f'{CAPTURE_COUNT:03d}';CAPTURE_COUNT+=1
        (CAPTURES/(prefix+'-actual.vic')).write_bytes(actual)
        (CAPTURES/(prefix+'-expected.vic')).write_bytes(expected)
        metadata=dict(name_hex=name.hex(),parent_hex=path.hex(),context=context,
                      result=result,sent=sent,focus=p.value('ui_selected'),caret=caret,
                      viewport=state[5],instructions=p.instructions,keys=p.events,
                      vdc_size=p.bus.size if isinstance(p,VDCFiles) else 0)
        if isinstance(p,VDCFiles):
            base=p.value('vd_base')*256
            (CAPTURES/(prefix+'-vdc.bin')).write_bytes(p.bus.bytes(base,16000))
            if p.bus.size==64:
                (CAPTURES/(prefix+'-attributes.bin')).write_bytes(p.bus.bytes(0x8000,2000))
            metadata.update(pointer_x=p.position[0],pointer_y=p.position[1],
                            pointer_visible=bool(p.value('vd_pointer_visible')))
        else:
            (CAPTURES/(prefix+'-actual.console')).write_bytes(p.screens[1])
            (CAPTURES/(prefix+'-expected.console')).write_bytes(expected_console)
        (CAPTURES/(prefix+'.json')).write_text(json.dumps(metadata,indent=2)+'\n')
    p.checked_folders += 1


def leave(p):
    p.key(27)
    assert not p.value('fm_active') and p.ram[0x3d1b] == 2


def seed_name(p,name):
    # Long-path packet tests do not repeat the separately qualified keyboard
    # insertion loop for every byte. End still runs the actual field service.
    assert len(name)<=127
    at=p.symbol('fm_name');p.ram[at:at+len(name)+1]=name+b'\0'
    p.ram[p.symbol('fm_length')]=len(name)
    p.key(5)


def finish(p):
    p.key(27,exited=True)
    p.clean();p.restored()
    assert p.ultimate.paths == {1:b'/shell',2:b'/browser'}
    assert p.ultimate.handles == {1:None,2:None}
    assert p.ultimate.state == 0


def main():
    global CAPTURES
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--group',choices=('all','ui','bounds','faults','safety'),default='all')
    args=parser.parse_args()
    CAPTURES=args.report.parent/(args.report.stem+'-captures')
    CAPTURES.mkdir(exist_ok=False)
    report=dict(passed=False,physical_hardware_io=False,cases=[])
    def done(name,p,**extra):
        report['cases'].append(dict(name=name,keys=p.events,canvases=p.checked_folders,
                                   instructions=p.instructions,commands=[c.hex() for c in p.ultimate.commands],**extra))
        args.report.write_text(json.dumps(report,indent=2)+'\n')
        print('PASS:',name,flush=True)
    try:
        if args.group in ('all','ui'):
            for size in (None,16,64):
                p=fixture(size=size,entries=[b'\x20KEEP'])
                prefs=p.preferences();p.key(11);dialog(p)
                p.type('NEW FOLDER');dialog(p,b'NEW FOLDER')
                p.key(157);p.key(20);p.key(ord('R'));dialog(p,b'NEW FOLDRR',caret=9)
                p.key(21);p.type('NEW FOLDER');p.key(13)
                dialog(p,b'NEW FOLDER',result=3,sent=True)
                assert p.ultimate.last_path==b'/Usb0/NEW FOLDER'
                assert p.ultimate.paths=={1:b'/shell',2:b'/browser'}
                writes=sum(c[1]==0x16 for c in p.ultimate.commands)
                p.type('UNCHANGED');dialog(p,b'NEW FOLDER',result=3,sent=True)
                assert sum(c[1]==0x16 for c in p.ultimate.commands)==writes==1
                leave(p)
                assert p.data('bu_path',p.value('bu_length'))==b'/Usb0'
                p.key(13)
                assert p.data('bu_path',p.value('bu_length'))==b'/Usb0/NEW FOLDER'
                p.key(ord('P'))
                assert p.data('bu_path',p.value('bu_length'))==b'/Usb0'
                finish(p);done(f'keyboard create, check, reopen and parent; VDC {size or "text"}',p)
            p=fixture(size=64,entries=[b'\x20KEEP'])
            prefs=p.preferences();commands=len(p.ultimate.commands)
            p.frame();p.click(30);dialog(p);p.type('CANCELLED');p.click(27)
            assert p.preferences()==prefs and len(p.ultimate.commands)==commands
            p.click(30);p.type('MOUSE DIR');p.click(26);dialog(p,b'MOUSE DIR',result=3,sent=True)
            p.click(27);finish(p);done('1351 entry, cancellation without I/O, Create and Back',p)
            p=fixture(context=2,entries=[b'\x20'+f'FILE{i:02}'.encode() for i in range(12)])
            assert p.value('bu_cursor')
            p.key(11);p.type('SECOND');p.key(13);dialog(p,b'SECOND',result=3,sent=True,context=2)
            assert not p.value('bu_cursor') and p.ultimate.cancel_attempts==1
            assert all(c[0]==2 for c in p.ultimate.commands if c[1] in (8,0x16))
            leave(p);finish(p);done('second DOS context and pending directory packet release',p)
        if args.group in ('all','bounds'):
            p=fixture();p.key(11)
            for name in (b'',b'.',b'..',b'END.',b'END ',b'A/B',b'A\\B',b'A:B',b'A*B',b'A?B',b'A"B',b'A<B',b'A>B',b'A|B'):
                p.key(21);p.type(name.decode());before=len(p.ultimate.commands);p.key(13)
                dialog(p,name,result=1)
                assert len(p.ultimate.commands)==before
            leave(p);finish(p);done('invalid leaf names cannot submit a packet',p)
            for path,length in ((b'/',127),(b'/Usb0',127),(b'/'+b'P'*126,127),
                                (b'/'+b'P'*127+b'/'+b'Q'*120,5)):
                p=fixture(path=path);p.key(11);name=b'N'*length;seed_name(p,name);p.key(13)
                dialog(p,name,result=3,sent=True,path=path)
                cmd=next(c for c in p.ultimate.commands if c[1]==0x16)
                stat=next(c for c in p.ultimate.commands if c[1]==8)
                joined=path.rstrip(b'/')+b'/'+name
                assert cmd[2:]==joined and stat[2:]==joined+b'\0'
                assert len(cmd)==2+len(joined) and len(stat)==3+len(joined)
                leave(p);finish(p);done(f'{len(joined)}-byte absolute path, parent length {len(path)}',p)
            path=b'/'+b'P'*127
            p=fixture(path=path);p.key(11);seed_name(p,b'X'*127);before=len(p.ultimate.commands);p.key(13)
            dialog(p,b'X'*127,result=2,path=path);assert len(p.ultimate.commands)==before
            leave(p);finish(p);done('256-byte joined path refused before I/O',p)
        if args.group in ('all','faults'):
            p=fixture(entries=[b'\x10EXISTS',b'\x20KEPT'])
            p.ultimate.directories[b'/Usb0/EXISTS']=[b'\x20ORIGINAL']
            p.ultimate.files[b'/Usb0/KEPT']=b'ORIGINAL BYTES'
            for target,name in (('directory',b'EXISTS'),('file',b'KEPT')):
                p.key(11);p.type(name.decode());p.key(13);dialog(p,name,result=4,sent=True)
                assert p.ultimate.directories[b'/Usb0/EXISTS']==[b'\x20ORIGINAL']
                assert p.ultimate.files[b'/Usb0/KEPT']==b'ORIGINAL BYTES'
                leave(p);done('existing '+target+' preserved',p)
            for response in (b'WRITE PROTECTED',b'NO SPACE'):
                p.ultimate.refuse_create=response
                p.key(11);p.type('NO');p.key(13);dialog(p,b'NO',result=4,sent=True)
                assert b'/Usb0/NO' not in p.ultimate.directories
                leave(p);done(response.decode(),p)
            p.ultimate.refuse_create=None
            for index,reply in enumerate(([(b'',b'88,FILE NOT FOUND')],[(bytes(12),b'00,OK')],
                          [(bytes(11)+b'\x20NAME',b'00,OK')],[(bytes(76),b'00,OK')],
                          [(bytes(11)+b'\x10XX',b'00,OK')])):
                name=f'F{index}'.encode()
                p.ultimate.inject[8]=lambda cmd,want,r=reply:r
                p.key(11);p.type(name.decode());p.key(13);dialog(p,name,result=5,sent=True)
                before=len(p.ultimate.commands);p.type('TRY');assert len(p.ultimate.commands)==before
                assert b'/Usb0/'+name in p.ultimate.directories
                leave(p);done('unverifiable metadata '+str(index),p)
            p.ultimate.inject.clear()
            p.ultimate.inject[0x16]=lambda cmd,want:[(b'EXTRA',b'00,OK')]
            p.key(11);p.type('EXTRA');p.key(13);dialog(p,b'EXTRA',result=5,sent=True)
            assert p.ultimate.commands[-1][1]==0x16
            p.ultimate.inject.clear();leave(p);done('unexpected create reply stops verification and replay',p)
            p.ultimate.inject[8]=lambda cmd,want:[(want[0][0].upper(),b'00,OK')]
            p.key(11);p.type('lower');p.key(13);dialog(p,b'lower',result=3,sent=True)
            p.ultimate.inject.clear();leave(p);done('metadata accepts ASCII case differences',p)
            finish(p)
        if args.group in ('all','safety'):
            p=fixture()
            foreign=dict(name=b'/external',mode=1,pos=7)
            p.ultimate.files[b'/external']=b'FOREIGN FILE'
            p.ultimate.handles[2]=foreign.copy()
            p.key(11);p.type('SHARED');p.key(13);dialog(p,b'SHARED',result=3,sent=True)
            assert p.ultimate.handles[2]==foreign and p.ultimate.paths=={1:b'/shell',2:b'/browser'}
            leave(p);done('foreign file position and both DOS working directories preserved',p)
            p.key(11);p.type('BUSY');before=len(p.ultimate.commands)
            aborted=p.ultimate.cancel_attempts
            p.ultimate.state=0x10;p.ultimate.stuck=True;p.key(13)
            dialog(p,b'BUSY',result=5,sent=True)
            assert p.value('fm_error')==0x15 and p.ram[0x3d90]==0xe2
            assert len(p.ultimate.commands)==before and p.ultimate.cancel_attempts==aborted
            assert p.ultimate.handles[2]==foreign
            p.ultimate.state=0;p.ultimate.stuck=False
            p.ultimate.handles[2]=None  # independent fixture owner releases its file
            leave(p);finish(p);done('foreign transaction refused without abort or replay',p)
            p=fixture(entries=[b'\x20'+f'FILE{i:02}'.encode() for i in range(12)])
            assert p.value('bu_cursor')
            p.ultimate.ignore_abort=True;p.key(11);p.type('CLOSE');p.key(13)
            dialog(p,b'CLOSE',result=6,sent=True)
            assert p.value('bu_cursor') and not any(c[1]==0x16 for c in p.ultimate.commands)
            p.ultimate.ignore_abort=False;leave(p);finish(p)
            done('uncertain cursor close retains ownership and blocks creation',p)
            p=fixture(size=64);p.key(11);p.type('DISPLAY')
            before=len(p.ultimate.commands);p.bus.stall=True;p.key(9)
            assert p.value('vd_fault') and not p.value('fm_sent')
            for key in (13,ord('A'),13):p.key(key)
            assert len(p.ultimate.commands)==before
            p.bus.stall=False;p.vdc_expected=False
            step=p.cpu.step;at=p.symbol('fm_leave');restored=[]
            def observe_restore():
                if p.cpu.pc==at:
                    assert not p.value('vd_phase')
                    assert p.bus.video_ram==p.bus.original[0]
                    restored.append(True)
                return step()
            p.cpu.step=observe_restore;leave(p);p.cpu.step=step
            assert restored==[True]
            # The resumed text browser now legitimately updates VDC text RAM.
            # Its earlier graphics snapshot was checked before that first draw.
            p.bus.original=None;finish(p)
            done('failed VDC presentation freezes creation until Escape restores',p,restore_before_text=True)
        report['passed']=True
    finally:
        args.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
