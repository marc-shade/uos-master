#!/usr/bin/env python3
"""Audit the temporary patch, six reads, byte proofs and restored resources."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent;RUN=HERE/'run';INPUTS=HERE/'inputs'
sys.dont_write_bytecode=True;sys.path.insert(0,str(INPUTS))
from native_editor_check import editor_screen
from native_browser_check import disk_records,browser_screen
from native_capture import expected_screen
from hwlib import lst_symbol
read=lambda p:json.loads(p.read_text())
sha=lambda data:hashlib.sha256(data).hexdigest()
parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
report=read(RUN/'report.json');context=read(HERE/'context.json')
assert context['diagnostic_only'] and not context['unmodified_product_qualification']
assert not context['initiating_fault_reproduced'] and context['frozen_inputs']==257
frozen=read(INPUTS/'frozen-inputs.json');assert len(frozen)==257
for name,digest in frozen.items():assert sha((INPUTS/name).read_bytes())==digest,name
for name,digest in report['build'].items():assert sha((INPUTS/name).read_bytes())==digest,name
assert report['build']['target/native/uos128.prg']==context['kernel_sha256']=='45281b86a55f93c6402a7b0159075148d0f19086471c504bf859332c0b25e63d'
for key in ('passed','native_checks_passed','legacy_desktop_restored','images_unchanged',
            'all_owned_memory_and_files_released','dos_paths_restored','private_files_removed'):
    assert report[key],key
assert not report['uncertain_host_writes'] and not report['host_connect_failures']
assert report['dos_paths_after_hex']==report['dos_paths_before_hex']
assert read(RUN/'drives-before.json')==read(RUN/'drives-restored.json')
assert bytes.fromhex(report['legacy_boot_settings_hex'])[2:7]==(RUN/'settings-before.bin').read_bytes()[2:7]
assert (RUN/'native.d64').read_bytes()==(INPUTS/'target/native/uos128.d64').read_bytes()
class Symbols(dict):
    def __missing__(self,key):
        self[key]=lst_symbol('native/editor',key)
        return self[key]
symbols=Symbols()
probe=report['rollback_probe'];assert probe['address']==symbols['ed_open_rollback']+3==0x8a3e
before=b'\x20'+symbols['ed_close_owned'].to_bytes(2,'little');after=b'\xea'*3
assert before.hex()==probe['before_hex']=='20dd88' and after.hex()==probe['after_hex']
assert all(probe[key] for key in ('patch_started','patch_verified','restore_started','restored'))
program=(INPUTS/'target/native/editor.prg').read_bytes()
offset=2+probe['address']-int.from_bytes(program[:2],'little');assert program[offset:offset+3]==before
for label,expected in [('rollback-probe-before',before),('rollback-probe-patched',after),
                       ('rollback-probe-before-restore',after),('rollback-probe-restored',before)]:
    assert (RUN/(label+'.bin')).read_bytes()==expected
cpu=read(INPUTS/'probe-cpu.json');assert cpu['passed'] and not cpu['hardware_io'] and len(cpu['cases'])==6
assert cpu['patch_address']==probe['address'] and cpu['before_hex']==before.hex() and cpu['after_hex']==after.hex()
assert cpu['cases']['unpatched-short-read']['first_transport']==0
for name,value in [('short-read',229),('overlong',252),('timeout',255)]:
    assert cpu['cases'][name]['first_transport']==value and cpu['cases'][name]['retained']
assert cpu['cases']['dos-error']['first_dos']==71 and cpu['cases']['success']['close_commands']==1
directory=report['private_directory'];assert re.fullmatch(r'/Usb0/uos-native-[0-9a-f]{12}',directory)
expected={}
assert set(report['fixture_readbacks'])=={'NOTE.TXT','EMPTY.TXT','LARGE.TXT'}
for name,record in report['fixture_readbacks'].items():
    data=(RUN/('fixture-'+name+'.bin')).read_bytes()
    assert data==(RUN/('fixture-readback-'+name+'.bin')).read_bytes()
    assert record==dict(bytes=len(data),sha256=sha(data),path=directory+'/'+name)
    expected[name]=data
note=expected['NOTE.TXT'];large=expected['LARGE.TXT'];assert len(note)==37 and len(large)==66053
saved=large[:65537]+b'C12'+large[65537:];assert len(saved)==66056
assert saved==(RUN/'saved-expected.bin').read_bytes() and sha(saved)==report['saved_sha256']
changed=note[:5]+b'!'+note[5:]
expected.update({'A LONG SAVED DOCUMENT NAME.TXT':changed,'LARGE COPY.TXT':saved})
assert set(report['output_readbacks'])==set(expected)
for name,data in expected.items():
    assert (RUN/('final-readback-'+name+'.bin')).read_bytes()==data
    assert report['output_readbacks'][name]==dict(bytes=len(data),sha256=sha(data),path=directory+'/'+name)
temporary={report['native_disk_upload_path']:(RUN/'native.d64').read_bytes(),
           report['restore_prg_path']:(RUN/'restore-loader-readback.bin').read_bytes()}
assert sha(temporary[report['restore_prg_path']])==report['build']['target/uos.prg']
assert report['restore_prg_verified_before_mounts'] and report['restore_prg_owned']
assert set(report['temporary_input_readbacks'])==set(report['temporary_inputs_removed'])==set(temporary)
for path,data in temporary.items():
    assert (RUN/('temporary-readback-'+Path(path).name+'.bin')).read_bytes()==data
    assert report['temporary_input_readbacks'][path]==dict(bytes=len(data),sha256=sha(data),path=path)
assert len(report['temporary_input_deletions'])==2
assert all(r['path'] in temporary and r['request_started'] and r['confirmed'] for r in report['temporary_input_deletions'])
assert all(r['request_started'] and r['response_received'] and not r['replayed'] and r['status']==200
           and not json.loads(bytes.fromhex(r['body_hex']))['errors'] for r in report['host_control_requests'])
probe_hash=sha((RUN/'native-read.prg').read_bytes());chunks=0
with tempfile.TemporaryDirectory(prefix='uos-reopen-observer-rebuild-') as temporary_dir:
    output=Path(temporary_dir)/'probe.prg'
    subprocess.run(['64tass','-a',str(INPUTS/'probes/native-read.asm'),'-o',str(output)],check=True,capture_output=True)
    assert sha(output.read_bytes())==probe_hash
for capture in report['captures']:
    assert capture['restored'] and capture['probe_sha256']==probe_hash
    assert capture['output_address']==0x3a00 and capture['chunk_limit']==512
    assert len((RUN/(capture['label']+'.bin')).read_bytes())==capture['count']
    offset=0
    for part in capture['chunks']:
        chunks+=1
        assert part['code']==1 and 1<=part['count']<=512 and part['address']==capture['address']+offset
        assert not part['mode_register']&64 and part['common_register']&15==4 and part['foreground_mmu']==14
        offset+=part['count']
    assert offset==capture['count']
disagreements=0
for observed in report['ram_observations']:
    actual=(RUN/(observed['label']+'.bin')).read_bytes();dma=(RUN/(observed['label']+'-dma.bin')).read_bytes()
    assert len(actual)==len(dma)==observed['count']
    assert sha(actual)==observed['cpu_sha256'] and sha(dma)==observed['direct_sha256']
    assert observed['direct_matches_cpu']==(actual==dma);disagreements+=actual!=dma
image=(INPUTS/'target/native/uos128.prg').read_bytes();origin=int.from_bytes(image[:2],'little')
layout=read(INPUTS/'target/native/layout.json');boot=report['resident_boot'];assert boot['layout']==layout
for prefix,start,size in [('resident',layout['staging_start'],layout['low_padded_end']-layout['low_start']),
                          ('service',layout['service_start'],layout['service_end']-layout['service_start'])]:
    expected_bytes=image[2+start-origin:2+start-origin+size]
    assert b''.join((RUN/f'{prefix}-initial-{offset:04x}.bin').read_bytes() for offset in range(0,size,2000))==expected_bytes
documents={'ultimate-editor-new':b'','ultimate-open-mixed':note,'ultimate-edited-quote':changed,
           'ultimate-saved-long-path':changed,'ultimate-open-failure-keeps-document':changed,
           'ultimate-open-empty':b'','ultimate-large-open':large,'ultimate-large-edited':saved,
           'ultimate-large-save-verified':saved,'ultimate-existing-file-rejected':saved,
           'ultimate-new-after-save':b'','ultimate-reopen-second-context':saved,'ultimate-reopened-edit':saved}
documents.update({f'diagnostic-new-{i}':b'' for i in range(1,6)})
documents.update({f'diagnostic-reopen-{i}':saved for i in range(2,7)})
states={r['label']:r for r in report['editor_states']};assert set(states)==set(documents)
for label,state in states.items():
    raw=(RUN/(label+'-app-state.bin')).read_bytes();doc=(RUN/(label+'-document-state.bin')).read_bytes()
    def value(name,size=1):
        at=symbols['ed_'+name]-symbols['ed_active'];return int.from_bytes(raw[at:at+size],'little')
    def string(name):
        at=symbols['ed_'+name]-symbols['ed_active'];return raw[at:at+256].split(b'\0')[0].decode()
    for key,size in [('cursor',3),('view',3),('horizontal',3),('status',1),('mode',1),('device',1)]:assert state[key]==value(key,size)
    assert state['fmt']==value('format') and state['name']==string('name') and state['field']==string('field')
    assert state['field_caret']==value('field_cursor') and not state['fault']
    assert (int.from_bytes(doc[:3],'little'),doc[12],doc[13],doc[14])==(len(documents[label]),state['dirty'],state['chunks'],state['fault'])
    for display,columns in [('vic',40),('vdc',80)]:
        view=raw[symbols['ed_field_views']-symbols['ed_active']+int(columns==80)]
        wanted=editor_screen(columns,documents[label],state['cursor'],name=state['name'],dirty=bool(state['dirty']),
            device=state['device'],fmt=state['fmt'],view=state['view'],horizontal=state['horizontal'],
            mode=state['mode'],status=state['status'],field=state['field'],field_caret=state['field_caret'],field_view=view)
        assert (RUN/(label+'-'+display+'.bin')).read_bytes()==wanted,(label,display)
assert len(probe['samples'])==6
for sample in probe['samples']:
    label=sample['label'];state=states[label]
    assert state['status']==state['fault']==state['dirty']==0 and state['length']==66056 and state['device']==2
    assert state['chunks']==17
    for key,suffix in [('files_hex','first-file-state'),('transport_hex','first-transport-state'),('ultimate_status_hex','first-ultimate-status')]:
        assert (RUN/(label+'-'+suffix+'.bin')).read_bytes().hex()==sample[key]
    files=bytes.fromhex(sample['files_hex'])
    assert files[14:17]==bytes(3) and sample['first_file_error']==sample['first_dos_error']==sample['first_transport_error']==0
keys=(RUN/'function-keys-before.bin').read_bytes();assert len(keys)==256 and keys==(RUN/'function-keys-after.bin').read_bytes()
for bank in (0,1):
    assert (RUN/f'workspace-{bank}-all.bin').read_bytes()==bytes((i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(8192))
assert report['heap_observations'][-1]['free']==[175,251,32]
records=disk_records((RUN/'native.d64').read_bytes())
for display,columns in [('vic',40),('vdc',80)]:
    assert (RUN/('browser-after-ultimate-editor-'+display+'.bin')).read_bytes()==browser_screen(columns,records)
    assert (RUN/('workspace-restored-'+display+'.bin')).read_bytes()==expected_screen(columns,1)
result=dict(passed=True,diagnostic_only=True,unmodified_product_qualification=False,
            frozen_inputs=257,reopens=6,initiating_fault_reproduced=False,
            cpu_probe_cases=6,captures=len(report['captures']),irq_chunks=chunks,
            ram_observations=len(report['ram_observations']),dma_disagreements=disagreements,
            editor_screen_pairs=len(states),closed_files=len(expected),closed_file_bytes=sum(map(len,expected.values())),
            temporary_inputs=2,temporary_bytes=sum(map(len,temporary.values())),
            patch_restored=True,desktop_and_resources_restored=True,
            complete_document_ram_comparisons_per_reopen=False)
if args.record:(HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
else:assert result==read(HERE/'verification.json')
print('PASS: diagnostic patch/restoration; six successful reopens; complete closed-file readbacks and restored resources')
