#!/usr/bin/env python3
"""Read only the hardware state needed to prepare native serial qualification."""
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parent
host = os.environ.get('CBM_ULTIMATE_HOST', '192.168.1.237')
report = dict(physical_network_io=True, mutation_requests=False, host=host, reads=[])
path = root/'hardware-readiness.json'
with path.open('x') as out:
    out.write(json.dumps(report, indent=2)+'\n')

def get(label, endpoint, binary=False):
    row = dict(label=label, method='GET', path=endpoint)
    report['reads'].append(row)
    try:
        try:
            with urlopen(Request('http://'+host+endpoint, method='GET'), timeout=20) as response:
                status, data = response.status, response.read()
        except HTTPError as error:
            status, data = error.code, error.read()
        row['status'] = status
        row['hex' if binary else 'body'] = data.hex() if binary else json.loads(data)
        print(label, status, row.get('body', row.get('hex')), flush=True)
    except BaseException as error:
        row['error'] = repr(error)
        raise
    finally:
        path.write_text(json.dumps(report, indent=2)+'\n')

try:
    get('version', '/v1/version')
    get('drives', '/v1/drives')
    for item in ('ACIA (6551) Mapping', 'ACIA (6551) Mode', 'Hardware Mode',
                 'Listening Port', 'Drop connection on DTR low',
                 'Do RING sequence (incoming)', 'Loop Delay'):
        get(item, '/v1/configs/'+quote('Modem Settings', safe='')+'/'+quote(item, safe=''))
    for label, address, size in (('legacy-tick-before', 0x33c, 2), ('legacy-app', 0x4122, 2),
                                  ('legacy-settings', 0x7350, 9), ('irq-vector', 0x314, 2)):
        get(label, f'/v1/machine:readmem?address={address:04X}&length={size}', True)
    time.sleep(1)
    get('legacy-tick-after', '/v1/machine:readmem?address=033C&length=2', True)
    report['completed'] = True
finally:
    path.write_text(json.dumps(report, indent=2)+'\n')
