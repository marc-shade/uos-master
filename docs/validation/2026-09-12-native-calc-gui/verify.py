#!/usr/bin/env python3
"""Offline raw capture, palette pixel, ownership, image and rebuild audit."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
import tempfile

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()
read=lambda path:json.loads((ROOT/path).read_text())
from capture_audit import captures


def audit():
    archives=read('archives.json')
    with tempfile.TemporaryDirectory(prefix='uos-calculator-audit-') as temporary:
        temp=Path(temporary)
        for label,info in archives.items():
            archive=ROOT/info['archive'];assert sha(archive.read_bytes())==info['sha256']
            manifest=read(info['manifest']);assert len(manifest)==info['payload_files']
            assert sum(row['bytes'] for row in manifest.values())==info['payload_bytes']
            with tarfile.open(archive,'r:gz') as tar:
                members=tar.getmembers();assert len(members)==len(manifest)
                assert {member.name for member in members}==set(manifest)
                for member in members:
                    path=PurePosixPath(member.name)
                    assert member.isfile() and not path.is_absolute() and '..' not in path.parts
                    raw=tar.extractfile(member).read();row=manifest[member.name]
                    assert len(raw)==row['bytes'] and sha(raw)==row['sha256']
                    target=temp/label/member.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        source=temp/'inputs';inputs=read('inputs-files.json');assert len(inputs)==425
        sys.path[:0]=[str(source),str(source/'tests')]
        from native_image import validate
        from native_files_check import exact_d64_files
        from native_calc_scene import surface as calc_surface
        from native_capture import calculator_screen
        from native_pointer_check import pixels,surface_pixels,check_canvas
        from launcher_scene import surface,console
        from native_running_layout import RunningLayout
        rebuilt=read('main-rebuild.json');frozen=read('frozen-rebuild.json')
        assert rebuilt['passed'] and frozen['passed'] and rebuilt['images']==frozen['images']
        assert len(rebuilt['images'])==21
        for name,digest in rebuilt['images'].items():assert inputs[name]['sha256']==digest,name
        changed={name for name,digest in read('base-images.json').items() if inputs[name]['sha256']!=digest}
        assert changed=={'target/native-desktop/calc.prg','target/native-desktop/desktop.prg',
                         'target/native-desktop/uos128.d64','target/native-desktop/workspace.d64'}
        assert (ROOT/'base-commit.txt').read_text().strip()=='9d2b36234e490f4c682df346e09d903271471263'
        calc=validate((source/'target/native-desktop/calc.prg').read_bytes())
        desk=validate((source/'target/native-desktop/desktop.prg').read_bytes())
        assert calc['pages']==37 and calc['bytes']==9352 and desk['pages']==23
        deployment=json.loads((source/'target/native-desktop/deployment.json').read_text())
        for disk in ('uos128.d64','workspace.d64'):
            contents=exact_d64_files((source/'target/native-desktop'/disk).read_bytes())
            for name,program in deployment['disk_entries'].items():
                path=source/'target/native-desktop'/program
                if disk=='workspace.d64' and name=='u':path=source/'target/native/uos128.prg'
                assert contents[name.upper().encode()]==(2,path.read_bytes()),(disk,name)
        cpu={}
        for label,count in (('cpu',7),('pointer',12),('desktop',24)):
            report=read('cpu/'+label+'.json');assert report['passed'] and len(report['cases'])==count
            for name,digest in report['images'].items():
                if not name.startswith('target/'):name='target/native-desktop/'+name
                assert inputs[name]['sha256']==digest,name
            cpu[label]=count
        assert read('cpu/pointer.json')['cases'][0]['counter_pairs']==16384
        original=read('cpu/text-cpu.json');assert original['passed'] and original['arithmetic_cases']==11
        assert original['calc_sha256']==inputs['target/native/calc.prg']['sha256']
        running=RunningLayout(source,image_dir=source/'target/native-desktop')
        def resident(folder):
            for prefix in ('resident-boot','resident-return'):
                data={name:(folder/(prefix+'-'+name+'.bin')).read_bytes() for name in running.regions}
                assert running.compare(data)['passed']
        totals={};frames=0
        for label,eighty in (('vice40',False),('vice80',True)):
            folder=temp/label;report=json.loads((folder/'report.json').read_text())
            assert report['passed'] and report['all_host_processes_terminal'] and report['system_disk_files_preserved']
            assert not report['physical_hardware_io'] and report['options']['eighty']==eighty
            assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_pointer_iec.py').read_bytes()
            for name,digest in report['images'].items():assert inputs['target/native-desktop/'+name]['sha256']==digest
            totals[label]=captures(folder,dict(report,captures=report['captures']+report['mode_captures']))
            assert not totals[label]['rejected']
            assert len(report['desktops'])==15 and len(report['calculator_frames'])==5
            for row in report['desktops']:
                name=row['label'];selected=row['selected'];x,y=row['position']
                assert (folder/(name+'-surface.bin')).read_bytes()==surface(selected)
                assert (folder/(name+'-vdc.bin')).read_bytes()==console(80,selected)
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),pixels(selected,x,y))==row['rectangle']
                assert row['mode']['vic_sprites']==3;frames+=1
            for row in report['calculator_frames']:
                name=row['label'];expected=row['expected'];x,y=row['position']
                wanted=calc_surface(**expected)
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),surface_pixels(wanted,x,y))==row['rectangle']
                status=[None,'HISTORY SAVED AND VERIFIED','DISK ERROR; FILE MAY BE PARTIAL','FILE EXISTS - CHOOSE ANOTHER NAME'][expected['status']]
                assert (folder/(name+'-vdc.bin')).read_bytes()==calculator_screen(80,expected['display'],expected['history'],
                    save_prompt=expected['name'] if expected['dialog'] else None,save_status=None if expected['dialog'] else status,
                    save_caret=expected['cursor'],save_view=0)
                assert row['mode']['vic_sprites']==3;frames+=1
            keys=(folder/'keys-before.bin').read_bytes();assert len(keys)==256
            for app in ('calc','editor','files','controls','claude'):
                assert (folder/(app+'-keys-restored.bin')).read_bytes()==keys
            assert [row['mouse_app'] for row in report['events'] if 'mouse_app' in row]==['calc','editor','files','controls','claude']
            assert [row['calculator_button'] for row in report['events'] if 'calculator_button' in row]==[8,9,15,10,13,14,17,21,17,22]
            assert all(row['keyboard_events_during_click']==0 for row in report['events'] if 'keyboard_events_during_click' in row)
            disk=exact_d64_files((folder/'suite.d64').read_bytes())
            assert disk.pop(b'GUIHIST')==(1,b'42\r')
            assert disk==exact_d64_files((source/'target/native-desktop/uos128.d64').read_bytes())
            pages=(folder/'final-page-table.bin').read_bytes();handles=(folder/'final-records.bin').read_bytes()
            assert pages[0x50:0xff]==bytes(175) and pages[0x104:0x1ff]==bytes(251)
            assert all(handles[i*8]==0 for i in range(32));resident(folder)
        folder=temp/'sequence';report=json.loads((folder/'hardware-sequence.json').read_text())
        assert report['native_checks_passed'] and not report['physical_hardware_io']
        totals['sequence']=captures(folder,dict(report,captures=report['captures']+report['mode_captures']))
        assert not totals['sequence']['rejected'];resident(folder)
        assert len(report['calculator_frames'])==2
        for row in report['calculator_frames']:
            name=row['label'];assert (folder/(name+'-surface.bin')).read_bytes()==calc_surface(row['result'],row['history'])
            assert (folder/(name+'-vdc.bin')).read_bytes()==calculator_screen(80,row['result'],row['history'])
        folder=temp/'keyboard';report=json.loads((folder/'report.json').read_text());assert report['passed']
        assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_desktop_iec.py').read_bytes()
        for row in report['calculator_frames']:
            name=row['label'];wanted=calc_surface(row['result'],row['history'])
            assert (folder/(name+'-surface.bin')).read_bytes()==wanted
            assert check_canvas((folder/(name+'-display-get.bin')).read_bytes(),surface_pixels(wanted,0,0,visible=False))==row['rectangle']
            frames+=1
        assert len(report['calculator_frames'])==2
        for row in report['desktops']:
            if row['fallback']:continue
            name=row['label'];wanted=surface(row['selected'],row['error'])
            assert (folder/(name+'-surface.bin')).read_bytes()==wanted
            assert check_canvas((folder/(name+'-display-get.bin')).read_bytes(),surface_pixels(wanted,0,0,visible=False))==row['rectangle']
            frames+=1
        provenance=read('provenance.json')
        assert not provenance['physical_hardware_io'] and not provenance['pushed']
        assert len(provenance['qualified_session_exit_codes'])==8
        assert all(code==0 for code in provenance['qualified_session_exit_codes'].values())
        return dict(passed=True,frozen_inputs=425,reproduced_images=21,cpu_groups=cpu,cpu_text_arithmetic_cases=11,
                    raw_capture_audits=totals,complete_palette_frames=frames,palette_pixels=frames*64000,
                    archive_payload_files=sum(row['payload_files'] for row in archives.values()),
                    archive_payload_bytes=sum(row['payload_bytes'] for row in archives.values()))


if __name__=='__main__':
    if (ROOT/'SHA256SUMS').exists():
        assert '--record' not in sys.argv,'sealed record is immutable'
        listed={line.split('  ',1)[1]:line.split('  ',1)[0] for line in (ROOT/'SHA256SUMS').read_text().splitlines()}
        assert set(listed)=={str(path.relative_to(ROOT)) for path in ROOT.rglob('*') if path.is_file() and path.name!='SHA256SUMS'}
        for name,digest in listed.items():assert sha((ROOT/name).read_bytes())==digest,name
    result=audit();print(json.dumps(result,indent=2))
    if '--record' in sys.argv:(ROOT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
