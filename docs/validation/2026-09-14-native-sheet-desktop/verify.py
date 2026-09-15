#!/usr/bin/env python3
"""Verify archived checkpoint hashes and independently decode saved USHT files."""
from pathlib import Path
import binascii,hashlib,json,tarfile
root=Path(__file__).resolve().parent
for name,digest in json.loads((root/'SHA256.json').read_text()).items():
 assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
with tarfile.open(root/'vice.tar.gz') as tar:
 for case in ('40col-16k','80col-64k'):
  report=json.load(tar.extractfile(case+'/report.json'));assert report['passed']
  data=tar.extractfile(case+'/budget.usht').read()
  assert len(data)==8208 and data[:10]==b'USHT\x01\x08\x20\x20\x00\x20'
  assert data[12:16]==bytes(4)
  assert int.from_bytes(data[10:12],'little')==binascii.crc_hqx(data[16:],65535)
  expected=bytearray(8192)
  for cell,value in enumerate((b'12',b'30',b'=a1+b1')):expected[cell*32:cell*32+len(value)]=value
  assert data[16:]==expected
  assert hashlib.sha256(data).hexdigest()==report['saved_sha256']
assert json.loads((root/'rebuild.json').read_text())['passed']
statuses=json.loads((root/'statuses.json').read_text())
assert len(statuses)==7 and all(row['exit_code']==0 for row in statuses)
print('PASS: archive hashes, seven CPU jobs, clean rebuild and two independently decoded workbooks')
