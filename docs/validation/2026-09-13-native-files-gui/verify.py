#!/usr/bin/env python3
"""Offline graphical Files, six-app input, serial lifetime, raw capture and rebuild audit."""
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
    with tempfile.TemporaryDirectory(prefix='uos-files-audit-') as temporary:
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
        source=temp/'inputs';inputs=read('inputs-files.json');assert len(inputs)>=460
        sys.path[:0]=[str(source),str(source/'tests')]
        from native_image import validate
        from native_module import validate as validate_module
        from native_browser_check import disk_records
        from native_files_scene import (browser_surface as files_surface,browser_console as files_console,
            copy_surface as files_copy_surface,copy_console as files_copy_console)
        from native_files_check import exact_d64_files
        from native_calc_scene import surface as calc_surface
        from native_capture import calculator_screen
        from native_pointer_check import pixels,surface_pixels,check_canvas
        from launcher_scene import surface,console
        from paint_scene import surface as paint_surface,console as paint_console,MESSAGES
        from native_paint_format import encode,decode
        from native_running_layout import RunningLayout
        from native_controls_check import panel_screen,absent_body
        from native_controls_scene import surface as controls_surface
        import re

        rebuilt=read('main-rebuild.json');frozen=read('frozen-rebuild.json')
        assert rebuilt['passed'] and frozen['passed'] and rebuilt['images']==frozen['images']
        assert rebuilt['build_exit_code']==frozen['build_exit_code']==0 and len(rebuilt['images'])==24
        for name,digest in rebuilt['images'].items():assert inputs[name]['sha256']==digest,name
        baseline=read('base-images.json');assert len(baseline)==22
        changed={name for name,digest in baseline.items() if inputs[name]['sha256']!=digest}
        assert changed=={'target/native-desktop/files.prg','target/native-desktop/uos128.d64','target/native-desktop/workspace.d64'}
        added=set(rebuilt['images'])-set(baseline)
        assert added=={'target/native-desktop/fspick.prg','target/native-desktop/fsview.prg'}
        assert (ROOT/'base-commit.txt').read_text().strip()=='b19671d592d8130fa93494c22dd714d68376b543'
        programs={name:validate((source/'target/native-desktop'/f'{name}.prg').read_bytes())
                  for name in ('desktop','calc','paint','controls','files')}
        assert [(programs[name]['bytes'],programs[name]['pages']) for name in programs]==[(6610,26),(9915,39),(22463,88),(20616,81),(14272,93)]
        assert (source/'target/native-desktop/files.prg').read_bytes()[8]==10
        modules={name:validate_module((source/f'target/native-desktop/{name}.prg').read_bytes(),
            (source/'target/native-desktop/files.prg').read_bytes()) for name in ('fspick','fsview')}
        deployment=json.loads((source/'target/native-desktop/deployment.json').read_text())
        assert deployment['free_pages_at_desktop']==364 and deployment['disk_entries']['paint']=='paint.prg'
        for disk in ('uos128.d64','workspace.d64'):
            contents=exact_d64_files((source/'target/native-desktop'/disk).read_bytes())
            assert len(contents)==len(deployment['disk_entries'])
            for name,program in deployment['disk_entries'].items():
                path=source/'target/native-desktop'/program
                if disk=='workspace.d64' and name=='u':path=source/'target/native/uos128.prg'
                assert contents[name.upper().encode()]==(2,path.read_bytes()),(disk,name)

        batch=json.loads((temp/'core-cpu/report.json').read_text())
        assert len(batch['jobs'])==len(batch['tests'])==26 and batch['all_host_processes_terminal']
        core_names=('browser','browser_ultimate','file_dialog','modules','heap','apps','display','keyboard','pointer','suite_oracles')
        for name in core_names:
            assert batch['tests'][name]['exit_code']==0 and batch['tests'][name]['terminal']
            assert json.loads((temp/'core-cpu'/(name+'.json')).read_text())['passed']
        # These suites exercise unchanged binaries. Earlier Files application
        # runs in the same archive are development evidence, not the final app.
        for name,digest in batch['images'].items():
            if name not in changed|added:assert digest==inputs[name]['sha256'],name
        app=json.loads((temp/'app-cpu/report.json').read_text())
        assert len(app['jobs'])==len(app['tests'])==16 and app['passed'] and app['all_host_processes_terminal']
        assert app['images_unchanged'] and app['images']==rebuilt['images']
        cpu={}
        for name,run in app['tests'].items():
            assert run['exit_code']==0 and run['terminal']
            result=json.loads((temp/'app-cpu'/(name+'.json')).read_text());assert result['passed']
            assert not result.get('physical_hardware_io',False)
            cpu[name]=len(result['cases'])
            for path,digest in result['images'].items():
                if path.startswith('target/'):assert inputs[path]['sha256']==digest,path
                else:
                    path=('target/native/' if path=='uos128.prg' else 'target/native-desktop/')+path
                    assert inputs[path]['sha256']==digest,path
            if name.startswith('gui_'):assert all(row['module_calls']>0 for row in result['cases'])
        assert cpu['gui_cancel']==2 and all(cpu[name]==1 for name in cpu if name.startswith('gui_') and name!='gui_cancel')
        pointer=json.loads((temp/'core-cpu/pointer.json').read_text())
        assert pointer['passed'] and pointer['cases'][0]['counter_pairs']==16384
        running=RunningLayout(source,image_dir=source/'target/native-desktop')
        def resident(folder):
            for prefix in ('resident-boot','resident-return'):
                data={name:(folder/(prefix+'-'+name+'.bin')).read_bytes() for name in running.regions}
                assert running.compare(data)['passed']

        blank=bytes(8192)+b'\x10'*1024
        totals={};frames=0;paint_frames=0;files_frames=0;admissions={};filter_counts={}
        for label,eighty in (('vice40',False),('vice80',True)):
            folder=temp/label;report=json.loads((folder/'report.json').read_text())
            assert report['passed'] and report['all_host_processes_terminal'] and report['system_disk_files_preserved']
            assert not report['physical_hardware_io'] and report['options']==dict(eighty=eighty,paint_only=False,controls_only=False,files_only=False)
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
            assert len(report['controls_frames'])==8 and report['mouse_routes']
            for row in report['controls_frames']:
                name=row['label'];page=row['page'];focus=row['focus'];notice=row['notice'];body=absent_body(page)
                wanted=controls_surface(body[2:] if page==1 else body,page=page,focus=focus,notice=notice)
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted
                assert (folder/(name+'-vdc.bin')).read_bytes()==panel_screen(80,body,page=page,focus=focus,notice=notice)
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),surface_pixels(wanted,*row['position']))==row['rectangle']
                assert row['mode']['vic_sprites']==3;frames+=1
            assert len(report['files_frames'])==9
            final_entries=disk_records((folder/'suite.d64').read_bytes())
            for row in report['files_frames']:
                name=row['label'];expected=dict(row['expected'])
                if 'records' in expected:
                    entries=[dict(entry,name=bytes.fromhex(entry['name'])) for entry in expected.pop('records')]
                    excluded={b'PAINTPIC'} if name=='files-copy-return' else {b'PAINTPIC',b'FSCOPY'}
                    assert entries==[entry for entry in final_entries if entry['name'] not in excluded]
                    wanted=files_surface(entries,**expected);vdc=files_console(entries,**expected)
                else:
                    original=bytes.fromhex(expected.pop('source'));destination=bytes.fromhex(expected.pop('name'))
                    assert original==b'EDFIND.PRG'
                    assert destination==(original if name=='files-copy-dialog' else b'FSCOPY')
                    wanted=files_copy_surface(original,destination,**expected)
                    vdc=files_copy_console(original,destination,**expected)
                    if name=='files-copy-verified':
                        data=exact_d64_files((source/'target/native-desktop/uos128.d64').read_bytes())[original][1]
                        assert expected['copied']==expected['verified']==len(data) and expected['status']==1
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted
                assert (folder/(name+'-vdc.bin')).read_bytes()==vdc
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),surface_pixels(wanted,*row['position']))==row['rectangle']
                assert row['mode']['vic_sprites']==3;frames+=1;files_frames+=1
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
            expected_disk=exact_d64_files((source/'target/native-desktop/uos128.d64').read_bytes())
            copied=disk.pop(b'FSCOPY');assert copied==expected_disk[b'EDFIND.PRG']
            assert report['files_copy_sha256']==sha(copied[1])
            assert disk==expected_disk
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

        assert len(report['controls_frames'])==4
        for row in report['controls_frames']:
            name=row['label'];page=row['page'];body=absent_body(page)
            wanted=controls_surface(body[2:] if page==1 else body,page=page,focus=page)
            assert (folder/(name+'-surface.bin')).read_bytes()==wanted
            assert (folder/(name+'-80.bin')).read_bytes()==panel_screen(80,body,page=page,focus=page)
            assert check_canvas((folder/(name+'-display-get.bin')).read_bytes(),surface_pixels(wanted,0,0,visible=False))==row['rectangle']
            frames+=1
        assert len(report['files_frames'])==1
        for row in report['files_frames']:
            name=row['label'];entries=disk_records((source/'target/native-desktop/uos128.d64').read_bytes())
            wanted=files_surface(entries)
            assert (folder/(name+'-surface.bin')).read_bytes()==wanted
            assert (folder/(name+'-80.bin')).read_bytes()==files_console(entries)
            assert check_canvas((folder/(name+'-display-get.bin')).read_bytes(),surface_pixels(wanted,0,0,visible=False))==row['rectangle']
            frames+=1;files_frames+=1
        totals['keyboard']=captures(folder,report);assert not totals['keyboard']['rejected']
        resident(folder)

        folder=temp/'serial';report=json.loads((folder/'report.json').read_text())
        assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_suite_iec.py').read_bytes()
        assert report['passed'] and report['all_host_processes_terminal'] and not report['physical_hardware_io']
        totals['serial']=captures(folder,dict(report,captures=report['captures']+report['mode_captures']))
        assert not totals['serial']['rejected'];resident(folder)
        for name,digest in report['images'].items():assert inputs['target/native-desktop/'+name]['sha256']==digest
        assert (folder/'suite.d64').read_bytes()==(source/'target/native-desktop/uos128.d64').read_bytes()
        assert report['suite_apps']['passed'] and len(report['suite_apps']['claude'])==2
        labels={m[2]:int(m[1],16) for m in re.finditer(r'^al ([0-9A-Fa-f]+) \.(\S+)',
                (source/'target/native-desktop/claude.lbl').read_text(),re.M)}
        for row,expected in zip(report['suite_apps']['claude'],(2,0)):
            name=row['label'];assert row['passed'] and row['close_outcome']==expected and row['host_exit_code']==0
            assert row['host_process_terminal'] and row['host_final_code']==0
            assert (folder/(name+'-close-outcome.bin')).read_bytes()==bytes([expected])
            checkpoint=(folder/(name+'-close-checkpoint.bin')).read_bytes()
            observation=row['close_observation']
            assert checkpoint.hex()==observation['checkpoint_hex'] and int.from_bytes(checkpoint[13:17],'little')>0
            assert observation['address']==labels['_closeOutcome'] and observation['cleanup_entry']==labels['_native_video_end']
            assert observation['lifetime']=='Claude allocation still live; before native_video_end'
            for kind in ('font','nmi','gate'):
                assert (folder/(name+'-'+kind+'-after.bin')).read_bytes()==(folder/('claude-'+kind+'-before.bin')).read_bytes()
        for row in report['suite_apps']['ultimate']:
            assert row['bitmap'];name=row['label'];page=row['page']
            wanted=controls_surface(row['graphical_body'],page=page,focus=page,count=row['drive_count'])
            assert (folder/(name+'-surface.bin')).read_bytes()==wanted and sha(wanted)==row['surface_sha256']
            assert (folder/(name+'-vdc.bin')).read_bytes()==panel_screen(80,row['body'],page=page,focus=page)

        # The shared serial workflow also renders the complete Files browser.
        for row in report['files_frames']:
            name=row['label'];entries=disk_records((folder/'suite.d64').read_bytes())
            assert (folder/(name+'-surface.bin')).read_bytes()==files_surface(entries)
            assert (folder/(name+'-vdc.bin')).read_bytes()==files_console(entries)

        folder=temp/'copyiec';report=json.loads((folder/'report.json').read_text())
        assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_files_copy_iec.py').read_bytes()
        assert report['passed'] and report['all_host_processes_terminal'] and not report['physical_hardware_io']
        assert report['source_disk_unchanged'] and report['system_disk_unchanged'] and report['nonempty_exports_match']
        totals['copyiec']=captures(folder,dict(report,captures=report['captures']+report['mode_captures']))
        assert not totals['copyiec']['rejected'];resident(folder)
        assert (folder/'suite.d64').read_bytes()==(source/'target/native-desktop/uos128.d64').read_bytes()
        assert (folder/'data-9.d81').read_bytes()==(folder/'initial-9.d81').read_bytes()
        for row in report['files_copy_frames']:
            name=row['label'];expected=dict(row['expected'])
            if 'source' in expected:
                original=bytes.fromhex(expected.pop('source'));destination=bytes.fromhex(expected.pop('name'))
                wanted=files_copy_surface(original,destination,**expected)
                vdc=files_copy_console(original,destination,**expected)
            else:
                entries=disk_records((folder/'initial-9.d81').read_bytes(),2)
                wanted=files_surface(entries,**expected);vdc=files_console(entries,**expected)
            assert (folder/(name+'-surface.bin')).read_bytes()==wanted and sha(wanted)==row['surface_sha256']
            assert (folder/(name+'-vdc.bin')).read_bytes()==vdc
        def d81_files(raw):
            assert len(raw)==80*40*256
            def sector(track,number):
                assert 1<=track<=80 and 0<=number<40
                at=((track-1)*40+number)*256;return raw[at:at+256]
            track,number=40,3;seen=set();result={}
            while track:
                assert (track,number) not in seen;seen.add((track,number));block=sector(track,number)
                for at in range(0,256,32):
                    kind=block[at+2]&7
                    if not kind:continue
                    assert block[at+2]&128
                    name=block[at+5:at+21].rstrip(b'\xa0');assert name not in result
                    part=bytearray();t,n=block[at+3:at+5];visited=set()
                    while t:
                        assert (t,n) not in visited;visited.add((t,n));data=sector(t,n)
                        if data[0]:part.extend(data[2:])
                        else:
                            assert data[1]>=1;part.extend(data[2:data[1]+1])
                        t,n=data[:2]
                    result[name]=(kind,bytes(part))
                track,number=block[:2]
            return result
        fixtures={b'LARGE':(1,bytes((i*73+19)&255 for i in range(66058))),b'EMPTY':(1,b''),b'PROGRAM':(2,b'\x01\x1cEXACT\0PRG\xff')}
        assert d81_files((folder/'initial-9.d81').read_bytes())==fixtures
        assert d81_files((folder/'data-10.d81').read_bytes())=={b'COPIED '+name:item for name,item in fixtures.items() if item[1]}
        for name,(_,data) in fixtures.items():
            if data:assert (folder/('copied-'+name.decode().lower()+'.bin')).read_bytes()==data
        heap=(folder/'final-native-heap.bin').read_bytes()
        assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251) and all(heap[0x400+i*8]==0 for i in range(32))

        provenance=read('provenance.json')
        assert not provenance['physical_hardware_io'] and not provenance['pushed']
        assert all(code==0 for code in provenance['qualified_session_exit_codes'].values())
        return dict(passed=True,frozen_inputs=len(inputs),reproduced_images=24,core_cpu_suites=len(core_names),
            application_cpu_runs=len(cpu),application_cpu_groups=cpu,total_application_cpu_groups=sum(cpu.values()),
            raw_capture_audits=totals,capture_admissions=admissions,paint_filtered_line_samples=filter_counts,
            complete_palette_frames=frames,complete_paint_frames=paint_frames,complete_files_frames=files_frames,
            palette_pixels=frames*64000,independent_d81_copy_bytes=66058+len(fixtures[b'PROGRAM'][1]),
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
