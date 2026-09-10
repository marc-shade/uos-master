#!/usr/bin/env python3
"""Compare archived DMA/CPU disagreements with separately installed C128 ROMs."""
import argparse
import hashlib
import json
from pathlib import Path

archive=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('rom_folder',type=Path)
parser.add_argument('--record',action='store_true')
args=parser.parse_args()
report=json.loads((archive/'hardware/report.json').read_text());assert report['passed']
roms={base:(args.rom_folder/name).read_bytes() for base,name in
      ((0x4000,'basiclo-318018-04.bin'),(0x8000,'basichi-318019-04.bin'))}
assert all(len(data)==16384 for data in roms.values())
basic=roms[0x4000]+roms[0x8000]
digest=lambda data:hashlib.sha256(data).hexdigest()
records=[]
for observation in report['ram_observations']:
    if observation['direct_matches_cpu']:continue
    label=observation['label'];start=observation['address'];count=observation['count']
    direct=(archive/'hardware'/(label+'-dma.bin')).read_bytes()
    cpu=(archive/'hardware'/(label+'.bin')).read_bytes()
    assert len(direct)==len(cpu)==count and direct!=cpu
    assert digest(direct)==observation['direct_sha256'] and digest(cpu)==observation['cpu_sha256']
    assert 0x4000<=start and start+count<=0xc000
    assert direct==basic[start-0x4000:start-0x4000+count],label
    matches=[base for base,data in roms.items() if start<base+len(data) and start+count>base]
    records.append(dict(label=label,address=start,count=count,different_bytes=sum(a!=b for a,b in zip(direct,cpu)),
                        direct_sha256=digest(direct),cpu_sha256=digest(cpu),matching_rom_bases=matches))
assert records,'expected the documented complete ROM snapshots'
result=dict(passed=True,roms={hex(base):dict(bytes=len(data),sha256=digest(data)) for base,data in roms.items()},
            observations=records,all_disagreements_match_rom=True)
if args.record:(archive/'rom-observations.json').write_text(json.dumps(result,indent=2)+'\n')
else:assert result==json.loads((archive/'rom-observations.json').read_text())
print(f'PASS: all {len(records)} DMA/CPU disagreements exactly match installed reference ROMs')
