#!/usr/bin/env python3
"""Verify retained observer inputs, raw capture evidence and nested IRQ returns."""
import hashlib
import json
from pathlib import Path
import sys
A=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(A/'frozen-inputs.json');assert len(manifest)==345
for name,digest in manifest.items():assert sha(A/'inputs'/name)==digest,name
previous=read(A/'predecessor-manifest.json')
assert all(manifest[n]==v for n,v in previous.items() if n.startswith(('src/','target/','probes/')))
controls={n:read(A/'host-controls'/(n+'.json')) for n in (
    'cpu-capture','host-controls','status-controls','borrower-default','lifecycle-controls','connections')}
assert all(r['passed'] for r in controls.values())
assert len(controls['cpu-capture']['cases'])==48
assert sum(len(controls[n]['cases']) for n in controls if n!='cpu-capture')==60
assert [r['value'] for r in controls['status-controls']['cases'] if r['accepted']]==[14,0]
assert all(r['raw_status_retained'] and r['restored'] for r in controls['status-controls']['cases'])

sys.path.insert(0,str(A/'inputs'))
from launcher_scene import surface,console

def captures(folder,rows):
    status_bytes=payload_bytes=borrower_bytes=0
    for row in rows:
        assert row['restored']
        result=bytearray()
        for chunk in row['chunks']:
            status=folder/chunk['status_file'];payload=folder/chunk['payload_file']
            assert sha(status)==chunk['status_sha256'] and sha(payload)==chunk['payload_sha256']
            raw=status.read_bytes();data=payload.read_bytes()
            assert len(raw)==12 and len(data)==chunk['count']==chunk['payload_bytes']
            assert raw[0]==chunk['code']==1 and raw[9]==chunk['mode_register']
            assert raw[10]==chunk['common_register'] and raw[11]==chunk['foreground_mmu']
            assert not raw[9]&0x40 and raw[10]&15==4 and raw[11] in (0,14)
            assert int.from_bytes(raw[7:9],'little')==chunk['address_resyncs']
            result.extend(data);status_bytes+=len(raw);payload_bytes+=len(data)
        assert len(result)==row['count'] and result==(folder/(row['label']+'.bin')).read_bytes()
        assert set(row['borrower_checks'])=={'output','scratch','metadata','resident'}
        for check in row['borrower_checks'].values():
            before=folder/check['before_file'];after=folder/check['after_file']
            assert sha(before)==check['before_sha256'] and sha(after)==check['after_sha256']
            assert before.read_bytes()==after.read_bytes() and before.stat().st_size==check['bytes']
            assert check['matches'] and check['different_offsets']==[]
            borrower_bytes+=2*check['bytes']
    return status_bytes,payload_bytes,borrower_bytes

e=A/'emulator-focused';r=read(e/'report.json');s=read(e/'hardware-sequence.json')
assert r['passed'] and s['native_checks_passed'] and r['options']['transport_sequence']
rows=s['captures']+s['mode_captures'];assert len(rows)==27
assert captures(e,rows)==(912,35726,262656)
assert len(s['paused_capture_batches'])==234
assert all(b['pause_acknowledged'] and b['resume_acknowledged'] for b in s['paused_capture_batches'])
assert s['events']==[{'key':9}] and len(s['transport_samples'])==16
for row in s['transport_samples']:
    selected=int(row['label'].startswith(('trial-','selected-')))
    expected=console(80,selected) if row['mode'] else surface(selected)[row['address']-0xc000:][:row['bytes']]
    assert (e/(row['label']+'.bin')).read_bytes()==expected
    assert (e/(row['label']+'-expected.bin')).read_bytes()==expected
    assert row['matches'] and row['capture_returned'] and not row['different_offsets']

n=A/'emulator-nested';r=read(n/'report.json')
assert r['passed'] and r['nested_checks_passed'] and r['options']['nested_irq']
assert len(r['captures'])==len(r['nested_frames'])==2
assert captures(n,r['captures'])==(24,1024,19456)
assert len(r['desktops'])==2 and sum(d['pixels'] for d in r['desktops'])==128000
for row,frame in zip(r['captures'],r['nested_frames']):
    assert row['foreground_mmu']==frame['saved_mmu']==0
    assert frame['outer_saved_mmu']==14 and frame['foreground_returned']
    assert frame['foreground_before']['SP']==frame['foreground_after']['SP']==241
    outer=(n/(frame['label']+'-outer-stack.bin')).read_bytes()
    nested=(n/(frame['label']+'-nested-stack.bin')).read_bytes()
    assert len(outer)==len(nested)==256
    assert outer[frame['outer']['SP']+3]==14 and nested[frame['nested']['SP']+1]==0
    sp=frame['nested']['SP']
    assert int.from_bytes(nested[sp+6:sp+8],'little')==frame['interrupted_pc']
    assert frame['interrupted_pc'] in (0xc567,0xc569)
    expected=surface()[0x7d0:0x9d0] if row['mode']==0 else console(80)[:512]
    assert (n/(row['label']+'.bin')).read_bytes()==expected
for directory in (A/'emulator-harness-history').iterdir():
    history=read(directory/'report.json')
    assert not history['passed'] and not history.get('nested_checks_passed')
print('PASS: 345 inputs, 48 CPU cases, 60 host controls, 35,726-byte focused VICE, forced nested RAM/VDC capture and complete foreground return')
