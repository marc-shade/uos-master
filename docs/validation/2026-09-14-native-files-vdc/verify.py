#!/usr/bin/env python3
"""Offline verification of the Files graphical VDC checkpoint."""
import argparse
import binascii
import difflib
import hashlib
import json
from pathlib import Path
import re
import struct
import tarfile

ROOT=Path(__file__).resolve().parent
def digest(data):return hashlib.sha256(data).hexdigest()
def read_json(name):return json.loads((ROOT/name).read_text())
def archive(name):
    expected=read_json(name+'-files.json');files={}
    with tarfile.open(ROOT/(name+'.tar.gz'),'r:gz') as tar:
        for item in tar:
            assert item.isfile() and not item.name.startswith('/') and '..' not in Path(item.name).parts
            assert item.name not in files
            data=tar.extractfile(item).read();files[item.name]=data
            assert expected[item.name]==dict(bytes=len(data),sha256=digest(data))
    assert set(files)==set(expected)
    return files

def media(data,fmt,boot=None):
    tracks=[40]*80 if fmt else [21]*17+[19]*7+[18]*6+[17]*5
    directory=40 if fmt else 18
    assert len(data)==sum(tracks)*256
    if boot is not None:assert data[:256]==boot and boot[:3]==b'CBM'
    def sector(t,s):
        assert 1<=t<=len(tracks) and 0<=s<tracks[t-1]
        at=(sum(tracks[:t-1])+s)*256;return data[at:at+256]
    used={(directory,0)}
    if boot is not None:used.add((1,0))
    if fmt:used|={(40,1),(40,2)}
    link=(40,3) if fmt else (18,1);files={}
    while link[0]:
        assert link[0]==directory and link not in used;used.add(link)
        row=sector(*link)
        for at in range(0,256,32):
            if not row[at+2]&128:continue
            name=row[at+5:at+21].rstrip(b'\xa0');assert name not in files
            payload=bytearray();blocks=0;chain=tuple(row[at+3:at+5])
            while chain[0]:
                assert chain not in used;used.add(chain);blocks+=1
                block=sector(*chain);assert block[0] or block[1]>=1
                payload+=block[2:] if block[0] else block[2:1+block[1]]
                chain=tuple(block[:2])
            assert blocks==int.from_bytes(row[at+30:at+32],'little')
            files[name]=(row[at+2]&7,bytes(payload))
        link=tuple(row[:2])
    free=0
    for t,count in enumerate(tracks,1):
        bam=sector(40,1 if t<=40 else 2) if fmt else sector(18,0)
        at=16+((t-1)%40)*6 if fmt else t*4
        flags=[bool(bam[at+1+s//8]&(1<<(s%8))) for s in range(count)]
        assert all(value==((t,s) not in used) for s,value in enumerate(flags))
        assert bam[at]==sum(flags)
        if t!=directory:free+=sum(flags)
    return files,dict(files=len(files),free_blocks=free,allocated_sectors=len(used),sha256=digest(data))

def canvas(data,rows):
    fields,=struct.unpack_from('<I',data)
    width,height,_,_,_,_,bpp=struct.unpack_from('<6HB',data,4)
    length,=struct.unpack_from('<I',data,4+fields);pixels=data[8+fields:]
    assert fields>=13 and bpp==8 and length==width*height and length-len(pixels) in (0,4)
    matches=[]
    for y in range(height-len(rows)+1):
        row=pixels[y*width:(y+1)*width];x=row.find(rows[0])
        while x>=0:
            if all(pixels[(y+dy)*width+x:(y+dy)*width+x+len(want)]==want for dy,want in enumerate(rows)):
                matches.append([x,y,len(rows[0]),len(rows)])
            x=row.find(rows[0],x+1)
    assert len(matches)==1
    return matches[0]

POINTER=('B','BB','BWB','BWWB','BWWWB','BWWWWB','BWWWWWB','BWWWWWWB',
         'BWWWWWWWB','BWWWWBBBBB','BWWBWWB','BWB BWWB','BB  BWWB','B    BWWB','     BWWB','      BB')
PALETTE=(0,15,8,7,10,4,2,13,12,12,9,1,14,5,3,14)
RGBI=((0,0,0),(85,85,85),(0,0,170),(85,85,255),(0,170,0),(85,255,85),
      (0,170,170),(85,255,255),(170,0,0),(255,85,85),(170,0,170),(255,85,255),
      (170,85,0),(255,255,85),(170,170,170),(255,255,255))

def scene(source,selected):
    source=source.decode().split('vd_scene_end:')[0]
    data=bytes(int(v,16) for v in re.findall(r'\$([0-9a-fA-F]{2})',source))
    out=bytearray();at=0
    while data[at]:
        code=data[at];at+=1
        if code<64:out+=data[at:at+code];at+=code
        elif code<128:out+=data[at:at+1]*(code-63);at+=1
        else:
            count=code-125;distance=int.from_bytes(data[at:at+2],'little');at+=2
            assert count<=distance<=len(out)
            start=len(out)-distance;out+=out[start:start+count]
    assert at==len(data)-1 and len(out)==16000
    for y,value in enumerate(bytes.fromhex('0040607078706040')):
        out[(32+24*selected+6+y)*80+13]=value
    attr=bytearray(b'\x2f'*2000)
    for card in range(6):
        for y in range(4+3*card,7+3*card):attr[y*80+4:y*80+76]=bytes([0xd0 if card==selected else 0x1f])*72
    return out,attr

def mirror(surface,color):
    assert len(surface)==9216
    out=bytearray(16000);attr=bytearray()
    for value in surface[8192:9192]:attr+=bytes([(PALETTE[value&15]<<4)|PALETTE[value>>4]])*2
    def brightness(index):
        rgb=RGBI[PALETTE[index]];return sum(a*b for a,b in zip(rgb,(299,587,114)))
    for y in range(200):
        for cell in range(40):
            byte=surface[y//8*320+cell*8+y%8];colors=surface[8192+y//8*40+cell]
            if not color and brightness(colors>>4)<brightness(colors&15):byte^=255
            wide=sum((3<<(14-2*bit)) for bit in range(8) if byte&(128>>bit))
            out[y*80+cell*2:y*80+cell*2+2]=wide.to_bytes(2,'big')
    return out,attr

def point(bitmap,x,y,visible):
    assert 0<=x<640 and 0<=y<200
    if visible:
        for dy,row in enumerate(POINTER):
            for dx,value in enumerate(row):
                if value!=' ' and x+dx<640 and y+dy<200:bitmap[(y+dy)*80+(x+dx)//8]^=128>>((x+dx)%8)

def vdc_pixels(bitmap,attr,color):
    return [bytes(((attr[y//8*80+x//8]&15) if ink else (attr[y//8*80+x//8]>>4))
                  if color else (15 if ink else 2)
                  for x in range(640) for ink in [bitmap[y*80+x//8]&(128>>(x%8))]) for y in range(200)]

def vic_pixels(surface,x,y):
    rows=[]
    for py in range(200):
        row=bytearray()
        for px in range(320):
            attr=surface[8192+py//8*40+px//8]
            ink=surface[py//8*320+px//8*8+py%8]&(128>>(px%8))
            color=attr>>4 if ink else attr&15
            dx,dy=px-x,py-y
            if 0<=dy<len(POINTER) and 0<=dx<len(POINTER[dy]):
                if POINTER[dy][dx] in 'BW':color=int(POINTER[dy][dx]=='W')
            row.append(color)
        rows.append(bytes(row))
    return rows

def reu_snapshot(data):
    assert data[:19]==b'VICE Snapshot File\x1a' and data[21:37].rstrip(b'\0')==b'C128'
    assert data[37:50]==b'VICE Version\x1a'
    at=58;found=None
    while at<len(data):
        assert at+22<=len(data)
        size=int.from_bytes(data[at+18:at+22],'little');assert 22<=size<=len(data)-at
        if data[at:at+16].rstrip(b'\0')==b'REU1764':
            assert found is None and data[at+16:at+18]==bytes(2)
            payload=data[at+22:at+size];kib=int.from_bytes(payload[:4],'little')
            assert kib in (128,256,512,1024,2048,4096,8192,16384) and len(payload)==20+kib*1024
            found=payload[20:]
        at+=size
    assert at==len(data) and found is not None
    return found


def napp(image):
    h=image[2:34]
    assert image[:8]==b'\0\x60NAPP\1\1' and len(h)==32 and h[6]<=12
    size=int.from_bytes(h[8:10],'little');entry=int.from_bytes(h[12:14],'little')
    window=h[7]+h[11]*256
    assert 1<=h[10]<=96 and 33<=size<=h[10]*256 and len(image)==size+2 and 32<=entry<size
    assert not window or h[6]>=7 and size<=window<h[10]*256
    assert all(v==0 or 32<=v<127 for v in h[16:])
    raw=bytearray(image[2:]);raw[14:16]=bytes(2)
    assert binascii.crc_hqx(raw,65535)==int.from_bytes(h[14:16],'little')
    return h


def lzsa(source,wanted):
    at=0;low=None;distance=None;out=bytearray()
    def byte():
        nonlocal at
        assert at<len(source)
        value=source[at];at+=1;return value
    def nibble():
        nonlocal low
        if low is not None:value=low;low=None;return value
        value=byte();low=value&15;return value>>4
    def length(code,limit,base,allow_end=False):
        if code<limit:return code+base
        value=limit+base+nibble()
        if value<limit+base+15:return value
        value+=byte()
        if value<256:return value
        if value==256 and allow_end:return None
        assert value==257
        value=byte()+256*byte();assert value>0;return value
    while True:
        token=byte();count=length((token>>3)&3,3,0)
        assert at+count<=len(source) and len(out)+count<=wanted
        out+=source[at:at+count];at+=count
        mode=token>>5;inverse=(~mode)&1
        if mode<2:distance=32-(nibble()*2+inverse)
        elif mode<4:distance=512-(inverse*256+byte())
        elif mode<6:distance=8704-(nibble()*512+inverse*256+byte())
        elif mode==6:distance=65536-(byte()*256+byte())
        count=length(token&7,7,2,True)
        if count is None:
            assert at==len(source) and len(out)==wanted
            return bytes(out)
        assert distance is not None and 1<=distance<=len(out) and len(out)+count<=wanted
        for _ in range(count):out.append(out[-distance])


def packed_app(image):
    outer=napp(image);assert image[34:38]==b'NPZ2'
    original=image[38:70]
    runtime,cleanup,payload,length,code,code_length=struct.unpack_from('<6H',image,70)
    size=int.from_bytes(original[8:10],'little')
    assert 0x6000+size<=runtime<=cleanup==0x6000+outer[10]*256-48
    assert original[:8]==outer[:8] and original[10:12]==outer[10:12] and original[16:]==outer[16:]
    assert int.from_bytes(outer[12:14],'little')==80
    assert 0x6050<=code<code+code_length<=payload and (code_length+255)//256==4
    at=payload-0x6000+2;assert at+length==len(image) and len(image)+0x6000-2<=cleanup
    result=b'\0\x60'+original+lzsa(image[at:],size-32);napp(result)
    return result,dict(raw_file_bytes=len(result),raw_runtime_bytes=len(result)-2,
        raw_sha256=digest(result),packed_file_bytes=len(image),packed_sha256=digest(image),
        packed_body_bytes=length,runtime_end=runtime,cleanup_address=cleanup,cleanup_bytes=48,
        temporary_code_base=0x5000,temporary_code_pages=4,temporary_input_pages=(length+255)//256,
        temporary_input_bank='automatic',codec='napp-lzsa2-startup')


def checkpoint_pc(catalog,registers):
    def records(raw):
        at=2;items=[]
        for _ in range(int.from_bytes(raw[:2],'little')):
            assert at<len(raw)
            size=raw[at];assert size and at+1+size<=len(raw)
            items.append(raw[at+1:at+1+size]);at+=size+1
        assert at==len(raw)
        return items
    names={}
    for item in records(catalog):
        assert len(item)>=3 and 3+item[2]<=len(item) and item[0] not in names
        names[item[0]]=item[3:3+item[2]]
    pc=[number for number,name in names.items() if name==b'PC'];assert len(pc)==1
    values={}
    for item in records(registers):
        assert len(item)==3 and item[0] not in values
        values[item[0]]=int.from_bytes(item[1:],'little')
    return values[pc[0]]

def files_module(data,parent,size):
    h=napp(parent);window=0x6000+h[7]+h[11]*256
    assert window==0x96ac and int.from_bytes(data[:2],'little')==window
    header=data[2:18]
    assert header[:8]==b'NMOD'+bytes([1,1,12,0]) and header[10:12]==h[14:16]
    assert int.from_bytes(header[8:10],'little')==size and len(data)==size+2
    assert window+size<=0xc000 and 16<=int.from_bytes(header[12:14],'little')<size
    raw=bytearray(data[2:]);raw[14:16]=bytes(2)
    assert binascii.crc_hqx(raw,65535)==int.from_bytes(header[14:16],'little')


def audit(unsealed=False):
    if not unsealed:
        sealed={}
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            h,name=line.split('  ',1);assert name not in sealed
            sealed[name]=h;assert digest((ROOT/name).read_bytes())==h
        assert set(sealed)=={p.name for p in ROOT.iterdir() if p.is_file() and p.name!='SHA256SUMS'}
    inputs=archive('inputs');jobfiles=archive('jobs');outputs=archive('outputs')
    rebuilt=archive('rebuilt-images');parent=archive('parent-images')
    assert len(inputs)==713
    assert json.loads(jobfiles['inputs.json'])=={p:digest(b) for p,b in inputs.items()}
    assert all(json.loads(jobfiles[name])['terminal'] for name in
        ('manager.json','vice-manager.json','rerun-manager.json','rerun-vice-manager.json'))
    generations=json.loads(jobfiles['input-generations.json'])
    inherited=json.loads(jobfiles['inherited-inputs.json']);sources=json.loads(jobfiles['inherited-sources.json'])
    changed=generations['changed_inputs']
    assert set(changed)=={'docs/IMPLEMENTATION-ROADMAP.md','native_capture_transport.py',
        'native_picker_scene.py','tests/ci_native_files_copy.py','tests/ci_native_pointer_iec.py'}
    assert set(sources)==set(changed) and set(inherited)==set(inputs)
    assert [p for p in inherited if inherited[p]!=digest(inputs[p])]==changed
    assert all(digest(sources[p].encode())==inherited[p] for p in changed)
    patch=''.join(''.join(difflib.unified_diff(sources[p].splitlines(True),inputs[p].decode().splitlines(True),
        fromfile='before/'+p,tofile='after/'+p)) for p in changed)
    assert patch.encode()==jobfiles['input-fixes.diff']
    assert generations['rerun_jobs']==['build','copy','vice-d64','vice-d81-reu']
    for name in ('copy','vice-d64'):
        failed=json.loads(jobfiles['original-'+name+'.status.json'])
        assert failed['terminal'] and not failed['passed'] and failed['exit_code']==1 and failed['inputs_unchanged']
    jobs=read_json('jobs.json');provenance=read_json('provenance.json')
    required={'vdc','vdc-picker','vdc-reu','vdc-recovery','vdc-fallback','workspace','gui','copy',
        'gui-mouse','gui-fields','gui-gestures','gui-ultimate','gui-longfields','gui-cancel',
        'pack','media','build','vice-d64','vice-d81-reu','vice-boot'}
    assert set(jobs)==required and provenance['physical_hardware_io'] is False
    commands=json.loads(jobfiles['commands.json'])|json.loads(jobfiles['vice-commands.json'])
    assert set(commands)==required
    for name,status in jobs.items():
        assert status==json.loads(jobfiles[name+'.status.json'])
        assert status['terminal'] and status['passed'] and status['exit_code']==0 and status['inputs_unchanged']
        assert status['physical_hardware_io'] is False and status['command']==commands[name]
        assert status['changed_inputs']==[]
        assert status['cwd']==generations['final' if name in generations['rerun_jobs'] else 'original']
    interruptions=json.loads(jobfiles['interruption-evidence.json'])
    assert set(interruptions)=={'original','final'}
    for generation,session,prefix,controller_name,expected_jobs in (
        ('original',85055,'original-','manager.json',['gui','vdc-fallback','vdc-picker']),
        ('final',41746,'','rerun-manager.json',['copy']),
    ):
        retained=interruptions[generation]
        assert retained and all(digest(jobfiles[p])==h for p,h in retained.items())
        assert all(p.startswith(prefix+'interrupted-') for p in retained)
        observation=json.loads(jobfiles[prefix+'interrupted-manager.json'])
        assert observation['terminal'] and observation['exit_code']==143 and observation['session_id']==session
        assert observation['matching_cpu_descendants_present'] is False
        assert observation['interrupted_jobs']==expected_jobs and observation['reason']=='signal termination; cause unknown'
        assert prefix+'interrupted-manager.json' in retained
        controller=json.loads(jobfiles[controller_name])
        assert controller['terminal'] and controller['controller']=='individual supervised commands after manager termination'
        assert controller['original_manager_session']==session and controller['original_manager_exit_code']==143
        assert controller['original_cause']=='unknown'
        expected_names=required-{'vice-d64','vice-d81-reu','vice-boot'} if generation=='original' else {'build','copy'}
        assert set(controller['jobs'])==expected_names
        for name,result in controller['jobs'].items():
            expected_status=json.loads(jobfiles['original-copy.status.json']) if generation=='original' and name=='copy' else jobs[name]
            assert result=={key:expected_status[key] for key in ('exit_code','passed')}
        for name in expected_jobs:
            path=prefix+'interrupted-'+name
            assert path+'.status.json' in retained and path+'.log' in retained
            interrupted=json.loads(jobfiles[path+'.status.json'])
            assert not interrupted['terminal'] and not interrupted['passed'] and interrupted['physical_hardware_io'] is False
            assert interrupted['cwd']==generations[generation] and interrupted['command']==commands[name]
            assert interrupted['started']<observation['observed_at']<=jobs[name]['started']
    assert set().union(*(set(v) for v in interruptions.values()))=={
        p for p in jobfiles if p.startswith(('original-interrupted-','interrupted-'))}
    reports={name:json.loads(jobfiles[name+'.json']) for name in required-{'vice-d64','vice-d81-reu'}}
    assert all(r['passed'] for r in reports.values())
    counts={name:len(r['cases']) for name,r in reports.items() if 'cases' in r}
    expected_counts={'vdc':2,'vdc-picker':2,'vdc-reu':4,'vdc-recovery':5,'vdc-fallback':5,
        'workspace':3,'gui':14,'copy':26,'pack':21,'vice-boot':6,
        'gui-mouse':1,'gui-fields':1,'gui-gestures':1,'gui-ultimate':1,'gui-longfields':1,'gui-cancel':2}
    assert counts==expected_counts,counts
    assert all(0<row['field_vdc_writes']<6000 and 0<row['pointer_vdc_writes']<=96 and
        row['picker_canvases']==5 and row['file_bytes']==1539 for row in reports['vdc-picker']['cases'])
    assert [row['free_pages'] for row in reports['vdc-reu']['cases'] if 'free_pages' in row]==[211,211]
    assert [(row['copied'],row['verified']) for row in reports['vdc-recovery']['cases'] if 'copied' in row]==[(8192,0),(10240,8192)]
    for name in ('gui-mouse','gui-fields','gui-gestures','gui-ultimate','gui-longfields','gui-cancel'):
        assert reports[name]['complete_vic_and_vdc_canvases']==sum(c['views'] for c in reports[name]['cases'])>0
    assert sum(row['interrupts'] for row in reports['pack']['cases'])==98
    changes=read_json('changes.json')
    assert all(digest(inputs[p])==v['after'] and v['before']!=v['after'] for p,v in changes.items())
    assert len(rebuilt)==34 and set(rebuilt)==set(parent)==set(reports['build']['images'])
    changed=[p for p,b in rebuilt.items() if b!=parent[p]]
    assert set(changed)=={'target/native-desktop/'+p for p in ('files.prg','fspick.prg','fsview.prg','uos128.d64','uos128.d81','workspace.d64','workspace.d81')}
    assert all(b==inputs[p] and digest(b)==reports['build']['images'][p] for p,b in rebuilt.items())
    deployment=json.loads(inputs['target/native-desktop/deployment.json'])
    savings=blocks=0
    for name in ('desktop','calc','editor','files','controls','claude','paint'):
        path='target/native-desktop/'+name+'.prg';raw,info=packed_app(inputs[path])
        assert info==deployment['packed_apps'][name]
        if name=='files':
            assert raw==jobfiles['files-expanded.prg'] and len(raw)==13998 and len(inputs[path])==9829
            h=napp(raw);assert h[6]==12 and h[10]==96
        else:assert inputs[path]==parent[path]
        savings+=len(raw)-len(inputs[path]);blocks+=(len(raw)+253)//254-(len(inputs[path])+253)//254
    assert savings==34276 and blocks==136
    for name,size in (('fspick',10221),('fsview',7441)):
        files_module(inputs['target/native-desktop/'+name+'.prg'],inputs['target/native-desktop/files.prg'],size)
    provider=inputs['target/native-desktop/vdsvc.prg'];header=provider[2:34]
    assert provider==parent['target/native-desktop/vdsvc.prg'] and header[16:]==bytes.fromhex('a20e4cab02')+bytes(11)
    disks={}
    for path,want in reports['media']['disks'].items():
        directory,filename=path.rsplit('/',1);stem,fmt=filename.split('.')
        entries=deployment['disk_entries'] if directory.endswith('native-desktop') else {
            'u':'uos128-boot.prg','browse':'browse.prg','calc':'calc.prg','editor':'editor.prg','edpick.prg':'edpick.prg','edfind.prg':'edfind.prg'}
        expected={}
        for name,file in entries.items():
            origin=directory
            if name=='u':
                if stem=='workspace':origin='target/native'
                if fmt=='d81':origin+='/d81'
            expected[name.upper().encode()]=(2,inputs[origin+'/'+file])
        files,result=media(inputs[path],fmt=='d81',inputs[directory+'/boot.prg'][2:])
        assert files==expected and result==want;disks[path]=result
    assert len(disks)==6
    assert disks['target/native-desktop/uos128.d64']['free_blocks']==140
    assert disks['target/native-desktop/uos128.d81']['free_blocks']==2636
    frames=pixels=restores=reu_bytes=0
    for name in ('vice-d64','vice-d81-reu'):
        prefix=name+'/';report=json.loads(outputs[prefix+'report.json'])
        assert report['passed'] and report['all_host_processes_terminal'] and report['system_disk_files_preserved']
        assert report['physical_hardware_io'] is False and report['options']['files_only']
        assert len(report['vdc_restores'])==1 and len(report['vdc_app_restores'])==1
        assert len({row['label'] for row in report['vdc_restores']+report['vdc_app_restores']})==2
        assert len(report['desktops'])==(8 if name=='vice-d81-reu' else 7) and len(report['files_frames'])==10
        assert len(report['picker_frames'])==2 and report['vdc_app_restores'][0]['app']=='files'
        assert outputs[prefix+'keys-before.bin']==outputs[prefix+'files-keys-restored.bin']
        assert [row['mouse_app'] for row in report['events'] if 'mouse_app' in row]==['files']
        assert all(row['keyboard_events_during_click']==0 for row in report['events'] if 'keyboard_events_during_click' in row)
        for path,h in report['images'].items():assert digest(inputs['target/native-desktop/'+path])==h
        pages=outputs[prefix+'final-page-table.bin'];handles=outputs[prefix+'final-records.bin']
        assert pages[0x50:0xff]==bytes(175) and pages[0x104:0x1ff]==bytes(251)
        assert all(handles[i*8]==0 for i in range(32))
        d81=report['options']['d81'];suffix='.d81' if d81 else '.d64'
        boot=inputs['target/native-desktop/boot.prg'][2:]
        before,_=media(inputs['target/native-desktop/uos128'+suffix],d81,boot)
        after,_=media(outputs[prefix+'suite'+suffix],d81,boot)
        assert before==after
        data_files,_=media(outputs[prefix+'data-9.d64'],False)
        original_data,_=media(outputs[prefix+'initial-data-9.d64'],False);assert not original_data
        assert data_files=={b'FSCOPY':before[b'EDFIND.PRG']}
        assert before[b'EDFIND.PRG']==(2,inputs['target/native-desktop/edfind.prg'])
        assert digest(data_files[b'FSCOPY'][1])==report['files_copy_sha256']
        assert report['files_copy_destination_device']==9
        for frame in report['files_frames']:
            fields=frame['expected']
            if 'source' in fields:
                assert bytes.fromhex(fields['source'])==b'EDFIND.PRG'
                assert bytes.fromhex(fields['name']) in (b'EDFIND.PRG',b'FSCOPY')
                if fields.get('status')==1:
                    assert fields['copied']==fields['verified']==len(data_files[b'FSCOPY'][1])
        for mirrored,entries in ((False,report['desktops']),(True,report['files_frames']),(True,report['picker_frames'])):
            for frame in entries:
                label=prefix+frame['label'];surface=outputs[label+'-surface.bin'];vdc=frame['vdc']
                assert canvas(outputs[label+'-canvas.bin'],vic_pixels(surface,*frame['position']))==frame['rectangle']
                bitmap,attr=mirror(surface,vdc['color']) if mirrored else scene(inputs['src/native/desktop/vdc-scene.inc'],frame['selected'])
                point(bitmap,*vdc['position'],vdc['pointer_visible'])
                assert outputs[label+'-vdc-bitmap.bin']==bitmap and digest(bitmap)==vdc['bitmap_sha256']
                if vdc['color']:assert outputs[label+'-vdc-attributes.bin']==attr
                assert canvas(outputs[label+'-vdc-canvas.bin'],vdc_pixels(bitmap,attr,vdc['color']))==vdc['rectangle']
                frames+=2;pixels+=192000
        for is_app,entries in ((False,report['vdc_restores']),(True,report['vdc_app_restores'])):
            for row in entries:
                label=prefix+row['label'];raw=outputs[label+'-snapshot.bin']
                restored=label+'-restored-vram.bin' if is_app else label.removesuffix('-close')+'-restored-vram.bin'
                assert outputs[restored]==raw and len(raw)==row['pages']*256 and digest(raw)==row['sha256']
                saved=bytes.fromhex(row['saved_registers'])
                assert outputs[label+'-saved-registers.bin']==outputs[label+'-component-vd_saved.bin']==saved
                code=bytearray(outputs[label+'-component-header.bin'])
                assert digest(code)==row['component']['header_sha256'] and int.from_bytes(code[22:24],'little')
                code[22:24]=bytes(2);assert code==header
                token=bytes.fromhex(row['component']['handle']);record=bytes.fromhex(row['component']['record'])
                assert record[:4]==bytes([32,1,96,header[10]]) and record[4:7]==token[1:]
                state=outputs[label+'-component-vd_phase.bin'];assert state[:4]==bytes([2,1,int(row['color']),0])
                assert state[5:]==bytes([row['base']//256,row['pages']])
                if row.get('storage')=='reu':
                    snapshot=outputs[prefix+row['reu_snapshot']['snapshot']]
                    assert digest(snapshot)==row['reu_snapshot']['snapshot_sha256']
                    memory=reu_snapshot(snapshot);assert digest(memory)==row['reu_snapshot']['sha256']
                    at=row['reu_address'];assert memory[at:at+len(raw)]==raw
                    initial=outputs[prefix+'initial.reu']
                    assert memory[:at]==initial[:at] and memory[at+len(raw):]==initial[at+len(raw):]
                    token=bytes.fromhex(row['token']);desc=outputs[label+'-component-ru_records.bin']
                    assert outputs[label+'-component-vs_reu.bin']==b'\1' and token[:4]==bytes.fromhex(row['handle'])
                    assert outputs[label+'-component-vs_token.bin']==token and outputs[label+'-component-ru_cookie.bin']==token[4:]
                    assert desc[0]==32 and desc[5:]==token[1:4] and int.from_bytes(desc[1:3],'little')*4096==at
                    assert int.from_bytes(desc[3:5],'little')==(row['pages']+15)//16
                    reu_bytes+=len(memory)
                else:assert outputs[label+'-component-vs_reu.bin']==b'\0'
                checkpoint=bytes.fromhex(row['checkpoint_hex'])
                observation=json.loads(outputs[label+'-restore-observation.json'])
                assert observation['mmu']==0x4e and observation['pc']==row['checkpoint_address']
                assert observation['checkpoint_hex']==row['checkpoint_hex']
                assert checkpoint_pc(bytes.fromhex(observation['register_catalog_hex']),bytes.fromhex(observation['registers_hex']))==row['checkpoint_address']
                proof=label if is_app else label.removesuffix('-close')
                assert outputs[proof+'-restore-checkpoint.bin']==checkpoint
                assert int.from_bytes(checkpoint[5:7],'little')==row['checkpoint_address']
                assert int.from_bytes(checkpoint[13:17],'little')>0 and checkpoint[21]==1
                restores+=1
        for path,data in outputs.items():
            if path.startswith(prefix) and '-borrower-' in path and path.endswith('-before.bin'):
                assert outputs[path.removesuffix('-before.bin')+'-after.bin']==data
    boot_canvases=boot_pixels=0
    boot=reports['vice-boot'];assert len(boot['cases'])==6
    for case in boot['cases']:
        assert case['passed']
        prefix='vice-boot/'+case['name']+'/'
        directory,stem,fmt=case['name'].rsplit('-',2);disk=outputs[prefix+'boot.'+fmt]
        assert disk==inputs['target/'+directory+'/'+stem+'.'+fmt] and digest(disk)==case['disk_sha256']
        color=fmt=='d81'
        for frame in case['frames']:
            surface=outputs[prefix+frame['label']+'-surface.bin']
            bitmap,attr=scene(inputs['src/native/desktop/vdc-scene.inc'],frame['selected'])
            for captured in frame['canvases']:
                is_vdc=captured['file'].endswith('-vdc.bin')
                rows=vdc_pixels(bitmap,attr,color) if is_vdc else vic_pixels(surface,320,200)
                raw=outputs[prefix+captured['file']]
                assert digest(raw)==captured['sha256'] and canvas(raw,rows)==captured['rectangle']
                boot_canvases+=1;boot_pixels+=128000 if is_vdc else 64000
    assert boot_canvases==24
    result=dict(passed=True,physical_hardware_io=False,inputs=len(inputs),changed_inputs=len(changes),
        terminal_jobs=len(jobs),interrupted_managers=2,resumed_interrupted_jobs=4,
        case_counts=counts,rebuilt_native_images=34,changed_native_images=7,
        unchanged_native_images=27,exact_expanded_files=True,unchanged_other_apps=6,
        packed_file_bytes_saved=savings,packed_disk_blocks_saved=blocks,
        d64_suite_free_blocks=140,d81_suite_free_blocks=2636,files_pages=96,
        files_free_pages_with_reu=211,files_workspace_pages=16,exact_copied_files=2,
        suite_vice_workflows=2,cold_boot_cases=6,graphical_canvases=frames+boot_canvases,
        independently_compared_pixels=pixels+boot_pixels,exact_vdc_restores=restores,
        independently_decoded_reu_bytes=reu_bytes)
    if (ROOT/'audit.json').exists():assert read_json('audit.json')==result
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--unsealed',action='store_true')
    args=parser.parse_args();print(json.dumps(audit(args.unsealed),indent=2,sort_keys=True))
