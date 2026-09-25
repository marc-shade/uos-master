from pathlib import Path
import json,hashlib,tarfile,binascii
root=Path(__file__).resolve().parent
for name,digest in json.loads((root/'SHA256.json').read_text()).items():
 assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
statuses=json.loads((root/'statuses.json').read_text())
assert len(statuses)==7 and all(row['exit_code']==0 for row in statuses)
with tarfile.open(root/'results.tar.gz') as tar:
 for name in [row['case'] for row in statuses]+['media','rebuild']:
  assert json.load(tar.extractfile(name+'.json'))['passed'],name
 images=json.load(tar.extractfile('rebuild.json'))['images'];assert len(images)==40
with tarfile.open(root/'inputs.tar.gz') as tar:
 for name,expected in images.items():
  data=tar.extractfile('inputs/'+name).read()
  assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256'],name
 app=tar.extractfile('inputs/target/native-desktop/sheet.prg').read()
 window=0x6000+app[9]+256*app[13]
 for name in ('shfont','shcalc','shclip'):
  data=tar.extractfile('inputs/target/native-desktop/'+name+'.prg').read()
  assert data[2:10]==b'NMOD\1\1\r\0'
  assert int.from_bytes(data[:2],'little')==window==0xb100
  assert len(data)==2+int.from_bytes(data[10:12],'little')
  assert window+len(data)-2<=0xc000
  assert data[12:14]==app[16:18]
  assert 16<=int.from_bytes(data[14:16],'little')<len(data)-2
  assert int.from_bytes(data[16:18],'little')==binascii.crc_hqx(data[2:16]+bytes(2)+data[18:],65535)
with tarfile.open(root/'vice.tar.gz') as tar:
 for case in ('40col-16k','80col-64k'):
  report=json.load(tar.extractfile(case+'/report.json'));assert report['passed'] and report['options']['clipboard']
  assert report['inputs']['sheet.prg']==hashlib.sha256(app).hexdigest()
  data=tar.extractfile(case+'/budget.usht').read()
  assert len(data)==8208 and data[:10]==b'USHT\1\10\40\40\0\40' and data[12:16]==bytes(4)
  assert int.from_bytes(data[10:12],'little')==binascii.crc_hqx(data[16:],65535)
  expected=bytearray(8192)
  for cell,value in enumerate((b'12',b'30',b'=a1+b1')):expected[cell*32:cell*32+len(value)]=value
  assert data[16:]==expected and hashlib.sha256(data).hexdigest()==report['saved_sha256']
print('PASS: archives, seven CPU jobs, 40 rebuilt images, module bindings and two saved workbooks')
