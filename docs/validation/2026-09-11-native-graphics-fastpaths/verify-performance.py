#!/usr/bin/env python3
"""Compare identical successful CPU cases with the sealed drawing baseline."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'2026-09-11-native-graphics-text'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
context=read(HERE/'candidate-context.json')
assert context['previous_manifest_sha256']==sha(PREVIOUS/'SHA256SUMS')=='ccbac6f2ab728e02734633cee5ea980196683a3c887a8e242e08b16b51058b10'
before=PREVIOUS/'source/graphics';after=HERE/'source/graphics'
assert (HERE/'source/client/expected-surface.bin').read_bytes()==(PREVIOUS/'source/client/expected-surface.bin').read_bytes()
result=read(after/'performance.json');assert result['passed']
assert result['before_library_sha256']==sha(before/'graphics.prg')
assert result['after_library_sha256']==sha(after/'graphics.prg')
cases=[('full_surface_xor','report.json',lambda r:r['bank']==0 and r.get('coords')==[-32768,-32768,32767,32767]),
       ('aligned_opaque_glyph','glyph-report.json',lambda r:r['bank']==0 and r['x']==0 and r['y']==0 and r['pen']==3 and not r['error']),
       ('aligned_opaque_label','text-report.json',lambda r:r['bank']==0 and r['x']==0 and r['y']==0 and r['pen']==3 and not r['error'] and r['text_hex']==b'Az09?/Usb0'.hex())]
for name,filename,match in cases:
    old=[r for r in read(before/filename)['cases'] if match(r)]
    new=[r for r in read(after/filename)['cases'] if match(r)]
    assert len(old)==len(new)==1
    a,b=old[0]['instructions'],new[0]['instructions'];assert b<a
    assert {k:v for k,v in old[0].items() if k!='instructions'}=={k:v for k,v in new[0].items() if k!='instructions'}
    assert result['cases'][name]==dict(before=a,after=b,ratio=round(a/b,3),reduction_percent=round(100*(a-b)/a,3))
print('PASS: unchanged surface oracle; 7.385x full-screen XOR, 8.893x aligned glyph and 8.427x aligned label instruction reductions')
