#!/usr/bin/env python3
"""Audit the retained upload failure, desktop recovery and exact reclamation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'oracle'))
from native_files_check import exact_d64_files
parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
def read(path):return json.loads((ROOT/path).read_text())
def sha(data):return hashlib.sha256(data).hexdigest()
def flatten(value):return {k:v for record in value['drives'] for k,v in record.items()}
failed='hardware-iec-boot-timeout/'
report=read(failed+'report.json')
assert not report['passed'] and report['error']=='native editor boot'
assert not report['legacy_desktop_restored'] and not report['uncertain_host_writes']
assert not report.get('native_checks_passed')
assert report['build']==read('hardware/report.json')['build']
assert sha((ROOT/failed/'native.d64').read_bytes())==report['native_disk_sha256']
assert sha((ROOT/failed/'documents.d64').read_bytes())==report['data_disk_sha256']

for label,count in [('resume',1),('reinitialize',2)]:
    recovery=read(failed+'boot-'+label+'-recovery.json')
    assert not recovery['passed'] and recovery['error']=='resumed desktop vector'
    assert recovery['vector_after']=='0000' and not recovery['uncertain_host_writes']
    assert len(recovery['requests'])==count
    assert all(r['status']==200 and json.loads(bytes.fromhex(r['body_hex']))['errors']==[] for r in recovery['requests'])
    if label=='resume':
        # The first recovery recorded its response before per-request
        # start/acknowledgement flags were added. Preserve that older schema.
        assert set(recovery['requests'][0])=={'method','endpoint','status','body_hex'}
        assert recovery['requests'][0]['endpoint']=='/v1/machine:resume'
    else:
        assert all(r['request_started'] and r['response_received'] and not r['replayed'] for r in recovery['requests'])
    terminal=read(failed+'uos_fields_boot_'+('recovery' if label=='resume' else 'reinitialize')+'-terminal.json')
    assert terminal['last']['exit_code']==1

basic=read(failed+'boot-basic-recovery.json')
assert not basic['passed'] and basic['commands']==['LOAD"UOS",8,1']
assert basic['error']=='direct IEC loader bytes differ; RUN withheld'
bad=(ROOT/'boot-diagnostics/uos-fields-boot-diagnostic-5i06qp8m/legacy-program.bin').read_bytes()
assert sha(bad)==basic['loaded_payload_sha256'] and bad[:2]==bytes(2)
diagnosis=read('boot-diagnostics/uos-fields-boot-diagnostic-f6l4bfoj/report.json')
expected_sizes={'temp0096':2036,'temp0097':174848,'temp0098':174848,'temp0099':2036,
                'temp009A':63488,'temp009B':0,'temp009C':0,'temp009D':0,'temp009E':0}
for name,size in expected_sizes.items():
    record=diagnosis['uploaded_file_info'][name];response=json.loads(record['body'])
    assert record['status']==200 and not response['errors'] and response['files']['size']==size
assert diagnosis['version']=={'version':'0.1','errors':[]}
assert diagnosis['info']['status']==diagnosis['menu-screen']['status']==404

recovered=read(failed+'boot-existing-recovery.json')
assert recovered['passed'] and recovered['desktop_live'] and recovered['images_unchanged']
assert recovered['other_drives_restored'] and not recovered['uncertain_host_writes']
assert recovered['commands']==['LOAD"UOS",8,1','RUN']
assert recovered['existing_image']['path']=='/Temp/temp0098'
assert recovered['drives_after']==flatten(read(failed+'drives-before.json'))
settings=(ROOT/failed/'settings-before.bin').read_bytes()
assert bytes.fromhex(recovered['settings_restored_hex'])==settings
assert bytes.fromhex(recovered['boot_settings_hex'])[2:7]==settings[2:7]
assert all(r['response_received'] and r['status']==200 and not r['replayed'] and
           json.loads(bytes.fromhex(r['body_hex']))['errors']==[] for r in recovered['requests'])
legacy_disk=(ROOT/'temporary-reclamation/legacy-before-removal.bin').read_bytes()
assert sha(legacy_disk)==report['build']['target/ultos.d64']
program=exact_d64_files(legacy_disk)[b'UOS'][1]
assert sha(program)==report['build']['target/uos.prg']
loaded=(ROOT/failed/'basic-loaded-program.bin').read_bytes()
assert loaded==program[2:] and sha(loaded)==recovered['loaded_payload_sha256']
assert not recovered['loaded_payload_differences']
assert basic['loaded_payload_differences']==[i for i,(a,b) in enumerate(zip(bad,loaded)) if a!=b]
assert read(failed+'uos_fields_boot_existing-terminal.json')['last']['exit_code']==0

reclaim=read('temporary-reclamation/report.json')
assert reclaim['passed'] and reclaim['desktop_live'] and reclaim['drives_unchanged']
assert reclaim['settings_unchanged'] and reclaim['images_unchanged'] and reclaim['dos_paths_restored']
assert reclaim['build']==report['build'] and not reclaim['uncertain_host_writes']
assert len(reclaim['files'])==3 and reclaim['bytes_reclaimed']==524544
assert {item['path'] for item in reclaim['files']}=={'/Temp/temp0093','/Temp/temp0094','/Temp/temp0095'}
mounted={v.get('image_file') for v in flatten(reclaim['drives_before']).values()}
for item in reclaim['files']:
    data=(ROOT/'temporary-reclamation'/(item['label']+'-before-removal.bin')).read_bytes()
    assert len(data)==item['readback']['bytes']==174848
    assert sha(data)==item['expected_sha256']==item['readback']['sha256']
    assert item['path'] not in mounted and item['delete_started'] and item['delete_acknowledged']
    assert item['delete_result']['code']==item['delete_result']['carry']==0
    assert item['file_info_after']['status']==404 and item['file_info_after']['response']['errors']
assert all(not item['request_sent'] for item in reclaim['host_connect_failures'])
assert read('temporary-reclamation/terminal.json')['last']['exit_code']==0

current=read('harness/SHA256.json')
assert len(current)==102
for path,digest in current.items():assert sha((ROOT/'harness'/path).read_bytes())==digest,path
old=read('boot-recovery-harness/original/original-harness-SHA256.json');assert len(old)==99
for path,digest in old.items():
    base=ROOT/'boot-recovery-harness/original' if path in ('hw_native_editor_check.py','hw_ultimate_check.py') else ROOT/'harness'
    assert sha((base/path).read_bytes())==digest,path
for manifest in sorted((ROOT/'boot-recovery-harness').glob('*/SHA256.json')):
    for path,digest in json.loads(manifest.read_text()).items():assert sha((manifest.parent/path).read_bytes())==digest,path

result=dict(passed=True,failed_native_boot_retained=True,failed_resume_and_reinitialization_retained=True,
            direct_basic_load_withheld_run=True,observed_uploaded_file_sizes=expected_sizes,
            verified_recovery_loader_bytes=len(loaded),saved_settings_bytes=len(settings),
            deployed_desktop_restored=True,exact_archived_images_reclaimed=3,bytes_reclaimed=524544,
            current_harness_files=len(current),original_harness_files=len(old),
            no_qualified_editor_checks_in_failed_run=True,hardware_io=False)
path=ROOT/'boot-recovery-verification.json'
if args.record:path.write_text(json.dumps(result,indent=2)+'\n')
else:assert json.loads(path.read_text())==result
print('PASS: retained boot/upload failure, verified recovery, exact reclamation and both harness versions')
