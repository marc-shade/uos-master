"""Cold-boot the native disk on the reference C128; restore the legacy desktop.

Invoked by hw_ultimate_check.py --native. This is a bounded memory-workspace
test, with no cartridge-file commands or drive-B changes. Host RAM DMA leaves
a full minute for native and legacy boot IEC traffic before observations.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import time

from hw_storage_check import HardwareMonitor, ci
from hwlib import desk_tick
from native_capture import NativeCapture, expected_screen, wait, ROOT


def hashes():
    files=sorted((ROOT/'target').glob('*.prg'))+[ROOT/'target/ultos.d64']
    files+=sorted((ROOT/'target/native').glob('*.prg'))+[ROOT/'target/native/uos128.d64']
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def quiet_boot(label):
    print(f'{label}: waiting 60 seconds for IEC before any RAM DMA',flush=True)
    time.sleep(30)
    print(f'{label}: continuing quiet boot interval',flush=True)
    time.sleep(30)


def run(ult):
    work=Path(tempfile.mkdtemp(prefix='uos-hardware-native-'))
    print(f'Native hardware evidence: {work}',flush=True)
    mon=HardwareMonitor(ult)
    report=dict(build=hashes(),passed=False,checks=[],boot_quiet_seconds=60,
                legacy_desktop_restored=False,host=ult.host)
    capture=NativeCapture(mon,work);report['captures']=capture.records

    def save():
        (work/'report.json').write_text(json.dumps(report,indent=2)+'\n')

    def read(address,count=1):return bytes(mon.read_mem(address,address+count-1))

    def drives(label):
        data=json.loads(ult.drives());assert not data['errors'],data
        (work/f'drives-{label}.json').write_text(json.dumps(data,indent=2)+'\n')
        return {name:value for record in data['drives'] for name,value in record.items()}

    # Only leave the already deployed, idle legacy desktop; never overwrite an
    # unknown foreground application or unsaved editor document to start a test.
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little'),'expected the deployed legacy desktop'
    assert ci.wait_desktop_live(mon,120),'legacy desktop is not responsive'
    settings=read(0x7350,9);(work/'settings-before.bin').write_bytes(settings)
    before=drives('before');assert before['a']['enabled'] and before['a']['bus_id']==8
    (work/'ultimate-version.json').write_text(ult.version())
    switched=False
    try:
        ult.mount((ROOT/'target/native/uos128.d64').read_bytes(),'a','d64','readonly')
        switched=True;ult.reset();quiet_boot('Native C128 boot')
        wait(lambda:read(0x1c13,6)==b'UOS128' and read(0x3d12)==b'\1','native cold boot',120)
        assert read(0x3d0e,3)==bytes([191,251,32]),read(0x3d00,32).hex()

        def key(value,expected=0):
            wait(lambda:read(0x3d12)==b'\1' and read(0xd0)==b'\0','native input ready',30)
            previous=int.from_bytes(read(0x3d13,2),'little')
            mon.write_mem(0x3d12,b'\0')
            mon.write_mem(0x34a,bytes([value]));mon.write_mem(0xd0,b'\1')
            time.sleep(2)
            wait(lambda:int.from_bytes(read(0x3d13,2),'little')==(previous+1)&65535 and read(0x3d12)==b'\1',
                 f'native key {value:02x}',60)
            assert read(0x3d16)==bytes([expected]),read(0x3d00,32).hex()
            report.setdefault('key_events',[]).append(dict(key=value,result=expected,event=previous+1))
            save()

        def screens(label,bank,free=(191,251),slots=32,handle=b'\0'*4,result=0):
            vic=read(0x400,1000);(work/f'{label}-vic.bin').write_bytes(vic)
            first=capture.capture(label+'-vdc',mode=1)
            second=capture.capture(label+'-vdc-repeat',mode=1)
            assert first==second,'native VDC captures disagree'
            assert vic==expected_screen(40,bank,free,slots,handle,result),'native VIC screen differs'
            assert first==expected_screen(80,bank,free,slots,handle,result),'native VDC screen differs'
            (work/f'{label}.txt').write_text('\n'.join(''.join(chr(c+64) if c<32 else chr(c) for c in first[row*80:(row+1)*80]).rstrip() for row in range(25))+'\n')
            save()

        screens('initial',0)
        report['checks'].append('native disk cold boot; both complete text screens; native MMU/common RAM confirmed by CPU probe')
        key(ord('V'),4)  # no allocation: the workspace must expose the error
        allocations=[]
        for bank,keycode in ((0,ord('1')),(1,ord('2'))):
            key(keycode,4 if bank==0 else 0);key(ord('A'))
            page=read(0x3d03)[0];handle=read(0x3d04,4)
            assert page==(0x40 if bank==0 else 4)
            allocations.append((bank,page,handle))
            key(ord('W'));key(ord('V'))
            assert read(0x3d0e+bank)[0]==(191 if bank==0 else 251)-32
            print(f'PASS: physical native bank {bank} allocated, filled and verified 8192 bytes',flush=True)
        for bank,page,handle in allocations:
            expected=bytes((i&255)^(i>>8)^(0xa5 if bank else 0) for i in range(8192))
            actual=read(page*256,8192) if bank==0 else b''.join(
                capture.capture(f'bank-{bank}-{offset:04x}',bank=bank,address=page*256+offset,count=min(2000,8192-offset))
                for offset in range(0,8192,2000))
            assert actual==expected,f'independent native bank {bank} bytes differ'
            (work/f'bank-{bank}-all.bin').write_bytes(actual)
        report['checks'].append('16,384 bytes independently compared; bank 0 DMA and bank 1 native ROM observer agree with host patterns')
        screens('allocated',1,(159,219),30,allocations[1][2])
        for bank,keycode in ((0,ord('1')),(1,ord('2'))):
            key(keycode);key(ord('V'));key(ord('F'))
        assert read(0x3d0e,3)==bytes([191,251,32])
        screens('released',1)
        key(ord('1'));key(ord('2'))
        report['checks'].append('both blocks survive switches and observations; all pages/handles released; native input remains live')
        after_native=drives('native')
        assert {k:v for k,v in before.items() if k!='a'}=={k:v for k,v in after_native.items() if k!='a'}
        report.update(native_checks_passed=True,bytes_independently_verified=16384)
    except BaseException as error:
        report['error']=str(error)
        try:
            (work/'failure-mailbox.bin').write_bytes(read(0x3d00,32))
            (work/'failure-vic.bin').write_bytes(read(0x400,1000))
        except Exception as diagnostic_error:report['diagnostic_error']=str(diagnostic_error)
        raise
    finally:
        save()
        if switched:
            print('Restoring the deployed uOS desktop after the native workspace test',flush=True)
            ult.mount((ROOT/'target/ultos.d64').read_bytes(),'a','d64','readwrite')
            ult.run_prg((ROOT/'target/uos.prg').read_bytes());quiet_boot('Legacy desktop boot')
            wait(lambda:read(0x33c,2)==desk_tick().to_bytes(2,'little'),'legacy desktop vector',120)
            assert ci.wait_desktop_live(mon,120),'restored legacy desktop is not live'
            assert read(0x7350,9)==settings,'legacy settings changed'
            after=drives('restored')
            assert {k:v for k,v in before.items() if k!='a'}=={k:v for k,v in after.items() if k!='a'}
            report['legacy_desktop_restored']=True
        report['images_unchanged']=report['build']==hashes();save()
    assert report['images_unchanged']
    report['passed']=True;save()
    print(f'HW-NATIVE PASS; native RAM/screens verified and deployed desktop restored; evidence {work}',flush=True)
