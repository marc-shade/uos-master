#!/usr/bin/env python3
"""Independent native image, disk and captured-display decoders."""
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

def listing_address(data,label):
    for line in data.decode('latin1').splitlines():
        if not re.search(r'\b'+re.escape(label)+r':',line):continue
        fields=line.split(label+':',1)[0].split()
        if not fields or not re.fullmatch(r'[.>][0-9a-fA-F]{4}',fields[0]):continue
        value=fields[1] if len(fields)>1 and re.fullmatch(r'[0-9a-fA-F]{4}',fields[1]) else fields[0][1:]
        return int(value,16)
    raise AssertionError(('missing emitted label',label))

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
    assert image[:8]==b'\0\x60NAPP\1\1' and len(h)==32 and h[6]<=14
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


def module(image,core):
    h=image[2:18];parent=napp(core)
    origin=int.from_bytes(image[:2],'little');size=int.from_bytes(h[8:10],'little')
    assert origin==0x6000+parent[7]+parent[11]*256
    assert h[:6]==b'NMOD\1\1' and 7<=h[6]<=14 and h[7]==0
    assert len(image)==size+2 and 17<=size and origin+size<=0xc000
    assert h[10:12]==parent[14:16] and 16<=int.from_bytes(h[12:14],'little')<size
    raw=bytearray(image[2:]);raw[14:16]=bytes(2)
    assert binascii.crc_hqx(raw,65535)==int.from_bytes(h[14:16],'little')
    return dict(origin=origin,bytes=size,end=origin+size)
