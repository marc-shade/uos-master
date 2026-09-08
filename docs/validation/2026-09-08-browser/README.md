# Ultimate desktop browser — 2026-09-08

This increment follows `684a6558`. The distribution adds `uos-ultimate` to the
desktop launcher. It browses the cartridge filesystem through DOS target 2,
keeps eight complete filenames per page, and supports keyboard and VIC mouse
navigation, long-name/path scrolling, retry and cancellation. The shell keeps
its independent DOS target 1. See the [browser guide](../../ULTIMATE-BROWSER.md)
for controls, memory ownership and current limits.

## Defects reproduced during validation

The original launcher drew app names but registered only Cancel when apps
were present. Core hit detection also rejected valid screen X positions
232–255 and rectangles crossing X=256. The
[CPU baseline](before-launcher-vdc-fix/desktop.json) records both failures.
Registration now reloads the app count after control creation, and hit testing
compares the full coordinate while ignoring freed table slots.

Launching through the real sixth callback then exposed a filename pointer
that reused row 1's high byte even when row 6 crossed a memory page. The
[callback baseline](before-launch-name-fix/desktop.json) reproduces the wrong
16-byte operand and the remaining hard-coded 14-pixel label spacing. The
physical loader returned error 4 for those same bytes. Callbacks now use both
bytes from the row pointer table; label origins use the configured row height.
The [failed hardware run](before-launch-name-fix/hardware.json) never entered
the browser. Its old cleanup also waited for the unloaded app and did not
restore DOS target 2. The helper now checks for a loaded browser before asking
it to exit, records starting paths before navigation, and reports cleanup
errors separately. A later run's restoration applies to that run's starting
paths, not to this earlier unrecorded context.

The [next physical attempt](partial-iec-load/report.json) supplied the correct
filename but stalled after a partial IEC load. Two identical RAM snapshots
matched the new browser only through `$52f6`; later bytes were left from the
earlier app. `LOADERR=0` is also the in-progress value, so it did not prove a
successful return. The
[firmware RAM-read implementation](https://github.com/GideonZ/1541ultimate/blob/a01c04e8267a0d916b7203cb34dcf1127f75981d/software/io/c64/c64_subsys.cc#L551)
stops and resumes the CPU. Frequent host polling can therefore disturb IEC
timing. The helper now leaves boot, launcher directory scanning and app loading
unobserved for 60, 30 and 30 seconds respectively before reading RAM. This is a
test-observation change; no production mouse/IRQ code was changed for this
stall. The installed firmware revision remains unconfirmed.

An earlier physical browser run reached ordinal 256 with all eight complete
cached names correct, but its VDC text contained a blank in place of the `C`
in `ADIDAS Championship Football (132)`. The
[failed hardware record](before-launcher-vdc-fix/report.json) and
[raw VDC cells](before-launcher-vdc-fix/ordinal-256.vdc.bin) preserve the failure.
The driver selected address registers without waiting for readiness.
The [strict protocol baseline](before-launcher-vdc-fix/vdc.json) rejects that
access. Runtime helpers now select, poll bit 7, then access the data register,
following the [Commodore 128 Programmer's Reference Guide](https://www.pagetable.com/docs/Commodore%20128%20Programmer%27s%20Reference%20Guide.pdf),
printed pages 296 and 306. The absent-VDC probe uses a bounded wait. The existing
three text passes and readback repairs are retained.

An [earlier interrupted attempt](interrupted-hardware/diagnostic.json) passed
first-page checks but encountered a cartridge REST timeout. Subsequent RAM and
version observations worked. The hardware helper now retries only read-only
RAM observations, never navigation or DMA writes. A separate
[helper failure](helper-alias-failure/hardware.json) came from a listing parser
that did not recognize an assignment-style label; the shared emulator helper
now handles that 64tass form.

The hardware packet oracle also had a capture range that crossed the live
settings record. Its limit now ends at `$7300`, below `$7350`, while the probe
continues draining the complete directory. An optional 16-bit skip count
captures a later-page oracle without filling main RAM with earlier entries.

## Evidence and reproduction

Current CPU records cover the assembled browser and actual UCI driver
([browser](cpu.json)), the public GETCAP ABI ([core](core.json)), launcher
registration/hit detection ([desktop](desktop.json)), and VDC access order,
exact text/attributes and absent probing ([VDC](vdc.json)). Earlier emulator
results under `before-launcher-vdc-fix/` apply only to the hashes recorded there.

All four final [emulator suites](emulator/report.json) pass: x64 and x128
storage, 15 VDC/clock/input checks, and 18 file-manager/shell checks. Both storage
runs launch through the sixth app's registered control at screen X=240, enter
the offline browser, preserve preferences and return to a dispatching desktop
before continuing their storage checks. The VDC suite captures the browser's
[absent-interface response](emulator/offline.png). Every one of the 14 PRGs in
the [distribution readback](disk.json) matches its built file byte for byte.

The final [physical C128 record](hardware/report.json) passes on the same
production hashes as those emulator runs. It verifies registered app-row
launch, all 32 Next actions to ordinal 256 in a 1,096-entry directory, and all
eight complete filenames against an independent packet oracle on both sampled
pages. Exact VDC cells pass, including the previously missing `C`. The
[first-page](hardware/first.png) and [ordinal-256](hardware/ordinal-256.png)
images render the physical VIC bitmap; the adjacent `.vdc.bin` files contain
raw VDC screen codes. The [header clock](hardware/clock-observation.json)
advanced from 04:58 PM to 05:06 PM while browsing.

Root → select Usb0 → Open → Parent succeeds, settings remain intact, and ESC
returns to a dispatching desktop. DOS target 1 returns to `/` and target 2 to
`/Usb0/c64/#-a/`, their values at the start of this successful run. Drive B was
not remounted, and the filesystem tests made no file changes. No RAM-read
retries were needed. This successful run supports the quiet-observation
approach; intermittent I/O and cold-boot soak coverage remains open.

The 32 observed page changes took 12.917–15.966 s (median 14.497 s), including
host polling. Full-screen redraws and repeated scans require further performance
work. These results establish the listed workflows, not completion of R2 or
the whole OS. The final source-comment clarification rebuild produced identical
PRGs and the same D64 hash, so the recorded binary evidence still applies.

```sh
./build.sh
python3 -m venv .venv-tests
.venv-tests/bin/python -m pip install -r tests/requirements-uci.txt
.venv-tests/bin/python -u tests/ci_ultimate.py --report /tmp/browser.json
.venv-tests/bin/python -u tests/ci_core.py --report /tmp/core.json
.venv-tests/bin/python -u tests/ci_desktop.py --report /tmp/desktop.json
.venv-tests/bin/python -u tests/ci_vdc_protocol.py --report /tmp/vdc.json
python3 -u tests/run_ci.py storage64 storage128 vdc fm
python3 -u hw_ultimate_check.py
```

The CPU checks use Py65 without VICE or the local `cbm` helper. Emulator and
hardware checks retain those existing dependencies. Never rebuild while a run
uses the target PRGs/listings; reports record exact binary hashes.

This remains a C64-mode application with an 80-column companion display.
File operations, shared pickers, associations, drive mount/eject, dynamic
hardware discovery and native C128 services remain in the
[completion roadmap](../../IMPLEMENTATION-ROADMAP.md). Coordinate injection
and keyboard-buffer input do not certify physical pointer movement or key
switches. Cold-boot and long-duration input/serial soak coverage remains open.
