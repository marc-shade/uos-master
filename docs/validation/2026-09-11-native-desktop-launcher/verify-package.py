#!/usr/bin/env python3
"""Rebuild the private desktop images and audit retained CPU evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode=True
ARCHIVE=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def materialize(clean):
    context=read(ARCHIVE/'candidate-context.json')
    base=ARCHIVE.parent/context['base_archive'];clip=ARCHIVE.parent/context['clipping_archive']
    assert sha(base/'SHA256SUMS')==context['base_manifest_sha256']
    assert sha(clip/'SHA256SUMS')==context['clipping_manifest_sha256']
    for directory,manifest in [(base/'frozen',read(base/'frozen.json')),
                               (clip/'source',read(clip/'candidate-context.json')['source_inputs']),
                               (ARCHIVE/'source',context['source_inputs'])]:
        for name,digest in manifest.items():
            source=directory/name;assert sha(source)==digest,name
            target=clean/name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
    return context


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--record',action='store_true');args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='uos-desktop-archive-rebuild-') as temporary:
        clean=Path(temporary);context=materialize(clean)
        assert not context['main_integrated'] and not context['physical_hardware_io']
        before={name:sha(clean/name) for name in ['target/native/'+n for n in (
            'uos128.prg','calc.prg','browse.prg','editor.prg','edpick.prg','uos128.d64',
            'desktop.prg','files.prg')]+['launcher/'+n for n in (
            'desktop.d64','desktop-boot.d64','boot/uos128.prg','expected-0.bin','expected-1.bin','expected-2.bin')]}
        for script in ('build-native.py','build-launcher.py'):
            subprocess.run([sys.executable,'-B',str(clean/script)],cwd=clean,check=True,capture_output=True)
        for name,digest in before.items():assert sha(clean/name)==digest,('rebuild mismatch',name)
        sys.path.insert(0,str(clean))
        from native_image import validate
        desktop=validate((clean/'target/native/desktop.prg').read_bytes())
        files=validate((clean/'target/native/files.prg').read_bytes())
        assert desktop['pages']==18 and desktop['bytes']==4477
        assert files['pages']==28 and files['bytes']==7129
        build=read(clean/'launcher/build.json')
        assert build==read(ARCHIVE/'source/launcher/build.json')
        assert build['boot_layout']==dict(main_end=0x37f8,low_end=0x1bf0,service_end=0x4ff9,load_end=0x5900)
        assert read(clean/'target/native/layout.json')['main_end']==0x37f6
        assert build['surface_pages']==36
        kernel=context['kernel_sha256'];boot=context['boot_kernel_sha256']
        assert before['target/native/uos128.prg']==kernel and before['launcher/boot/uos128.prg']==boot
        reports={}
        for name,path,digest in [('workspace','launcher/cpu-report.json',kernel),('boot','launcher/boot-reports/desktop.json',boot)]:
            report=read(clean/path)
            assert report['passed'] and not report['hardware_io'] and len(report['cases'])==9
            assert report['images']=={'uos128.prg':digest,'desktop.prg':context['desktop_sha256'],'files.prg':context['files_sha256']}
            reports[name]=report['cases']
        assert [r['name'] for r in reports['workspace']]==[r['name'] for r in reports['boot']]
        suites={}
        for name,count in [('relocation',9),('apps',53),('display',27),('modules',113),('heap',None)]:
            report=read(clean/f'launcher/boot-reports/{name}.json')
            assert report['passed'] and report.get('kernel_sha256',report.get('image_sha256'))==boot
            if count is not None:assert len(report['cases'])==count
            else:assert report['managed_pages']==426 and report['bank_boundary_transfers']==50
            suites[name]=count
        first=read(clean/'launcher/first-cpu-attempt/report.json')
        assert not first['passed'] and len(first['cases'])==6
        assert 'self.m.invoke' not in (clean/'tests/ci_native_desktop.py').read_text()
        result=dict(passed=True,main_integrated=False,physical_hardware_io=False,
                    new_frozen_inputs=len(context['source_inputs']),desktop=desktop,files=files,
                    default_kernel_sha256=kernel,boot_kernel_sha256=boot,boot_layout=build['boot_layout'],
                    distinct_launcher_cpu_workflows=9,launcher_cpu_executions=18,additional_boot_cpu_suites=suites,
                    all_default_images_unchanged=True,all_private_images_rebuilt=True,desktop_free_pages=426-18-36,
                    initial_cpu_harness_failure_retained=True)
    if args.record:(ARCHIVE/'package-report.json').write_text(json.dumps(result,indent=2)+'\n')
    else:assert result==read(ARCHIVE/'package-report.json')
    print('PASS: rebuilt default/private images; nine desktop workflows on both kernels; five boot CPU suites; 372 free desktop pages')


if __name__=='__main__':main()
