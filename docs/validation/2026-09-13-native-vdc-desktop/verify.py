#!/usr/bin/env python3
"""Offline audit of the native VDC launcher and complete suite workflows."""
import hashlib,json,re,sys,tarfile,tempfile
from pathlib import Path,PurePosixPath
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()
read=lambda name:json.loads((ROOT/name).read_text())
from capture_audit import captures

def audit():
    if (ROOT/'SHA256SUMS').exists():
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            digest,name=line.split('  ',1);assert sha((ROOT/name).read_bytes())==digest,name
    archives=read('archives.json')
    with tempfile.TemporaryDirectory(prefix='uos-vdc-audit-') as temporary:
        temp=Path(temporary)
        for label,info in archives.items():
            archive=ROOT/info['archive'];assert sha(archive.read_bytes())==info['sha256']
            manifest=read(info['manifest']);assert len(manifest)==info['payload_files']
            assert sum(row['bytes'] for row in manifest.values())==info['payload_bytes']
            with tarfile.open(archive,'r:gz') as tar:
                members=tar.getmembers();assert len(members)==len(manifest)
                assert {m.name for m in members}==set(manifest)
                for member in members:
                    name=PurePosixPath(member.name)
                    assert member.isfile() and not name.is_absolute() and '..' not in name.parts
                    raw=tar.extractfile(member).read();row=manifest[member.name]
                    assert len(raw)==row['bytes'] and sha(raw)==row['sha256']
                    target=temp/label/member.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        source=temp/'inputs';inputs=read('inputs-files.json')
        sys.path[:0]=[str(source),str(source/'tests')]
        from native_image import validate
        from native_module import validate as validate_module
        from native_browser_check import disk_records
        from native_files_scene import browser_surface as files_surface,browser_console as files_console,copy_surface as files_copy_surface,copy_console as files_copy_console
        from native_files_check import exact_d64_files
        from native_calc_scene import surface as calc_surface
        from native_editor_scene import surface as editor_surface,console as editor_console
        from native_picker_scene import surface as picker_surface,console as picker_console
        from native_capture import calculator_screen
        from native_pointer_check import pixels,surface_pixels,check_canvas
        from launcher_scene import surface,console
        from paint_scene import surface as paint_surface,console as paint_console,MESSAGES
        from native_paint_format import encode,decode
        from native_running_layout import RunningLayout
        from native_controls_check import panel_screen,absent_body
        from native_controls_scene import surface as controls_surface
        from native_claude_scene import surface as claude_surface
        from native_claude_check import landing_screen,waiting_panel
        from native_suite_workflow import terminal_screen
        from native_vdc_scene import bitmap as vdc_bitmap,pack as vdc_pack,unpack as vdc_unpack
        packed=vdc_pack(vdc_bitmap());assert len(packed)==2393 and vdc_unpack(packed)==vdc_bitmap()
        from vdc_audit import frame as vdc_frame, restore as vdc_restore, font as vdc_font
        frozen=read('frozen-rebuild.json')
        if (ROOT/'main-rebuild.json').exists():rebuilt=read('main-rebuild.json')
        else:
            assert not (ROOT/'SHA256SUMS').exists(),'sealed record requires main build'
            rebuilt=frozen
        assert rebuilt['passed'] and frozen['passed'] and rebuilt['images']==frozen['images']
        assert rebuilt['build_exit_code']==frozen['build_exit_code']==0 and len(rebuilt['images'])==24
        build_processes=read('build-processes.json')
        for label,result in (('frozen',frozen),('main',rebuilt)):
            status=build_processes[label]
            assert status['terminal'] and status['passed'] and status['exit_code']==0
            command=status['command'];assert command[command.index('--source')+1]==result['source']
        for name,digest in rebuilt['images'].items():assert inputs[name]['sha256']==digest,name
        base=read('base-images.json')
        assert {name for name,digest in base.items() if inputs[name]['sha256']!=digest}=={
            'target/native-desktop/desktop.prg','target/native-desktop/uos128.d64','target/native-desktop/workspace.d64'}
        assert (ROOT/'base-commit.txt').read_text().strip()=='5975914bead1ccd09e4d7da90255702a991f2838'
        app=validate((source/'target/native-desktop/desktop.prg').read_bytes())
        assert (app['bytes'],app['pages'],app['entry'],app['title'])==(10885,43,0x6020,'UOS DESKTOP')
        for core,parts in (('editor',('edpick','edfind')),('files',('fspick','fsview'))):
            for part in parts:validate_module((source/f'target/native-desktop/{part}.prg').read_bytes(),(source/f'target/native-desktop/{core}.prg').read_bytes())
        deployment=json.loads((source/'target/native-desktop/deployment.json').read_text())
        for disk in ('uos128.d64','workspace.d64'):
            files=exact_d64_files((source/'target/native-desktop'/disk).read_bytes())
            assert len(files)==12
            disk_bytes=(source/'target/native-desktop'/disk).read_bytes()
            bam=disk_bytes[357*256:358*256]
            assert sum(bam[4+(track-1)*4] for track in range(1,36) if track!=18)==8
            for name,filename in deployment['disk_entries'].items():
                path=source/('target/native' if name=='u' and disk=='workspace.d64' else 'target/native-desktop')/filename
                assert files[name.upper().encode()]==(2,path.read_bytes())
        provenance=read('provenance.json');runs=read('qualified-runs.json')
        for name,run in runs.items():
            status,config=run['status'],run['config']
            assert status['terminal'] and status['exit_code']==0 and status['passed']
            overlay=run.get('source_overlay',{})
            for path,digest in config['source_sha256'].items():
                if path in run.get('unexercised_source_changes',[]):
                    assert path in ('tests/ci_native_claude_iec.py','tests/ci_native_desktop_iec.py') and path!=config['driver']
                    assert Path(path).stem not in (source/config['driver']).read_text()
                    continue
                if path.endswith(('.py','.inc','.asm','.c','.s','.cfg','.prg','.d64')):
                    if path in overlay:
                        assert sha((temp/'run-sources'/overlay[path]).read_bytes())==digest,(name,path)
                    else:assert inputs[path]['sha256']==digest,(name,path)
            driver=config['driver']
            actual=temp/'run-sources'/overlay[driver] if driver in overlay else source/driver
            assert sha(actual.read_bytes())==config['source_sha256'][driver]
        cpu_cases=0
        for name in provenance['cpu_jobs']:
            report=json.loads((temp/'app-cpu'/(name+'.json')).read_text());assert report['passed'] and not report['physical_hardware_io']
            cpu_cases+=len(report['cases'])
            for path,digest in report.get('images',{}).items():assert inputs[path]['sha256']==digest
        manual=read('manual-terminal-observations.json')
        assert manual['cpu-fault-v2']['exit_code']==0 and manual['cpu-fault-v2']['session_id']==4566
        assert manual['cpu-fault-v2']['report_sha256']==sha((temp/'app-cpu/cpu-fault-v2.json').read_bytes())
        assert cpu_cases==39
        assert manual['cpu-fault-v2']['driver_sha256_at_sealing']==inputs['tests/ci_native_vdc_desktop.py']['sha256']
        ref=json.loads((temp/'reference/provenance.json').read_text())
        assert ref['commit']=='86fb219f3214bf0dcbb74dc965bde4116109d388' and len(ref['files'])==8
        for path,info in ref['files'].items():
            raw=(temp/'reference'/Path(path).name).read_bytes()
            assert len(raw)==info['bytes'] and sha(raw)==info['sha256']
        running=RunningLayout(source,image_dir=source/'target/native-desktop')
        def resident(folder):
            for prefix in ('resident-boot','resident-return'):
                data={name:(folder/(prefix+'-'+name+'.bin')).read_bytes() for name in running.regions}
                assert running.compare(data)['passed']
        def claude_frames(folder,report):
            count=0
            for row in report['claude_frames']:
                name=row['label'];expected=row['expected'];panel=bytes.fromhex(row['panel_hex'])
                if expected['live']:assert panel==waiting_panel(connected=True)
                else:assert panel in (landing_screen(40),landing_screen(40,2))
                assert (folder/(name+'-panel.bin')).read_bytes()==panel
                glyphs=(folder/(name+'-font.bin')).read_bytes();assert len(glyphs)==4096
                wanted=claude_surface(panel,b'\1'*1000,glyphs,**expected)
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted and sha(wanted)==row['surface_sha256']
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),surface_pixels(wanted,*row['position'],visible=row.get('pointer_visible',True)))==row['rectangle']
                count+=1
            return count
        blank=bytes(8192)+b'\x10'*1024
        totals={};frames=0;vdc_frames=0;vdc_restores=0;paint_frames=0;files_frames=0;editor_frames=0;picker_frames=0;admissions={};filter_counts={}
        for label,eighty in (('vice40',False),('vice80',True)):
            folder=temp/label;report=json.loads((folder/'report.json').read_text())
            assert report['passed'] and report['all_host_processes_terminal'] and report['system_disk_files_preserved']
            assert not report['physical_hardware_io'] and report['options']==dict(eighty=eighty,vdc64=eighty,boot_frame_only=False,paint_only=False,controls_only=False,files_only=False,editor_only=False,claude_only=False)
            assert sha((folder/'run.py').read_bytes())==runs[provenance['vice_jobs'][label]]['config']['source_sha256']['tests/ci_native_pointer_iec.py']
            for name,digest in report['images'].items():assert inputs['target/native-desktop/'+name]['sha256']==digest
            totals[label]=captures(folder,dict(report,captures=report['captures']+report['mode_captures']))
            assert not totals[label]['rejected']
            assert len(report['desktops'])==17 and len(report['calculator_frames'])==5 and len(report['paint_frames'])==10
            for row in report['desktops']:
                name=row['label'];selected=row['selected'];x,y=row['position']
                assert (folder/(name+'-surface.bin')).read_bytes()==surface(selected)
                vdc_frame(folder,row['vdc'],report['captures'],color=eighty);vdc_frames+=1
                assert row['vdc']['position']==[x*2,y] and row['vdc']['pointer_visible']
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
            assert len(report['editor_frames'])==len(report['editor_states'])==9
            for row,state in zip(report['editor_frames'],report['editor_states']):
                name=row['label'];data=bytes.fromhex(row['data_hex']);expected=row['expected'];cursor=row['cursor']
                assert state['label']==name and state['cursor']==cursor
                assert state['eg_bitmap']==1 and state['ed_module_kind']==2 and state['ui_selected']==expected['focus']
                assert state['ed_mode']==expected.get('mode',0) and state['ed_status']==expected.get('status',0)
                wanted=editor_surface(data,cursor,**expected)
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted
                assert (folder/(name+'-vdc.bin')).read_bytes()==editor_console(data,cursor,**expected)
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),surface_pixels(wanted,*row['position']))==row['rectangle']
                assert row['mode']['vic_sprites']==3;frames+=1;editor_frames+=1
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
            assert len(report['files_frames'])==10
            final_entries=disk_records((folder/'suite.d64').read_bytes())
            for row in report['files_frames']:
                name=row['label'];expected=dict(row['expected'])
                if 'records' in expected:
                    entries=[dict(entry,name=bytes.fromhex(entry['name'])) for entry in expected.pop('records')]
                    assert entries==final_entries
                    wanted=files_surface(entries,**expected);vdc=files_console(entries,**expected)
                else:
                    original=bytes.fromhex(expected.pop('source'));destination=bytes.fromhex(expected.pop('name'))
                    assert original==b'EDFIND.PRG'
                    assert destination==(original if name=='files-copy-dialog' else b'FSCOPY')
                    wanted=files_copy_surface(original,destination,**expected)
                    vdc=files_copy_console(original,destination,**expected)
                    if name in ('files-data-destination','files-copy-verified'):assert expected['device']==9 and expected['source_device']==8
                    if name=='files-copy-verified':
                        data=exact_d64_files((source/'target/native-desktop/uos128.d64').read_bytes())[original][1]
                        assert expected['copied']==expected['verified']==len(data) and expected['status']==1
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted
                assert (folder/(name+'-vdc.bin')).read_bytes()==vdc
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),surface_pixels(wanted,*row['position']))==row['rectangle']
                assert row['mode']['vic_sprites']==3;frames+=1;files_frames+=1
            assert len(report['picker_frames'])==5
            for row in report['picker_frames']:
                name=row['label'];expected=row['expected']
                entries=[dict(name=bytes.fromhex(e['name_hex']),type=e['type'],blocks=e['blocks'],flags=e['flags'],app=False) for e in row['entries']]
                excluded={b'GUINOTE',b'FSCOPY',b'PAINTPIC'} if row['app']=='editor' else {b'FSCOPY',b'PAINTPIC'} if row['app']=='files' else set()
                if expected['device']==9:
                    if name=='files-data-picker':assert entries==[]
                    else:
                        data_entries=[dict(e,app=False) for e in disk_records((folder/'data-9.d64').read_bytes())]
                        if name=='paint-save-destination':data_entries=[e for e in data_entries if e['name']!=b'PAINTPIC']
                        assert entries==data_entries
                else:assert entries==[dict(entry,app=False) for entry in final_entries if entry['name'] not in excluded]
                wanted=picker_surface(entries,**expected)
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted
                assert (folder/(name+'-vdc.bin')).read_bytes()==picker_console(entries,**{k:v for k,v in expected.items() if k not in ('focus','mode')})
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),surface_pixels(wanted,*row['position']))==row['rectangle']
                assert row['mode']['vic_sprites']==3;frames+=1;picker_frames+=1
            assert len(report['claude_frames'])==4
            frames+=claude_frames(folder,report)
            assert len(report['vdc_restores'])==6
            for row in report['vdc_restores']:
                vdc_restore(folder,row,report['captures'],source);vdc_restores+=1
            keys=(folder/'keys-before.bin').read_bytes();assert len(keys)==256
            apps=['calc','editor','files','controls','claude','paint']
            for app in apps:assert (folder/(app+'-keys-restored.bin')).read_bytes()==keys
            assert [row['mouse_app'] for row in report['events'] if 'mouse_app' in row]==apps
            assert [row['calculator_button'] for row in report['events'] if 'calculator_button' in row]==[8,9,15,10,13,14,17,21,17,22]
            assert all(row['keyboard_events_during_click']==0 for row in report['events'] if 'keyboard_events_during_click' in row)
            assert all(row['keys_after']==(row['keys_before']+1)&65535 for row in report['events'] if 'key' in row)
            disk=exact_d64_files((folder/'suite.d64').read_bytes())
            assert disk.pop(b'GUIHIST')==(1,b'42\r')
            assert bytes.fromhex(report['editor_saved_hex'])==b'C1X28 TEXT'
            assert disk.pop(b'GUINOTE')==(1,b'C1X28 TEXT')
            data_disk=exact_d64_files((folder/'data-9.d64').read_bytes())
            assert report['paint_destination_device']==9
            picture=data_disk.pop(b'PAINTPIC');assert picture==(1,encode(document)) and decode(picture[1])==document
            assert report['paint_file_sha256']==sha(picture[1]) and len(picture[1])==9016
            expected_disk=exact_d64_files((source/'target/native-desktop/uos128.d64').read_bytes())
            assert exact_d64_files((folder/'initial-data-9.d64').read_bytes())=={} and set(data_disk)=={b'FSCOPY'}
            assert report['files_copy_destination_device']==9
            copied=data_disk[b'FSCOPY'];assert copied==expected_disk[b'EDFIND.PRG']
            assert report['files_copy_sha256']==sha(copied[1])
            assert disk==expected_disk
            pages=(folder/'final-page-table.bin').read_bytes();handles=(folder/'final-records.bin').read_bytes()
            assert pages[0x50:0xff]==bytes(175) and pages[0x104:0x1ff]==bytes(251)
            assert all(handles[i*8]==0 for i in range(32));resident(folder)
            admissions[label]=dict(batches=len(report['capture_admissions']),deferred=sum(row['deferred'] for row in report['capture_admissions']))
            filter_counts[label]=report['paint_filtered_line_samples']

        for label,color in (('keyboard64',True),('keyboard16',False)):
            folder=temp/label;report=json.loads((folder/'report.json').read_text())
            assert report['passed'] and not report['physical_hardware_io'] and report['options']['desktop_boot']
            assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_desktop_iec.py').read_bytes()
            assert report['options']['vdc64']==color and report['options']['eighty']
            assert report['disk_sha256']==inputs['target/native-desktop/uos128.d64']['sha256']
            for row in report['calculator_frames']:
                name=row['label'];wanted=calc_surface(row['result'],row['history'])
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted
                assert check_canvas((folder/(name+'-display-get.bin')).read_bytes(),surface_pixels(wanted,0,0,visible=False))==row['rectangle']
                frames+=1
            assert len(report['calculator_frames'])==2 and len(report['paint_frames'])==4
            assert len(report['desktops'])==19 and sum(row['fallback'] for row in report['desktops'])==2
            for row in report['desktops']:
                if row['fallback']:
                    name=row['label']
                    assert (folder/(name+'-80.bin')).read_bytes()==console(80,row['selected'],row['error'],True)
                    assert (folder/(name+'-40.bin')).read_bytes()==console(40,row['selected'],row['error'],True)
                    continue
                vdc_frame(folder,row['vdc'],report['captures'],color=color);vdc_frames+=1
                assert not row['vdc']['pointer_visible']
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

            assert len(report['editor_frames'])==4
            for row in report['editor_frames']:
                name=row['label'];data=bytes.fromhex(row['data_hex']);expected=row['expected'];cursor=row['cursor']
                wanted=editor_surface(data,cursor,**expected)
                assert (folder/(name+'-surface.bin')).read_bytes()==wanted
                assert (folder/(name+'-80.bin')).read_bytes()==editor_console(data,cursor,**expected)
                assert check_canvas((folder/(name+'-display-get.bin')).read_bytes(),surface_pixels(wanted,0,0,visible=False))==row['rectangle']
                frames+=1;editor_frames+=1
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
            totals[label]=captures(folder,report);assert not totals[label]['rejected']
            resident(folder)


            assert vdc_font(folder,report['original_vdc_snapshot'],report['captures'])==vdc_font(folder,report['restored_vdc_snapshot'],report['captures'])

        for label,host_exit in (('serial40',False),('serial80',True)):
            folder=temp/label;report=json.loads((folder/'report.json').read_text())
            assert report['passed'] and not report['physical_hardware_io'] and report['host_exit_code']==0
            assert report['options']['mouse'] and report['options']['eighty']==host_exit and report['options']['host_exit']==host_exit
            assert report['mouse_enabled_after_claude_launch'] and len(report['private_x_windows'])==2
            assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_claude_iec.py').read_bytes()
            assert (folder/'suite.d64').read_bytes()==(source/'target/native-desktop/uos128.d64').read_bytes()
            for name,digest in report['images'].items():assert inputs['target/native-desktop/'+name]['sha256']==digest
            totals[label]=captures(folder,dict(captures=report['cpu_captures'],paused_capture_batches=report['cpu_capture_batches']))
            assert not totals[label]['rejected'] and len(report['claude_frames'])==6
            frames+=claude_frames(folder,report)
            assert (folder/'session-vdc.bin').read_bytes()==terminal_screen(True)
            assert (folder/'returned-desktop-surface.bin').read_bytes()==surface(4)
            assert report['options']['vdc64']==host_exit
            assert len(report['desktop_frames'])==2
            assert [row['selected'] for row in report['desktop_frames']]==[0,4]
            for row in report['desktop_frames']:
                vdc_frame(folder,row,report['cpu_captures'],color=host_exit);vdc_frames+=1
                assert (folder/(row['label']+'-surface.bin')).read_bytes()==surface(row['selected'])
            assert vdc_font(folder,report['original_vdc_snapshot'],report['cpu_captures'])==(folder/'font-before.bin').read_bytes()
            assert vdc_font(folder,report['restored_vdc_snapshot'],report['cpu_captures'])==(folder/'font-after.bin').read_bytes()
            assert (folder/'font-after.bin').read_bytes()==(folder/'font-before.bin').read_bytes()
            assert (folder/'nmi-after.bin').read_bytes()==(folder/'nmi-before.bin').read_bytes()
            expected=0 if host_exit else 2
            assert report['close_outcome']==expected and (folder/'close-outcome.bin').read_bytes()==bytes([expected])
            assert report['serial_counters']['_rxDropped']==report['serial_counters']['_rxOverruns']==0
            assert report['serial_counters']['_rxCount']>0 and report['serial_counters']['_nmiCount']>=report['serial_counters']['_rxCount']
            checkpoint=(folder/'close-checkpoint.bin').read_bytes()
            assert checkpoint.hex()==report['close_observation']['checkpoint_hex'] and int.from_bytes(checkpoint[13:17],'little')>0
            assert report['close_observation']['lifetime']=='Claude allocation still live; before native_video_end'
            assert [row['code'] for row in report['rom_keys']]==[255,9,9,13,27]
            assert all(row['keyboard_events']==0 for row in report['mouse_events'])
            assert all(row['after']==(row['before']+1)&65535 for row in report['rom_keys'])
            pages=(folder/'final-heap.bin').read_bytes();assert pages[0x50:0xff]==bytes(175) and pages[0x104:0x1ff]==bytes(251)
        folder=temp/'boot64-40';report=json.loads((folder/'report.json').read_text())
        assert report['passed'] and report['all_host_processes_terminal'] and report['system_disk_unchanged']
        assert report['options']['vdc64'] and report['options']['boot_frame_only'] and not report['options']['eighty']
        assert report['mouse_enabled_after_boot'] and len(report['desktops'])==1
        assert (folder/'suite.d64').read_bytes()==(source/'target/native-desktop/uos128.d64').read_bytes()
        row=report['desktops'][0];name=row['label'];x,y=row['position']
        assert (folder/(name+'-surface.bin')).read_bytes()==surface(0)
        assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),pixels(0,x,y))==row['rectangle'];frames+=1
        vdc_frame(folder,row['vdc'],report['captures'],color=True);vdc_frames+=1
        totals['boot64-40']=captures(folder,dict(report,captures=report['captures']+report['mode_captures']))
        assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_pointer_iec.py').read_bytes()
        assert all(not row['rejected'] for row in totals.values())
        assert vdc_restores==12

        return dict(passed=True,physical_hardware_io=False,inputs=len(inputs),images=len(rebuilt['images']),
            cpu_cases=cpu_cases,qualified_processes=len(runs),manual_terminal_observations=len(manual),
            vice_workflows=len(provenance['vice_jobs']),vic_palette_frames=frames,vdc_palette_frames=vdc_frames,
            palette_frames=frames+vdc_frames,pixels=frames*64000+vdc_frames*128000,vdc_restores=vdc_restores,
            capture_totals=totals,captures=sum(row['captures'] for row in totals.values()),
            chunks=sum(row['chunks'] for row in totals.values()),borrower_pairs=sum(row['borrower_pairs'] for row in totals.values()),
            archives={label:dict(files=row['payload_files'],bytes=row['payload_bytes']) for label,row in archives.items()})

if __name__=='__main__':print(json.dumps(audit(),indent=2))
