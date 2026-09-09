#!/usr/bin/env python3
"""Compare archived DMA/CPU disagreements with separately installed C128 ROMs."""
import hashlib
import json
from pathlib import Path
import sys

archive=Path(__file__).resolve().parent
rom_folder=Path(sys.argv[1])
report=json.loads((archive/'hardware/report.json').read_text())
roms={base:(rom_folder/name).read_bytes() for base,name in ((0x4000,'basiclo-318018-04.bin'),(0x8000,'basichi-318019-04.bin'))}
basic=roms[0x4000]+roms[0x8000]
digest=lambda data:hashlib.sha256(data).hexdigest()
records=[]
for observation in report['ram_observations']:
    if observation['direct_matches_cpu']:continue
    label=observation['label'];start=observation['address'];count=observation['count']
    direct=(archive/'hardware'/(label+'-dma.bin')).read_bytes()
    cpu=(archive/'hardware'/(label+'.bin')).read_bytes()
    assert len(direct)==len(cpu)==count and direct!=cpu
    matches=[base for base,data in roms.items() if start<base+len(data) and start+count>base] if (
        0x4000<=start and start+count<=0xc000 and direct==basic[start-0x4000:start-0x4000+count]) else []
    records.append(dict(label=label,address=start,count=count,different_bytes=sum(a!=b for a,b in zip(direct,cpu)),
                        direct_sha256=digest(direct),cpu_sha256=digest(cpu),matching_rom_bases=matches))
assert any(record['matching_rom_bases'] for record in records),'expected the documented complete ROM snapshot'
result=dict(passed=True,roms={hex(base):dict(bytes=len(data),sha256=digest(data)) for base,data in roms.items()},
            observations=records,all_disagreements_match_rom=all(record['matching_rom_bases'] for record in records))
(archive/'rom-observations.json').write_text(json.dumps(result,indent=2)+'\n')
print(f'PASS: {len(records)} DMA/CPU disagreements compared with installed reference ROMs')
