#!/usr/bin/env python3
"""Read-only verification of integrated sources and all captured VICE bytes."""
import hashlib
import json
from pathlib import Path
import sys

A=Path(__file__).resolve().parent
B=A.parent/'2026-09-12-native-capture-context/inputs'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(A/'source-manifest.json');assert len(manifest)==15
for name,digest in manifest.items():assert sha(A/'overlays'/name)==digest,name
for name,digest in read(A/'unchanged-images-and-sources.json').items():assert sha(B/name)==digest,name
for name,count in [('cpu-capture',48),('transport-controls',33),('status-controls',10),
                   ('borrower-controls',7),('lifecycle-controls',4)]:
    result=read(A/'controls'/(name+'.json'))
    assert result['passed'] and len(result['cases'])==count,name
sys.path.insert(0,str(B))
from launcher_scene import console,surface

def captures(folder,rows,*,input_fault=False):
    payload_bytes=status_bytes=0
    for row in rows:
        assert row['restored']==(not input_fault)
        data=bytearray()
        for chunk in row['chunks']:
            status=folder/chunk['status_file'];payload=folder/chunk['payload_file']
            assert sha(status)==chunk['status_sha256'] and sha(payload)==chunk['payload_sha256']
            raw=status.read_bytes();part=payload.read_bytes()
            assert len(raw)==12 and len(part)==chunk['count']==chunk['payload_bytes']
            assert raw[0]==chunk['code']==1 and raw[9]==chunk['mode_register']
            assert raw[10]==chunk['common_register'] and raw[11]==chunk['foreground_mmu']
            assert not raw[9]&0x40 and raw[10]&15==4 and raw[11] in (0,14)
            data.extend(part);payload_bytes+=len(part);status_bytes+=len(raw)
        assert len(data)==row['count'] and data==(folder/(row['label']+'.bin')).read_bytes()
        changes=[]
        for name,check in row['borrower_checks'].items():
            before=folder/check['before_file'];after=folder/check['after_file']
            assert sha(before)==check['before_sha256'] and sha(after)==check['after_sha256']
            a,b=before.read_bytes(),after.read_bytes();assert len(a)==len(b)==check['bytes']
            different=[i for i,(x,y) in enumerate(zip(a,b)) if x!=y]
            assert different==check['different_offsets'] and check['matches']==(a==b)
            changes.extend((name,check['address']+i,a[i],b[i]) for i in different)
        if input_fault:
            assert changes==[('metadata',0x3d0c,27,7),('metadata',0x3d13,0,2),
                             ('metadata',0x3d15,0,17),('resident',0x17d0,27,7)]
            assert [f['region'] for f in row['borrower_failures']]==['metadata','resident']
        else:assert not changes and not row['borrower_failures']
    return payload_bytes,status_bytes

E=A/'emulator-sequence';r=read(E/'report.json');s=read(E/'hardware-sequence.json')
assert r['passed'] and s['native_checks_passed'] and not s['physical_hardware_io']
assert r['options']['hardware_sequence']
rows=s['captures']+s['mode_captures'];assert len(rows)==66
assert captures(E,rows)==(101274,2580)
assert len(s['events'])==19 and len(s['desktops'])==5 and len(s['screens'])==6
assert len(s['paused_capture_batches'])==647
assert all(b['pause_acknowledged'] and b['resume_acknowledged'] for b in s['paused_capture_batches'])
labels={b['label'] for b in s['paused_capture_batches']}
for mode in s['mode_captures']:
    assert mode['label']+'-before' in labels and mode['label']+'-restore' in labels
for desktop in s['desktops']:
    assert (E/(desktop['label']+'-surface.bin')).read_bytes()==surface(desktop['selected'])
    assert (E/(desktop['label']+'-vdc.bin')).read_bytes()==console(80,desktop['selected'])
assert s['resident_boot']['passed'] and s['resident_return']['passed']

N=A/'emulator-nested';r=read(N/'report.json')
assert r['passed'] and r['nested_checks_passed'] and not r['physical_hardware_io']
assert captures(N,r['captures'])==(1024,24)
for row,frame in zip(r['captures'],r['nested_frames']):
    assert row['foreground_mmu']==frame['saved_mmu']==0 and frame['outer_saved_mmu']==14
    assert frame['foreground_returned'] and frame['foreground_before']['SP']==frame['foreground_after']['SP']==241
assert sum(d['pixels'] for d in r['desktops'])==128000

I=A/'emulator-input';r=read(I/'report.json')
assert r['passed'] and not r['physical_hardware_io']
assert captures(I,r['captures'],input_fault=True)==(2000,48)
c=r['input_control'];assert c['passed'] and c['activity_rejected'] and not c['physical_failure_cause_proven']
assert c['all_first_readbacks_retained'] and c['resident_immutable_bytes_match']
assert c['injected_keys']==[17,17] and (I/'input-vdc.bin').read_bytes()==console(80)
assert sum(d['pixels'] for d in r['desktops'])==128000
print('PASS: 15 integrated sources; 48 CPU and 54 host controls; full 101,274-byte sequence, propagated mode pauses, nested returns and complete input-failure evidence')
