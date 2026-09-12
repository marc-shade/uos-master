#!/usr/bin/env python3
"""Independently compare retained desktop pixels, consoles and boot disks."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.dont_write_bytecode=True
ARCHIVE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('package',ARCHIVE/'verify-package.py')
package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
read=package.read;sha=package.sha
parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='uos-desktop-evidence-') as temporary:
    clean=Path(temporary);context=package.materialize(clean)
    sys.path[:0]=[str(clean),str(clean/'tests')]
    from launcher_scene import surface,console
    from native_capture import expected_screen,calculator_screen
    from native_editor_check import editor_screen
    from native_browser_check import browser_screen,disk_records
    totals=dict(workflows=0,events=0,complete_surfaces=0,pixels=0,desktop_vdc_frames=0,
                fallback_vic_frames=0,text_screen_pairs=0,observations=0)
    runs={}
    for name in context['emulator_runs']:
        work=ARCHIVE/'emulator'/name;report=read(work/'report.json');options=report['options']
        assert report['passed'] and not report['physical_hardware_io'] and 'error' not in report
        boot=options.get('desktop_boot',False);missing=options.get('missing_calc',False)
        absent=options.get('missing_desktop',False)
        kernel=context['boot_kernel_sha256'] if boot else context['kernel_sha256']
        if 'kernel_sha256' in report:assert report['kernel_sha256']==kernel
        disk=work/'desktop.d64';assert sha(disk)==report['disk_sha256']
        records=disk_records(disk.read_bytes());names={row['name'] for row in records}
        assert (b'CALC' not in names)==missing and (b'BROWSE' not in names)==absent
        assert disk.read_bytes()[:256]==(clean/'target/native/boot.prg').read_bytes()[2:]
        images={'u':clean/('target/native-desktop/uos128.prg' if boot else 'target/native/uos128.prg'),
                'files':clean/'target/native-desktop/files.prg','editor':clean/'target/native-desktop/editor.prg',
                'edpick.prg':clean/'target/native-desktop/edpick.prg'}
        if not missing:images['calc']=clean/'target/native-desktop/calc.prg'
        if not absent:images['browse']=clean/'target/native-desktop/desktop.prg'
        for filename,original in images.items():
            extracted=clean/'extracted.prg'
            subprocess.run(['c1541','-attach',str(disk),'-read',filename,str(extracted)],check=True,capture_output=True)
            assert extracted.read_bytes()==original.read_bytes(),(name,filename)
        assert sha(work/'desktop.prg')==context['desktop_sha256']
        assert sha(work/'files.prg')==context['files_sha256']
        observations={row['label']:row for row in report['observations']}
        for row in report['observations']:
            for key,value in row.items():
                if key!='label':assert (work/f"{row['label']}-{key}.bin").read_bytes()==bytes.fromhex(value)
        final=observations['final'];assert final['display_tag']=='00' and final['port']=='2f73'
        heap=bytes.fromhex(final['heap'])
        assert heap[0x50:0xff]==bytes(175) and heap[0x104:0x1ff]==bytes(251)
        assert all(heap[0x400+index*8]==0 for index in range(32))
        assert bytes.fromhex(final['app'])[0]==bytes.fromhex(final['app'])[3]==0
        desktop_count=pixels=0
        for row in report['desktops']:
            label=row['label'];selected=row['selected'];error=row['error'];fallback=row['fallback']
            assert (work/f'{label}-80.bin').read_bytes()==console(80,selected,error,fallback)
            totals['desktop_vdc_frames']+=1
            obs=observations[label];heap=bytes.fromhex(obs['heap'])
            records_heap=[(index+1,heap[0x400+index*8:0x408+index*8]) for index in range(32) if heap[0x400+index*8]]
            assert len(records_heap)==2
            assert any(r[0]==32 and r[1:4]==bytes([0,0x60,18]) for slot,r in records_heap)
            if fallback:
                assert (work/f'{label}-40.bin').read_bytes()==console(40,selected,error,True)
                assert obs['display_tag']=='00' and obs['port']=='2f73'
                assert any(r[0]==16 and r[1:4]==bytes([0,0xdf,32]) for slot,r in records_heap)
                totals['fallback_vic_frames']+=1
                continue
            assert obs['display_tag']!='00' and obs['port']=='2f75'
            assert any(r[0]==32 and r[1:4]==bytes([0,0xc0,36]) and slot==int(obs['display_tag'],16) for slot,r in records_heap)
            assert heap[0x50:0xff].count(0)+heap[0x104:0x1ff].count(0)==372
            expected=surface(selected,error)
            assert (work/f'{label}-surface.bin').read_bytes()==expected
            raw=(work/f'{label}-display-get.bin').read_bytes()
            fields,=struct.unpack_from('<I',raw)
            width,height,xoff,yoff,innerw,innerh,bpp=struct.unpack_from('<6HB',raw,4)
            length,=struct.unpack_from('<I',raw,4+fields);actual=raw[8+fields:]
            assert fields>=13 and bpp==8 and length==width*height
            assert length-len(actual)==row['missing_canvas_tail_bytes'] and row['missing_canvas_tail_bytes'] in (0,4)
            x0,y0,w,h=row['rectangle'];assert w==320 and h==200
            assert 0<=x0<=width-w and 0<=y0<=height-h
            expected_pixels=bytearray()
            for y in range(200):
                for x in range(320):
                    color=expected[8192+y//8*40+x//8]
                    ink=expected[y//8*320+x//8*8+y%8]&(128>>(x%8))
                    expected_pixels.append(color>>4 if ink else color&15)
            actual_pixels=b''.join(actual[(y0+y)*width+x0:(y0+y)*width+x0+320] for y in range(200))
            assert actual_pixels==expected_pixels and row['pixels']==64000 and row['bytes']==9216
            desktop_count+=1;pixels+=64000
        for label in report['screens']:
            for columns in (40,80):
                if label in ('workspace-boot','workspace-returned','workspace-all-free','fallback-calculator-return'):
                    expected=expected_screen(columns,0)
                elif label=='missing-desktop-workspace':expected=expected_screen(columns,0,result=0x11)
                elif label=='workspace-owner-retained':
                    heap=bytes.fromhex(observations['occupied-surface-fallback']['heap'])
                    records_heap=[(i+1,heap[0x400+i*8:0x408+i*8]) for i in range(32)]
                    slot,r=next((slot,r) for slot,r in records_heap if r[0]==16)
                    expected=expected_screen(columns,0,(143,251),31,bytes([slot])+r[4:7])
                elif label in ('calculator-new','fallback-calculator'):expected=calculator_screen(columns,'0',[])
                elif label=='calculator-result':expected=calculator_screen(columns,'42',['42'])
                elif label=='editor-new':expected=editor_screen(columns,b'',0)
                elif label in ('editor-typed','editor-kept','editor-discard-prompt'):
                    expected=editor_screen(columns,b'Native desktop',14,dirty=True,mode=5 if label=='editor-discard-prompt' else 0)
                elif label in ('files','files-after-missing'):expected=browser_screen(columns,records)
                else:raise AssertionError(('unrecognized screen',label))
                assert (work/f'{label}-{columns}.bin').read_bytes()==expected,(name,label,columns)
        totals['workflows']+=1;totals['events']+=len(report['events'])
        totals['complete_surfaces']+=desktop_count;totals['pixels']+=pixels
        totals['text_screen_pairs']+=len(report['screens']);totals['observations']+=len(report['observations'])
        runs[name]=dict(kernel_sha256=kernel,complete_graphics_frames=desktop_count,text_pairs=len(report['screens']),events=len(report['events']))
    assert totals['workflows'] == 5 and totals['complete_surfaces'] == 33 and totals['pixels'] == 2112000
    assert all(not read(ARCHIVE/'emulator'/name/'report.json').get('error') for name in context['emulator_runs'])
    result=dict(passed=True,physical_hardware_io=False,totals=totals,runs=runs,
                all_boot_app_files_match=True,full_final_heap_cleanup=True)
if args.record:(ARCHIVE/'emulator-verification.json').write_text(json.dumps(result,indent=2)+'\n')
else:assert result==read(ARCHIVE/'emulator-verification.json')
print('PASS: five production emulator workflows; 33 complete surfaces and 2,112,000 pixels; boot files and final cleanup')
