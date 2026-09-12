#!/usr/bin/env python3
"""Rebuild the exact desktop hardware candidate in a disposable directory."""
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
    assert sha(ARCHIVE/'input-manifest.json') == context['input_manifest_sha256']
    assert len(manifest) == context['frozen_inputs'] == 385
    parent = ARCHIVE.parent.parent/context['launcher_archive']
    assert sha(parent/'SHA256SUMS') == context['launcher_manifest_sha256']
    previous = read(parent/'candidate-context.json')
    for field in ('desktop_sha256', 'files_sha256'):
        assert context[field] == previous[field]
    assert context['kernel_sha256'] == previous['boot_kernel_sha256']
    assert context['disk_sha256'] == sha(parent/'source/launcher/desktop-boot.d64')
    for name, digest in manifest.items():
        source = ARCHIVE/'inputs'/name
        assert sha(source) == digest, name
        target = clean/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return context, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='uos-desktop-hardware-rebuild-') as temporary:
        clean = Path(temporary)
        context, manifest = materialize(clean)
        before = {name: digest for name, digest in manifest.items()
                  if name.startswith('target/') and name.endswith(('.prg', '.d64'))}
        subprocess.run([sys.executable, '-B', str(clean/'build-desktop-hardware.py')],
                       cwd=clean, check=True, capture_output=True)
        for name, digest in before.items():
            assert sha(clean/name) == digest, name
        assert len(before) == 27
        for name in ('layout.json', 'images.json'):
            assert (clean/'target/native'/name).read_bytes() == (ARCHIVE/'inputs/target/native'/name).read_bytes()
        disk = clean/'target/native/uos128.d64'
        files = {'u': 'uos128', 'browse': 'desktop', 'files': 'files',
                 'calc': 'calc', 'editor': 'editor', 'edpick.prg': 'edpick'}
        for filename, original in files.items():
            target = clean/'extracted.prg'
            subprocess.run(['c1541', '-attach', str(disk), '-read', filename, str(target)],
                           check=True, capture_output=True)
            assert target.read_bytes() == (clean/f'target/native/{original}.prg').read_bytes()
        assert disk.read_bytes()[:256] == (clean/'target/native/boot.prg').read_bytes()[2:]
        subprocess.run([sys.executable, '-B', str(clean/'tests/ci_native_running_layout.py'),
                        '--report', str(clean/'controls.json'), '--observed',
                        str(ARCHIVE.parent/'emulator/running-layout')], check=True, capture_output=True)
        controls = read(clean/'controls.json')
        assert controls == read(ARCHIVE/'inputs/launcher/running-layout-negative-controls.json')
        result = dict(passed=True, physical_hardware_io=False, frozen_inputs=len(manifest),
                      exact_images=len(before), extracted_files=len(files), boot_sector_exact=True,
                      kernel_sha256=context['kernel_sha256'], disk_sha256=context['disk_sha256'],
                      running_layout_controls=len(controls['cases']), matching_full_boot_layout=True)
    if args.record:
        (ARCHIVE/'input-verification.json').write_text(json.dumps(result, indent=2)+'\n')
    else:
        assert result == read(ARCHIVE/'input-verification.json')
    print('PASS: 385 frozen inputs; exact desktop disk rebuild; 27 unchanged images; nine layout controls')


if __name__ == '__main__':
    main()
