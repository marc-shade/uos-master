"""Controlled key injection demonstrates why a strict capture must reject activity."""
from contextlib import contextmanager

from launcher_scene import console
from native_capture import NativeCapture, ROOT
from native_capture_transport import PausedViceMonitor
from native_running_layout import RunningLayout


def run_input_capture(mon, work, report, key):
    paused = PausedViceMonitor(mon)
    injected = []

    @contextmanager
    def batch(label):
        # Deliberately inject after all CPU VDC reads and before restoration.
        # This models a possible scheduling window, not the physical key source.
        if label == 'input-vdc-restore':
            for value in (0x11, 0x11):
                key(value)
                injected.append(value)
        with paused.paused(label):
            yield

    capture = NativeCapture(paused, work, quiet=.1, kernel_prefix='native-desktop', batch=batch)
    report['captures'] = capture.records
    report['paused_capture_batches'] = paused.batches
    try:
        capture.capture('input-vdc', mode=1, address=0, count=2000)
    except AssertionError as error:
        assert str(error) == 'native heap changed during observation'
        report['expected_capture_error'] = str(error)
    else:
        raise AssertionError('Activity during observation must be rejected')
    assert injected == [0x11, 0x11]
    assert (work/'input-vdc.bin').read_bytes() == console(80)
    row = capture.records[0]
    assert not row['restored']
    before = (work/'input-vdc-borrower-metadata-before.bin').read_bytes()
    after = (work/'input-vdc-borrower-metadata-after.bin').read_bytes()
    changes = [dict(address=0x3800+i, before=a, after=b)
               for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert changes == [dict(address=0x3d0c, before=27, after=7),
                       dict(address=0x3d13, before=0, after=2),
                       dict(address=0x3d15, before=0, after=17)], changes
    assert all(row['borrower_checks'][name]['matches'] for name in ('output', 'scratch'))
    resident = bytes(mon.read_mem(0x1300, 0x1bff)); mon.resume()
    (work/'input-vdc-independent-resident-after.bin').write_bytes(resident)
    before_resident = (work/'input-vdc-borrower-resident-before.bin').read_bytes()
    resident_changes = [dict(address=0x1300+i, before=a, after=b)
                        for i, (a, b) in enumerate(zip(before_resident, resident)) if a != b]
    layout = RunningLayout(ROOT, image_dir=ROOT/'target/native-desktop')
    # N_FILL retains its last fill byte in explicitly mutable hbyte state.
    assert layout.syms['hbyte'] == 0x17d0 and layout.mutable[0x17d0] == 'hbank'
    assert resident_changes == [dict(address=0x17d0, before=27, after=7)]
    report['input_control'] = dict(passed=True, injected_keys=injected,
        exact_physical_difference_pattern=changes, physical_failure_cause_proven=False,
        activity_rejected=True, original_vdc_payload_matches=True,
        independent_resident_after_changes=resident_changes,
        independent_resident_immutable_bytes_match=True)
