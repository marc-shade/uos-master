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
sys.path.insert(0,str(ARCHIVE/'oracle'))
from native_browser_check import browser_screen,disk_records,ultimate_browser_screen

parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
def read(path):return json.loads(path.read_text())
def digest(data):return hashlib.sha256(data).hexdigest()
listing=(ARCHIVE/'package/clean/target/native/editor.lst').read_text()
def address(name):
    match=re.search(r'^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?'+re.escape(name)+r':',listing,re.M)
    assert match,name
    return int(match[1],16)
def frames(directory,label,expected):
    for display,columns in (('vic',40),('vdc',80)):
        assert (directory/(label+'-'+display+'.bin')).read_bytes()==expected(columns),(directory.name,label,display)

documents=[]
for folder in ('emulator-editor-d64','emulator-editor-d71','emulator-editor-d81','hardware-iec','hardware'):
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

directory=ARCHIVE/'hardware';report=read(directory/'report.json');nav=report['usb_dialogs']
assert nav['passed'] and nav['final_order_verified'] and nav['oracles']==report['usb_browser']['oracles']
assert nav['final_oracle']==report['usb_browser']['final_oracle']
def data(label):return (directory/(label+'.bin')).read_bytes()
def entries(oracle,base=0):return [bytes.fromhex(raw) for raw in oracle['pages'][str(base)]['entries_hex']]
final=entries(nav['final_oracle']);captures={item['label']:item for item in report['captures']}
assert len(final)==11
pages={};deferred=0;local_records=banked_records=0
for page in nav['pages']:
    label=page['label'];assert label not in pages
    mailbox=data(label+'-browser-mailbox');state=data(label+'-browser-state')
    def value(name,size=1):
        at=address(name)-address('bu_cursor');return int.from_bytes(state[at:at+size],'little')
    count=value('bu_count');side=value('bu_side');assert 0<count<=8 and side in (0,16)
    assert len(mailbox)==21 and mailbox[0]==32 and mailbox[9]==page['device']==1 and mailbox[10]==3
    assert (value('bu_base',4),value('bu_row'),bool(value('bu_more')),value('bu_cursor',4))==(
        page['base'],page['selected'],page['more'],page['cursor'])
    assert int.from_bytes(mailbox[16:20],'little')==page['ordinal']==page['base']+page['selected']
    path=data(label+'-retained-path');name=data(label+'-retained-name-direct')
    assert len(path)==mailbox[14] and path.hex()==page['path_hex']
    assert len(name)==mailbox[20] and name.hex()==page['selected_name_hex']
    assert page['retained_name_observation']=='direct below-ROM RAM; observer borrows this buffer'
    lengths=data(label+'-cache-name-lengths');handles=data(label+'-cache-handles')
    assert len(lengths)==16 and len(handles)==40
    cache=data(label+'-cache');assert page['cache_record_bytes']==256 and len(cache)==count*256
    actual=[]
    for index in range(count):
        logical=side//2+index;length=lengths[logical];assert 1<=length<=255
        assert page['cache_name_lengths'][index]==length
        if logical<8:
            bank=0;source=address(('d_input','d_output','ed_other_page','ed_verify_data')[logical//2])+(logical%2)*256
            local_records+=1
        else:
            heap_page=logical-8;at=(heap_page//4)*4;handle=handles[at:at+4]
            descriptor=data(f'{label}-cache-descriptor-{index}')
            assert 1<=handle[0]<=32 and descriptor[0]==32 and descriptor[1] in (0,1)
            assert descriptor[3]==4 and descriptor[4:7]==handle[1:]
            bank=descriptor[1];source=(descriptor[2]+heap_page%4)*256;banked_records+=1
        capture=captures[f'{label}-cache-record-{index}']
        assert (capture['mode'],capture['bank'],capture['address'],capture['count'])==(0,bank,source,256)
        record=data(f'{label}-cache-record-{index}');assert record==cache[index*256:(index+1)*256]
        actual.append(record[:length+1])
    assert [entry.hex() for entry in actual]==page['entries_hex'] and name==actual[page['selected']][1:]
    if 'stage_names_hex' in page:
        names={bytes.fromhex(raw) for raw in page['stage_names_hex']}
        ordered=[entry for entry in final if entry[1:] in names]
        assert len(ordered)==len(names) and actual==ordered[page['base']:page['base']+8]
        assert ordered[page['ordinal']][1:].hex()==page['expected_selection_hex']
        assert page['order_check']=='passed against independent post-boot directory order'
        total=len(ordered);deferred+=1
    else:
        oracle=next(item for item in nav['oracles'].values() if item['path_hex']==path.hex())
        assert actual==entries(oracle,page['base'])[:8];total=oracle['count']
    assert count==min(8,total-page['base']) and page['more']==(page['base']+count<total)
    pages[label]=page
assert local_records and banked_records
assert pages['ultimate-picker-ordinal-256']['base']==256 and pages['ultimate-picker-back-248']['base']==248
for frame in nav['frames']:
    assert frame['picker'] and frame['label'] in pages
    frames(directory,frame['label'],lambda cols:ultimate_browser_screen(cols,
        bytes.fromhex(frame['path_hex']),[bytes.fromhex(raw) for raw in frame['entries_hex']],
        frame['base'],frame['selected'],frame['device'],frame['more'],frame['error'],
        path_prompt=frame['path_prompt'],prompt_device=frame['prompt_device'],directory_prompt=frame['directory_prompt'],picker=True))
assert {frame['label'] for frame in nav['frames']}==set(pages)
assert len(nav['next_seconds'])==32
for elapsed in nav['next_seconds']:
    assert any(event.get('key')==ord('N') and event['elapsed_seconds']==elapsed for event in report['events'])
cpu=read(ARCHIVE/'cpu-file-dialog.json');assert cpu['passed'] and len(cpu['cases'])==11
assert cpu['saved_large']==dict(bytes=66056,sha256=documents[0]['sha256'])
result=dict(passed=True,cpu_flows=11,complete_live_documents=documents,physical_usb_pages=len(pages),
    physical_usb_frame_pairs=len(nav['frames']),physical_local_cache_records=local_records,
    physical_banked_cache_records=banked_records,post_creation_order_checks=deferred,
    physical_next_actions=32,largest_checked_ordinal=256,full_os_complete=False)
destination=ARCHIVE/'dialog-verification.json'
if args.record:destination.write_text(json.dumps(result,indent=2)+'\n')
else:assert result==read(destination)
print('PASS: five complete retained 66,056-byte documents, IEC picker screens and exact Ultimate picker cache pages')
