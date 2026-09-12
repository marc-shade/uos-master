#!/usr/bin/env python3
"""Qualify temporary rollback instrumentation, including its negative control."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ci_native_editor_ultimate import UltimateEditor
from ci_native_files import STATUS,DOS,RECORDS
from native_reopen_probe import patch_spec


address,before,after=patch_spec();cases={}
for kind in ('unpatched-short-read','short-read','dos-error','overlong','timeout','success'):
    e=UltimateEditor({b'/SOURCE':b'X'*768})
    assert bytes(e.ram[address:address+3])==before
    patched=kind!='unpatched-short-read'
    if patched:e.ram[address:address+3]=after
    if 'short-read' in kind:e.ultimate.read_limit=300
    if kind=='dos-error':e.ultimate.read_status=b'71,DISK ERROR'
    if kind=='overlong':e.ultimate.inject[4]=lambda command,reply:[(bytes(513),b'00,OK')]
    if kind=='timeout':
        def stall(command,reply):e.ultimate.stuck=True;return reply
        e.ultimate.inject[4]=stall
    e.prompt(0x85,'/SOURCE')
    commands=list(e.ultimate.commands);closes=sum(c[1]==3 for c in commands)
    if kind in ('unpatched-short-read','success'):
        assert closes==1 and not e.ram[RECORDS] and e.ram[STATUS]==0
        e.check(b'X'*768 if kind=='success' else b'',0,False,status=0 if kind=='success' else 2)
    else:
        assert not closes and e.ram[RECORDS]==32 and e.ram[RECORDS+3]&6==6
        assert e.ram[STATUS]=={'short-read':0xe5,'dos-error':0,'overlong':0xfc,'timeout':0xff}[kind]
        assert e.ram[DOS]==(71 if kind=='dos-error' else 255 if kind=='short-read' else 0)
        e.check(b'',0,False,released=False)
    cases[kind]=dict(first_transport=e.ram[STATUS],first_dos=e.ram[DOS],close_commands=closes,
                     retained=bool(e.ram[RECORDS]),instructions=e.instructions)
    e.ram[address:address+3]=before
    e.ultimate.stuck=False;e.ultimate.inject.clear();e.ultimate.read_limit=None;e.ultimate.read_status=b''
    e.exit()
report=dict(passed=True,hardware_io=False,patch_address=address,before_hex=before.hex(),after_hex=after.hex(),cases=cases)
(Path(__file__).resolve().parents[1]/'probe-cpu.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: temporary rollback instrumentation; six workflows; original patch restored and all ownership released')
