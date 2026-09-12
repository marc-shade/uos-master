#!/usr/bin/env python3
"""Compare two pinned source excerpts with the local C128 ROM; no device I/O."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--cbmsrc', type=Path, required=True)
parser.add_argument('--rom', type=Path, required=True)
parser.add_argument('--work', type=Path, required=True)
args = parser.parse_args()
reference = Path(__file__).resolve().parent
manifest = json.loads((reference/'provenance.json').read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
for name, digest in manifest['files'].items():
    assert sha((args.cbmsrc/name).read_bytes()) == digest, name
rom = args.rom.read_bytes()
assert len(rom) == 16384 and sha(rom) == manifest['rom_sha256']
args.work.mkdir(parents=True, exist_ok=True)

def normalize(excerpt):
    result = []
    for raw in excerpt.splitlines():
        line = raw.split(';', 1)[0].rstrip()
        if not line.strip() or line.strip() == '.page': continue
        line = re.sub(r'(\d+)\$', r'local_\1', line)
        if not line[0].isspace():
            label, *tail = line.split(maxsplit=1)
            line = label+':'+(' '+tail[0] if tail else '')
        result.append(line)
    return '\n'.join(result)+'\n'

kernel = (args.cbmsrc/'KERNAL_C128_05/interrupt.src').read_text()
editor = (args.cbmsrc/'EDITOR_C128/ed1.src').read_text()
irq = re.search(r'^irq\s.*?^prend\s.*?^\s+rti\b', kernel, re.M|re.S).group()
editor_return = re.search(r'^irqrts\s.*?^20\$\s+rts\b', editor, re.M|re.S).group()
blocks = [
    ('irq-dispatch-return', 0xff17, 38, irq,
     'mmucr=$ff00\nsysbnk=0\nibrk=$0316\niirq=$0314\n'),
    ('editor-interruptible-keyscan', 0xc214, 32, editor_return,
     'vicreg=$d000\ngraphm=$d8\nscnkey=$c55d\nblink=$c6e7\n')]
report = dict(passed=False, repository=manifest['repository'], commit=manifest['commit'],
              rom_sha256=sha(rom), complete_rom_rebuilt=False, blocks=[])
for name, address, count, excerpt, symbols in blocks:
    source = args.work/(name+'.asm'); binary = args.work/(name+'.prg')
    source.write_text(f'*=${address:04x}\n'+symbols+normalize(excerpt))
    subprocess.run(['64tass', '-a', str(source), '-o', str(binary)], check=True, capture_output=True)
    assembled = binary.read_bytes()
    assert assembled[:2] == address.to_bytes(2, 'little') and len(assembled) == count+2
    expected = rom[address-0xc000:address-0xc000+count]
    (args.work/(name+'-rom.bin')).write_bytes(expected)
    assert assembled[2:] == expected
    report['blocks'].append(dict(name=name, address=address, bytes=count,
        sha256=sha(expected), source_excerpt_sha256=sha(excerpt.encode()), matches=True))
assert rom[0xc229-0xc000] == 0x58
assert rom[0xc012-0xc000:0xc015-0xc000] == bytes.fromhex('4c5dc5')
assert rom[0xc024-0xc000:0xc027-0xc000] == bytes.fromhex('4c94c1')
assert rom[0xfa65-0xc000:0xfa69-0xc000] == bytes.fromhex('d82024c0')
report['passed'] = True
(args.work/'report.json').write_text(json.dumps(report, indent=2)+'\n')
print('PASS: 70 bytes from two pinned cbmsrc excerpts match the local 318020-05 ROM; IRQ mapping save/restore and editor CLI confirmed')
