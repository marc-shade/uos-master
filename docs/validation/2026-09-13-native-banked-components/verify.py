#!/usr/bin/env python3
"""Offline audit of the sealed banked-component software checkpoint."""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import re
import tarfile

ROOT=Path(__file__).resolve().parent
def digest(data):return hashlib.sha256(data).hexdigest()
def read_json(path):return json.loads((ROOT/path).read_text())
def unpack(name):
    expected=read_json(name+'-files.json');actual={}
    with tarfile.open(ROOT/(name+'.tar.gz'),'r:gz') as tar:
        for m in tar:
            assert m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts
            assert m.name not in actual
            data=tar.extractfile(m).read();actual[m.name]=data
            assert expected[m.name]==dict(bytes=len(data),sha256=digest(data))
    assert set(actual)==set(expected)
    return actual
def image(data,kind):
    assert data[:2]==b'\0\x60' and data[2:6]==kind and data[6:8]==b'\1\1'
    header=data[2:34];size=int.from_bytes(header[8:10],'little')
    assert len(data)==size+2 and 33<=size<=24576
    assert header[10]==(size+255)//256 and 32<=int.from_bytes(header[12:14],'little')<size
    crc=int.from_bytes(header[14:16],'little');payload=bytearray(data[2:]);payload[14:16]=bytes(2)
    assert binascii.crc_hqx(payload,65535)==crc
    if kind==b'NBK1':assert header[11]==1 and header[16:]==bytes.fromhex('a20e4cab02')+bytes(11)
    return dict(bytes=size,pages=header[10],entry=0x6000+int.from_bytes(header[12:14],'little'),crc16=crc)
def reu_snapshot(data):
    assert data[:19]==b'VICE Snapshot File\x1a' and data[21:37].rstrip(b'\0')==b'C128'
    assert data[37:50]==b'VICE Version\x1a'
    at=58;reu=None
    while at<len(data):
        assert len(data)-at>=22
        size=int.from_bytes(data[at+18:at+22],'little')
        assert 22<=size<=len(data)-at
        if data[at:at+16].rstrip(b'\0')==b'REU1764':
            assert reu is None and data[at+16:at+18]==bytes(2)
            payload=data[at+22:at+size];kib=int.from_bytes(payload[:4],'little')
            assert len(payload)==20+kib*1024
            reu=payload[20:]
        at+=size
    assert at==len(data) and reu is not None
    return reu
def initial(kib):
    page=bytes((i*37+(i>>8)*73+19)&255 for i in range(65536))
    return b''.join(bytes((v+b*53)&255 for v in page) for b in range(kib//64))

def audit(unsealed=False):
    if not unsealed:
        lines=(ROOT/'SHA256SUMS').read_text().splitlines();names=[]
        for line in lines:
            h,name=line.split('  ',1);names.append(name)
            assert digest((ROOT/name).read_bytes())==h,name
        assert set(names)=={p.name for p in ROOT.iterdir() if p.is_file() and p.name!='SHA256SUMS'}
    inputs=unpack('inputs');jobs_files=unpack('jobs');outputs=unpack('outputs')
    rebuilt=unpack('rebuilt-images');overlay=unpack('build-source-overlay')
    hashes=json.loads(jobs_files['inputs.json'])
    assert hashes=={p:digest(b) for p,b in inputs.items()}
    jobs=read_json('jobs.json')
    assert set(jobs)=={'cpu','sdk','vice','reu-regression','build'}
    for label,status in jobs.items():
        assert status==json.loads(jobs_files[label+'.status.json'])
        assert status['terminal'] and status['passed'] and status['exit_code']==0
        if label!='build':assert status['inputs_unchanged'] and status['physical_hardware_io'] is False
    build=jobs['build'];assert not build['source_changes'] and not build['changed_images']
    provenance=read_json('provenance.json');assert provenance['physical_hardware_io'] is False
    assert len(rebuilt)==33
    for p,data in rebuilt.items():
        h=digest(data)
        assert h==provenance['base_images'][p]==build['images'][p]['before']==build['images'][p]['after']==digest(inputs[p])
    before=json.loads(jobs_files['build-input-overlay.json'])
    assert set(overlay)==set(before['changed_host_tests'])=={'tests/ci_native_banked.py','tests/ci_native_banked_vice.py'}
    assert before['original_inputs']=={p:digest(overlay.get(p,b)) for p,b in inputs.items()}
    changes=read_json('changes.json')
    assert all(h['after']==digest(inputs[p]) and h['before']!=h['after'] for p,h in changes.items())
    reports={name:json.loads(jobs_files[name+'.json']) for name in ('cpu','sdk','vice','reu-regression')}
    for report in reports.values():assert report['passed'] and report['physical_hardware_io'] is False
    cpu,sdk,vice=reports['cpu'],reports['sdk'],reports['vice']
    assert len(cpu['cases'])==33 and len(sdk['cases'])==9 and len(reports['reu-regression']['cases'])==23
    assert digest(outputs['cpu/parent.prg'])==cpu['parent_sha256']
    # CPU assembler output precedes CRC sealing; the report hashes the sealed provider.
    cpu_provider=bytearray(outputs['cpu/provider.prg']);cpu_provider[16:18]=bytes(2)
    cpu_provider[16:18]=binascii.crc_hqx(cpu_provider[2:],65535).to_bytes(2,'little')
    assert digest(cpu_provider)==cpu['provider_sha256']
    sdk_info={}
    for name,kind in (('BANKDEMO.PRG',b'NAPP'),('BKREU.PRG',b'NBK1')):
        data=outputs['sdk/'+name];sdk_info[name]=image(data,kind)
        assert digest(data)==sdk['images']['images'][name]['sha256']
    assert outputs['sdk/BKREU.PRG']==cpu_provider==outputs['vice/provider.prg']
    image(outputs['vice/parent.prg'],b'NAPP')
    for name in ('parent','provider'):assert digest(outputs['vice/'+name+'.prg'])==vice['images'][name]
    ps={n:int(v,16) for n,v in re.findall(r'^(\w+)\s*=\s*\$([\da-fA-F]+)',outputs['vice/parent.sym'].decode(),re.M)}
    assert [c['kib'] for c in vice['cases']]==[128,256,16384]
    compared=0;guard_bytes=0;snapshots=0
    for case in vice['cases']:
        assert case['passed'] and case['bank0_probe_shadow_preserved']
        assert case['borrowed_registers']['before']==case['borrowed_registers']['after']
        assert case['probe_shadow']['before']==case['probe_shadow']['after']
        prefix='vice/'+str(case['kib'])+'/'
        original=initial(case['kib']);assert outputs[prefix+'initial.reu']==original
        want=bytearray(original)
        for offset in (0xff80,case['kib']*1024-512,0x7ff80 if case['kib']>=1024 else 0):
            want[offset:offset+512]=bytes((i*93+(offset>>16)*11)&255 for i in range(512))
        assert len(case['snapshots'])==2
        for number,entry in enumerate(case['snapshots']):
            raw=outputs[prefix+entry['snapshot']];memory=reu_snapshot(raw)
            assert digest(raw)==entry['snapshot_sha256'] and digest(memory)==entry['sha256']
            assert memory==(original if number==0 else want)
            compared+=len(memory);snapshots+=1
        low=outputs[prefix+'bank1-low-before.bin'];assert len(low)==0x5c00
        assert outputs[prefix+'bank1-low-after-reu.bin']==low
        expected=bytearray(low);expected[:512]=b'\3'+bytes((i*41+13)&255 for i in range(511))
        assert outputs[prefix+'bank1-low-after-callbacks.bin']==expected
        guard_bytes+=len(low)*2
        loaded=bytearray(outputs['vice/provider.prg'][2:]);loaded[22:24]=ps['bk_callback'].to_bytes(2,'little')
        assert outputs[prefix+'provider-loaded.bin']==loaded
    result=dict(passed=True,physical_hardware_io=False,inputs=len(inputs),changed_inputs=len(changes),
        terminal_jobs=len(jobs),unchanged_native_images=len(rebuilt),cpu_case_groups=65,
        interrupt_attempts=sum(c.get('interrupt_attempts',0) for c in cpu['cases']),
        sdk_complete_console_frames=sum(c['complete_screens'] for c in sdk['cases']),sdk_images=sdk_info,
        vice_boots=len(vice['cases']),reu_snapshots=snapshots,independently_compared_reu_bytes=compared,
        independently_compared_bank1_guard_bytes=guard_bytes,executor_loader_bytes=len(outputs['cpu/parent.prg'])-34)
    if (ROOT/'audit.json').exists():assert read_json('audit.json')==result
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--unsealed',action='store_true')
    args=parser.parse_args();print(json.dumps(audit(args.unsealed),indent=2,sort_keys=True))
