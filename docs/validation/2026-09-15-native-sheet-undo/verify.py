from pathlib import Path
import hashlib,json,tarfile,binascii
root=Path(__file__).resolve().parent
for name,digest in json.loads((root/'SHA256.json').read_text()).items():
 assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
with tarfile.open(root/'results.tar.gz') as tar:
 for name in ('undo','undo-faults','media','rebuild'):
  assert json.load(tar.extractfile(name+'.json'))['passed'],name
 rebuilt=json.load(tar.extractfile('rebuild.json'))['images']
with tarfile.open(root/'inputs.tar.gz') as tar:
 for name,item in rebuilt.items():
  data=tar.extractfile('inputs/'+name).read()
  assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256']
with tarfile.open(root/'vice.tar.gz') as tar:
 report=json.load(tar.extractfile('vice/report.json'));assert report['passed']
 data=tar.extractfile('vice/budget.usht').read()
 assert len(data)==8208 and data[:10]==b'USHT\1\10\40\40\0\40' and data[12:16]==bytes(4)
 assert int.from_bytes(data[10:12],'little')==binascii.crc_hqx(data[16:],65535)
 expected=bytearray(8192)
 for cell,value in enumerate((b'12',b'30',b'=a1+b1')):expected[cell*32:cell*32+len(value)]=value
 assert data[16:]==expected
 assert hashlib.sha256(data).hexdigest()==report['saved_sha256']
print('PASS: archives, CPU/media reports, 37 rebuilt images and independent saved workbook')
