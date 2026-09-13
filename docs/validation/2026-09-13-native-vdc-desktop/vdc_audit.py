"""Independent linkage of native VDC scenes, CPU capture chunks and handoffs."""
import hashlib,re
from native_vdc_scene import bitmap,attributes,pointer_bitmap,pixels
from native_pointer_check import check_canvas
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def region(folder,label,captures,*,address,count,mode,bank=0):
    records={row['label']:row for row in captures};data=bytearray()
    for offset in range(0,count,2000):
        name=label+f'-{offset:04x}';row=records[name];size=min(2000,count-offset)
        assert (row['address'],row['count'],row['mode'],row['bank'])==(address+offset,size,mode,bank)
        raw=(folder/(name+'.bin')).read_bytes();assert len(raw)==size
        assert raw==b''.join((folder/chunk['payload_file']).read_bytes() for chunk in row['chunks'])
        data.extend(raw)
    return bytes(data)

def frame(folder,row,captures,*,color):
    name=row['label'];selected=row['selected'];error=row['error'];x,y=row['position']
    assert row['color']==color and 0<=selected<6 and 0<=x<640 and x%2==0 and 0<=y<200
    base,pages=(0x4000,72) if color else (0,64)
    state=(folder/(name+'-vdc-state.bin')).read_bytes()
    assert len(state)==7 and state[:4]==bytes((2,1,int(color),0))
    assert state[5:]==bytes((base//256,pages))
    assert row['snapshot_pages']==pages and row['pixels']==128000
    expected=pointer_bitmap(bitmap(selected,error),x,y,row['pointer_visible'])
    raw=region(folder,name+'-vdc-bitmap',captures,address=base,count=16000,mode=1)
    assert raw==expected==(folder/(name+'-vdc-bitmap.bin')).read_bytes()
    assert sha(raw)==row['bitmap_sha256']
    if color:
        colors=region(folder,name+'-vdc-attributes',captures,address=0x8000,count=2000,mode=1)
        assert colors==attributes(selected)==(folder/(name+'-vdc-attributes.bin')).read_bytes()
    expected_pixels=pixels(selected,color=color,x=x,y=y,visible=row['pointer_visible'],error=error)
    wanted=[expected_pixels[offset:offset+640] for offset in range(0,128000,640)]
    assert check_canvas((folder/(name+'-vdc-canvas.bin')).read_bytes(),wanted)==row['rectangle']

def snapshot(folder,row,captures):
    name=row['label'];handle=bytes.fromhex(row['handle']);record=bytes.fromhex(row['record'])
    assert len(handle)==4 and 1<=handle[0]<=32 and len(record)==8
    assert record[0]==32 and record[1] in (0,1) and record[3]==row['pages'] and record[4:7]==handle[1:]
    assert (row['base'],row['pages'])==((0x4000,72) if row['color'] else (0,64))
    raw=region(folder,name+'-snapshot',captures,address=record[2]*256,count=record[3]*256,mode=0,bank=record[1])
    assert raw==(folder/(name+'-snapshot.bin')).read_bytes() and sha(raw)==row['sha256']
    saved=(folder/(name+'-saved-registers.bin')).read_bytes()
    assert len(saved)==14 and saved.hex()==row['saved_registers']
    return raw,saved

def restore(folder,row,captures,source):
    raw,_=snapshot(folder,row,captures);name=row['label'].removesuffix('-close')
    symbols=dict((m[1],int(m[2],16)) for m in re.finditer(r'^(\w+)\s*=\s*\$([0-9a-f]+)',(source/'target/native-desktop/desktop.sym').read_text(),re.M))
    assert row['checkpoint_address']==symbols['vd_restore_registers']
    checkpoint=(folder/(name+'-restore-checkpoint.bin')).read_bytes()
    assert checkpoint.hex()==row['checkpoint_hex'] and len(checkpoint)==23
    assert checkpoint[7:9]==checkpoint[5:7] and checkpoint[9:13]==bytes((1,1,4,0))
    assert checkpoint[21:]==bytes(2)  # No condition; computer memory space.
    assert int.from_bytes(checkpoint[5:7],'little')==row['checkpoint_address']
    assert int.from_bytes(checkpoint[13:17],'little')>0
    assert row['lifetime']=='desktop snapshot still owned; VRAM restored before register restoration'
    assert (folder/(name+'-restored-vram.bin')).read_bytes()==raw

def font(folder,row,captures):
    raw,saved=snapshot(folder,row,captures);base=row['base'];name=row['label']
    # The incoming text address arrangement can differ from physical capacity.
    def address(at):
        if saved[11]&16:return at if row['color'] else (at&255)|((at&0x7e00)>>1)
        return (at&0x80ff)|((at&0x3f00)<<1)|(at&0x100) if row['color'] else at&0x3fff
    untouched={}
    for item in captures:
        if item['label'].startswith(name+'-untouched-'):
            assert item['mode']==1 and item['bank']==0 and item['count']<=2000
            data=(folder/(item['label']+'.bin')).read_bytes()
            assert len(data)==item['count']
            for i,value in enumerate(data):
                at=item['address']+i;assert not base<=at<base+len(raw) and at not in untouched
                untouched[at]=value
    expected=bytes(raw[at-base] if base<=at<base+len(raw) else untouched[at] for at in map(address,range(0x3000,0x4000)))
    assert (folder/(name+'-original-vdc.bin')).read_bytes()==expected
    return expected
