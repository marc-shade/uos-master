#!/usr/bin/env python3
"""Rebuild the production desktop paths from the retained input closure."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ARCHIVE = Path(__file__).resolve().parent
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def materialize(clean):
    context = read(ARCHIVE/'candidate-context.json')
    manifest = read(ARCHIVE/'input-manifest.json')
    assert len(manifest) == context['frozen_inputs'] == 335
    assert sha(ARCHIVE/'input-manifest.json') == context['input_manifest_sha256']
    for name, digest in manifest.items():
        source = ARCHIVE/'inputs'/name
        assert sha(source) == digest, name
        target = clean/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for name, digest in read(ARCHIVE/'source-overlays.json').items():
        assert manifest[name] == digest, name
    return context


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='uos-desktop-production-rebuild-') as temporary:
        clean = Path(temporary)
        context = materialize(clean)
        assert not any((clean/name).exists() for name in ('graphics', 'client', 'launcher'))
        manifest = read(ARCHIVE/'input-manifest.json')
        before = {name: digest for name, digest in manifest.items()
                  if name.startswith('target/') and name.endswith(('.prg', '.d64'))}
        for builder in ('build-native-desktop.py', 'build-native-graphics.py'):
            subprocess.run([sys.executable, '-B', str(clean/builder)], cwd=clean,
                           check=True, capture_output=True)
        for name, digest in before.items():
            assert sha(clean/name) == digest, name
        for folder in ('native', 'native-desktop'):
            for name in ('images.json', 'layout.json'):
                assert (clean/'target'/folder/name).read_bytes() == (ARCHIVE/'inputs/target'/folder/name).read_bytes()
        assert (clean/'target/native-desktop/deployment.json').read_bytes() == (ARCHIVE/'inputs/target/native-desktop/deployment.json').read_bytes()
        desktop = clean/'target/native-desktop'
        members = {'u':'uos128.prg', 'browse':'desktop.prg', 'files':'files.prg',
                   'calc':'calc.prg', 'editor':'editor.prg', 'edpick.prg':'edpick.prg'}
        for disk_name in ('uos128.d64', 'workspace.d64'):
            disk = desktop/disk_name
            assert disk.read_bytes()[:256] == (desktop/'boot.prg').read_bytes()[2:]
            for name, original in members.items():
                reference = clean/'target/native/uos128.prg' if name == 'u' and disk_name == 'workspace.d64' else desktop/original
                output = clean/'extracted.prg'
                subprocess.run(['c1541', '-attach', str(disk), '-read', name, str(output)], check=True, capture_output=True)
                assert output.read_bytes() == reference.read_bytes()
        assert sha(desktop/'uos128.prg') == context['boot_kernel_sha256']
        assert sha(desktop/'uos128.d64') == context['disk_sha256']
        assert sha(clean/'target/native/uos128.prg') == context['kernel_sha256']
        for name, field in [('desktop', 'desktop_sha256'), ('files', 'files_sha256')]:
            assert sha(desktop/(name+'.prg')) == context[field]
        for kind, kernel in [('workspace', 'kernel_sha256'), ('desktop', 'boot_kernel_sha256')]:
            report = read(ARCHIVE/'cpu'/('cpu-'+kind+'.json'))
            assert report['passed'] and not report['hardware_io'] and len(report['cases']) == 9
            assert report['images']['uos128.prg'] == context[kernel]
            for name in ('desktop', 'files'):
                assert report['images'][name+'.prg'] == context[name+'_sha256']
        cases = interrupts = 0
        for name in ('report.json', 'glyph-report.json', 'text-report.json', 'clip-report.json'):
            report = read(ARCHIVE/'cpu'/('graphics-'+name))
            assert report['passed'] and not report['hardware_io']
            assert report['kernel_sha256'] == context['kernel_sha256']
            assert report['library_sha256'] == context['graphics_sha256'] == sha(clean/'target/native-graphics/graphics.prg')
            assert report['library_bytes'] == 2685
            cases += len(report['cases']); interrupts += report['interrupts']
        assert cases == context['graphics_cpu_cases'] == 1243
        assert interrupts == context['modeled_graphics_interrupts'] == 22943
        calc = read(ARCHIVE/'cpu/default-calculator.json')
        assert calc['passed'] and calc['kernel_sha256'] == context['kernel_sha256']
        assert calc['calc_sha256'] == sha(clean/'target/native/calc.prg')
        assert calc['exit_releases_all'] and calc['saved_history_verified']
        subprocess.run([sys.executable, '-B', str(clean/'tests/ci_native_running_layout.py'),
                        '--desktop-boot', '--report', str(clean/'controls.json'), '--observed',
                        str(ARCHIVE/'emulator/shared-sequence')], check=True, capture_output=True)
        assert read(clean/'controls.json') == read(ARCHIVE/'cpu/desktop-layout-controls.json')
        result = dict(passed=True, frozen_inputs=335, unchanged_images=len(before),
                      extracted_disk_members=12, exact_boot_sectors=2,
                      cpu_desktop_workflows=18, graphics_cases=cases, modeled_graphics_interrupts=interrupts,
                      default_calculator_passed=True, running_layout_controls=9,
                      prototype_directories_required=False)
    if args.record:
        (ARCHIVE/'package-verification.json').write_text(json.dumps(result, indent=2)+'\n')
    else:
        assert result == read(ARCHIVE/'package-verification.json')
    print('PASS: clean production rebuild; exact packaged images; 18 desktop CPU workflows and 1,243 graphics cases')


if __name__ == '__main__':
    main()
