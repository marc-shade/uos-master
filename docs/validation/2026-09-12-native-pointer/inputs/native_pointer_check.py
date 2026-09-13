"""Independent VIC palette-index oracle, including the outlined pointer."""
from launcher_scene import POINTER, surface


def pixels(selected, x, y, *, visible=True):
    source=surface(selected)
    rows=[]
    for py in range(200):
        row=bytearray()
        for px in range(320):
            colors=source[8192+py//8*40+px//8]
            ink=source[py//8*320+px//8*8+py%8]&(128>>(px%8))
            color=colors>>4 if ink else colors&15
            dx,dy=px-x,py-y
            if visible and 0<=dy<len(POINTER) and 0<=dx<len(POINTER[dy]):
                mark=POINTER[dy][dx]
                if mark in 'BW':color=int(mark=='W')
            row.append(color)
        rows.append(bytes(row))
    return rows


def check_canvas(raw, expected):
    import struct
    fields,=struct.unpack_from('<I',raw)
    width,height,xoff,yoff,innerw,innerh,bpp=struct.unpack_from('<6HB',raw,4)
    length,=struct.unpack_from('<I',raw,4+fields);data=raw[8+fields:]
    assert fields>=13 and bpp==8 and length==width*height and length-len(data) in (0,4)
    matches=[]
    for y in range(height-199):
        row=data[y*width:(y+1)*width];x=row.find(expected[0])
        while x>=0:
            if all(data[(y+dy)*width+x:(y+dy)*width+x+320]==wanted for dy,wanted in enumerate(expected)):
                matches.append([x,y,320,200])
            x=row.find(expected[0],x+1)
    assert len(matches)==1,('rendered pointer/desktop mismatch',matches)
    return matches[0]
