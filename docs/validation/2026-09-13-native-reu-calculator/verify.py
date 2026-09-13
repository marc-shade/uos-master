#!/usr/bin/env python3
"""Offline verification of native REU allocation, Calculator backing and full-suite workflows."""
import hashlib,json,sys,tarfile,tempfile
from pathlib import Path,PurePosixPath
sys.dont_write_bytecode=True
RECORD=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda n:json.loads((RECORD/n).read_text())
from capture_audit import captures


def audit():
    if (RECORD/'SHA256SUMS').exists():
        for line in (RECORD/'SHA256SUMS').read_text().splitlines():
            digest,name=line.split('  ',1);assert sha((RECORD/name).read_bytes())==digest,name
    with tempfile.TemporaryDirectory(prefix='uos-reu-audit-') as temporary:
        temp=Path(temporary)
        for label,row in read('archives.json').items():
            path=RECORD/row['archive'];assert sha(path.read_bytes())==row['sha256']
            manifest=read(row['manifest']);assert len(manifest)==row['payload_files']
            with tarfile.open(path,'r:gz') as tar:
                members=tar.getmembers();assert len(members)==len(manifest)
                assert {m.name for m in members}==set(manifest)
                for member in members:
                    name=PurePosixPath(member.name)
                    assert member.isfile() and not name.is_absolute() and '..' not in name.parts
                    raw=tar.extractfile(member).read();info=manifest[member.name]
                    assert len(raw)==info['bytes'] and sha(raw)==info['sha256']
                    dest=temp/label/member.name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        source=temp/'inputs';sys.path[:0]=[str(source),str(source/'tests')]
        inputs=read('inputs-files.json');images=read('images.json')
        assert len(inputs)==577 and len(images)==33
        base=read('base-images.json');assert len(base)==33
        assert {p for p,h in base.items() if images[p]!=h}=={
            'target/native-desktop/calc.prg',
            'target/native-desktop/uos128.d64','target/native-desktop/workspace.d64',
            'target/native-desktop/uos128.d81','target/native-desktop/workspace.d81'}
        assert set(images)==set(base)
        for name,digest in images.items():assert inputs[name]['sha256']==digest
        builds=[read('rebuild-1.json'),read('rebuild-2.json')]
        assert all(b['passed'] and b['build_exit_code']==0 and b['images']==images for b in builds)
        from ci_native_boot_media import inspect
        from native_files_check import exact_disk_files
        from native_image import validate
        from native_module import validate as module_validate
        from native_running_layout import RunningLayout
        from native_pointer_check import pixels,surface_pixels,check_canvas
        from native_browser_check import disk_records
        from launcher_scene import surface
        from native_calc_scene import surface as calc_surface
        from native_capture import calculator_screen
        from native_editor_scene import surface as editor_surface,console as editor_console
        from native_files_scene import browser_surface, browser_console,copy_surface,copy_console
        from native_picker_scene import surface as picker_surface,console as picker_console
        from native_controls_scene import surface as controls_surface
        from native_controls_check import panel_screen,absent_body
        from native_claude_scene import surface as claude_surface
        from native_claude_check import landing_screen
        from native_paint_format import encode,decode
        from paint_scene import surface as paint_surface,console as paint_console,MESSAGES
        from vdc_audit import frame as vdc_frame,restore as vdc_restore
        media=json.loads((temp/'cpu/media1.json').read_text());assert media['passed']
        deployment=json.loads((source/'target/native-desktop/deployment.json').read_text())
        for name,row in media['disks'].items():
            path=source/name;fmt=2 if path.suffix=='.d81' else 0
            assert inspect(path.read_bytes(),fmt,(path.parent/'boot.prg').read_bytes()[2:])==row
            entries=deployment['disk_entries'] if path.parent.name=='native-desktop' else {
                'u':'uos128-boot.prg','calc':'calc.prg','browse':'browse.prg','editor':'editor.prg',
                'edpick.prg':'edpick.prg','edfind.prg':'edfind.prg'}
            expected={}
            for disk_name,filename in entries.items():
                origin=path.parent
                if disk_name=='u':
                    if path.stem=='workspace':origin=source/'target/native'
                    if fmt==2:origin/='d81'
                expected[disk_name.upper().encode()]=(2,(origin/filename).read_bytes())
            assert exact_disk_files(path.read_bytes(),fmt)==expected
        assert media['full_disk']['free_blocks']==0 and media['full_disk']['payload_bytes']==634492
        assert media['rejected_corruptions']==3
        deployment=json.loads((source/'target/native-desktop/deployment.json').read_text())
        assert deployment['abi']=='1.12' and deployment['boot_format_address']==0x3de4
        assert deployment['free_pages_at_desktop']=={'16':283,'64':275}
        app=source/'target/native-desktop'
        assert (app/'desktop.prg').read_bytes()[8]==12
        for name in ('desktop','files','calc','editor','paint','claude','controls'):validate((app/(name+'.prg')).read_bytes())
        for core,parts in [('editor',('edpick','edfind')),('files',('fspick','fsview'))]:
            for part in parts:module_validate((app/(part+'.prg')).read_bytes(),(app/(core+'.prg')).read_bytes())
        for prefix in ('native','native-desktop'):
            a=(source/'target'/prefix/'uos128.prg').read_bytes();b=(source/'target'/prefix/'d81/uos128.prg').read_bytes()
            assert [(x,y) for x,y in zip(a,b) if x!=y]==[(0,2)] and len(a)==len(b)
            for profile in ('','d81/'):
                layout=json.loads((source/'target'/prefix/(profile+'layout.json')).read_text())
                assert layout['managed_pages']==426 and layout['service_limit']==0x5000
        jobs=read('jobs.json')
        for label,job in jobs.items():
            status=job['status'];assert status['terminal'] and status['passed'] and status['exit_code']==0,label
            for name,digest in job['config']['source_sha256'].items():
                if Path(name).suffix not in ('.py','.asm','.inc','.c','.s','.cfg','.prg','.d64','.d81'):continue
                actual=source/name
                if name in job['source_overlay']:actual=temp/'source-versions'/job['source_overlay'][name]
                assert sha(actual.read_bytes())==digest,(label,name)
        cpu_count=0
        for name in read('cpu-reports.json'):
            report=json.loads((temp/'cpu'/name).read_text());assert report['passed'],name
            for path,digest in report.get('images',{}).items():assert images[path]==digest,(name,path)
            cpu_count+=len(report.get('cases',[]))
        expected_counts={'cpu-reu1.json':23,'calc-reu2.json':7,'calc-vdc1.json':11,'calc-gui1.json':7,'setup1.json':8}
        for name,count in expected_counts.items():
            result=json.loads((temp/'cpu'/name).read_text());assert len(result['cases'])==count,(name,count)
        reu=json.loads((temp/'cpu/cpu-reu1.json').read_text())
        assert sha((temp/'cpu/reu-library.prg').read_bytes())==reu['image_sha256']
        from native_reu_check import decode_snapshot,initial_memory
        reu_vice=json.loads((temp/'reu-vice/report.json').read_text())
        assert reu_vice['passed'] and not reu_vice['physical_hardware_io']
        assert sha((temp/'reu-vice/check.prg').read_bytes())==reu_vice['fixture_sha256']
        assert [row['kib'] for row in reu_vice['cases']]==[128,256,512,1024,2048,4096,8192,16384]
        reu_bytes=0
        for row in reu_vice['cases']:
            assert row['passed'] and len(row['snapshots'])==2
            kib=row['kib'];folder=temp/'reu-vice'/str(kib)
            expected=bytearray(initial_memory(kib))
            for offset,count in ((0,512),(0xff80,512),(kib*1024-512,512)):
                expected[offset:offset+count]=bytes((i*51+(i>>3)*7+(offset>>16))&255 for i in range(count))
            if kib>=1024:expected[0x7ff80:0x80180]=bytes((i*93+61)&255 for i in range(512))
            for i,info in enumerate(row['snapshots']):
                raw=(folder/info['snapshot']).read_bytes();assert sha(raw)==info['snapshot_sha256']
                memory,decoded=decode_snapshot(raw)
                assert decoded['kib']==kib and decoded['sha256']==info['sha256']
                assert memory==(initial_memory(kib) if i==0 else expected)
                reu_bytes+=len(memory)
        assert validate((app/'calc.prg').read_bytes())['pages']==57
        assert validate((app/'calc.prg').read_bytes())['bytes']==14369
        totals={};frames=vdc_frames=restores=0
        for label in ('vice81','vice64'):
            folder=temp/label;report=json.loads((folder/'report.json').read_text());fmt=report['boot_format']
            assert fmt==(2 if label=='vice81' else 0)
            assert report['passed'] and report['all_host_processes_terminal'] and report['system_disk_files_preserved']
            assert not report['physical_hardware_io']
            for name,digest in report['images'].items():assert images['target/native-desktop/'+name]==digest
            totals[label]=captures(folder,dict(report,captures=report['captures']+report['mode_captures']))
            assert not totals[label]['rejected']
            running=RunningLayout(source,image_dir=source/'target'/report['kernel_prefix'])
            for prefix in ('resident-boot','resident-return'):
                assert running.compare({n:(folder/(prefix+'-'+n+'.bin')).read_bytes() for n in running.regions})['passed']
            def graphic(row,wanted,vdc=None):
                name=row['label'];assert (folder/(name+'-surface.bin')).read_bytes()==wanted,name
                assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),surface_pixels(wanted,*row['position']))==row['rectangle'],name
                if vdc is not None:assert (folder/(name+'-vdc.bin')).read_bytes()==vdc,name
                assert row['mode']['vic_sprites']==3
            for row in report['desktops']:
                graphic(row,surface(row['selected']))
                vdc_frame(folder,row['vdc'],report['captures'],color=report['options']['vdc64']);vdc_frames+=1;frames+=1
            for row in report['calculator_frames']:
                wanted=calc_surface(**row['expected'])
                graphic(row,wanted)
                vdc_frame(folder,row['vdc'],report['captures'],color=report['options']['vdc64'],surface_data=wanted)
                frames+=1;vdc_frames+=1
            for row in report['editor_frames']:
                data=bytes.fromhex(row['data_hex']);e=row['expected'];assert e['fmt']==fmt
                graphic(row,editor_surface(data,row['cursor'],**e),editor_console(data,row['cursor'],**e));frames+=1
            ext='d81' if fmt==2 else 'd64'
            final_entries=disk_records((folder/('suite.'+ext)).read_bytes(),fmt)
            for row in report['files_frames']:
                e=dict(row['expected'])
                if 'records' in e:
                    entries=[dict(item,name=bytes.fromhex(item['name'])) for item in e.pop('records')]
                    assert e['fmt']==fmt
                    assert entries==[item for item in final_entries if item['name']!=b'PAINTPIC']
                    wanted,vdc=browser_surface(entries,**e),browser_console(entries,**e)
                else:
                    original=bytes.fromhex(e.pop('source'));name=bytes.fromhex(e.pop('name'))
                    wanted,vdc=copy_surface(original,name,**e),copy_console(original,name,**e)
                graphic(row,wanted,vdc);frames+=1
            for row in report['picker_frames']:
                e=row['expected'];entries=[dict(name=bytes.fromhex(item['name_hex']),type=item['type'],blocks=item['blocks'],flags=item['flags'],app=False) for item in row['entries']]
                graphic(row,picker_surface(entries,**e),picker_console(entries,**{k:v for k,v in e.items() if k not in ('mode','focus')}));frames+=1
            for row in report['controls_frames']:
                page,focus,notice=row['page'],row['focus'],row['notice'];body=absent_body(page)
                graphic(row,controls_surface(body[2:] if page==1 else body,page=page,focus=focus,notice=notice),panel_screen(80,body,page=page,focus=focus,notice=notice));frames+=1
            for row in report['claude_frames']:
                panel=bytes.fromhex(row['panel_hex']);assert panel in (landing_screen(40),landing_screen(40,2))
                glyphs=(folder/(row['label']+'-font.bin')).read_bytes();assert len(glyphs)==4096
                graphic(row,claude_surface(panel,b'\1'*1000,glyphs,**row['expected']),landing_screen(80,2 if panel==landing_screen(40,2) else 0));frames+=1
            blank=bytes(8192)+b'\x10'*1024;document=bytearray(blank);versions=[]
            for row in [r for r in report['events'] if 'paint_point' in r]:
                x,y=row['paint_point'];versions.append(bytes(document))
                document[y//8*320+x//8*8+y%8]|=128>>(x%8);document[8192+y//8*40+x//8]=row['color']*16
            assert len(versions)==2
            for row in report['paint_frames']:
                name=row['label'];e=dict(row['expected']);e['name']=e['name'].encode('latin1')
                expected=blank if name in ('paint-open','paint-open-confirm') else versions[-1] if name=='paint-undo' else bytes(document)
                assert (folder/(name+'-document.bin')).read_bytes()==expected and row['document_sha256']==sha(expected)
                vdc=paint_console(80,bitmap=True,message=row['status'],view=row['console_field_view'],**{k:v for k,v in e.items() if k not in ('view_x','view_y','field_view')})
                graphic(row,paint_surface(expected,message=MESSAGES[row['status']],**e),vdc);frames+=1
            assert len(report['vdc_restores'])==6
            for row in report['vdc_restores']:vdc_restore(folder,row,report['captures'],source);restores+=1
            assert len(report['vdc_app_restores'])==1 and report['vdc_app_restores'][0]['app']=='calc'
            for row in report['vdc_app_restores']:vdc_restore(folder,row,report['captures'],source);restores+=1
            apps=['calc','editor','files','controls','claude','paint']
            assert [r['mouse_app'] for r in report['events'] if 'mouse_app' in r]==apps
            keys=(folder/'keys-before.bin').read_bytes()
            for name in apps:assert (folder/(name+'-keys-restored.bin')).read_bytes()==keys
            assert all(r['keyboard_events_during_click']==0 for r in report['events'] if 'keyboard_events_during_click' in r)
            assert all(r['keys_after']==(r['keys_before']+1)&65535 for r in report['events'] if 'key' in r)
            ext='d81' if fmt==2 else 'd64';disk=exact_disk_files((folder/('suite.'+ext)).read_bytes(),fmt)
            original=exact_disk_files((app/('uos128.'+ext)).read_bytes(),fmt)
            assert disk.pop(b'GUIHIST')==(1,b'42\r') and disk.pop(b'GUINOTE')==(1,b'C1X28 TEXT')
            data=exact_disk_files((folder/'data-9.d64').read_bytes())
            assert data.pop(b'FSCOPY')==original[b'EDFIND.PRG']
            picture=(disk if fmt==2 else data).pop(b'PAINTPIC')
            assert picture==(1,encode(document)) and decode(picture[1])==document
            assert not data and disk==original
            assert report['paint_destination_device']==(8 if fmt==2 else 9)
            if fmt==2:assert report['workspace_system_shortcuts']
            pages=(folder/'final-page-table.bin').read_bytes();handles=(folder/'final-records.bin').read_bytes()
            assert pages[0x50:0xff]==bytes(175) and pages[0x104:0x1ff]==bytes(251) and all(handles[i*8]==0 for i in range(32))
        return dict(passed=True,inputs=len(inputs),images=len(images),cpu_cases=cpu_count,
            vic_frames=frames,vdc_frames=vdc_frames,palette_pixels=frames*64000+vdc_frames*128000,
            restored_vdc_snapshots=restores,captures=totals,reu_configurations=8,independently_compared_reu_bytes=reu_bytes,physical_hardware_io=False)


if __name__=='__main__':print(json.dumps(audit(),indent=2))
