#!/usr/bin/env python3
"""Verify session selection, ABI admission, packaged images and retained displays."""
import hashlib
import json
from pathlib import Path
import sys

A=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name,digest in read(A/'source-manifest.json').items():assert sha(A/'overlays'/name)==digest,name
for name,digest in read(A/'controls/images-before-tests.json').items():
    assert sha(A/'images'/Path(name).relative_to('target'))==digest,name
for name,count in [('desktop',18),('workspace',18),('apps',54),('ultimate-loader',56),('modules',115),('restart',4)]:
    result=read(A/'controls'/(name+'-cpu.json'))
    assert result['passed'] and len(result['cases'])==count,name
for p in (A/'controls/cpu-harness-history').glob('*.json'):assert not read(p)['passed']
layout=read(A/'controls/layout-differences.json')
assert layout['all_layouts_unchanged'] and layout['all_images_unchanged_during_tests']
for name,offset in [('native',8913),('native-desktop',8916)]:
    assert layout[name]['bytes']==15617
    assert layout[name]['changes']==[dict(address=7343,before=3,after=4),
        dict(address=7345,before=48,after=47),dict(address=offset,before=9,after=10),
        dict(address=18606,before=9,after=10)]
deployment=read(A/'images/native-desktop/deployment.json')
assert deployment['abi']=='1.9' and deployment['selection_state_address']==0x3d2f
assert deployment['desktop']['pages']==18 and deployment['surface_pages']==36 and deployment['free_pages_at_desktop']==372
assert (A/'images/native-desktop/desktop.prg').stat().st_size==4497
sys.path.insert(0,str(A.parent/'2026-09-12-native-capture-context/inputs'))
from launcher_scene import console,surface

pixels=0
for mode in ('desktop','80col','workspace','missing-app','input','sequence'):
    folder=A/('emulator-'+mode);r=read(folder/'report.json')
    assert r['passed'] and not r['physical_hardware_io'],mode
    for row in r['desktops']:
        label=row['label'];selected=row['selected'];error=row['error'];fallback=row['fallback']
        assert (folder/(label+'-80.bin')).read_bytes()==console(80,selected,error,fallback)
        if fallback:
            assert (folder/(label+'-40.bin')).read_bytes()==console(40,selected,error,True)
        else:
            expected=surface(selected,error)
            assert (folder/(label+'-surface.bin')).read_bytes()==expected
            raw=(folder/(label+'-display-get.bin')).read_bytes()
            import struct
            fields,=struct.unpack_from('<I',raw)
            width,height,xoff,yoff,iw,ih,bpp=struct.unpack_from('<6HB',raw,4)
            x,y,w,h=row['rectangle'];data=raw[8+fields:]
            assert bpp==8 and (w,h)==(320,200) and row['pixels']==64000
            for py in range(200):
                for px in range(320):
                    color=expected[8192+py//8*40+px//8]
                    ink=expected[py//8*320+px//8*8+py%8]&(128>>(px%8))
                    assert data[(y+py)*width+x+px]==(color>>4 if ink else color&15)
            pixels+=row['pixels']
    if mode in ('desktop','80col','workspace','missing-app'):
        states={d['label']:d['selected'] for d in r['desktops']}
        assert states['desktop-after-files']==states['desktop-after-workspace']==2
        if mode!='missing-app':assert states['desktop-after-editor']==1
assert pixels==2496000

folder=A/'emulator-sequence';s=read(folder/'hardware-sequence.json')
assert s['native_checks_passed'] and len(s['captures'])+len(s['mode_captures'])==66
assert [d['selected'] for d in s['desktops']]==[0,1,0,1,2]
payload_bytes=0
for row in s['captures']+s['mode_captures']:
    assert row['restored'] and not row['borrower_failures']
    data=bytearray()
    for chunk in row['chunks']:
        status=folder/chunk['status_file'];payload=folder/chunk['payload_file']
        assert sha(status)==chunk['status_sha256'] and sha(payload)==chunk['payload_sha256']
        raw=status.read_bytes();part=payload.read_bytes()
        assert len(raw)==12 and raw[0]==1 and raw[11] in (0,14)
        assert len(part)==chunk['count']==chunk['payload_bytes']
        data.extend(part);payload_bytes+=len(part)
    assert data==(folder/(row['label']+'.bin')).read_bytes()
    for check in row['borrower_checks'].values():
        before=folder/check['before_file'];after=folder/check['after_file']
        assert sha(before)==check['before_sha256'] and sha(after)==check['after_sha256']
        assert before.read_bytes()==after.read_bytes() and check['matches']
assert payload_bytes==101274 and len(s['paused_capture_batches'])==647
assert all(b['pause_acknowledged'] and b['resume_acknowledged'] for b in s['paused_capture_batches'])
assert s['resident_boot']['passed'] and s['resident_return']['passed']

i=read(A/'emulator-input/report.json')['input_control']
assert i['passed'] and i['activity_rejected'] and i['all_first_readbacks_retained']
assert not i['physical_failure_cause_proven']
assert i['expected_input_metadata_changes'][-1]==dict(address=0x3d2f,before=0,after=2)
print('PASS: ABI 1.9 selection; 265 CPU cases, six VICE workflows, 2,496,000 rendered pixels, unchanged resident layout and complete 101,274-byte app sequence')
