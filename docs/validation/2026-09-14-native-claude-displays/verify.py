#!/usr/bin/env python3
"""Offline verification of the Claude coordinated display checkpoint."""
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


def audit(unsealed=False):
    if not unsealed:
        sealed={}
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            h,name=line.split('  ',1);assert name not in sealed
            sealed[name]=h;assert digest((ROOT/name).read_bytes())==h
        assert set(sealed)=={p.name for p in ROOT.iterdir() if p.is_file() and p.name!='SHA256SUMS'}
    inputs=archive('inputs');jobfiles=archive('jobs');outputs=archive('outputs')
    blobs=archive('execution-blobs');rebuilt=archive('rebuilt-images');parent=archive('parent-images')
    development=archive('development')
    assert len(inputs)==745 and json.loads(jobfiles['inputs.json'])=={p:digest(b) for p,b in inputs.items()}
    production=json.loads(jobfiles['production.json']);assert len(production)==363
    assert all(digest(inputs[p])==h for p,h in production.items())
    provenance=read_json('provenance.json')
    assert provenance['base']=='84fac1ef9190f4f7f56741419ad58d91024b641e'
    assert provenance['previous_seal']=='197e30cfbb31e8613fa51b5d95cebdff34bf6f30039997925d549416c3d4103c'
    assert provenance['physical_hardware_io'] is False and provenance['processes_terminal_at_archival']
    assert digest(json.dumps(production,sort_keys=True).encode())==provenance['production']
    executions=read_json('executions.json');jobs=read_json('jobs.json')
    assert set(executions)=={'dev4','dev5','dev6','dev7','final'} and len(jobs)==18
    assert set(sum((v['jobs'] for v in executions.values()),[]))==set(jobs)
    needed=set()
    def executed(generation,path):
        h=executions[generation]['inputs'][path]
        if path in inputs and digest(inputs[path])==h:return inputs[path]
        needed.add(h);assert digest(blobs[h])==h;return blobs[h]
    for generation,execution in executions.items():
        manifest=execution['inputs']
        for p,h in manifest.items():assert digest(executed(generation,p))==h
        assert all(manifest.get(p)==h for p,h in production.items())
        for name in execution['jobs']:
            status=jobs[name];assert status==json.loads(jobfiles[name+'.status.json'])
            assert status['terminal'] and status['passed'] and status['exit_code']==0 and status['inputs_unchanged']
            assert status['physical_hardware_io'] is False and status['cwd']==execution['root']
            assert json.loads(jobfiles[name+'.inputs.json'])==manifest
            assert status['command'][2] in manifest
    assert needed==set(blobs) and set(provenance['excluded_development_jobs']).isdisjoint(jobs)
    assert not json.loads(development['uos-claude-displays-dev6-resources-fallback.status.json'])['passed']
    reports={n:json.loads(jobfiles[n+'.report.json']) for n in jobs if n+'.report.json' in jobfiles}
    assert len(reports)==16 and all(r['passed'] and r['physical_hardware_io'] is False for r in reports.values())
    counts={n:len(r['cases']) for n,r in reports.items() if 'cases' in r}
    assert sum(counts.values())==35
    stream=reports['dev4-vdc-stream']['cases'][0]
    assert stream['bytes_received']==3228 and stream['peak_ring']==192
    assert stream['component_interrupts']>0 and 0x4e in stream['interrupted_maps']
    assert counts['dev7-resources-fallback']==4 and counts['dev6-protocol']==11
    build=json.loads(jobfiles['build.json']);assert build['passed'] and build['generated_source_unchanged']
    changes=read_json('changes.json')
    assert all(digest(inputs[p])==v['after'] and v['before']!=v['after'] for p,v in changes.items())
    assert len(rebuilt)==34 and set(rebuilt)==set(parent)==set(build['images'])
    changed={p for p,b in rebuilt.items() if b!=parent[p]}
    assert changed=={'target/native-desktop/'+p for p in ('claude.prg','uos128.d64','uos128.d81','workspace.d64','workspace.d81')}
    assert all(b==inputs[p] and digest(b)==build['images'][p] for p,b in rebuilt.items())
    deployment=json.loads(inputs['target/native-desktop/deployment.json'])
    for name in ('desktop','calc','editor','files','controls','claude','paint'):
        path='target/native-desktop/'+name+'.prg';raw,info=packed_app(inputs[path])
        assert info==deployment['packed_apps'][name]
        if name=='claude':
            h=napp(raw);assert h[6]==12 and h[10]==94 and len(raw)==15872
            assert len(inputs[path])==10676 and info['runtime_end']==48527
            assert info['raw_sha256']=='995305dad95448cd95ae29cf77de1752f283a64ad3f6473b60075a9cc8bf987c'
        else:assert inputs[path]==parent[path]
    provider=inputs['target/native-desktop/vdsvc.prg'];assert provider==parent['target/native-desktop/vdsvc.prg']
    assert len(provider)==8450 and provider[12]==33
    disks={}
    for path,want in reports['final-boot-media']['disks'].items():
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
    assert len(disks)==6 and disks['target/native-desktop/uos128.d64']['free_blocks']==124
    assert disks['target/native-desktop/uos128.d81']['free_blocks']==2620
    frames=pixels=captures=0
    for name in ('dev5-vice16','dev5-vice64'):
        prefix=name+'/';report=json.loads(outputs[prefix+'report.json'])
        assert report['passed'] and report['host_exit_code']==0 and report['close_outcome']==2
        assert report['physical_hardware_io'] is False and report['options']['mouse'] and report['options']['cpu_capture']
        assert report['options']['eighty']==report['options']['vdc64']==name.endswith('64')
        assert outputs[prefix+'run.py']==executed('dev5','tests/ci_native_claude_iec.py')
        for path,h in report['images'].items():assert digest(inputs['target/native-desktop/'+path])==h
        assert outputs[prefix+'suite.d64']==inputs['target/native-desktop/uos128.d64']
        assert outputs[prefix+'font-before.bin']==outputs[prefix+'font-after.bin']
        assert outputs[prefix+'nmi-before.bin']==outputs[prefix+'nmi-after.bin']
        heap=outputs[prefix+'final-heap.bin'];assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251)
        assert report['serial_counters']['_rxDropped']==report['serial_counters']['_rxOverruns']==0
        assert len(report['mouse_events'])==11 and all(row['keyboard_events']==0 for row in report['mouse_events'])
        assert any(row['button']=='right' and row['menu']==1 for row in report['mouse_events'])
        assert report['rom_keys'][0]['code']==255 and len(report['rom_keys'])==5
        checkpoint=bytes.fromhex(report['close_observation']['checkpoint_hex'])
        assert outputs[prefix+'close-checkpoint.bin']==checkpoint and int.from_bytes(checkpoint[13:17],'little')>0
        assert outputs[prefix+'close-outcome.bin']==b'\2'
        assert len(report['claude_frames'])==10 and len(report['desktop_frames'])==2
        for frame in report['claude_frames']:
            label=prefix+frame['label'];surface=outputs[label+'-surface.bin']
            assert digest(surface)==frame['surface_sha256'] and len(surface)==9216
            assert outputs[label+'-panel.bin']==bytes.fromhex(frame['panel_hex'])
            assert frame['pointer_visible']
            assert canvas(outputs[label+'-canvas.bin'],vic_pixels(surface,*frame['position']))==frame['rectangle']
            frames+=1;pixels+=64000
            record=bytes.fromhex(frame['model']['record']);token=bytes.fromhex(frame['model']['handle'])
            assert record[:2]==b'\x20\1' and record[3]==16 and record[4:7]==token[1:]
            assert len(outputs[label+'-terminal.bin'])==4048 and len(outputs[label+'-font.bin'])==4096
            assert frame['font_address']==0x5000
            if 'vdc' in frame:
                vdc=frame['vdc'];bitmap,attr=mirror(surface,vdc['color'])
                point(bitmap,*vdc['position'],vdc['pointer_visible'])
                assert outputs[label+'-vdc-bitmap.bin']==bitmap and digest(bitmap)==vdc['bitmap_sha256']
                if vdc['color']:assert outputs[label+'-vdc-attributes.bin']==attr
                assert canvas(outputs[label+'-vdc-canvas.bin'],vdc_pixels(bitmap,attr,vdc['color']))==vdc['rectangle']
                frames+=1;pixels+=128000
        for frame in report['desktop_frames']:
            label=prefix+frame['label'];bitmap,attr=scene(inputs['src/native/desktop/vdc-scene.inc'],frame['selected'])
            point(bitmap,*frame['position'],frame['pointer_visible'])
            assert outputs[label+'-vdc-bitmap.bin']==bitmap and digest(bitmap)==frame['bitmap_sha256']
            if frame['color']:assert outputs[label+'-vdc-attributes.bin']==attr
            assert canvas(outputs[label+'-vdc-canvas.bin'],vdc_pixels(bitmap,attr,frame['color']))==frame['rectangle']
            frames+=1;pixels+=128000
        before=outputs[prefix+'claude-left-terminal-terminal.bin']
        updated=outputs[prefix+'claude-right-terminal-bottom-terminal.bin']
        restored=outputs[prefix+'claude-full-terminal-return-terminal.bin']
        assert before[:1997]==updated[:1997] and before[1997:2000]==b'   ' and updated[1997:2000]!=b'   '
        assert updated==restored
        assert restored[:2000]==outputs[prefix+'session-vdc.bin']
        assert restored[2048:]==outputs[prefix+'session-attrs.bin']
        assert outputs[prefix+'claude-full-terminal-return-font.bin']==outputs[prefix+'font-during.bin']
        for capture in report['cpu_captures']:
            assert capture['restored'] and not capture['borrower_failures'] and capture['code']==1
            data=b''
            for chunk in capture['chunks']:
                status=outputs[prefix+chunk['status_file']];raw=outputs[prefix+chunk['payload_file']]
                assert digest(status)==chunk['status_sha256'] and status[0]==1
                assert digest(raw)==chunk['payload_sha256'] and len(raw)==chunk['payload_bytes']<=512
                assert chunk['common_register']&15==4 and chunk['foreground_mmu'] in (0,14)
                data+=raw
            assert len(data)==capture['count'] and outputs[prefix+capture['label']+'.bin']==data
            for row in capture['borrower_checks'].values():
                a=outputs[prefix+row['before_file']];b=outputs[prefix+row['after_file']]
                assert a==b and digest(a)==row['before_sha256']==row['after_sha256'] and row['matches']
            captures+=1
    assert (frames,pixels)==(36,3328000)
    result=dict(passed=True,physical_hardware_io=False,inputs=len(inputs),changed_inputs=len(changes),
        runtime_jobs=len(jobs),cpu_cases=sum(counts.values()),case_counts=counts,independent_builds=1,
        execution_generations=len(executions),identical_production_files=len(production),
        rebuilt_native_images=34,changed_native_images=5,unchanged_native_images=29,
        claude_app_pages=94,terminal_pages=16,font_pages=16,bitmap_pages=36,provider_pages=33,
        main_ram_free_with_reu=231,d64_suite_free_blocks=124,d81_suite_free_blocks=2620,
        vice_cold_boots=2,graphical_canvases=frames,independently_compared_pixels=pixels,
        restored_cpu_captures=captures,serial_window_peak=stream['peak_ring'],
        component_interrupts=stream['component_interrupts'])
    if (ROOT/'audit.json').exists():assert read_json('audit.json')==result
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--unsealed',action='store_true')
    args=parser.parse_args();print(json.dumps(audit(args.unsealed),indent=2,sort_keys=True))

