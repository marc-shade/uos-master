#!/usr/bin/env python3
"""Audit the sealed lifecycle evidence without emulator or hardware access."""
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
sha = lambda data: hashlib.sha256(data).hexdigest()
manifest = {}
for line in (root/'SHA256SUMS').read_text().splitlines():
    digest, name = line.split('  ', 1)
    assert name not in manifest and not Path(name).is_absolute() and '..' not in Path(name).parts
    manifest[name] = digest
    assert sha((root/name).read_bytes()) == digest, name
assert set(manifest) == {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}

source = root/'inputs'
sys.path[:0] = [str(source), str(source/'apps/claude/host')]
from launcher_scene import surface, console
from native_image import validate
import petscii
import font

for name, digest in json.loads((root/'inputs.json').read_text()).items():
    assert sha((source/name).read_bytes()) == digest, name
clean = json.loads((root/'clean-rebuild.json').read_text())
assert clean['passed'] and clean['initially_empty_target'] and len(clean['images']) == 19
for name, info in clean['images'].items():
    data = (source/name).read_bytes()
    assert len(data) == info['bytes'] and sha(data) == info['sha256'], name
info = validate((source/'target/native-desktop/claude.prg').read_bytes())
assert info['pages'] == 50 and info['bytes'] == 4862
cpu = json.loads((root/'cpu.json').read_text())
host = json.loads((root/'host.json').read_text())
desktop = json.loads((root/'desktop.json').read_text())
startup = json.loads((root/'startup.json').read_text())
assert cpu['passed'] and len(cpu['cases']) == 11
assert cpu['claude_sha256'] == sha((source/'target/native-desktop/claude.prg').read_bytes())
assert host['passed'] and len(host['cases']) == 9
assert desktop['passed'] and len(desktop['cases']) == 24
assert startup['passed'] and len(startup['cases']) == 4
render = (root/'render.log').read_text()
assert '30/30 passed' in render and 'SKIP' not in render and 'FAIL' not in render and 'ERROR' not in render
extractions = json.loads((root/'extraction.json').read_text())
assert len(extractions) == 4 and all(row['matches'] for row in extractions)
for row in extractions:
    data = (root/row['file']).read_bytes()
    assert sha(data) == row['sha256'] and data == (source/row['source']).read_bytes()

expected = bytearray(b' '*2000)
for row, text in enumerate(['UOS CLAUDE LINK READY', '❯ ✳ ⏺', 'Keyboard, glyphs and return test',
                            'KEY RECEIVED: p', 'ESCAPE RECEIVED']):
    codes = bytes(petscii.to_screen_code(char) for char in text)
    expected[row*80:row*80+len(codes)] = codes

captured_chunks = 0
for dirname, outcome in (('vice-f8', 2), ('vice-host-exit', 0)):
    folder = root/dirname
    report = json.loads((folder/'report.json').read_text())
    assert report['passed'] and not report['physical_hardware_io'] and report['host_exit_code'] == 0
    assert report['close_outcome'] == outcome and (folder/'close-outcome.bin').read_bytes() == bytes([outcome])
    for name, digest in report['images'].items():
        assert sha((source/'target/native-desktop'/name).read_bytes()) == digest
    for label, selected in (('boot-desktop', 0), ('returned-desktop', 4)):
        assert (folder/(label+'-surface.bin')).read_bytes() == surface(selected)
        assert (folder/(label+'-vdc.bin')).read_bytes() == console(80, selected)
    assert (folder/'session-vdc.bin').read_bytes() == expected
    before = (folder/'font-before.bin').read_bytes()
    assert len(before) == 4096 and (folder/'font-after.bin').read_bytes() == before
    during = (folder/'font-during.bin').read_bytes()
    for code, bitmap in font.definitions():
        assert during[16*code:16*code+16] == bytes(bitmap)+bytes(8)
    nmi = (folder/'nmi-before.bin').read_bytes()
    assert len(nmi) == 4 and (folder/'nmi-after.bin').read_bytes() == nmi
    counters = report['serial_counters']
    assert counters['_rxCount'] >= 3+10*len(list(font.definitions()))
    assert counters['_nmiCount'] >= counters['_rxCount'] and counters['_rxDropped'] == counters['_rxOverruns'] == 0
    heap = (folder/'final-heap.bin').read_bytes()
    assert heap[0x50:0xff] == bytes(175) and heap[0x104:0x1ff] == bytes(251)
    for capture in report.get('cpu_captures', []):
        assert capture['restored'] and capture['borrower_failures'] == []
        for borrower in capture['borrower_checks'].values():
            left = (folder/borrower['before_file']).read_bytes()
            right = (folder/borrower['after_file']).read_bytes()
            assert borrower['matches'] and left == right
            assert sha(left) == borrower['before_sha256'] and sha(right) == borrower['after_sha256']
        payload = bytearray()
        for chunk in capture['chunks']:
            status = (folder/chunk['status_file']).read_bytes()
            part = (folder/chunk['payload_file']).read_bytes()
            assert sha(status) == chunk['status_sha256'] and status[0] == 1
            assert not status[9]&0x40 and status[10]&15 == 4 and status[11] in (0, 0x0e)
            assert sha(part) == chunk['payload_sha256'] and len(part) == chunk['count']
            payload.extend(part)
            captured_chunks += 1
        assert payload == (folder/(capture['label']+'.bin')).read_bytes()
    if dirname == 'vice-f8':
        assert len(report['cpu_captures']) == 4
        assert (folder/'cpu-session-vdc.bin').read_bytes() == expected
        assert (folder/'cpu-session-vic.bin').read_bytes() == (folder/'session-vic.bin').read_bytes()
        assert (folder/'cpu-session-nmi.bin').read_bytes() == bytes.fromhex('f01b')
        labels = dict((m[2], int(m[1], 16)) for m in re.finditer(r'^al ([0-9a-fA-F]+) \.(\S+)',
                      (source/'target/native-desktop/claude.lbl').read_text(), re.M))
        assert (folder/'cpu-session-gate.bin').read_bytes() == labels['nmiHandler'].to_bytes(2, 'little')

readiness = json.loads((root/'hardware-readiness.json').read_text())
assert readiness['completed'] and not readiness['mutation_requests']
assert all(row['method'] == 'GET' and row['status'] == 200 for row in readiness['reads'])
print(f'PASS: {len(manifest)} sealed payloads; 11 native, 9 host, 30 render, 24 desktop, 4 startup checks; '
      f'2 serial workflows and {captured_chunks} CPU-observer chunks. No hardware writes performed by this audit.')
