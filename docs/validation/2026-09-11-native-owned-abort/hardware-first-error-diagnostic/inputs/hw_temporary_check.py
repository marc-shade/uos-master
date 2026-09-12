"""Reclaim exact, archived and unmounted test images from Ultimate /Temp."""
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.parse import quote

from hw_storage_check import HardwareMonitor,ci
from hw_native_check import hashes
from hw_native_ultimate_check import raw_read
from hw_uci_check import Probe
from hwlib import desk_tick
from native_capture import ROOT


def reclaim(ult,saved_report):
    prior=json.loads(saved_report.read_text());source=saved_report.parent
    assert prior['passed'] and prior['legacy_desktop_restored'] and prior['data_drive_restored']
    assert prior['independent_readback']['saved_sha256']==prior['saved_sha256']
    restored=json.loads((source/'drives-restored.json').read_text())
    legacy={k:v for entry in restored['drives'] for k,v in entry.items()}['a']
    legacy_path=legacy['image_file']
    if not legacy_path.startswith('/'):legacy_path=legacy['image_path'].rstrip('/')+'/'+legacy_path
    candidates=[('native',prior['native_disk_path'],source/'native.d64',prior['native_disk_sha256']),
                ('documents',prior['data_disk_path'],source/'editor-readback.d64',prior['independent_readback']['sha256']),
                ('legacy',legacy_path,ROOT/'target/ultos.d64',prior['build']['target/ultos.d64'])]
    for _,path,file,digest in candidates:
        assert path.startswith('/Temp/') and '..' not in path and path.count('/')==2
        assert file.stat().st_size==174848 and hashlib.sha256(file.read_bytes()).hexdigest()==digest
    assert len({path for _,path,_,_ in candidates})==3
    work=Path(tempfile.mkdtemp(prefix='uos-hardware-temp-reclaim-'))
    print(f'Temporary-image reclamation evidence: {work}',flush=True)
    result=dict(passed=False,source_report=str(saved_report),build=hashes(),files=[])
    def save():(work/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    mon=HardwareMonitor(ult)
    def read(address,count=1):return bytes(mon.read_mem(address,address+count-1))
    def drives():
        value=json.loads(ult.drives());assert not value['errors'];return value
    before=drives();result['drives_before']=before
    mounted=set()
    for entry in before['drives']:
        for value in entry.values():
            path=value.get('image_file','')
            if path:
                if not path.startswith('/'):path=value['image_path'].rstrip('/')+'/'+path
                mounted.add(path)
    assert not mounted.intersection(path for _,path,_,_ in candidates)
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and ci.wait_desktop_live(mon,120)
    assert read(0x4122,2)==bytes(2)
    settings=read(0x7350,9);controls=read(0x9000,256)
    (work/'settings-before.bin').write_bytes(settings)
    probe=Probe(ult,work);original={}
    try:
        mon.write_mem(0x9000,b'\0'+b'\xff'*255)
        for target in (1,2):original[target]=probe.ok(bytes([target,0x12]))['records'][0][0]
        result['dos_paths_before_hex']={str(k):v.hex() for k,v in original.items()};save()
        for label,path,file,digest in candidates:
            print(f'Comparing all 174848 bytes before reclaiming {path}',flush=True)
            observed=raw_read(probe,path.encode(),file.read_bytes(),work,label+'-before-removal')
            record=dict(label=label,path=path,source_file=str(file),expected_sha256=digest,
                        readback=observed,delete_started=False,delete_acknowledged=False)
            result['files'].append(record);save()
            assert drives()==before,'drive mounts changed before deletion'
            record['delete_started']=True;save()
            reply=probe.ok(b'\x01\x09'+path.encode())
            record['delete_acknowledged']=True;record['delete_result']={k:v for k,v in reply.items() if k!='records'};save()
            status,body=ult._call('GET','/v1/files'+quote(path,safe='/')+':info')
            info=json.loads(body);record['file_info_after']=dict(status=status,response=info);save()
            assert info.get('errors') and 'files' not in info,'deleted file still has metadata'
            print(f'PASS: exact archived image reclaimed: {path}',flush=True)
        result['bytes_reclaimed']=sum(item['readback']['bytes'] for item in result['files'])
    except BaseException as error:
        result['error']=str(error)
        raise
    finally:
        try:
            for target,path in original.items():
                probe.ok(bytes([target,0x11])+path)
                assert probe.ok(bytes([target,0x12]))['records'][0][0]==path
            result['dos_paths_restored']=True
        finally:
            mon.write_mem(0x9000,controls)
            result['uncertain_host_writes']=ult.uncertain_writes
            result['host_connect_failures']=ult.connect_failures
            save()
    assert drives()==before and read(0x7350,9)==settings and read(0x4122,2)==bytes(2)
    assert result['build']==hashes() and ci.wait_desktop_live(mon,120)
    result.update(passed=True,desktop_live=True,drives_unchanged=True,settings_unchanged=True,images_unchanged=True)
    save();print(f'PASS: {result["bytes_reclaimed"]} bytes reclaimed; desktop/settings/drives restored',flush=True)
