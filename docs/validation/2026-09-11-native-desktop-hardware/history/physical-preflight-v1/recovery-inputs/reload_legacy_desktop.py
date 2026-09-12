"""Restore the original deployed desktop after its recorded preflight panic."""
import hashlib
import json
from pathlib import Path
import tempfile
from hw_storage_check import HardwareMonitor,ci,ROOT
from hw_native_check import quiet_boot
from hwlib import desk_tick
from native_capture import wait


def restore(ult):
    prior=Path('/var/tmp/arc-scratch/uos-hardware-native-desktop-d1l06q1c')
    evidence=Path('/var/tmp/arc-scratch/uos-desktop-pc-observation-ve3hzdlq')
    pc=json.loads((evidence/'report.json').read_text())
    assert pc['passed'] and pc['borrowed_page_restored'] and all(row['pc']==0x0dcb for row in pc['samples'])
    work=Path(tempfile.mkdtemp(prefix='uos-desktop-preflight-reload-',dir='/var/tmp/arc-scratch'))
    print('Legacy desktop recovery:',work,flush=True)
    mon=HardwareMonitor(ult)
    def read(at,count=1):return bytes(mon.read_mem(at,at+count-1))
    before=json.loads(ult.drives());expected=json.loads((prior/'drives-before.json').read_text())
    settings=(prior/'settings-before.bin').read_bytes()
    assert before==expected and read(0x7350,9)==settings and read(0x4122,2)==bytes(2)
    assert read(0x33c,2)==desk_tick().to_bytes(2,'little') and read(0x314,2)==b'\x57\x9e'
    assert read(0xe0c,4)==b'4FFF' and read(0xdf1c)[0]&0x3f==0
    program=(ROOT/'target/uos.prg').read_bytes()
    assert len(program)==2036 and hashlib.sha256(program).hexdigest()=='11ff8decc029255aa8d6847a8c3c92aacbd191f9555e91d8fac6a45e31aa4a55'
    result=dict(passed=False,source=str(prior),pc_evidence=str(evidence),drives_before=before,
                settings_hex=settings.hex(),sent_loader_sha256=hashlib.sha256(program).hexdigest(),
                uncertain_writes=ult.uncertain_writes,control_requests=ult.control_requests,
                connect_failures=ult.connect_failures,cartridge_probe_command_replayed=False)
    def save():(work/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    ult.record_event=save;save()
    try:
        ult.control('POST','/v1/runners:run_prg',program)
        quiet_boot('Original legacy desktop recovery')
        wait(lambda:read(0x33c,2)==desk_tick().to_bytes(2,'little'),'original desktop vector after loader',120)
        assert ci.wait_desktop_live(mon,120),'reloaded desktop did not dispatch'
        current=read(0x7350,9);result['boot_settings_hex']=current.hex();save()
        assert current[2:7]==settings[2:7]
        mon.write_mem(0x7350,settings)
        result['drives_after']=json.loads(ult.drives())
        assert result['drives_after']==before and read(0x7350,9)==settings and read(0x4122,2)==bytes(2)
        assert ci.wait_desktop_live(mon,120)
        assert not ult.uncertain_writes
        result.update(passed=True,desktop_live=True,settings_restored=True,drives_unchanged=True)
        save();print('PASS: original desktop reloaded and dispatching; original drives and settings restored',flush=True)
    except BaseException as error:
        result['error']=str(error);raise
    finally:save()
