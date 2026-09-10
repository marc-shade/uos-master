"""Independent text/layout and stored-byte checks for the native editor."""
import hashlib
import re
import shutil
import subprocess
import time

from hwlib import lst_symbol
from native_browser_check import BrowserClient,disk_records,browser_screen
from native_capture import ROOT,expected_screen,verify_boot_layout,wait

STATUS=(
    'HOME: LINE START  CTRL-E: LINE END',
    'SAVED AND REOPENED: ALL BYTES VERIFIED',
    'DISK ERROR; DOCUMENT KEPT',
    'NOT ENOUGH MEMORY; DOCUMENT KEPT',
    'POSITION OR DEVICE IS OUT OF RANGE',
    'DOCUMENT MEMORY ERROR; CANNOT SAVE',
    'FILE EXISTS; CHOOSE ANOTHER NAME',
    'SAVE FAILED; FILE MAY BE PARTIAL',
    'CANCELLED; DOCUMENT KEPT',
    'DISK CLOSE FAILED; DOCUMENT KEPT',
    'CANCELLED; PARTIAL FILE MAY REMAIN',
    'OPENED; OLD BUFFER CLEANUP FAILED',
)


def document_lines(data):
    lines=[];start=0
    for match in re.finditer(rb'\r\n|\r|\n',data):
        lines.append((start,data[start:match.start()],match.group()))
        start=match.end()
    lines.append((start,data[start:],b''))
    return lines


def editor_screen(columns,data,cursor,*,name='',dirty=False,device=8,fmt=0,
                  view=0,horizontal=0,mode=0,field='',status=0):
    assert 0<=cursor<=len(data) and columns in (40,80)
    def tail(text,limit):return text if len(text)<=limit else '<'+text[-(limit-1):]
    message=STATUS[status]
    if mode and status!=4:
        message='DISCARD DOCUMENT CHANGES? Y/N' if mode==5 else (
            ('OPEN: ','SAVE AS: ','BYTE (HEX): ','DOS CONTEXT: ' if fmt==3 else 'IEC DEVICE: ')[mode-1]+tail(field,columns-24)+'  ENTER/ESC')
    headers=['UOS 128 TEXT EDITOR','NAME: '+tail(name or 'UNTITLED',columns-8)+('*' if dirty else ''),
             f'BYTES: {len(data):06X} AT: {cursor:06X} '+('DOS' if fmt==3 else 'IEC')+f':{device:02} '+('D64','D71','D81','ULT')[fmt],
             'F1 OPEN F3 SAVE AS F5 NEW F7 GO TO','F2 TOP F4 END F6 FORMAT F8 DEVICE',
             'ARROWS MOVE  DEL ERASE  ESC RETURN',message]
    assert all(len(line)<columns for line in headers)
    def code(value):return value-64 if 64<=value<96 else value-32 if 96<=value<128 else value
    screen=bytearray(b' '*(columns*25))
    for row,line in enumerate(headers):
        screen[row*columns:row*columns+len(line)]=bytes(code(ord(char)) for char in line)
    lines=document_lines(data);starts=[line[0] for line in lines]
    assert view in starts,(view,starts[:20])
    first=starts.index(view);width=columns-2;caret=False
    for row in range(16):
        base=(row+7)*columns
        screen[base]=ord('<') if horizontal else 32
        if first+row>=len(lines):continue
        start,content,separator=lines[first+row]
        visible=content[horizontal:horizontal+width]
        screen[base+1:base+1+len(visible)]=bytes(code(value if 32<=value<127 else 46) for value in visible)
        screen[base+columns-1]=ord('>') if len(content)>horizontal+width else 32
        end=start+len(content)
        owns_cursor=start<=cursor<end+len(separator) or (not separator and start<=cursor<=end)
        if owns_cursor and not caret:
            column=min(cursor-start,len(content))-horizontal
            assert 0<=column<=width,(columns,cursor,start,horizontal)
            screen[base+1+column]|=128;caret=True
    assert caret,'cursor must remain visible on both displays'
    return bytes(screen)


def prepare_editor(work,fmt=0):
    disk=work/'native.d64';shutil.copyfile(ROOT/'target/native/uos128.d64',disk)
    if not fmt:
        # The D64 workflow needs the kernel, browser, editor, large source and
        # complete saved copy. Its private disk does not use the calculator.
        subprocess.run(['c1541','-attach',str(disk),'-delete','calc'],
                       check=True,capture_output=True)
    data_disk=work/('documents.'+('d64','d71','d81')[fmt]) if fmt else disk
    if fmt:
        subprocess.run(['c1541','-format','documents,02',('d64','d71','d81')[fmt],str(data_disk)],
                       check=True,capture_output=True)
    fixtures=dict(note=b'ONE "QUOTED" LINE\r\nTWO\nTHREE\r'+bytes([0,255])+b' END\r\n'+b'X'*110+b'\r\nLAST',
                  empty=b'',large=(b'0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n'*1800)[:66053])
    for name,data in fixtures.items():
        source=work/(name+'.seq');source.write_bytes(data)
        subprocess.run(['c1541','-attach',str(data_disk),'-write',str(source),name+',s'],check=True,capture_output=True)
    if not fmt:
        bam=disk.read_bytes()[357*256:358*256]
        free=sum(bam[track*4] for track in range(1,36) if track!=18)
        assert free>=(len(fixtures['large'])+3+253)//254,'editor fixture cannot hold the complete saved copy'
    return disk,data_disk,fixtures


class EditorClient(BrowserClient):
    """Drive actual GETIN, including its programmable-key expansion path."""
    def __init__(self,mon,work,*,quiet=.2,scan_quiet=2,capture_quiet=.2,poll=.1,key_timeout=300):
        super().__init__(mon,work,quiet,scan_quiet,capture_quiet)
        self.poll,self.key_timeout=poll,key_timeout
        self.editor_active=False;self.states=[];self.observations=[]
        self.addresses={name:lst_symbol('native/editor',name) for name in (
            'ed_active','ed_cursor','ed_view','ed_horizontal','ed_mode','ed_status','ed_device','ed_format',
            'ed_name','ed_field','ed_field_len','d_states','ed_saved_keys')}
        self.key_codes=bytes.fromhex('8589868a878b888c8384')

    def key(self,value,quiet=None):
        wait(lambda:self.read(0x3d12)==b'\1' and self.read(0xd0,3)==bytes(3),'native editor ready',120)
        before=int.from_bytes(self.read(0x3d13,2),'little');started=time.monotonic();last_notice=started
        self.put(0x3d12,b'\0')
        expansion=self.editor_active and value in self.key_codes
        if expansion:
            index=self.key_codes.index(value)
            assert self.read(0x1000,20)==bytes([1]*10)+self.key_codes
            # This is the ROM GETIN expansion path, not a physical matrix key.
            # Publish count/index together after the foreground loop is idle.
            self.put(0xd1,bytes([1,index]))
        else:
            self.put(0x34a,bytes([value]));self.put(0xd0,b'\1')
        time.sleep(self.quiet if quiet is None else quiet)
        while True:
            state=self.read(0x3d12,3)
            if state[0]==1 and int.from_bytes(state[1:],'little')==(before+1)&65535:break
            elapsed=time.monotonic()-started
            assert elapsed<self.key_timeout,('editor key timeout',value,elapsed,state.hex())
            if time.monotonic()-last_notice>=30:
                print(f'Native editor key {value:02X}: waiting for complete operation ({elapsed:.0f}s)',flush=True)
                last_notice=time.monotonic()
            time.sleep(self.poll)
        # KEYIDX can remain nonzero after the final expanded byte. KYNDX=0
        # means no expansion is pending; reset the idle index for the next key.
        assert self.read(0xd0,2)==bytes(2)
        self.put(0xd2,b'\0')
        self.events.append(dict(key=value,rom_expansion=expansion,elapsed_seconds=round(time.monotonic()-started,3),
                                app_state=self.read(0x3d20,13).hex(),files=self.read(0x3d80,0x64).hex()))

    def prompt(self,key,text,confirm=None):
        self.key(key)
        for value in text.encode():self.key(value)
        self.key(13,quiet=self.scan_quiet)
        if confirm is not None:self.key(ord(confirm),quiet=self.scan_quiet)

    def cpu_read(self,label,address,count):
        direct=self.read(address,count)
        actual=self.capture.capture(label,address=address,count=count)
        (self.work/(label+'-dma.bin')).write_bytes(direct)
        self.observations.append(dict(label=label,address=address,count=count,direct_matches_cpu=direct==actual,
                                      direct_sha256=hashlib.sha256(direct).hexdigest(),cpu_sha256=hashlib.sha256(actual).hexdigest()))
        return actual

    def check(self,label,data,cursor,*,dirty=False,name='',status=0,mode=0,device=8,fmt=0):
        addresses=self.addresses;base=addresses['ed_active']
        raw=self.cpu_read(label+'-app-state',base,addresses['ed_field_len']-base+1)
        def number(name,size=1):return int.from_bytes(raw[addresses[name]-base:addresses[name]-base+size],'little')
        def string(name):return raw[addresses[name]-base:addresses[name]-base+256].split(b'\0')[0].decode()
        context=self.cpu_read(label+'-document-state',addresses['d_states']+number('ed_active'),128)
        actual=dict(cursor=number('ed_cursor',3),view=number('ed_view',3),horizontal=number('ed_horizontal',3),
                    length=int.from_bytes(context[:3],'little'),dirty=context[12],chunks=context[13],fault=context[14],
                    name=string('ed_name'),status=number('ed_status'),mode=number('ed_mode'),
                    device=number('ed_device'),fmt=number('ed_format'))
        self.states.append(dict(label=label,**actual))
        assert (actual['cursor'],actual['length'],actual['dirty'],actual['fault'])==(cursor,len(data),int(dirty),0),(label,actual)
        assert (actual['name'],actual['status'],actual['mode'],actual['device'],actual['fmt'])==(name,status,mode,device,fmt),(label,actual)
        self.frames_equal(label,lambda columns:editor_screen(columns,data,cursor,name=name,dirty=dirty,device=device,fmt=fmt,
                          view=actual['view'],horizontal=actual['horizontal'],mode=mode,field=string('ed_field'),status=status))
        assert self.read(0x98)==b'\0' and self.read(0x3de0,4)==bytes(4),'editor retained a file channel'
        if len(data)>65536:
            records=self.read(0x3c00,256);banks=set()
            for index in range(context[13]):
                handle=context[16+index*4:20+index*4];record=records[(handle[0]-1)*8:handle[0]*8]
                assert record[0]==32 and record[3]==16 and record[4:7]==handle[1:]
                banks.add(record[1])
            assert banks=={0,1},banks
        return actual


def editor_workflow(client,disk,data_disk,fixtures,fmt,report,save):
    report.update(events=client.events,frames=client.frames,captures=client.capture.records,
                  heap_observations=client.heaps,editor_states=client.states,ram_observations=client.observations)
    report['resident_boot']=verify_boot_layout(client.capture)
    protected=[]
    for bank in (0,1):
        client.key(ord('1')+bank);client.key(ord('A'));page=client.read(0x3d03)[0]
        client.key(ord('W'));client.key(ord('V'));assert client.read(0x3d16)==b'\0'
        protected.append((bank,page))
    original_keys=client.read(0x1000,256);(client.work/'function-keys-before.bin').write_bytes(original_keys)
    client.key(ord('B'),quiet=client.scan_quiet)
    boot_records=disk_records(disk.read_bytes())
    client.select([r['name'] for r in boot_records].index(b'EDITOR'))
    client.key(13,quiet=client.scan_quiet);client.editor_active=True
    assert client.cpu_read('editor-saved-function-keys',client.addresses['ed_saved_keys'],256)==original_keys
    client.heap_equal('empty-editor-with-workspace',(143-((ROOT/'target/native/editor.prg').read_bytes()[12]),219,29))
    if fmt:
        client.prompt(0x8c,'9')
        for _ in range(fmt):client.key(0x8b)
    device=9 if fmt else 8
    def check(label,data,cursor,**extra):
        actual=client.check(label,data,cursor,device=device,fmt=fmt,**extra);save();return actual
    check('editor-new',b'',0)
    raw=fixtures['note'];client.prompt(0x85,'NOTE');check('editor-open-mixed-quotes',raw,0,name='NOTE')
    client.prompt(0x88,'000005');check('editor-caret-inside-quote',raw,5,name='NOTE')
    client.key(ord('!'));want=raw[:5]+b'!'+raw[5:];check('editor-insert',want,6,dirty=True,name='NOTE')
    client.prompt(0x85,'EMPTY');check('editor-discard-prompt',want,6,dirty=True,name='NOTE',mode=5)
    client.key(ord('N'));check('editor-declined-discard',want,6,dirty=True,name='NOTE')
    client.prompt(0x85,'MISSING',confirm='Y');check('editor-failed-open-retains',want,6,dirty=True,name='NOTE',status=2)
    client.prompt(0x85,'EMPTY',confirm='Y');check('editor-empty-file',b'',0,name='EMPTY')
    raw=fixtures['large'];client.prompt(0x85,'LARGE');check('editor-large-open',raw,0,name='LARGE')
    client.prompt(0x88,'010001');at=65537
    if raw[at-1:at+1]==b'\r\n':at+=1
    check('editor-cursor-over-64k',raw,at,name='LARGE')
    for value in b'C128':client.key(value)
    client.key(20);want=raw[:at]+b'C12'+raw[at:]
    check('editor-large-edited',want,at+3,dirty=True,name='LARGE')
    (client.work/'saved-expected.seq').write_bytes(want)
    client.prompt(0x86,'SAVED');check('editor-saved-verified',want,at+3,name='SAVED',status=1)
    client.prompt(0x86,'SAVED');check('editor-existing-file-rejected',want,at+3,name='SAVED',status=6)
    client.key(0x87);check('editor-new-after-save',b'',0)
    client.prompt(0x85,'SAVED');check('editor-reopened-saved',want,0,name='SAVED')
    client.prompt(0x88,f'{at:06X}');check('editor-reopened-edit-position',want,at,name='SAVED')
    client.key(27,quiet=client.scan_quiet);client.editor_active=False;client.selected=0
    assert client.read(0x1000,256)==original_keys
    (client.work/'function-keys-after.bin').write_bytes(client.read(0x1000,256))
    assert client.read(0x3d21)==b'\x08' and client.read(0x3d2c)==b'\0','browser system image source not restored'
    records=disk_records(data_disk.read_bytes(),fmt)
    # The physical private host image has not received drive writes; the
    # independent whole-disk readback below qualifies this expected new entry.
    if not any(r['name']==b'SAVED' for r in records):
        records.append(dict(name=b'SAVED',type=1,flags=128,blocks=(len(want)+253)//254,app=False))
    client.frames_equal('browser-after-editor',lambda columns:browser_screen(columns,records,0,device,fmt));save()
    client.key(27);client.heap_equal('workspace-after-editor',(143,219,30))
    for bank,page in protected:
        client.key(ord('1')+bank);client.key(ord('V'));assert client.read(0x3d16)==b'\0'
        actual=client.capture.capture(f'workspace-bank-{bank}',bank=bank,address=page*256,count=2000)
        assert actual==bytes((i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(2000))
        client.key(ord('F'))
    client.frames_equal('workspace-restored',lambda columns:expected_screen(columns,1));save()
    client.heap_equal('all-memory-released',(175,251,32))
    assert client.read(0x98)==b'\0' and client.read(0x3de0,4)==bytes(4)
    report.update(native_checks_passed=True,large_input_bytes=len(raw),saved_bytes=len(want),edit_offset=at,
                  saved_sha256=hashlib.sha256(want).hexdigest(),data_device=device,format=fmt,
                  function_key_bytes_restored=256,rom_getin_expansion_verified=True,
                  independent_workspace_prefix_bytes=2000,native_workspace_verify_bytes=8192,
                  all_owned_memory_and_files_released=True)
    save()
