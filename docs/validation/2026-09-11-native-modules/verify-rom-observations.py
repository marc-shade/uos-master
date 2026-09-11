#!/usr/bin/env python3
"""Compare archived DMA/CPU disagreements with separately installed C128 ROMs."""
import argparse
import hashlib
import json
from pathlib import Path

archive=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('rom_folder',type=Path)
parser.add_argument('--folder',choices=('hardware','hardware-iec'),default='hardware')
parser.add_argument('--record',action='store_true')
args=parser.parse_args()
directory=archive/args.folder
report=json.loads((directory/'report.json').read_text())
assert report['passed'] and report['legacy_desktop_restored']
roms={base:(args.rom_folder/name).read_bytes() for base,name in
      ((0x4000,'basiclo-318018-04.bin'),(0x8000,'basichi-318019-04.bin'))}
assert all(len(data)==16384 for data in roms.values())
basic=roms[0x4000]+roms[0x8000]
digest=lambda data:hashlib.sha256(data).hexdigest()
records=[]
for observation in report['ram_observations']:
    if observation['direct_matches_cpu']:continue
    label=observation['label'];start=observation['address'];count=observation['count']
    direct=(directory/(label+'-dma.bin')).read_bytes()
    cpu=(directory/(label+'.bin')).read_bytes()
    assert len(direct)==len(cpu)==count and direct!=cpu
    assert digest(direct)==observation['direct_sha256'] and digest(cpu)==observation['cpu_sha256']
    assert 0x4000<=start and start+count<=0xc000
    reference=basic[start-0x4000:start-0x4000+count]
    deviations=[dict(address=start+i,offset=i,direct_byte=a,cpu_byte=b,reference_byte=c)
                for i,(a,b,c) in enumerate(zip(direct,cpu,reference)) if a!=c]
    unexplained=[item for item in deviations if item['direct_byte']!=item['cpu_byte']]
    matches=[base for base,data in roms.items() if start<base+len(data) and start+count>base]
    records.append(dict(label=label,address=start,count=count,different_bytes=sum(a!=b for a,b in zip(direct,cpu)),
                        direct_sha256=digest(direct),cpu_sha256=digest(cpu),comparison_rom_bases=matches,
                        whole_sample_matches_reference_rom=direct==reference,
                        reference_matching_bytes=count-len(deviations),reference_deviations=deviations,
                        unexplained_direct_bytes=unexplained))
result=dict(passed=True,roms={hex(base):dict(bytes=len(data),sha256=digest(data)) for base,data in roms.items()},
            observations=records,all_disagreements_match_rom=all(item['whole_sample_matches_reference_rom'] for item in records),
            whole_reference_matches=sum(item['whole_sample_matches_reference_rom'] for item in records),
            unexplained_direct_bytes=sum(len(item['unexplained_direct_bytes']) for item in records),
            qualification='This audit reproduces byte comparisons; it does not establish the origin of unmatched DMA bytes. CPU captures are the RAM authority.')
output=directory/'rom-observations.json'
if args.record:output.write_text(json.dumps(result,indent=2)+'\n')
else:assert result==json.loads(output.read_text())
print(f"PASS: audited {len(records)} DMA/CPU disagreements; {result['whole_reference_matches']} whole reference-ROM matches; {result['unexplained_direct_bytes']} unexplained direct bytes retained")
