#!/usr/bin/env python3
"""Reproduce the focused diagnostic's five comparisons with installed ROMs."""
import argparse
import hashlib
import json
from pathlib import Path

root=Path(__file__).resolve().parent;run=root/'hardware-first-error-diagnostic/run'
parser=argparse.ArgumentParser();parser.add_argument('rom_folder',type=Path);args=parser.parse_args()
report=json.loads((run/'report.json').read_text())
refs={address:(args.rom_folder/name).read_bytes() for address,name in
      [(0x4000,'basiclo-318018-04.bin'),(0x8000,'basichi-318019-04.bin')]}
assert all(len(data)==16384 for data in refs.values())
basic=refs[0x4000]+refs[0x8000];rows=[];sha=lambda data:hashlib.sha256(data).hexdigest()
for row in report['ram_observations']:
    if row['direct_matches_cpu']:continue
    assert 0x4000<=row['address'] and row['address']+row['count']<=0xc000
    data=(run/(row['label']+'-dma.bin')).read_bytes()
    assert len(data)==row['count'] and sha(data)==row['direct_sha256']
    want=basic[row['address']-0x4000:row['address']-0x4000+row['count']]
    rows.append(dict(label=row['label'],address=row['address'],count=row['count'],
                     whole_sample_matches_reference_rom=data==want,sha256=sha(data)))
result=dict(passed=True,source_report_sha256=sha((run/'report.json').read_bytes()),
    roms={hex(base):{'bytes':len(data),'sha256':sha(data)} for base,data in refs.items()},
    observations=rows,all_disagreements_match_rom=all(row['whole_sample_matches_reference_rom'] for row in rows),
    qualification='Compares retained DMA bytes with installed C128 BASIC ROM images; does not establish the cause of DMA mapping or the native USB failure. CPU captures remain authoritative for RAM.')
assert len(rows)==5 and result==json.loads((root/'first-error-rom-observations.json').read_text())
print('PASS: all five complete disagreeing DMA samples match reference ROM bytes; no cause inferred')
