#!/usr/bin/env python3
"""Offline native Files copy audit, including raw captures and stored bytes."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sha=lambda data:hashlib.sha256(data).hexdigest()
read=lambda name:json.loads((ROOT/name).read_text())
from capture_audit import captures


def d81_files(raw):
    assert len(raw)==819200
    def block(track,sector):
        assert 1<=track<=80 and 0<=sector<40
        at=((track-1)*40+sector)*256
        return raw[at:at+256]
    result={};link=(40,3);seen=set()
    while link[0]:
        assert link not in seen and link[0]==40;seen.add(link)
        directory=block(*link)
        for at in range(0,256,32):
            kind=directory[at+2]&7
            if not kind:continue
            assert directory[at+2]&128
            name=directory[at+5:at+21].rstrip(b'\xa0');assert name not in result
            position=tuple(directory[at+3:at+5]);visited=set();data=bytearray()
            while position[0]:
                assert position not in visited;visited.add(position)
                part=block(*position)
                assert part[0] or part[1]>=1
                data.extend(part[2:] if part[0] else part[2:part[1]+1]);position=tuple(part[:2])
            result[name]=(kind,bytes(data))
        link=tuple(directory[:2])
    return result


def audit():
    source=ROOT/'inputs';manifest=read('frozen-inputs.json')
    assert set(manifest)=={str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
    for name,digest in manifest.items():assert sha((source/name).read_bytes())==digest,name
    base=read('base-inputs.json')
    assert (ROOT/'base-commit.txt').read_text().strip()=='3b4847e8070e7ed1d63e324f5b971442647d2660'
    for name,digest in base.items():
        if name.endswith('.prg') and not name.endswith('/files.prg'):
            assert manifest[name]==digest,('unrelated PRG changed',name)
    rebuild=read('main-rebuild.json');assert rebuild['passed'] and len(rebuild['images'])==21
    for name,digest in rebuild['images'].items():assert manifest[name]==digest,name
    provenance=read('provenance.json')
    assert not provenance['physical_hardware_io'] and not provenance['pushed']
    assert all(code==0 for code in provenance['qualified_sessions'].values())
    sys.path.insert(0,str(source))
    from native_image import validate
    from native_files_check import exact_d64_files
    from native_files_copy_check import copy_screen
    from hwlib import lst_symbol
    app=(source/'target/native-desktop/files.prg').read_bytes();info=validate(app)
    assert info['pages']==82 and info['window'] is None
    for name in ('uos128.d64','workspace.d64'):
        contents=exact_d64_files((source/'target/native-desktop'/name).read_bytes())
        assert contents[b'FILES']==(2,app)
        for disk,program in ((b'CLAUDE','claude'),(b'ULTIMATE','controls'),(b'EDITOR','editor')):
            assert contents[disk]==(2,(source/'target/native-desktop'/(program+'.prg')).read_bytes())
    cpu={}
    for label in ('files','browser'):
        report=read('cpu/'+label+'.json');assert report['passed'],label
        for name,digest in report['images'].items():
            assert any(n.endswith('/'+name) and h==digest for n,h in manifest.items()),(label,name)
        cpu[label]=dict(cases=len(report['cases']),frames=sum(c.get('frames',0) for c in report['cases'].values()))
    assert cpu['files']['cases']>=25 and cpu['browser']['cases']==8
    original=read('preliminary/cpu-report-metadata/original-report.json')
    assert original['images']['uos128.prg']==manifest['target/native-desktop/uos128.prg']
    original['images']['uos128.prg']=manifest['target/native/uos128.prg']
    assert original==read('cpu/files.json'),'CPU results changed beyond the identified kernel digest'
    folder=ROOT/'vice';report=read('vice/report.json')
    assert report['passed'] and report['native_checks_passed'] and report['all_host_processes_terminal']
    assert report['source_disk_unchanged'] and report['system_disk_unchanged'] and report['nonempty_exports_match']
    assert not report['physical_hardware_io']
    for name,row in report['images'].items():assert manifest['target/native-desktop/'+name]==row['sha256']
    observation=captures(folder,dict(report,captures=report['captures']+report['mode_captures']))
    assert not observation['rejected']
    large=bytes((i*73+19)&255 for i in range(66058));program=b'\x01\x1cEXACT\0PRG\xff'
    expected={b'LARGE':(1,large),b'EMPTY':(1,b''),b'PROGRAM':(2,program)}
    assert (folder/'data-9.d81').read_bytes()==(folder/'initial-9.d81').read_bytes()
    assert d81_files((folder/'data-9.d81').read_bytes())==expected
    assert d81_files((folder/'initial-10.d81').read_bytes())=={}
    assert d81_files((folder/'data-10.d81').read_bytes())=={b'COPIED LARGE':(1,large),b'COPIED PROGRAM':(2,program)}
    assert (folder/'copied-large.bin').read_bytes()==large
    assert (folder/'copied-program.bin').read_bytes()==program
    assert (folder/'suite.d64').read_bytes()==(source/'target/native-desktop/uos128.d64').read_bytes()
    source_keys=(folder/'files-key-table-before.bin').read_bytes();assert len(source_keys)==256
    frame_pairs=0
    for name,body in (('large',large),('empty',b''),('program',program)):
        assert (folder/(name+'-keys-restored.bin')).read_bytes()==source_keys
        labels=[(name+'-initial',9,0,0,0),(name+'-destination',10,0,0,0),
                (name+('-verified' if body else '-unsupported'),10,len(body),len(body),1 if body else 13)]
        if name=='large':labels.append(('large-exclusive',10,0,0,4))
        for label,device,copied,verified,status in labels:
            state=(folder/(label+'-state.bin')).read_bytes();start=lst_symbol('native-desktop/files','fc_active')
            def data(symbol,size=1):
                at=lst_symbol('native-desktop/files',symbol)-start;return state[at:at+size]
            assert data('fc_active')==b'\1' and data('fc_status')==bytes([status])
            assert int.from_bytes(data('fc_copied',4),'little')==copied
            assert int.from_bytes(data('fc_verified',4),'little')==verified
            assert data('fc_handles',8)[::4]==bytes(2)
            original=name.upper().encode();target=original if label.endswith('-initial') else b'COPIED '+original
            for index,(suffix,cols) in enumerate((('vic',40),('vdc',80))):
                frame=copy_screen(cols,original,target,source_format=2,fmt=2,kind=int(name=='program'),
                    device=device,copied=copied,verified=verified,status=status,error=0x11 if status==4 else 0,
                    dos=63 if status==4 else 0,caret=data('fc_caret')[0],view=data('fc_views',2)[index])
                assert (folder/(label+'-'+suffix+'.bin')).read_bytes()==frame,(label,cols)
            frame_pairs+=1
    from native_running_layout import RunningLayout
    from launcher_scene import surface,console
    running=RunningLayout(source,image_dir=source/'target/native-desktop')
    for prefix in ('resident-boot','resident-return'):
        observed={r:(folder/(prefix+'-'+r+'.bin')).read_bytes() for r in running.regions}
        assert running.compare(observed)['passed']
    for row in report['desktops']:
        assert (folder/(row['label']+'-surface.bin')).read_bytes()==surface(row['selected'])
        assert (folder/(row['label']+'-vdc.bin')).read_bytes()==console(80,row['selected'])
    heap=(folder/'final-native-heap.bin').read_bytes()
    assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251)
    assert all(heap[0x400+i*8]==0 for i in range(32))
    negative=read('preliminary/empty-create/report.json')
    assert not negative['passed'] and negative['all_host_processes_terminal']
    assert d81_files((ROOT/'preliminary/empty-create/data-10.d81').read_bytes())[b'COPIED EMPTY']==(1,b'\r')
    return dict(passed=True,frozen_inputs=len(manifest),byte_identical_images=21,files=info,cpu=cpu,
        vice=observation,copy_frame_pairs=frame_pairs,large_copy_bytes=len(large),large_copy_sha256=sha(large),
        empty_iec_rejected_before_create=True,final_free_pages=426,physical_hardware_io=False)


if __name__=='__main__':
    if '--record' not in sys.argv:
        sealed={}
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            digest,name=line.split('  ',1)
            assert name not in sealed and not Path(name).is_absolute() and '..' not in Path(name).parts
            assert sha((ROOT/name).read_bytes())==digest,name
            sealed[name]=digest
        assert set(sealed)=={str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
    result=audit()
    if '--record' in sys.argv:(ROOT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    else:assert result==read('audit.json')
    print(json.dumps(result,indent=2))
