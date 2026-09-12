"""Temporary editor rollback instrumentation; never an installed product change."""
from hwlib import lst_symbol
from native_capture import ROOT


def patch_spec():
    address=lst_symbol('native/editor','ed_open_rollback')+3
    target=lst_symbol('native/editor','ed_close_owned')
    before=b'\x20'+target.to_bytes(2,'little');after=b'\xea'*3
    image=(ROOT/'target/native/editor.prg').read_bytes()
    assert image[2+address-0x6000:5+address-0x6000]==before
    return address,before,after


def install(client,report,save):
    address,before,after=patch_spec()
    assert client.read(0x3de0,4)==bytes(4)
    assert client.cpu_read('rollback-probe-before',address,3)==before
    record=dict(address=address,before_hex=before.hex(),after_hex=after.hex(),
                purpose='Keep the initiating read error by deferring automatic file release on rollback.',
                patch_started=True,patch_verified=False,restored=False,samples=[])
    report['rollback_probe']=record;save()
    client.put(address,after)
    assert client.cpu_read('rollback-probe-patched',address,3)==after
    record['patch_verified']=True;save()


def sample(client,report,save,label):
    # File services have already returned to the editor. No DOS command is
    # issued between the failing read and these CPU observations.
    context=client.cpu_read(label+'-first-file-state',0x3d80,0x64)
    start=lst_symbol('native/uos128','nu_high');end=lst_symbol('native/uos128','nu_code_end')
    transport=client.cpu_read(label+'-first-transport-state',start,end-start)
    status=client.cpu_read(label+'-first-ultimate-status',0x4f00,32)
    report['rollback_probe']['samples'].append(dict(label=label,files_hex=context.hex(),
        transport_hex=transport.hex(),ultimate_status_hex=status.hex(),
        first_file_error=context[14],first_dos_error=context[15],first_transport_error=context[16]))
    save()


def restore(client,report,save):
    address,before,after=patch_spec()
    assert client.cpu_read('rollback-probe-before-restore',address,3)==after
    report['rollback_probe']['restore_started']=True;save()
    client.put(address,before)
    assert client.cpu_read('rollback-probe-restored',address,3)==before
    report['rollback_probe']['restored']=True;save()
