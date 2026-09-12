#!/usr/bin/env python3
"""Reconstruct retained documents and picker pages from saved CPU captures."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ARCHIVE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ARCHIVE/'frozen'))
from native_browser_check import browser_screen,disk_records,ultimate_browser_screen

parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
def read(path):return json.loads(path.read_text())
def digest(data):return hashlib.sha256(data).hexdigest()
listing=(ARCHIVE/'frozen/target/native/editor.lst').read_text()
def address(name):
    match=re.search(r'^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?'+re.escape(name)+r':',listing,re.M)
    assert match,name
    return int(match[1],16)
def frames(directory,label,expected):
    for display,columns in (('vic',40),('vdc',80)):
        assert (directory/(label+'-'+display+'.bin')).read_bytes()==expected(columns),(directory.name,label,display)

documents=[]
for folder in ('emulator-editor-d64','emulator-editor-d71','emulator-editor-d81'):
    directory=ARCHIVE/folder;report=read(directory/'report.json');assert report['passed']
    usb=folder=='hardware'
    saved=(directory/('saved-expected.bin' if usb else 'saved-expected.seq')).read_bytes()
    original=(directory/('fixture-LARGE.TXT.bin' if usb else 'large.seq')).read_bytes()
    assert len(original)==66053 and saved==original[:65537]+b'C12'+original[65537:]
    doc=report['usb_dialogs']['document_during_dialog'] if usb else report['document_during_dialog']
    label=doc['label'];context=(directory/(label+'-context.bin')).read_bytes()
    length,gap,end,capacity=(int.from_bytes(context[i:i+3],'little') for i in (0,3,6,9))
    assert length==len(saved)==66056 and 0<=gap<=end<=capacity and context[12]==1 and not context[14]
    assert context[13]==len(doc['handles'])==17 and capacity==17*4096
    assert {handle['bank'] for handle in doc['handles']}=={0,1}
    assert len({handle['handle_hex'] for handle in doc['handles']})==17
    occupied={(0,page) for page in range(0x60,0xaf)}
    occupied.update((0,page) for page in range(0xdf,0xff))
    occupied.update((1,page) for page in range(4,36))
    captures={item['label']:item for item in report['captures']};physical=bytearray()
    for index,handle in enumerate(doc['handles']):
        assert bytes.fromhex(handle['handle_hex'])==context[16+index*4:20+index*4]
        pages={(handle['bank'],page) for page in range(handle['page'],handle['page']+16)}
        assert all((0x50 if bank==0 else 4)<=page<255 for bank,page in pages)
        assert not pages&occupied;occupied.update(pages)
        chunk_label=f'{label}-chunk-{index:02}'
        chunk=(directory/(chunk_label+'.bin')).read_bytes();parts=[]
        for offset in range(0,4096,2000):
            part_label=f'{chunk_label}-part-{offset:04x}';capture=captures[part_label]
            count=min(2000,4096-offset)
            assert (capture['bank'],capture['address'],capture['count'])==(handle['bank'],handle['page']*256+offset,count)
            assert capture['mode']==0 and capture['restored']
            part=(directory/(part_label+'.bin')).read_bytes();assert len(part)==count;parts.append(part)
        assert chunk==b''.join(parts) and len(chunk)==4096 and digest(chunk)==handle['sha256']
        physical.extend(chunk)
    actual=bytes(physical[:gap]+physical[end:capacity])
    assert actual==saved and digest(actual)==doc['sha256']==report['saved_sha256']
    assert doc['all_bytes_equal'] and (doc['bytes'],doc['gap'],doc['gap_end'],doc['capacity'])==(length,gap,end,capacity)
    documents.append(dict(folder=folder,bytes=length,chunks=17,sha256=digest(actual)))
    if not usb:
        fmt=report['format'];assert report['data_device']==9
        disk=directory/('editor-readback.d64' if folder=='hardware-iec' else 'documents.'+('d64','d71','d81')[fmt])
        final=disk_records(disk.read_bytes(),fmt)
        initial=[row for row in final if row['name']!=b'SAVED'];assert len(final)==len(initial)+1==4
        for label in ('editor-open-file-picker','editor-save-file-picker'):
            frames(directory,label,lambda cols:browser_screen(cols,initial,0,9,fmt,picker=True))
        frames(directory,'browser-after-editor',lambda cols:browser_screen(cols,final,0,9,fmt))

result=dict(passed=True,hardware_io=False,documents=documents,retained_bytes=sum(d['bytes'] for d in documents))
assert len(documents)==3 and result['retained_bytes']==198168
destination=ARCHIVE/'dialog-verification.json'
if args.record:destination.write_text(json.dumps(result,indent=2)+'\n')
else:assert result==read(destination)
print('PASS: three complete retained documents and picker pages reconstructed from CPU captures')
