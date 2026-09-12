#!/usr/bin/env python3
"""Offline byte, frame, module and saved-document audit; no hardware access."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sha=lambda data:hashlib.sha256(data).hexdigest()
read=lambda name:json.loads((ROOT/name).read_text())
from capture_audit import captures


def audit():
    source=ROOT/'inputs';manifest=read('frozen-inputs.json')
    assert set(manifest)=={str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
    for name,digest in manifest.items():assert sha((source/name).read_bytes())==digest,name
    base=read('base-inputs.json')
    assert (ROOT/'base-commit.txt').read_text().strip()=='e140f3aae5ce1ca304654549ba74191ccd61f82c'
    for name,digest in base.items():
        if name.endswith('.prg') and not name.endswith(('/editor.prg','/edpick.prg')):
            assert manifest[name]==digest,('unrelated program changed',name)
    provenance=read('provenance.json')
    assert not provenance['physical_hardware_io'] and not provenance['authenticated_claude_session']
    assert all(code==0 for code in provenance['qualified_sessions'].values())
    rebuild=read('main-rebuild.json');assert rebuild['passed'] and len(rebuild['images'])==21
    for name,digest in rebuild['images'].items():assert manifest[name]==digest
    sys.path.insert(0,str(source))
    from native_image import validate
    from native_module import validate as module
    from native_files_check import exact_d64_files
    from native_editor_check import editor_screen
    from hwlib import lst_symbol
    programs={}
    for prefix in ('native','native-desktop'):
        app=(source/'target'/prefix/'editor.prg').read_bytes()
        info=validate(app);assert info['pages']==79
        programs[prefix]={'editor':info}
        for name in ('edpick','edfind'):
            blob=(source/'target'/prefix/(name+'.prg')).read_bytes()
            programs[prefix][name]=module(blob,app)
        assert programs[prefix]['edfind']['bytes']<programs[prefix]['edpick']['bytes']
    for disk in ('target/native/uos128.d64','target/native-desktop/uos128.d64','target/native-desktop/workspace.d64'):
        files=exact_d64_files((source/disk).read_bytes())
        for name,file in ((b'EDITOR','editor'),(b'EDPICK.PRG','edpick'),(b'EDFIND.PRG','edfind')):
            assert files[name]==(2,(source/'target/native'/(file+'.prg')).read_bytes()),(disk,name)
    cpu={}
    for name in ('search','dialog','document','editor','editor_ultimate','editor_redraw','module_editor','desktop'):
        r=read('cpu/'+name+'.json');assert r['passed'],name
        cpu[name]=len(r.get('cases',{})) or r.get('checked_frames')
        for image,digest in r.get('images',{}).items():
            candidates=[n for n in manifest if n.endswith('/'+image)]
            assert any(manifest[n]==digest for n in candidates),(name,image)
    assert cpu['search']==15 and cpu['dialog']==11 and cpu['document']==7
    assert cpu['module_editor']==12 and cpu['desktop']==24
    assert sha((ROOT/'cpu/document.prg').read_bytes())==read('cpu/document.json')['document_sha256']

    folder=ROOT/'vice-search';r=read('vice-search/report.json')
    assert r['passed'] and r['native_checks_passed'] and r['all_host_processes_terminal']
    assert r['independent_export_matches'] and r['all_owned_memory_and_files_released']
    for name,info in r['build'].items():assert manifest['target/native/'+name]==info['sha256']
    search_capture=captures(folder,r);assert not search_capture['rejected']
    large=(folder/'large.seq').read_bytes();at=65534
    if large[at-1:at+1]==b'\r\n':at+=1
    expected=large[:at]+b'MATCH'+large[at:]
    assert len(large)==66053 and len(expected)==66058
    for name in ('saved-expected.seq','saved-c1541.seq'):assert (folder/name).read_bytes()==expected
    small=b'XBA X Q '
    assert (folder/'small-c1541.seq').read_bytes()==(folder/'small-expected.seq').read_bytes()==small
    for name in ('large','note'):
        assert (folder/(name+'.seq')).read_bytes()==(folder/(name+'-c1541.seq')).read_bytes()
    assert sha(expected)==r['saved_sha256']
    assert sha((folder/'initial.d81').read_bytes())==r['initial_disk_sha256']
    assert sha((folder/'documents.d81').read_bytes())==r['final_disk_sha256']
    assert (folder/'native.d64').read_bytes()==(source/'target/native/uos128.d64').read_bytes()
    # The picker snapshot observes every physical extent independently of the
    # saved file, then reconstructs the logical gap buffer.
    document=r['document_during_dialog'];physical=bytearray()
    for index,handle in enumerate(document['handles']):
        data=(folder/(document['label']+f'-chunk-{index:02}.bin')).read_bytes()
        assert len(data)==4096 and sha(data)==handle['sha256']
        physical.extend(data)
    assert {h['bank'] for h in document['handles']}=={0,1}
    assert bytes(physical[:document['gap']]+physical[document['gap_end']:])==expected
    assert document['bytes']==len(expected) and document['capacity']==len(physical)
    assert document['sha256']==sha(expected) and document['all_bytes_equal']
    raw=b'ABABA AbA abc ABC'
    bodies={name:raw for name in ('search-query-field','search-first-wrapped','search-overlap','search-wrap',
        'search-ignore-case-field','search-mixed-case-result','search-no-match','search-one-all-choice',
        'search-cancel-keeps-original')}
    bodies.update({'search-new':b'','search-next-without-query':b'',
        'search-all-nonoverlap':b'XBA X abc ABC','search-replace-one':b'XBA X Q ABC',
        'search-empty-replacement':small,'search-small-saved':small,'search-small-reopened':small,
        'search-large-open':large,'search-across-64k':large[:at]+b'FINDME'+large[at:],
        'search-replaced-across-64k':expected,'search-picker-return':expected,'search-large-saved':expected,
        'search-large-reopened':expected,'search-reopened-result':expected})
    base_address=lst_symbol('native/editor','ed_active')
    for state in r['editor_states']:
        label=state['label'];data=bodies[label]
        assert state['length']==len(data) and not state['fault']
        record=(folder/(label+'-app-state.bin')).read_bytes()
        def number(name,size=1):
            offset=lst_symbol('native/editor',name)-base_address
            return int.from_bytes(record[offset:offset+size],'little')
        for field,size in (('cursor',3),('view',3),('horizontal',3),('mode',1),('status',1)):
            assert number('ed_'+field,size)==state[field],(label,field)
        context=(folder/(label+'-document-state.bin')).read_bytes()
        assert int.from_bytes(context[:3],'little')==len(data) and context[12]==state['dirty'] and context[14]==0
        search=(folder/(label+'-search-state.bin')).read_bytes()
        assert search[0]==state['search_case'] and int.from_bytes(search[2:5],'little')==state['replacements']
        for index,(suffix,columns) in enumerate((('vic',40),('vdc',80))):
            frame=editor_screen(columns,data,state['cursor'],name=state['name'],dirty=bool(state['dirty']),
                device=state['device'],fmt=state['fmt'],view=state['view'],horizontal=state['horizontal'],
                mode=state['mode'],field=state['field'],status=state['status'],field_caret=state['field_caret'],
                field_view=state['field_views'][index],search_case=state['search_case'],replacements=state['replacements'])
            assert (folder/(label+'-'+suffix+'.bin')).read_bytes()==frame,(label,suffix)
    assert set(bodies)=={s['label'] for s in r['editor_states']}
    assert (folder/'function-keys-before.bin').read_bytes()==(folder/'function-keys-after.bin').read_bytes()
    assert r['function_key_bytes_restored']==256
    assert r['heap_observations'][-1]['free']==[175,251,32]

    folder=ROOT/'vice-suite';suite=read('vice-suite/report.json')
    assert suite['passed'] and suite['all_host_processes_terminal'] and not suite['physical_hardware_io']
    for name,digest in suite['images'].items():assert manifest['target/native-desktop/'+name]==digest
    assert sha((folder/'suite.d64').read_bytes())==suite['images']['uos128.d64']
    suite_capture=captures(folder,dict(suite,captures=suite['captures']+suite['mode_captures']))
    assert not suite_capture['rejected']
    from native_running_layout import RunningLayout
    from launcher_scene import surface,console
    running=RunningLayout(source,image_dir=source/'target/native-desktop')
    for prefix in ('resident-boot','resident-return'):
        observed={region:(folder/(prefix+'-'+region+'.bin')).read_bytes() for region in running.regions}
        assert running.compare(observed)['passed']
    for row in suite['desktops']:
        assert (folder/(row['label']+'-surface.bin')).read_bytes()==surface(row['selected'])
        assert (folder/(row['label']+'-vdc.bin')).read_bytes()==console(80,row['selected'])
    apps=suite['suite_apps'];assert apps['passed'] and len(apps['claude'])==2 and len(apps['ultimate'])==5
    for row in apps['claude']:
        assert row['passed'] and row['host_process_terminal'] and row['host_final_code']==0
        for name,size in (('font',4096),('nmi',2),('gate',2)):
            before=(folder/('claude-'+name+'-before.bin')).read_bytes()
            assert len(before)==size and before==(folder/(row['label']+'-'+name+'-after.bin')).read_bytes()
    heap=(folder/'final-native-heap.bin').read_bytes()
    assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251)
    assert all(heap[0x400+i*8]==0 for i in range(32))
    negative=read('preliminary/builtin-memory/report.json')
    assert not negative['passed']
    failed=negative['editor_states'][-1]
    assert failed['label']=='search-large-open' and failed['status']==3 and failed['length']==0
    return dict(passed=True,frozen_inputs=len(manifest),byte_identical_images=21,app_pages=79,
        programs=programs,cpu=cpu,vice_search=search_capture,vice_suite=suite_capture,
        checked_editor_frame_pairs=len(bodies),saved_bytes=len(expected),saved_sha256=sha(expected),
        document_extents=len(document['handles']),final_free_pages=426,physical_hardware_io=False,
        authenticated_claude_session=False)


if __name__=='__main__':
    if '--record' not in sys.argv:
        seal={}
        for line in (ROOT/'SHA256SUMS').read_text().splitlines():
            digest,name=line.split('  ',1)
            assert name not in seal and not Path(name).is_absolute() and '..' not in Path(name).parts
            assert sha((ROOT/name).read_bytes())==digest,name
            seal[name]=digest
        assert set(seal)=={str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p.name!='SHA256SUMS'}
    result=audit()
    if '--record' in sys.argv:(ROOT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    else:assert result==read('audit.json')
    print(json.dumps(result,indent=2))
