"""Record the pending legacy probe without installing another probe or command."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
from hwlib import desk_tick, lst_symbol


def observe(ult):
    work=Path(tempfile.mkdtemp(prefix='uos-desktop-preflight-observation-',dir='/var/tmp/arc-scratch'))
    print('Preflight observation:',work,flush=True)
    result=dict(physical_hardware_io=True,memory_writes=False,cartridge_commands=False,
                machine_controls=False,expected_tick=desk_tick(),samples=[],
                uncertain_writes=ult.uncertain_writes,connect_failures=ult.connect_failures)
    for sample in range(2):
        state={}
        for name,address,count in [('low',0,1024),('kernel',0x800,256),('panic',0xd00,288),('desktop',0x1000,256),
            ('app_state',0x4100,128),('probe',0x5000,512),('command',0x5500,16),
            ('probe_state',0x5f00,32),('settings',0x7350,9),('transport',0x8a00,2048),
            ('vic',0xd000,64),('mmu',0xd500,12),('uci_status',0xdf1c,1)]:
            data=bytes(ult.read_mem(address,count));assert len(data)==count
            (work/f'{sample}-{name}.bin').write_bytes(data)
            state[name]=dict(address=address,bytes=count,sha256=hashlib.sha256(data).hexdigest())
            if name in ('probe_state','settings','mmu','uci','command'):state[name]['hex']=data.hex()
            if name=='low':state['tick_hex']=data[0x33c:0x33e].hex();state['jiffy_hex']=data[0xa0:0xa3].hex();state['port_hex']=data[:2].hex()
        result['samples'].append(state)
        (work/'report.json').write_text(json.dumps(result,indent=2)+'\n')
        if sample==0:time.sleep(2)
    (work/'drives.json').write_text(ult.drives())
    print(json.dumps(result,indent=2),flush=True)


def restore_tick(ult):
    from hw_storage_check import HardwareMonitor,ci
    prior=Path('/var/tmp/arc-scratch/uos-hardware-native-desktop-d1l06q1c')
    work=Path(tempfile.mkdtemp(prefix='uos-desktop-preflight-restore-',dir='/var/tmp/arc-scratch'))
    print('Pending tick restoration:',work,flush=True)
    mon=HardwareMonitor(ult)
    def read(at,count=1):return bytes(mon.read_mem(at,at+count-1))
    before=json.loads(ult.drives());expected=json.loads((prior/'drives-before.json').read_text())
    settings=(prior/'settings-before.bin').read_bytes()
    assert before==expected and read(0x7350,9)==settings and read(0x4122,2)==bytes(2)
    tick=desk_tick().to_bytes(2,'little');meta=read(0x5f00,16)
    assert tick==b'\x5e\x1f' and read(0x33c,2)==b'\0\x50'
    assert meta[:15]==tick+b'\2\0'+bytes(11) and read(0x5500,2)==b'\1\7'
    code=(prior/'uci-stream.prg').read_bytes()[2:]
    assert read(0x5000,len(code))==code and read(0xdf1c)[0]&0x3f==0
    result=dict(passed=False,source=str(prior),drives_before=before,settings_hex=settings.hex(),
                probe_state_before_hex=meta.hex(),tick_before_hex='0050',
                uncertain_writes=ult.uncertain_writes,connect_failures=ult.connect_failures,
                command_or_abort_resubmitted=False)
    def save():(work/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    save()
    try:
        ult.write_mem(0x33c,tick)
        result['tick_restored_before_liveness']=read(0x33c,2)==tick;save()
        result['desktop_live']=ci.wait_desktop_live(mon,120);save()
        assert result['desktop_live'],'desktop does not dispatch after restoring its original tick'
        assert read(0x33c,2)==tick
        result['probe_state_after_hex']=read(0x5f00,16).hex()
        result['drives_after']=json.loads(ult.drives())
        assert result['drives_after']==before and read(0x7350,9)==settings
        assert not ult.uncertain_writes
        result['passed']=True;save()
        print('PASS: original desktop dispatch restored; no cartridge command replay or disk changes',flush=True)
    except BaseException as error:
        result['error']=str(error);raise
    finally:
        current=read(0x33c,2)
        if current in (b'\0\x50',b'\0\x7f'):ult.write_mem(0x33c,tick)
        result['final_tick_hex']=read(0x33c,2).hex();save()
