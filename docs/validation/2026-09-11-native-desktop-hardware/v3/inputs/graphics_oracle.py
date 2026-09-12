"""Independent pixel/attribute model for the clipped graphics demo."""
from graphics.font import font
CLIP_BOX=(40,88,144,136)
CLIP_TEXT=(28,104,3,b'Window clip test')
OPS=[
    (0,(-5,-3,325,203),0),
    (0,(4,4,316,196),1),
    (0,(12,12,308,188),0),
    (0,(18,22,152,76),1),
    (0,(140,60,330,150),2),
    (0,(0,0,1,1),1),
    (0,(319,199,320,200),1),
    (1,(2,2,18,10),0x73),
    (1,(38,23,44,27),0xf0),
    (2,CLIP_BOX,0),
    (0,(30,80,160,144),1),
    (0,(44,92,140,132),0),
    (1,(0,0,40,25),0x10),
    (2,(0,0,320,200),0),
]
TEXT_OPS=[(20,14,3,b'uOS native graphics'),(24,32,3,b'uOS 128'),
          (154,96,3,b'Native text'),(24,174,3,b'ASCII: Aa09 /Usb0'),
          (-4,188,3,b'Clipped left'),(306,192,3,b'END'),(96,-3,3,b'Top clip')]


def surface():
    data=bytearray(b'\xaa'*8192+b'\xe6'*1024)
    clip=(0,0,320,200)
    for mode,(x0,y0,x1,y1),value in OPS:
        if mode==2:
            clip=(x0,y0,x1,y1)
            continue
        width,height=(40,25) if mode else (320,200)
        bounds=clip if mode==0 else ((clip[0]+7)//8,(clip[1]+7)//8,clip[2]//8,clip[3]//8)
        for y in range(max(0,y0,bounds[1]),min(height,y1,bounds[3])):
            for x in range(max(0,x0,bounds[0]),min(width,x1,bounds[2])):
                if mode:data[8192+y*40+x]=value
                else:
                    index=y//8*320+x//8*8+y%8;mask=128>>(x%8)
                    if value==0:data[index]&=255^mask
                    elif value==1:data[index]|=mask
                    else:data[index]^=mask
    glyphs=font()
    for (x0,y0,pen,label),bounds in [(op,(0,0,320,200)) for op in TEXT_OPS]+[(CLIP_TEXT,CLIP_BOX)]:
        for index,code in enumerate(label):
            for dy,row in enumerate(glyphs[(code-32)*8:][:8]):
                for dx in range(8):
                    x,y=x0+index*8+dx,y0+dy
                    if not (bounds[0]<=x<bounds[2] and bounds[1]<=y<bounds[3]):continue
                    at=y//8*320+x//8*8+y%8;mask=128>>(x%8)
                    ink=bool(row&(128>>dx));old=bool(data[at]&mask)
                    on=ink if pen==3 else ((old and not ink) if pen==0 else (old or ink) if pen==1 else old!=ink)
                    if on:data[at]|=mask
                    else:data[at]&=255^mask
    return bytes(data)
