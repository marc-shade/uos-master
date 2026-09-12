#!/usr/bin/env python3
"""Audit the failed physical experiment without contacting any device."""
import hashlib
import json
from pathlib import Path
import sys

A=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(A/'frozen-inputs.json')
assert len(manifest)==343
for name,digest in manifest.items():assert sha(A/'inputs'/name)==digest,name
baseline=read(A/'baseline-manifest.json')
changed={name for name,digest in baseline.items() if manifest[name]!=digest}
assert changed=={'native_capture.py','native_mode_capture.py','hw_native_desktop_check.py','tests/ci_native_desktop_iec.py'}
assert all(manifest[name]==digest for name,digest in baseline.items() if name.startswith(('target/','src/','probes/')))
for name in ('host-controls','lifecycle-controls','borrower-default','connections'):
    assert read(A/'host-controls'/(name+'.json'))['passed']
assert len(read(A/'host-controls/host-controls.json')['cases'])==33
assert len(read(A/'host-controls/lifecycle-controls.json')['cases'])==4

sys.path.insert(0,str(A/'inputs'))
from launcher_scene import surface,console

def borrowers(folder,captures):
    total=0
    for c in captures:
        assert c['restored']
        assert set(c['borrower_checks'])=={'output','scratch','metadata','resident'}
        for row in c['borrower_checks'].values():
            before=folder/row['before_file'];after=folder/row['after_file']
            assert sha(before)==row['before_sha256'] and sha(after)==row['after_sha256']
            assert before.read_bytes()==after.read_bytes() and before.stat().st_size==row['bytes']
            assert row['matches'] and row['different_offsets']==[]
            total+=before.stat().st_size+after.stat().st_size
    return total

def samples(folder,rows):
    for row in rows:
        selected=int(row['label'].startswith(('trial-','selected-')))
        expected=console(80,selected) if row['mode'] else surface(selected)[row['address']-0xc000:][:row['bytes']]
        assert (folder/(row['label']+'-expected.bin')).read_bytes()==expected
        assert hashlib.sha256(expected).hexdigest()==row['expected_sha256']
        observed=folder/(row['label']+'.bin')
        if row['capture_returned']:
            assert observed.read_bytes()==expected and row['matches'] and not row['different_offsets']
        else:assert not observed.exists() and not row['matches']

e=A/'emulator';er=read(e/'report.json');sequence=read(e/'hardware-sequence.json')
assert er['passed'] and er['options']['transport_sequence'] and sequence['native_checks_passed']
ec=sequence['captures']+sequence['mode_captures']
assert len(ec)==27 and sum(c['count'] for c in ec)==35726
assert len(sequence['paused_capture_batches'])==234
assert all(r['pause_acknowledged'] and r['resume_acknowledged'] for r in sequence['paused_capture_batches'])
assert len(sequence['transport_samples'])==16 and sequence['events']==[{'key':9}]
borrowers(e,ec);samples(e,sequence['transport_samples'])

h=A/'hardware-failed';r=read(h/'report.json');attempt=read(A/'physical-attempt.json')
assert not attempt['passed'] and attempt['process_finished'] and not attempt['full_desktop_qualification']
assert attempt['manifest_sha256']==sha(A/'frozen-inputs.json')
assert not r['passed'] and r['physical_hardware_io'] and not r['full_desktop_workflow']
assert not r.get('native_checks_passed') and not r['events']
assert r['legacy_desktop_restored'] and r['cleanup_complete'] and r['images_unchanged']
assert r['dos_paths_restored'] and r['controls_restored'] and r['preflight_controls_restored']
assert not r['uncertain_host_writes'] and not r['host_connect_failures']
hc=r['captures']+r['mode_captures'];assert len(hc)==12
assert borrowers(h,hc)==116736
completed=[h/(c['label']+'.bin') for c in hc if (h/(c['label']+'.bin')).exists()]
assert len(completed)==11 and sum(p.stat().st_size for p in completed)==15567
last=r['captures'][-1]
assert last['label']=='boot-surface-07d0' and last['restored'] and last['count']==2000
assert last['chunks']==[dict(address=0xc7d0,count=512,code=1,address_resyncs=0,
                            mode_register=55,common_register=4,foreground_mmu=0)]
assert "'foreground_mmu': 0" in r['native_error']
assert len(r['transport_samples'])==2;samples(h,r['transport_samples'])
assert len(r['paused_capture_batches'])==106
assert all(x['pause_acknowledged'] and x['resume_acknowledged'] for x in r['paused_capture_batches'])
receipts=r['ram_write_receipts'];assert len(receipts)==856
for row in receipts:
    expected=f'{row["address"]:04x}-{row["address"]+row["bytes"]-1:04x}'
    reply=json.loads(bytes.fromhex(row['body_hex']))
    assert row['range_acknowledged'] and row['response_received'] and row['status']==200
    assert row['expected_range']==reply['address'].lower()==expected and reply['errors']==[]
    assert not row['replayed'] and 1<=row['bytes']<=128
assert r['resident_boot']['immutable_bytes']==11971 and r['resident_boot']['mutable_bytes']==1581
assert r['resident_boot']['passed'] and not r['resident_boot']['unexpected_changes']
assert read(h/'drives-before.json')==read(h/'drives-restored.json')==read(h/'drives-final.json')
assert (h/'settings-before.bin').read_bytes()==bytes.fromhex('507302f0a502030000')
assert r['dos_paths_before_hex']=={'1':'2f','2':'2f557362302f6336342f232d612f'}
files={r['native_disk_upload_path']:h/'native.d64',r['restore_prg_path']:A/'inputs/target/uos.prg'}
assert set(r['temporary_readbacks'])==set(files) and len(files)==2
for path,p in files.items():
    recorded=r['temporary_readbacks'][path]
    assert recorded['sha256']==sha(p) and recorded['bytes']==p.stat().st_size
    assert (h/('readback-'+Path(path).name+'.bin')).read_bytes()==p.read_bytes()
assert sum(x['bytes'] for x in r['temporary_readbacks'].values())==176884
assert {x['path'] for x in r['temporary_deletions'] if x['confirmed']}==set(files)

n=A/'nested-irq-model';model=read(n/'report.json')
assert model['passed'] and model['actual_rom_irq_entry_and_cli_executed'] and model['induced_nested_irq']
assert model['outer_saved_mmu']==14 and model['nested_saved_mmu']==0
assert model['outer_frame_and_registers_preserved'] and model['old_host_guard_would_reject']
assert not model['physical_failure_cause_proven'] and not model['full_c128_emulator']
assert (n/'captured.bin').read_bytes()==(n/'expected.bin').read_bytes()
assert sha(n/'captured.bin')==model['captured_sha256'] and sha(n/'probe.prg')==model['probe_sha256']
print('PASS: 343 frozen inputs; focused VICE pass; physical MMU guard failure retained; 856 exact receipts; restoration and two-file cleanup verified; ROM nested-IRQ model retained')
