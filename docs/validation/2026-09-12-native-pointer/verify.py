#!/usr/bin/env python3
"""Offline pointer pixels, input/restoration records and native suite audit."""
import hashlib
import json
from pathlib import Path
import re
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
    assert (ROOT/'base-commit.txt').read_text().strip()=='5742c726b6ccdb7f962ef5d93209d30116674214'
    for name,digest in read('base-inputs.json').items():
        if name.endswith('.prg') and not name.endswith(('/desktop.prg','/claude.prg')):
            assert manifest[name]==digest,('unrelated app/kernel changed',name)
    rebuilt=read('main-rebuild.json');assert rebuilt['passed'] and len(rebuilt['images'])==21
    for name,digest in rebuilt['images'].items():assert manifest[name]==digest,name
    frozen=read('frozen-rebuild.json');assert frozen['passed'] and frozen['images']==rebuilt['images']
    provenance=read('provenance.json')
    assert not provenance['physical_hardware_io'] and not provenance['pushed']
    assert all(code==0 for code in provenance['qualified_sessions'].values())
    sys.path.insert(0,str(source))
    from native_image import validate
    from native_files_check import exact_d64_files
    from native_pointer_check import pixels,check_canvas
    from launcher_scene import surface,console
    from hwlib import lst_symbol
    from native_running_layout import RunningLayout
    desktop=validate((source/'target/native-desktop/desktop.prg').read_bytes())
    claude=validate((source/'target/native-desktop/claude.prg').read_bytes())
    assert desktop['pages']==23 and claude['pages']==51
    deployment=json.loads((source/'target/native-desktop/deployment.json').read_text())
    for name in ('uos128.d64','workspace.d64'):
        contents=exact_d64_files((source/'target/native-desktop'/name).read_bytes())
        for disk,program in deployment['disk_entries'].items():
            image=source/'target/native-desktop'/program
            if name=='workspace.d64' and disk=='u':image=source/'target/native/uos128.prg'
            assert contents[disk.upper().encode()]==(2,image.read_bytes()),(name,disk)
    cpu={}
    for label in ('cpu','desktop','claude'):
        row=read('cpu/'+label+'.json');assert row['passed']
        cpu[label]=len(row['cases'])
        if label=='cpu':
            for name,digest in row['images'].items():assert manifest[name]==digest
            assert row['cases'][0]['counter_pairs']==16384
        elif label=='desktop':
            for name,digest in row['images'].items():assert manifest['target/native-desktop/'+name]==digest
        else:assert row['claude_sha256']==manifest['target/native-desktop/claude.prg']
    assert cpu==dict(cpu=12,desktop=24,claude=11)
    running=RunningLayout(source,image_dir=source/'target/native-desktop')
    def resident(folder):
        for prefix in ('resident-boot','resident-return'):
            data={name:(folder/(prefix+'-'+name+'.bin')).read_bytes() for name in running.regions}
            assert running.compare(data)['passed']
    vice={};frames=0
    for label,eighty in (('vice40',False),('vice80',True)):
        folder=ROOT/label;report=read(label+'/report.json')
        assert report['passed'] and report['all_host_processes_terminal'] and report['system_disk_unchanged']
        assert not report['physical_hardware_io'] and report['options']['eighty']==eighty
        assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_pointer_iec.py').read_bytes()
        for name,digest in report['images'].items():assert manifest['target/native-desktop/'+name]==digest,name
        result=captures(folder,dict(report,captures=report['captures']+report['mode_captures']))
        assert not result['rejected'];vice[label]=result
        assert len(report['desktops'])==15
        for row in report['desktops']:
            name=row['label'];selected=row['selected'];x,y=row['position'];assert 0<=x<320 and 0<=y<200
            assert (folder/(name+'-surface.bin')).read_bytes()==surface(selected)
            assert (folder/(name+'-vdc.bin')).read_bytes()==console(80,selected)
            assert check_canvas((folder/(name+'-canvas.bin')).read_bytes(),pixels(selected,x,y))==row['rectangle']
            state=(folder/(name+'-state.bin')).read_bytes()
            start=lst_symbol('native-desktop/desktop','pm_active')
            def field(symbol,size=1):
                at=lst_symbol('native-desktop/desktop',symbol)-start;return state[at:at+size]
            assert field('pm_active')==field('pm_seen')==b'\1'
            assert int.from_bytes(field('pm_x',2),'little')==x and field('pm_y')[0]==y
            assert row['mode']['vic_sprites']==3 and not row['mode']['cpu_speed']&1
            frames+=1
        keys=(folder/'keys-before.bin').read_bytes();assert len(keys)==256
        for name in ('calc','editor','files','controls','claude'):
            assert (folder/(name+'-keys-restored.bin')).read_bytes()==keys
        apps=[row['mouse_app'] for row in report['events'] if 'mouse_app' in row]
        assert apps==['calc','editor','files','controls','claude']
        assert all(row['keyboard_events_during_click']==0 for row in report['events'] if 'mouse_app' in row)
        table=(folder/'final-page-table.bin').read_bytes();records=(folder/'final-records.bin').read_bytes()
        assert len(table)==512 and len(records)==256
        assert table[0x50:0xff]==bytes(175) and table[0x104:0x1ff]==bytes(251)
        assert all(records[i*8]==0 for i in range(32))
        assert report['final_mode']['vic_sprites']==0 and report['final_mode']['text_graphics']==0
        assert (folder/'suite.d64').read_bytes()==(source/'target/native-desktop/uos128.d64').read_bytes()
        resident(folder)
    folder=ROOT/'serial';serial=read('serial/report.json')
    assert serial['passed'] and serial['host_exit_code']==0 and serial['close_outcome']==2
    assert not serial['physical_hardware_io']
    for name,digest in serial['images'].items():assert manifest['target/native-desktop/'+name]==digest,name
    assert (folder/'run.py').read_bytes()==(source/'tests/ci_native_claude_iec.py').read_bytes()
    serial_observation=captures(folder,dict(captures=serial['cpu_captures'],paused_capture_batches=serial['cpu_capture_batches']))
    assert not serial_observation['rejected']
    assert (folder/'font-before.bin').read_bytes()==(folder/'font-after.bin').read_bytes()
    assert (folder/'nmi-before.bin').read_bytes()==(folder/'nmi-after.bin').read_bytes()
    assert (folder/'close-outcome.bin').read_bytes()==b'\2'
    checkpoint=(folder/'close-checkpoint.bin').read_bytes()
    assert checkpoint.hex()==serial['close_observation']['checkpoint_hex']
    labels={m[2]:int(m[1],16) for m in re.finditer(r'^al ([0-9A-Fa-f]+) \.(\S+)',(source/'target/native-desktop/claude.lbl').read_text(),re.M)}
    assert int.from_bytes(checkpoint[5:7],'little')==int.from_bytes(checkpoint[7:9],'little')==labels['_native_video_end']
    assert int.from_bytes(checkpoint[13:17],'little')==1
    assert serial['close_observation']['address']==labels['_closeOutcome']
    assert serial['serial_counters']['_rxDropped']==serial['serial_counters']['_rxOverruns']==0
    assert (folder/'boot-desktop-surface.bin').read_bytes()==surface(0)
    assert (folder/'returned-desktop-surface.bin').read_bytes()==surface(4)
    for label,selected in (('boot-desktop',0),('returned-desktop',4)):
        assert (folder/(label+'-vdc.bin')).read_bytes()==console(80,selected)
    table=(folder/'final-heap.bin').read_bytes()
    assert table[0x50:0xff]==bytes(175) and table[0x104:0x1ff]==bytes(251)
    negative=read('preliminary/delayed-scan/early-read-negative.json')
    assert negative['negative_control_failed_as_expected'] and negative['old_driver_early_pot_reads']==2
    assert negative['elapsed_lines_since_noticed_irq']==0
    assert not read('preliminary/basic-sprite-hook/report.json')['passed']
    macro=read('preliminary/claude-f8-macro/report.json')
    assert not macro['passed'] and 'F8 reaches desktop' in macro['error']
    return dict(passed=True,frozen_inputs=len(manifest),byte_identical_images=21,desktop=desktop,claude=claude,
        cpu=cpu,counter_pairs=16384,pointer_input_frames=sum(row['frames'] for row in read('cpu/cpu.json')['cases']),
        vice=vice,complete_desktop_frame_pairs=frames,rendered_pixels=frames*64000,
        serial=serial_observation,serial_received_bytes=serial['serial_counters']['_rxCount'],
        final_free_pages=426,physical_hardware_io=False)


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
