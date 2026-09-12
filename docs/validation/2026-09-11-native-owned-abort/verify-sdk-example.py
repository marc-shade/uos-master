#!/usr/bin/env python3
"""Rebuild and execute the saved SDK example privately; no hardware I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ARCHIVE = Path(__file__).resolve().parent
SDK = ARCHIVE / 'sdk-example'
sys.dont_write_bytecode = True


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    sources = read(SDK / 'source/SHA256.json')
    assert len(sources) == 6
    for name, expected in sources.items():
        assert digest(SDK / 'source' / name) == expected, name
    report = read(SDK / 'cpu-report.json')
    assert report['passed'] and not report['hardware_io']
    assert report['kernel_sha256'] == read(ARCHIVE / 'images.json')['uos128.prg']['sha256']
    expected_cases = {f'source-{fmt}-context-{context}' for fmt, context in
                      ((0, 1), (1, 1), (2, 1), (3, 1), (3, 2))}
    expected_cases |= {f'{kind}-source-{fmt}' for kind in ('missing', 'checksum', 'parent', 'short')
                       for fmt in (0, 3)}
    expected_cases |= {'stale-call-token', 'ultimate-retained-close'}
    assert set(report['cases']) == expected_cases and len(expected_cases) == 15
    build = read(SDK / 'build/build.json')
    assert report['build'] == build
    assert build['parent']['pages'] == 4 and build['parent']['window'] == 0x6300
    assert build['module']['origin'] == 0x6300 and build['module']['bytes'] == 29
    assert build['module']['parent_crc16'] == build['parent']['crc16']
    for name, record in build['images'].items():
        path = SDK / 'build' / name
        assert path.stat().st_size == record['bytes'] and digest(path) == record['sha256']
    with tempfile.TemporaryDirectory(prefix='uos-sdk-archive-') as scratch:
        clean = Path(scratch)
        shutil.copytree(ARCHIVE / 'package/clean', clean, dirs_exist_ok=True)
        harness = read(ARCHIVE / 'harness/SHA256.json')
        for name, expected in harness.items():
            path = ARCHIVE / 'harness' / name
            assert digest(path) == expected, name
            destination = clean / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        for name in sources:
            destination = clean / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SDK / 'source' / name, destination)
        rebuilt = clean / 'example-output'
        result = subprocess.run([
            sys.executable, '-B', str(clean / 'tests/ci_native_sdk_module.py'),
            '--output', str(rebuilt), '--report', str(clean / 'sdk-report.json'),
        ], cwd=clean, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert read(clean / 'sdk-report.json') == report
        for name in build['images']:
            assert (rebuilt / name).read_bytes() == (SDK / 'build' / name).read_bytes()
        assert digest(clean / 'target/native/uos128.prg') == report['kernel_sha256']
    summary = dict(passed=True, hardware_io=False, sources=6, workflows=15,
                   reproducible_prgs=2, kernel_sha256=report['kernel_sha256'],
                   included_in_24_suite_run=True)
    path = ARCHIVE / 'sdk-example-verification.json'
    if args.record:
        path.write_text(json.dumps(summary, indent=2) + '\n')
    else:
        assert read(path) == summary
    print('PASS: SDK example rebuilt from six archived sources; both PRGs and all 15 CPU workflows reproduced')


if __name__ == '__main__':
    main()
