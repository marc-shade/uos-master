#!/usr/bin/env python3
"""Offline verification of the sealed shared VDC service checkpoint."""
import argparse
import binascii
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

def audit(unsealed=False):
    if not unsealed:
        sealed={}
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            h,name=line.split('  ',1);assert name not in sealed
            sealed[name]=h;assert digest((ROOT/name).read_bytes())==h
        assert set(sealed)=={p.name for p in ROOT.iterdir() if p.is_file() and p.name!='SHA256SUMS'}
    inputs=archive('inputs');jobfiles=archive('jobs');outputs=archive('outputs');rebuilt=archive('rebuilt-images')
    hashes=json.loads(jobfiles['inputs.json']);assert hashes=={p:digest(b) for p,b in inputs.items()}
    earlier=archive('earlier-host-files');earlier_hashes=json.loads(jobfiles['earlier-inputs.json'])
    assert set(earlier)=={'tests/ci_native_pointer_iec.py'} and set(earlier_hashes)==set(hashes)
    assert earlier_hashes=={p:digest(earlier.get(p,data)) for p,data in inputs.items()}
    jobs=read_json('jobs.json')
    required={'desktop','calc','reu-calc','client','service','banked','pointer','calc-gui','vice-d64','vice-d81-reu','media','build'}
    assert set(jobs)==required
    for name,status in jobs.items():
        assert status==json.loads(jobfiles[name+'.status.json'])
        assert status['terminal'] and status['passed'] and status['exit_code']==0 and status['physical_hardware_io'] is False
        if name!='build':assert status['inputs_unchanged']
    assert not jobs['build']['changed_images'] and not jobs['build']['source_changes']
    provenance=read_json('provenance.json');assert provenance['physical_hardware_io'] is False
    assert provenance['job_input_sets']=={name:'current' if name=='vice-d64' else 'earlier' for name in jobs}
    superseded=json.loads(jobfiles['superseded-vice-d64.status.json'])
    assert superseded['terminal'] and not superseded['passed'] and superseded['exit_code']==1 and superseded['inputs_unchanged']
    intermediate=json.loads(outputs['superseded-picker-oracle/vice-d64.status.json'])
    assert intermediate['terminal'] and not intermediate['passed'] and intermediate['exit_code']==1 and intermediate['inputs_unchanged']
    intermediate_hashes=json.loads(outputs['superseded-picker-oracle/inputs.json'])
    assert intermediate_hashes=={p:digest(outputs['superseded-picker-oracle/ci_native_pointer_iec.py'])
                                if p=='tests/ci_native_pointer_iec.py' else h for p,h in hashes.items()}
    changes=read_json('changes.json')
    assert all(digest(inputs[p])==v['after'] and v['before']!=v['after'] for p,v in changes.items())
    assert len(rebuilt)==34 and set(rebuilt)==set(provenance['base_images'])
    changed=[]
    for p,data in rebuilt.items():
        h=digest(data);assert h==hashes[p]==jobs['build']['images'][p]['before']==jobs['build']['images'][p]['after']
        if h!=provenance['base_images'][p]:changed.append(p)
    assert set(changed)=={'target/native-desktop/'+name for name in
        ('desktop.prg','calc.prg','vdsvc.prg','uos128.d64','uos128.d81','workspace.d64','workspace.d81')}
    provider=inputs['target/native-desktop/vdsvc.prg'];header=provider[2:34]
    assert provider[:8]==b'\0\x60NBK1\1\1' and header[6:8]==b'\x0c\0' and header[11]==1
    assert len(provider)==int.from_bytes(header[8:10],'little')+2 and header[10]==(len(provider)+253)//256
    assert header[16:]==bytes.fromhex('a20e4cab02')+bytes(11)
    crcdata=bytearray(provider[2:]);crcdata[14:16]=bytes(2)
    assert binascii.crc_hqx(crcdata,65535)==int.from_bytes(header[14:16],'little')
    reports={p:json.loads(jobfiles[p+'.json']) for p in required-{'build','vice-d64','vice-d81-reu'}}
    assert all(r['passed'] for r in reports.values())
    deployment=json.loads(inputs['target/native-desktop/deployment.json']);disks={}
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
    assert disks['target/native-desktop/uos128.d64']['free_blocks']==1
    assert disks['target/native-desktop/uos128.d81']['free_blocks']==2497
    frames=pixels=restores=reu_bytes=0
    for name in ('vice-d64','vice-d81-reu'):
        prefix=name+'/';report=json.loads(outputs[prefix+'report.json'])
        assert report['passed'] and report['all_host_processes_terminal'] and report['system_disk_files_preserved']
        assert report['physical_hardware_io'] is False and len(report['vdc_restores'])==6 and len(report['vdc_app_restores'])==1
        d81=report['options']['d81'];suffix='.d81' if d81 else '.d64'
        boot=inputs['target/native-desktop/boot.prg'][2:]
        before,_=media(inputs['target/native-desktop/uos128'+suffix],d81,boot)
        after,_=media(outputs[prefix+'suite'+suffix],d81,boot)
        data_files,_=media(outputs[prefix+'data-9.d64'],False)
        assert after.pop(b'GUIHIST')==(1,b'42\r')
        assert (after if report['editor_destination_device']==8 else data_files).pop(b'GUINOTE')==(1,bytes.fromhex(report['editor_saved_hex']))
        paint=(after if report['paint_destination_device']==8 else data_files).pop(b'PAINTPIC')
        assert paint[0]==1 and digest(paint[1])==report['paint_file_sha256']
        copied=data_files.pop(b'FSCOPY');assert copied in before.values() and copied[0]==2
        assert digest(copied[1])==report['files_copy_sha256'] and after==before and not data_files
        if name=='vice-d64':
            assert report['files_load_seconds']<600 and report['files_load_progress']
            assert any(row['loaded'] and row['entries'] for row in report['files_load_progress'])
        for mirror_mode,entries in ((False,report['desktops']),(True,report['calculator_frames'])):
            for frame in entries:
                label=prefix+frame['label'];surface=outputs[label+'-surface.bin'];vdc=frame['vdc']
                assert canvas(outputs[label+'-canvas.bin'],vic_pixels(surface,*frame['position']))==frame['rectangle']
                bitmap,attr=mirror(surface,vdc['color']) if mirror_mode else scene(inputs['src/native/desktop/vdc-scene.inc'],frame['selected'])
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
                code_token=bytes.fromhex(row['component']['handle']);record=bytes.fromhex(row['component']['record'])
                assert record[:4]==bytes([32,1,96,header[10]]) and record[4:7]==code_token[1:]
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
                    assert outputs[label+'-component-vs_token.bin']==token
                    assert outputs[label+'-component-ru_cookie.bin']==token[4:]
                    assert desc[0]==32 and desc[5:]==token[1:4] and int.from_bytes(desc[1:3],'little')*4096==at
                    assert int.from_bytes(desc[3:5],'little')==(row['pages']+15)//16
                    reu_bytes+=len(memory)
                else:assert outputs[label+'-component-vs_reu.bin']==b'\0'
                checkpoint=bytes.fromhex(row['checkpoint_hex'])
                assert int.from_bytes(checkpoint[5:7],'little')==row['checkpoint_address']
                assert int.from_bytes(checkpoint[13:17],'little')>0 and checkpoint[21]==1
                restores+=1
        for path,data in outputs.items():
            if path.startswith(prefix) and '-borrower-' in path and path.endswith('-before.bin'):
                assert outputs[path.removesuffix('-before.bin')+'-after.bin']==data
    result=dict(passed=True,physical_hardware_io=False,inputs=len(inputs),changed_inputs=len(changes),
        terminal_jobs=len(jobs),rebuilt_native_images=len(rebuilt),changed_native_images=len(changed),
        unchanged_native_images=len(rebuilt)-len(changed),cpu_cases={k:len(v.get('cases',[])) for k,v in reports.items() if k!='media'},
        suite_vice_boots=2,graphical_canvases=frames,independently_compared_pixels=pixels,exact_vdc_restores=restores,
        independently_decoded_reu_bytes=reu_bytes,d64_suite_free_blocks=1,d81_suite_free_blocks=2497)
    if (ROOT/'audit.json').exists():assert read_json('audit.json')==result
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--unsealed',action='store_true')
    args=parser.parse_args();print(json.dumps(audit(args.unsealed),indent=2,sort_keys=True))
