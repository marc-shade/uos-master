#!/usr/bin/env python3
"""Verify this filename-search checkpoint offline using Python's standard library."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('formats',ROOT/'format-check.py')
fmt=importlib.util.module_from_spec(spec);spec.loader.exec_module(fmt)
digest=fmt.digest

def read(name):return json.loads((ROOT/name).read_text())

def archive(name):
    expected=read(name+'-files.json');result={}
    with tarfile.open(ROOT/(name+'.tar.gz'),'r:gz') as source:
        for item in source:
            assert item.isfile() and not item.name.startswith('/') and '..' not in Path(item.name).parts
            assert item.name not in result
            data=source.extractfile(item).read();result[item.name]=data
            assert expected[item.name]==dict(bytes=len(data),sha256=digest(data))
    assert set(result)==set(expected)
    return result

def audit(unsealed=False):
    if not unsealed:
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            sha,name=line.split('  ',1)
            assert '..' not in Path(name).parts and not name.startswith('/')
            assert digest((ROOT/name).read_bytes())==sha,name
    inputs=archive('inputs');jobs=archive('jobs');outputs=archive('vice')
    variants=archive('execution-variants');archive('references');archive('development')
    provenance=read('provenance.json');executions=read('executions.json')
    assert provenance['physical_hardware_io'] is False and provenance['pushed'] is False
    used=set()
    for execution in executions.values():
        for name,sha in execution['inputs'].items():
            if name in inputs and digest(inputs[name])==sha:continue
            assert digest(variants[sha])==sha
            used.add(sha)
    assert used==set(variants)
    statuses=read('statuses.json');reports={}
    for name,status in statuses.items():
        assert status==json.loads(jobs[name+'.status.json']) and status['exit_code']==0
        execution=executions[status['cwd']]
        assert status['command'][2] in execution['inputs']
        if name.startswith('cpu/'):
            report=json.loads(jobs[name+'.json']);reports[name]=report
            assert report['passed'] and report.get('physical_hardware_io',False) is False
    assert len(reports)==provenance['cpu_jobs']
    cases=sum(len(r['cases']) for r in reports.values())
    assert cases==provenance['cpu_cases']
    matcher=reports['cpu/find-match']
    assert matcher['module_sha256']==digest(inputs['target/native-desktop/fsview.prg'])
    assert matcher['cases'][0]['comparisons']==49822
    rebuilt=read('rebuild.json');assert rebuilt['passed'] and rebuilt['exit_code']==0
    assert len(rebuilt['images'])==36
    assert set(rebuilt['prior_outputs_removed'])==set(rebuilt['images'])
    for name,item in rebuilt['images'].items():
        assert item==dict(bytes=len(inputs[name]),sha256=digest(inputs[name]))
        for execution in executions.values():assert execution['inputs'][name]==item['sha256']
    apps={};modules={}
    for name in ('desktop','calc','editor','files','controls','claude','paint'):
        image=inputs['target/native-desktop/'+name+'.prg']
        _,apps[name]=fmt.packed_app(image)
    for name,app in (('fspick','files'),('fsview','files'),('fsopen','files'),
                     ('edpick','editor'),('edfind','editor'),('edclip','editor')):
        modules[name]=fmt.module(inputs['target/native-desktop/'+name+'.prg'],inputs['target/native-desktop/'+app+'.prg'])
    assert modules['fspick']['end']<=0xc000 and modules['fsview']['end']<=0xc000
    assert modules['fsopen']['bytes']==340
    deployment=json.loads(inputs['target/native-desktop/deployment.json'])
    disks={}
    for directory in ('target/native','target/native-desktop'):
        for stem in (('uos128',) if directory.endswith('/native') else ('uos128','workspace')):
            for kind in ('d64','d81'):
                entries=deployment['disk_entries'] if directory.endswith('native-desktop') else {
                    'u':'uos128-boot.prg','browse':'browse.prg','calc':'calc.prg','editor':'editor.prg',
                    'edpick.prg':'edpick.prg','edfind.prg':'edfind.prg'}
                expected={}
                for name,filename in entries.items():
                    origin=directory
                    if name=='u':
                        if stem=='workspace':origin='target/native'
                        if kind=='d81':origin+='/d81'
                    expected[name.upper().encode()]=(2,inputs[origin+'/'+filename])
                path=directory+'/'+stem+'.'+kind
                files,info=fmt.media(inputs[path],kind=='d81',inputs[directory+'/boot.prg'][2:])
                assert files==expected;disks[path]=info
    assert disks['target/native-desktop/uos128.d64']['free_blocks']==81
    assert disks['target/native-desktop/uos128.d81']['free_blocks']==2577
    folder_frames=folder_pixels=0
    for name,data in jobs.items():
        if '-captures/' not in name or not name.endswith('.json'):continue
        prefix=name[:-5];meta=json.loads(data)
        actual=jobs[prefix+'-actual.vic'];assert len(actual)==9216
        assert actual==jobs[prefix+'-expected.vic']
        folder_frames+=1;folder_pixels+=64000
        if meta['vdc_size']:
            bitmap,attr=fmt.mirror(actual,meta['vdc_size']==64)
            fmt.point(bitmap,2*meta['pointer_x'],meta['pointer_y'],meta['pointer_visible'])
            assert jobs[prefix+'-vdc.bin']==bitmap
            if meta['vdc_size']==64:assert jobs[prefix+'-attributes.bin']==attr
            folder_frames+=1;folder_pixels+=128000
        else:
            assert jobs[prefix+'-actual.console']==jobs[prefix+'-expected.console']
    assert folder_frames>0
    frames=pixels=captures=0
    for name in ('d64','d81'):
        prefix=name+'/';report=json.loads(outputs[prefix+'report.json'])
        assert report['passed'] and report['physical_hardware_io'] is False
        assert report['all_host_processes_terminal'] and report['xvfb_terminal']
        assert report['options']['files_only'] and report['options']['files_open_with'] and report['options']['files_find']
        found=report['filename_search']
        assert found['document']==b'DOC.TXT'.hex() and found['document_ordinal']>=8
        assert found['wrapped_to']==b'BROWSE'.hex() and found['wrapped_ordinal']<8 and found['missing_kept_selection']
        labels={frame['label'] for frame in report['files_frames']}
        assert {'files-find-dialog','files-find-query','files-found-document','files-find-wrapped',
                'files-find-missing','files-find-kept-selection'}<=labels
        assert report['options']['d81']==report['options']['vdc64']==(name=='d81')
        assert not report['options']['reu_kib'] and report['system_disk_files_preserved']
        for path,sha in report['images'].items():assert digest(inputs['target/native-desktop/'+path])==sha
        assert [(x['app'],x['name_hex'],x['button']) for x in report['open_with']]==[
            ('editor',b'DOC.TXT'.hex(),28),('paint',b'DRAW.UPNT'.hex(),29)]
        assert all(x['keyboard_events_during_click']==0 for x in report['open_with'])
        allframes=sum((report.get(key,[]) for key in ('files_frames','editor_frames','paint_frames','picker_frames','desktops')),[])
        for frame in allframes:
            label=prefix+frame['label'];surface=outputs[label+'-surface.bin'];assert len(surface)==9216
            assert fmt.canvas(outputs[label+'-canvas.bin'],fmt.vic_pixels(surface,*frame['position']))==frame['rectangle']
            frames+=1;pixels+=64000;vdc=frame['vdc']
            if frame in report['desktops']:
                bitmap,attr=fmt.scene(inputs['src/native/desktop/vdc-scene.inc'],frame['selected'])
            else:bitmap,attr=fmt.mirror(surface,vdc['color'])
            fmt.point(bitmap,*vdc['position'],vdc['pointer_visible'])
            assert outputs[label+'-vdc-bitmap.bin']==bitmap and digest(bitmap)==vdc['bitmap_sha256']
            if vdc['color']:assert outputs[label+'-vdc-attributes.bin']==attr
            assert fmt.canvas(outputs[label+'-vdc-canvas.bin'],fmt.vdc_pixels(bitmap,attr,vdc['color']))==vdc['rectangle']
            frames+=1;pixels+=128000
        assert outputs[prefix+'files-app-close-restored-vram.bin']==outputs[prefix+'files-app-close-snapshot.bin']
        heap=outputs[prefix+'final-page-table.bin'];records=outputs[prefix+'final-records.bin']
        assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251)
        assert all(records[i*8]==0 for i in range(32))
        source=inputs['target/native-desktop/uos128.'+name]
        expected,_=fmt.media(source,name=='d81',source[:256])
        text=b'Files opens this document.\r\nExact name and device.\r\n'
        assert outputs[prefix+'doc.txt']==text
        expected.update({b'DOC.TXT':(1,text),b'DRAW.UPNT':(1,outputs[prefix+'draw.upnt'])})
        files,_=fmt.media(outputs[prefix+'suite.'+name],name=='d81',source[:256]);assert files==expected
        files,_=fmt.media(outputs[prefix+'data-9.d64'],False)
        assert files=={b'FSCOPY':(2,inputs['target/native-desktop/edfind.prg'])}
        for capture in report['captures']:
            assert capture['restored'] and not capture['borrower_failures'] and capture['code']==1
            data=b''
            for chunk in capture['chunks']:
                status=outputs[prefix+chunk['status_file']];raw=outputs[prefix+chunk['payload_file']]
                assert digest(status)==chunk['status_sha256'] and status[0]==1
                assert digest(raw)==chunk['payload_sha256'] and len(raw)==chunk['payload_bytes']<=512
                data+=raw
            assert len(data)==capture['count'] and outputs[prefix+capture['label']+'.bin']==data
            for check in capture['borrower_checks'].values():
                assert outputs[prefix+check['before_file']]==outputs[prefix+check['after_file']]
            captures+=1
    return dict(passed=True,physical_hardware_io=False,cpu_jobs=len(reports),cpu_cases=cases,
                images=36,disks=disks,apps=apps,modules=modules,modal_canvases=folder_frames,
                modal_pixels=folder_pixels,vice_canvases=frames,vice_pixels=pixels,restored_cpu_captures=captures)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--unsealed',action='store_true')
    parser.add_argument('--report',type=Path);args=parser.parse_args();result=audit(args.unsealed)
    if args.report:args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
