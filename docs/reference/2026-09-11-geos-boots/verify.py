#!/usr/bin/env python3
"""Audit saved GEOS boot metadata and screenshots; no emulator or hardware I/O."""
import hashlib
import json
from pathlib import Path

ARCHIVE=Path(__file__).resolve().parent
read=lambda name:json.loads((ARCHIVE/name).read_text())
digest=lambda data:hashlib.sha256(data).hexdigest()
summary=read('observations.json')
assert not summary['hardware_io'] and not summary['native_uos_images_used']
assert not summary['runtime_parity_qualified']
assert set(summary['runs'])=={'40','80'}
screens=0
for columns,entry in summary['runs'].items():
    report=read(entry['report'])
    folder=(ARCHIVE/entry['report']).parent/columns
    run=report['runs'][columns]
    assert report['source_sha256']==summary['source_disk_sha256']
    assert report['source_unchanged'] and run['capture_complete']
    assert not run['working_disk_changed']
    assert run['working_disk_sha256_after']==report['source_sha256']
    assert entry['initial_display_argument'] in run['command']
    assert '-VDC16KB' in run['command'] and '-warp' in run['command']
    assert 'VDC64KB=0' in (folder/'vice.log').read_text()
    assert not entry['interaction_tested'] and not entry['actual_runtime_version_verified']
    assert len(run['captures'])==3
    for stamp,capture in zip((30,60,90),run['captures']):
        assert capture['screenshot']==f'host-display-{stamp:03}.png'
        assert digest((folder/capture['screenshot']).read_bytes())==capture['screenshot_sha256']
        for name,size in (('mmu',12),('vic-registers',64)):
            data=(folder/capture[name]['file']).read_bytes()
            assert len(data)==size==capture[name]['bytes']
            assert digest(data)==capture[name]['sha256']
        for name,size in (('ram00',65536),('ram01',65536),('vdc',16384)):
            assert capture[name]['bytes']==size and len(capture[name]['sha256'])==64
        screens+=1
initial=read('initial/report.json')
assert not initial['capture_complete'] and initial['runs']['80']['capture_complete']
assert not initial['runs']['40']['capture_complete']
assert "Unknown option '+80col'." in (ARCHIVE/'initial/40/vice.log').read_text()
assert read('retry40/report.json')['capture_complete']
assert set(read('retry40/report.json')['runs'])=={'40'}
assert len(summary['loaded_resource_files'])==7
print(f'PASS: {screens} saved host screenshots; both completed reference boots; failed option retained; no interaction/parity claim')

