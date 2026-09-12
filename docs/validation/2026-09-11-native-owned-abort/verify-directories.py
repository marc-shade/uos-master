#!/usr/bin/env python3
"""Reconstruct native USB pages and screens from archived bytes and DOS listings."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ARCHIVE=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ARCHIVE/'oracle'))
from native_browser_check import ultimate_browser_screen,preview_screen,browser_screen,disk_records

parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
directory=ARCHIVE/'hardware'
report=json.loads((directory/'report.json').read_text());nav=report['usb_browser']
assert report['passed'] and nav['passed'] and nav['final_order_verified']
assert report['legacy_desktop_restored'] and report['dos_paths_restored'] and report['private_files_removed']
listing=(ARCHIVE/'package/clean/target/native/browse.lst').read_text()
def address(name):
    match=re.search(r'^[.>]([0-9a-fA-F]{4})\s+(?:(?:[0-9a-fA-F]{2} ?)+\s+)?'+re.escape(name)+r':',listing,re.M)
    assert match,name
    return int(match[1],16)
def data(label):return (directory/(label+'.bin')).read_bytes()
def entries(oracle,base=0):return [bytes.fromhex(raw) for raw in oracle['pages'][str(base)]['entries_hex']]
def frames(label,expect):
    assert data(label+'-vic')==expect(40),label+' VIC'
    assert data(label+'-vdc')==expect(80),label+' VDC'

oracles=nav['oracles'];final=entries(nav['final_oracle'])
assert oracles['large']['count']>264 and oracles['empty']['open_code']==1 and oracles['empty']['count']==0
assert len(final)==nav['final_oracle']['count']==11 and not nav['final_oracle']['pages']['0']['full']
initial=entries(oracles['private']);assert len(initial)==8
assert {entry[1:] for entry in final}=={entry[1:] for entry in initial}|{
    b'HISTORY',b'A LONG SAVED DOCUMENT NAME.TXT',b'LARGE COPY.TXT'}
for oracle in [*oracles.values(),nav['final_oracle']]:
    assert bytes.fromhex(oracle['path_hex']).startswith(b'/')
    for base,page in oracle['pages'].items():
        assert page['count']==oracle['count'] and not page['clipped']
        raw=entries(oracle,int(base))
        assert len(raw)>=min(8,max(0,oracle['count']-int(base)))
        assert all(2<=len(entry)<=256 and not any(value in entry[1:] for value in (0,47,92)) for entry in raw)

page_records={};deferred=0
for page in nav['pages']:
    label=page['label'];assert label not in page_records
    mailbox=data(label+'-browser-mailbox');state=data(label+'-browser-state')
    def value(name,size=1):
        start=address(name)-address('bu_cursor');return int.from_bytes(state[start:start+size],'little')
    assert len(mailbox)==21 and mailbox[0]==32 and mailbox[10]==3 and mailbox[9]==page['device']
    assert (value('bu_base',4),value('bu_row'),bool(value('bu_more')),value('bu_cursor',4))==(
        page['base'],page['selected'],page['more'],page['cursor'])
    assert int.from_bytes(mailbox[16:20],'little')==page['ordinal']==page['base']+page['selected']
    path=data(label+'-retained-path');name=data(label+'-retained-name-direct')
    assert len(path)==mailbox[14] and path.hex()==page['path_hex']
    assert len(name)==mailbox[20] and name.hex()==page['selected_name_hex']
    assert page['retained_name_observation']=='direct below-ROM RAM; observer borrows this buffer'
    handle=data(label+'-cache-handle');descriptor=data(label+'-cache-descriptor')
    assert 1<=handle[0]<=32 and descriptor[:2]==bytes([32,1]) and descriptor[3]==37 and descriptor[4:7]==handle[1:]
    assert value('bu_side') in (0,16)
    cache=data(label+'-cache');count=value('bu_count')
    assert 0<=count<=8 and len(cache)==count*512
    assert cache==b''.join(data(label+f'-cache-{offset:04x}') for offset in range(0,len(cache),2000))
    actual=[]
    for index in range(count):
        row=cache[index*512:(index+1)*512];length=row[510]
        assert 1<=length<=255
        actual.append(row[:length+1])
    assert [entry.hex() for entry in actual]==page['entries_hex']
    assert name==(actual[page['selected']][1:] if actual else b'')
    if 'stage_names_hex' in page:
        wanted_names={bytes.fromhex(raw) for raw in page['stage_names_hex']}
        ordered=[entry for entry in final if entry[1:] in wanted_names]
        assert len(ordered)==len(wanted_names)
        assert actual==ordered[page['base']:page['base']+8]
        assert ordered[page['ordinal']][1:].hex()==page['expected_selection_hex']
        assert page['order_check']=='passed against independent post-boot directory order'
        total=len(ordered);deferred+=1
    else:
        matches=[oracle for oracle in oracles.values() if oracle['path_hex']==path.hex()]
        assert len(matches)==1
        oracle=matches[0];assert actual==entries(oracle,page['base'])[:8]
        total=oracle['count']
    assert count==min(8,total-page['base']) and page['more']==(page['base']+count<total)
    page_records[label]=page

signature=lambda frame:tuple(json.dumps(frame[key],sort_keys=True) for key in
    ('path_hex','entries_hex','base','selected','device','more'))
page_signatures={signature(page) for page in nav['pages']}
for frame in nav['frames']:
    assert signature(frame) in page_signatures
    frames(frame['label'],lambda columns:ultimate_browser_screen(columns,
        bytes.fromhex(frame['path_hex']),[bytes.fromhex(raw) for raw in frame['entries_hex']],
        frame['base'],frame['selected'],frame['device'],frame['more'],frame['error'],
        path_prompt=frame['path_prompt'],prompt_device=frame['prompt_device'],directory_prompt=frame['directory_prompt'],field_caret=frame.get('field_caret'),
        field_view=None if frame.get('field_views') is None else frame['field_views'][int(columns==80)]))
assert {page['label'] for page in nav['pages']}<={frame['label'] for frame in nav['frames']}
assert page_records['directory-ordinal-256']['base']==256 and page_records['directory-back-248']['base']==248
assert page_records['directory-empty']['entries_hex']==[]
assert page_records['usb-browser-after-calculator']['expected_selection_hex']==b'USB CALCULATOR LONG NAME.PRG'.hex()
assert page_records['usb-browser-after-editor']['expected_selection_hex']==b'TEXT EDITOR.PRG'.hex()
assert page_records['usb-browser-after-corrupt']['expected_selection_hex']==b'BAD APP.PRG'.hex()
assert len(nav['next_seconds'])==32 and all(value>0 for value in nav['next_seconds'])
for elapsed in nav['next_seconds']:
    assert any(event.get('key')==ord('N') and event['elapsed_seconds']==elapsed for event in report['events'])
note=data('fixture-NOTE.TXT')
frames('directory-note-preview',lambda columns:preview_screen(columns,b'NOTE.TXT',note,eof=True))
records=disk_records((directory/'native.d64').read_bytes())
frames('directory-iec-start',lambda columns:browser_screen(columns,records))
result=dict(passed=True,pages=len(nav['pages']),frame_pairs=len(nav['frames'])+2,
    directory_entries=oracles['large']['count'],next_actions=32,largest_checked_ordinal=256,
    post_creation_order_checks=deferred,final_directory_entries=len(final),
    selection_after_history_verified=True,selection_after_editor_verified=True,
    complete_cached_names_verified=True,direct_retained_name_observations=len(nav['pages']),
    full_os_complete=False)
destination=ARCHIVE/'directory-verification.json'
if args.record:destination.write_text(json.dumps(result,indent=2)+'\n')
else:assert result==json.loads(destination.read_text())
print(f"PASS: {result['pages']} exact native USB pages; ordinal 256, full names, app return selection and both screens")
