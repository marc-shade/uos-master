#!/usr/bin/env python3
"""Offline Paint, six-app input, raw capture, file and rebuild audit."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import tarfile
import tempfile

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sha=lambda data:hashlib.sha256(data).hexdigest()
read=lambda name:json.loads((ROOT/name).read_text())
from capture_audit import captures


def audit():
    archives=read('archives.json')
    with tempfile.TemporaryDirectory(prefix='uos-paint-audit-') as temporary:
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
        source=temp/'inputs';inputs=read('inputs-files.json');assert len(inputs)==452
        sys.path[:0]=[str(source),str(source/'tests')]
        from native_image import validate
        from native_files_check import exact_d64_files
        from native_calc_scene import surface as calc_surface
        from native_capture import calculator_screen
        from native_pointer_check import pixels,surface_pixels,check_canvas
        from launcher_scene import surface,console
        from paint_scene import surface as paint_surface,console as paint_console,MESSAGES
        from native_paint_format import encode,decode
        from native_running_layout import RunningLayout

        rebuilt=read('main-rebuild.json');frozen=read('frozen-rebuild.json')
        assert rebuilt['passed'] and frozen['passed'] and rebuilt['images']==frozen['images']
        assert rebuilt['build_exit_code']==frozen['build_exit_code']==0 and len(rebuilt['images'])==22
        for name,digest in rebuilt['images'].items():assert inputs[name]['sha256']==digest,name
        baseline=read('base-images.json');assert len(baseline)==21
        changed={name for name,digest in baseline.items() if inputs[name]['sha256']!=digest}
        assert changed=={'target/native-desktop/calc.prg','target/native-desktop/desktop.prg',
                         'target/native-desktop/uos128.d64','target/native-desktop/workspace.d64'}
        assert set(rebuilt['images'])-set(baseline)=={'target/native-desktop/paint.prg'}
        assert (ROOT/'base-commit.txt').read_text().strip()=='e9a504034a581e1ba479d7ca6a865f6e44b6d48b'
        programs={name:validate((source/'target/native-desktop'/f'{name}.prg').read_bytes())
                  for name in ('desktop','calc','paint')}
        assert [(programs[name]['bytes'],programs[name]['pages']) for name in programs]==[(6610,26),(9915,39),(22463,88)]
        deployment=json.loads((source/'target/native-desktop/deployment.json').read_text())
        assert deployment['free_pages_at_desktop']==364 and deployment['disk_entries']['paint']=='paint.prg'
        for disk in ('uos128.d64','workspace.d64'):
            contents=exact_d64_files((source/'target/native-desktop'/disk).read_bytes())
            assert len(contents)==len(deployment['disk_entries'])
            for name,program in deployment['disk_entries'].items():
                path=source/'target/native-desktop'/program
                if disk=='workspace.d64' and name=='u':path=source/'target/native/uos128.prg'
                assert contents[name.upper().encode()]==(2,path.read_bytes()),(disk,name)

        cpu={}
        for label,count in (('paint_document',13),('paint_files',14),('paint_gui',5),
                            ('paint_ultimate_gui',3),('keys',3),('pointer',13),('desktop',27),('calc_gui',7)):
            report=read('cpu/'+label+'.json');assert report['passed'] and len(report['cases'])==count
            for name,digest in report['images'].items():
                if name=='uos128.prg' and report.get('kernel_path'):name=report['kernel_path']
                elif not name.startswith('target/'):name='target/native-desktop/'+name
                assert inputs[name]['sha256']==digest,name
            cpu[label]=count
        assert read('cpu/pointer.json')['cases'][0]['counter_pairs']==16384
        key_cases=read('cpu/keys.json');assert (key_cases['accepted'],key_cases['rejected'])==(702,66)
        running=RunningLayout(source,image_dir=source/'target/native-desktop')
        def resident(folder):
            for prefix in ('resident-boot','resident-return'):
                data={name:(folder/(prefix+'-'+name+'.bin')).read_bytes() for name in running.regions}
                assert running.compare(data)['passed']

        blank=bytes(8192)+b'\x10'*1024
        totals={};frames=0;paint_frames=0;admissions={};filter_counts={}
        for label,eighty in (('vice40',False),('vice80',True)):
            folder=temp/label;report=json.loads((folder/'report.json').read_text())
            assert report['passed'] and report['all_host_processes_terminal'] and report['system_disk_files_preserved']
            assert not report['physical_hardware_io'] and report['options']==dict(eighty=eighty,paint_only=False)
            assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_pointer_iec.py').read_bytes()
            for name,digest in report['images'].items():assert inputs['target/native-desktop/'+name]['sha256']==digest
            totals[label]=captures(folder,dict(report,captures=report['captures']+report['mode_captures']))
            assert not totals[label]['rejected']
            assert len(report['desktops'])==17 and len(report['calculator_frames'])==5 and len(report['paint_frames'])==10
            for row in report['desktops']:
                name=row['label'];selected=row['selected'];x,y=row['position']
                assert (folder/(name+'-surface.bin')).read_bytes()==surface(selected)
                assert (folder/(name+'-vdc.bin')).read_bytes()==console(80,selected)
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),pixels(selected,x,y))==row['rectangle']
                assert row['mode']['vic_sprites']==3;frames+=1
            for row in report['calculator_frames']:
                name=row['label'];expected=row['expected'];x,y=row['position'];wanted=calc_surface(**expected)
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),surface_pixels(wanted,x,y))==row['rectangle']
                status=[None,'HISTORY SAVED AND VERIFIED','DISK ERROR; FILE MAY BE PARTIAL','FILE EXISTS - CHOOSE ANOTHER NAME'][expected['status']]
                assert (folder/(name+'-vdc.bin')).read_bytes()==calculator_screen(80,expected['display'],expected['history'],
                    save_prompt=expected['name'] if expected['dialog'] else None,save_status=None if expected['dialog'] else status,
                    save_caret=expected['cursor'],save_view=0)
                assert row['mode']['vic_sprites']==3;frames+=1
            document=bytearray(blank);versions=[]
            points=[row for row in report['events'] if 'paint_point' in row];assert len(points)==2
            for row,(tx,ty,color) in zip(points,((40,24,1),(80,48,2))):
                x,y=row['paint_point'];assert abs(x-tx)<=2 and abs(y-ty)<=2 and row['color']==color
                versions.append(bytes(document));document[y//8*320+x//8*8+y%8]|=128>>(x%8)
                document[8192+y//8*40+x//8]=color*16
            for row in report['paint_frames']:
                name=row['label'];expected=dict(row['expected']);expected['name']=expected['name'].encode('latin1')
                expected_document=blank if name in ('paint-open','paint-open-confirm') else versions[-1] if name=='paint-undo' else bytes(document)
                assert (folder/(name+'-document.bin')).read_bytes()==expected_document
                assert row['document_sha256']==sha(expected_document)
                wanted=paint_surface(expected_document,message=MESSAGES[row['status']],**expected)
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted
                state={k:v for k,v in expected.items() if k not in ('view_x','view_y','field_view')}
                assert (folder/(name+'-vdc.bin')).read_bytes()==paint_console(80,bitmap=True,message=row['status'],view=row['console_field_view'],**state)
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),surface_pixels(wanted,*row['position']))==row['rectangle']
                assert row['mode']['vic_sprites']==3;frames+=1;paint_frames+=1
            keys=(folder/'keys-before.bin').read_bytes();assert len(keys)==256
            apps=['calc','editor','files','controls','claude','paint']
            for app in apps:assert (folder/(app+'-keys-restored.bin')).read_bytes()==keys
            assert [row['mouse_app'] for row in report['events'] if 'mouse_app' in row]==apps
            assert [row['calculator_button'] for row in report['events'] if 'calculator_button' in row]==[8,9,15,10,13,14,17,21,17,22]
            assert all(row['keyboard_events_during_click']==0 for row in report['events'] if 'keyboard_events_during_click' in row)
            disk=exact_d64_files((folder/'suite.d64').read_bytes())
            assert disk.pop(b'GUIHIST')==(1,b'42\r')
            picture=disk.pop(b'PAINTPIC');assert picture==(1,encode(document)) and decode(picture[1])==document
            assert report['paint_file_sha256']==sha(picture[1]) and len(picture[1])==9016
            assert disk==exact_d64_files((source/'target/native-desktop/uos128.d64').read_bytes())
            pages=(folder/'final-page-table.bin').read_bytes();handles=(folder/'final-records.bin').read_bytes()
            assert pages[0x50:0xff]==bytes(175) and pages[0x104:0x1ff]==bytes(251)
            assert all(handles[i*8]==0 for i in range(32));resident(folder)
            admissions[label]=dict(batches=len(report['capture_admissions']),deferred=sum(row['deferred'] for row in report['capture_admissions']))
            filter_counts[label]=report['paint_filtered_line_samples']

        folder=temp/'keyboard';report=json.loads((folder/'report.json').read_text())
        assert report['passed'] and not report['physical_hardware_io'] and report['options']['desktop_boot']
        assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_desktop_iec.py').read_bytes()
        assert report['disk_sha256']==inputs['target/native-desktop/uos128.d64']['sha256']
        for row in report['calculator_frames']:
            name=row['label'];wanted=calc_surface(row['result'],row['history'])
            assert (folder/(name+'-surface.bin')).read_bytes()==wanted
            assert check_canvas((folder/(name+'-display-get.bin')).read_bytes(),surface_pixels(wanted,0,0,visible=False))==row['rectangle']
            frames+=1
        assert len(report['calculator_frames'])==2 and len(report['paint_frames'])==4
        assert len(report['desktops'])==19 and sum(row['fallback'] for row in report['desktops'])==2
        for row in report['desktops']:
            if row['fallback']:continue
            name=row['label'];wanted=surface(row['selected'],row['error'])
            assert (folder/(name+'-surface.bin')).read_bytes()==wanted
            assert check_canvas((folder/(name+'-display-get.bin')).read_bytes(),surface_pixels(wanted,0,0,visible=False))==row['rectangle']
            frames+=1
        document=bytearray(blank);document[0]=192
        for row in report['paint_frames']:
            name=row['label'];mode=row['mode'];x=row['x'];dirty=row['dirty'];focus=25 if mode else 23
            expected_document=blank if name=='paint-keyboard-open' else document
            assert (folder/(name+'-document.bin')).read_bytes()==expected_document
            wanted=paint_surface(expected_document,x=x,dirty=dirty,mode=mode,action=1,focus=focus)
            assert (folder/(name+'-surface.bin')).read_bytes()==wanted
            assert (folder/(name+'-80.bin')).read_bytes()==paint_console(80,x=x,dirty=dirty,mode=mode,action=1,focus=focus)
            assert check_canvas((folder/(name+'-display-get.bin')).read_bytes(),surface_pixels(wanted,8+x,32,visible=not mode))==row['rectangle']
            frames+=1;paint_frames+=1

        provenance=read('provenance.json')
        assert not provenance['physical_hardware_io'] and not provenance['pushed']
        assert len(provenance['qualified_session_exit_codes'])==11
        assert all(code==0 for code in provenance['qualified_session_exit_codes'].values())
        return dict(passed=True,frozen_inputs=452,reproduced_images=22,cpu_groups=cpu,total_cpu_groups=sum(cpu.values()),
            keyboard_filter_cases=key_cases['accepted']+key_cases['rejected'],raw_capture_audits=totals,
            capture_admissions=admissions,paint_filtered_line_samples=filter_counts,complete_palette_frames=frames,
            complete_paint_frames=paint_frames,palette_pixels=frames*64000,
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
