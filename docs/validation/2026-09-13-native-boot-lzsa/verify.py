#!/usr/bin/env python3
"""Offline verification of the sealed native boot compression checkpoint."""
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

def lzsa(data,size):
    at=0;nibbles=[];out=bytearray();distance=None
    def get():
        nonlocal at
        assert at<len(data)
        value=data[at];at+=1;return value
    def nibble():
        if not nibbles:
            value=get();nibbles.extend([value&15,value>>4])
        return nibbles.pop()
    def length(initial,escape,bias):
        result=initial+bias
        if initial==escape:
            extra=nibble();result+=extra
            if extra==15:
                result+=get()
                if result==256 and bias==2:return None
                if result>=256:
                    assert result==257
                    result=get()+256*get();assert result>0
        return result
    while True:
        token=get();count=length(token>>3&3,3,0)
        assert at+count<=len(data) and len(out)+count<=size
        out.extend(data[at:at+count]);at+=count
        kind=token>>5;z=1-(kind&1)
        if kind<=1:distance=32-2*nibble()-z
        elif kind<=3:distance=512-256*z-get()
        elif kind<=5:
            high=nibble();distance=8704-512*high-256*z-get()
        elif kind==6:distance=65536-256*get()-get()
        count=length(token&7,7,2)
        if count is None:
            assert at==len(data) and len(out)==size
            return bytes(out)
        assert distance is not None and 1<=distance<=len(out) and len(out)+count<=size
        for _ in range(count):out.append(out[-distance])

def media(data,fmt,boot):
    tracks=[40]*80 if fmt else [21]*17+[19]*7+[18]*6+[17]*5
    directory=40 if fmt else 18
    assert len(data)==sum(tracks)*256 and data[:256]==boot and boot[:3]==b'CBM'
    def sector(t,s):
        assert 1<=t<=len(tracks) and 0<=s<tracks[t-1]
        at=(sum(tracks[:t-1])+s)*256;return data[at:at+256]
    used={(1,0),(directory,0)}
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

def vdc_scene(source,selected,color):
    text=source.decode().split('vd_scene_end:')[0]
    data=bytes(int(v,16) for v in re.findall(r'\$([0-9a-fA-F]{2})',text))
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
    rows=[]
    for y in range(200):
        row=bytearray()
        for x in range(640):
            ink=out[y*80+x//8]&(128>>(x%8))
            attr=0x2f
            if 4<=x//8<76:
                for card in range(6):
                    if 4+3*card<=y//8<7+3*card:attr=0xd0 if card==selected else 0x1f
            row.append((attr&15 if ink else attr>>4) if color else (15 if ink else 2))
        rows.append(bytes(row))
    return rows

def audit(unsealed=False):
    if not unsealed:
        sealed={}
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            h,name=line.split('  ',1);assert name not in sealed
            sealed[name]=h;assert digest((ROOT/name).read_bytes())==h
        assert set(sealed)=={p.name for p in ROOT.iterdir() if p.is_file() and p.name!='SHA256SUMS'}
    inputs=archive('inputs');jobs_files=archive('jobs');outputs=archive('outputs');rebuilt=archive('rebuilt-images')
    hashes=json.loads(jobs_files['inputs.json']);assert hashes=={p:digest(b) for p,b in inputs.items()}
    jobs=read_json('jobs.json');assert set(jobs)=={'cpu','media','vice','build'}
    for name,status in jobs.items():
        assert status==json.loads(jobs_files[name+'.status.json'])
        assert status['terminal'] and status['passed'] and status['exit_code']==0
        if name!='build':assert status['inputs_unchanged'] and status['physical_hardware_io'] is False
    assert not jobs['build']['changed_images'] and not jobs['build']['source_changes']
    provenance=read_json('provenance.json');assert provenance['physical_hardware_io'] is False
    for p,entry in provenance['lzsa']['files'].items():assert digest(inputs['third_party/lzsa/'+p])==entry['sha256']
    changes=read_json('changes.json')
    assert all(digest(inputs[p])==v['after'] and v['before']!=v['after'] for p,v in changes.items())
    assert len(rebuilt)==33 and set(rebuilt)==set(provenance['base_images'])
    changed=[]
    for p,data in rebuilt.items():
        h=digest(data);assert h==hashes[p]==jobs['build']['images'][p]['before']==jobs['build']['images'][p]['after']
        if h!=provenance['base_images'][p]:changed.append(p)
    assert len(changed)==10 and all(p.endswith(('.d64','.d81','uos128-boot.prg')) for p in changed)
    profiles=[]
    for prefix in ('native','native/d81','native-desktop','native-desktop/d81'):
        path='target/'+prefix+'/';raw=inputs[path+'uos128.prg'];packed=inputs[path+'uos128-boot.prg']
        assert digest(raw)==provenance['base_images'][path+'uos128.prg']
        syms={n:int(v[1:],16) if v.startswith('$') else int(v) for n,v in re.findall(
            r'^(\w+)\s*=\s*(\$[0-9a-fA-F]+|\d+)$',inputs[path+'uos128-boot.sym'].decode(),re.M)}
        assert packed[:2]==raw[:2]==b'\1\x1c' and syms['decoder_end']<=0x1c00
        start=syms['boot_payload']-0x1c01+2;payload=packed[start:]
        assert len(payload)==syms['BOOT_LENGTH'] and lzsa(payload,len(raw)-2)==raw[2:]
        assert binascii.crc_hqx(raw[2:],65535)==syms['BOOT_EXPECTED_CRC']
        profiles.append(dict(name=prefix,boot_bytes=len(packed),unpacked_bytes=len(raw)-2,packed_bytes=len(payload)))
    reports={p:json.loads(jobs_files[p+'.json']) for p in ('cpu','media','vice')}
    assert all(r['passed'] and r['physical_hardware_io'] is False for r in reports.values())
    assert len(reports['cpu']['cases'])==59 and len(reports['vice']['cases'])==6
    deployment=json.loads(inputs['target/native-desktop/deployment.json'])
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
        assert files==expected and result==want
    frames=0;compared=0;surfaces={}
    for case in reports['vice']['cases']:
        assert case['passed'] and case['keys']
        prefix='vice/'+case['name']+'/'
        disk=outputs[prefix+'boot.'+case['name'].rsplit('-',1)[1]]
        assert digest(disk)==case['disk_sha256']
        assert disk in [inputs[p] for p in reports['media']['disks']]
        for frame in case['frames']:
            label=frame['label'];selected=frame['selected'];surface=outputs[prefix+label+'-surface.bin']
            assert len(surface)==9216
            if selected in surfaces:assert surface==surfaces[selected]
            else:surfaces[selected]=surface
            vic=[]
            for y in range(200):
                row=bytearray()
                for x in range(320):
                    attr=surface[8192+y//8*40+x//8]
                    ink=surface[y//8*320+x//8*8+y%8]&(128>>(x%8))
                    row.append(attr>>4 if ink else attr&15)
                vic.append(bytes(row))
            vdc=vdc_scene(inputs['src/native/desktop/vdc-scene.inc'],selected,case['name'].endswith('d81'))
            assert len(frame['canvases'])==2
            for entry,rows in zip(frame['canvases'],(vic,vdc)):
                raw=outputs[prefix+entry['file']]
                assert digest(raw)==entry['sha256'] and canvas(raw,rows)==entry['rectangle']
                frames+=1;compared+=len(rows)*len(rows[0])
    assert frames==24 and compared==2304000
    result=dict(passed=True,physical_hardware_io=False,inputs=len(inputs),changed_inputs=len(changes),terminal_jobs=len(jobs),
                independently_decoded_boot_profiles=profiles,rebuilt_native_images=len(rebuilt),changed_native_images=len(changed),
                unchanged_native_images=len(rebuilt)-len(changed),cpu_cases=59,vice_boots=6,desktop_canvases=frames,
                independently_compared_pixels=compared,d64_suite_free_blocks=15,d81_suite_free_blocks=2511)
    if (ROOT/'audit.json').exists():assert read_json('audit.json')==result
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--unsealed',action='store_true')
    args=parser.parse_args();print(json.dumps(audit(args.unsealed),indent=2,sort_keys=True))
