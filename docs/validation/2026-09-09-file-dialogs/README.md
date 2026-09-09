# Shared file selector and editor Save As validation

This checkpoint adds a reusable cartridge Open/Save As selector and connects
the small editor to it. It includes directory restoration, exclusive file
creation, complete reopened verification, dirty-document protection and precise
VIC/VDC redraws. The API and remaining editor limits are in
[FILE-DIALOGS.md](../../FILE-DIALOGS.md).

## Image and memory boundaries

[images.json](images.json) records all 17 modules and the disk.
[disk.json](disk.json) confirms that each extracted disk member matches its PRG
byte for byte and that extraction did not change the source disk. Linux and
Windows build scripts list the same 17 modules; Windows execution is untested.
[The isolated source rebuild](source-rebuild.json) also reproduced all 17 PRGs
and the disk exactly after the final ABI comment correction.

| Module | Loaded range / boundary |
|---|---|
| Core | `$0801–$0ff2`; 13 bytes before the desktop |
| Desktop | `$1000–$406c`; below the file service at `$4100` |
| File service | `$4100–$4fff`, including viewer, selector gateway and saved directory |
| Selector | `$6200–$6ea4`; scratch avoids the settings at `$7350–$7358` |
| Editor | `$5000–$61ff`; code ends at `$5971`, document occupies `$5f00–$61ff` |

The final disk SHA-256 is
`f86a8771c96cb1434d401f86161d41ebbcb94f19787a457f50905b16c8547747`.
The editor stages reads at `$6e00–$70ff` only after the selector returns; a
subsequent selection reloads the library. The directory lease is resident and
survives replacement of the entire modal workspace.

## CPU and emulator checks

These tests execute the assembled 6502 modules. Protocol-model tests adapt the
cartridge and KERNAL interfaces; they do not certify physical filename limits.

| Evidence | Result and scope |
|---|---|
| [core.json](core.json) | 1,024 GETCAP calls across all 256 IDs; address results, registers, non-stack memory, D/I flags and stack wrap |
| [files.json](files.json) | Eight groups: 66,310-byte binary reads, 66,053-byte copies, name/buffer bounds, 127-byte creation components, 511+1 USB-write workaround, foreign ownership, launch cleanup and 16 faults |
| [desktop.json](desktop.json) | Five groups, including hidden system modules and the new selector |
| [copy/report.json](copy/report.json) | Six copy-dialog groups on the changed resident service: 66,053 bytes, 33 overlay cycles, full names, 14 faults and actual display comparisons |
| [picker.json](picker.json) | Six groups: both DOS contexts, variable pages, navigation beyond ordinal 255, existing-file rejection, cancellation, full relative names, 1,021-byte combined read path, creation bounds, malformed packets and failed-close/directory recovery |
| [editor.json](editor.json) | Four groups: 768-byte ASCII/CRLF round trip, six transfer/format/corruption faults, legacy read-only import, scrolling, dirty actions, empty files and unavailable/foreign-file cases |
| [display/report.json](display/report.json) | Actual graphics/VDC execution: complete erasure, title removal, caret positions 16/24/32/24, document and clock preservation, wide text and border pixels |
| [irq-sampler.json](irq-sampler.json) | 32 varied foreground register/stack/flag samples; sampler restores the original interrupt chain and entry state |
| [emulator/report.json](emulator/report.json) | x64 editor suite 5/5 and x128 storage suite 10 groups; logs and selected raw artifacts included |

Tests are reproducible from the repository with Python plus Py65 where needed:

```sh
python3 tests/ci_core.py
python3 tests/ci_picker.py
python3 tests/ci_editor_files.py
python3 tests/ci_file_dialog_display.py
python3 tests/ci_irq_state.py
python3 -u tests/ci_edit.py
python3 -u tests/ci_storage.py --machine x128
```

Refer to each script's `--help` for report/output options. The environment used
for CPU tests was `/home/marc/.venvs/uos-tests/bin/python`; emulator and hardware
helpers still have developer-machine dependencies, which remain an SDK gap.

[Input profiling](display/input-profile.json) records actual assembled graphics
work in the display model: initial selector entry uses 9,113,723 CPU cycles;
inserting a filename character uses 576,587. These are model cycle counts,
not physical timings. Rendering and input throughput still need improvement.

## Physical C128 workflow

**PASS** on the reference C128/Ultimate II+ at `192.168.1.237`, booting the final
distributable through `python3 -u hw_ultimate_check.py --editor`.
[hardware/report.json](hardware/report.json) records the complete run, exact
image/host-source hashes, transitions and cleanup. Five paired VDC/VIC captures
include [the selector](hardware/open-selector.png),
[filename entry](hardware/save-name.png),
[verified save](hardware/saved-verified.png) and
[existing-name rejection](hardware/existing-rejected.png).

The workflow creates one private USB directory containing two nested 112-byte
components and a 63-byte source basename. It opens 735 bytes, appends `OK` and
LF, and saves 738 bytes through a 273-byte OPEN command. It checks modal document
retention, existing-name rejection, cancel and dirty-discard behavior. Independent
raw-protocol reads compare the source and saved file after leaving the editor.
Cleanup restores both DOS directories, verifies the settings and resident file
instructions, deletes the exact owned files/directories and returns to the
desktop. Paired VDC captures must agree in the application area and restore all
borrowed RAM; VIC bitmap captures are stored alongside them. Every check passed.
The independent source and saved-file hashes were respectively
`af42f303054814d24041125086ee926b0e2b4400acc2e5825012ddefe9849ade` and
`4308e7d189d4aec90b7606c9f001516f46891c5415c8516c2a378e19322d2c03`.
Both files and all three directories were removed. Settings, resident file
instructions and both original DOS directories were restored; the desktop was
live. Drive inventory matched before and after: system D64 on A/IEC 8, B/IEC 9
empty, Software IEC at 10 and disabled printer emulation at 4.

Completion observation times include deliberate quiet intervals and must not
be interpreted as operation benchmarks. The physical test uses injected keys;
mouse hit testing is covered by CPU execution, not a new physical mouse trial.

## Failures retained with their recoveries

The [first attempt](before-initial-clear-fix/hardware/report.json) used the
previous renderer/editor binaries, retained in `before-initial-clear-fix/`.
Its captures exposed a title fragment above the modal selector. The final
renderer clears that strip explicitly, and the actual-graphics test checks it.
The host then falsely rejected exit because it treated the desktop's app ID as
an active-app count. IRQ samples proved that the desktop was already running.
Separate raw reads verified all 735 source and 738 saved bytes before the exact
fixture was removed. The failed attempt remains `passed: false`.

The [second attempt](load-stall/hardware/report.json) used the final image and
completed a verified save, then stalled during the next selector's IEC LOAD.
The [state analysis](load-stall/analysis.json) records an intact editor and
document, a library missing its final loaded byte, no owned file or directory
lease, and stack returns consistent with KERNAL serial receive. Its IRQ sampler
did not complete. The test helper was polling C6 immediately after publishing
F1, before its intended quiet interval; the corrected helper waits first.
This identifies an observation-timing defect but does not prove every IEC stall
has that cause. Serial/input/load soak testing remains required.
The subsequent complete run passed the repeated LOAD with the corrected input
driver and unchanged production binaries.

Recovery captured the complete document, restarted the unchanged test image,
proved the desktop foreground through IRQ samples, independently verified both
files and removed this run's exact fixture. That attempt also remains failed;
its recovery does not substitute for the final complete workflow.

## Remaining limits

This is still a C64-mode OS running on the C128. Native MMU/kernel services,
interactive 80-column desktop, larger cursor-editable documents, clipboard,
undo, shared IEC selection and the productivity suite remain open. Save As
creates a new file; it does not replace an existing one. Reopened comparison
proves observed bytes, not power-loss durability. Raw DOS clients must honor
the shared directory lease.

The earlier inaccessible 255-byte file component in
`/Usb0/uos-files-d03c9eb71227` remains a separate firmware cleanup issue recorded
in the [file-service validation](../2026-09-08-ultimate-files/README.md). It was
not altered by this checkpoint. No 511-byte physical filename support or blanket
expansion compatibility is claimed.
