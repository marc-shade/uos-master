# Desktop cartridge-file copy

The Ultimate browser's C / Copy action loads an exclusive-copy dialog from
the system disk. It retains the complete selected source name and accepts an
editable destination path. Copied/checked counters and cancellation cover both
the initial transfer and a full comparison after closing/reopening both files.
Success requires the final closes too. Existing destinations are rejected;
unverified new files are retained. See the [user/API guide](../../ULTIMATE-FILES.md#desktop-copy).

## Build

| Artifact | PRG bytes | Resident/load span | SHA-256 |
|---|---:|---|---|
| `uos-copy.prg` | 2,815 | `$5000–$5afc` | `c57cd09f1fd0c42fee755edf2498154d3b4158b11f1fb2e46610df0eb0131ddd` |
| `uos-ultimate.prg` | 6,146 | `$5000–$67ff` | `531fa52ecff0f93625580ae2d39a2a581aa7bbfe2386488d1f7a78428f9d32a7` |
| `uos-desktop.prg` | 12,385 | `$1000–$405e` | `0dc4786d5d4ab96c3c5e498a82d7ccca9fc00bd9ce7559e085f5704e67cd8189` |

The D64 SHA-256 is
`ff96db90aa9dc1fa11132f31e5f87e5c5e4012ae257e4c09063281c1c2fba74f`.
[disk.json](disk.json) records extraction and byte comparison of all 16 PRGs,
their bounds/hashes, and an unchanged source disk. Both build scripts package
the same module list; the Windows script was inspected, not executed here.
The core, shared file service and other drivers are unchanged from the
[preceding file-service checkpoint](../2026-09-08-ultimate-files/README.md).

The new module is hidden from Apps and loads only through the browser.
It uses the core's original-device loader and owns separate source/destination
buffers while active. An eight-byte versioned handoff preserves page/row and
system IEC device across reloads. Both overlay entries reset dead stack frames.
The browser still retains eight complete 511-byte names; its cache was not reduced.

## CPU, display and packaging evidence

- [copy/report.json](copy/report.json): the assembled dialog, core launch path,
  service and UCI transport copied/verified all 66,053 bytes with a 511-byte
  source name. Thirty-three overlay round trips retained stack/app registration.
  A separate run restored page ordinal 256 and selected row 2.
- The same suite checks a full 893-byte destination, insertion/deletion across
  memory pages, raw letter case, mouse release actions, empty files, failed
  module LOAD, and invalid handoff without I/O. Fourteen failure/cancel cases
  include existing names, short reads/writes, disk full, corruption after CLOSE
  including the last byte, changed source size, initial/final close failures,
  cancellation during copy/verification, foreign handles, relative paths and
  unsafe long components. An idle error dialog sends no retry commands.
- Whole VIC bitmap and VDC memory comparisons cover editing and browser return.
  Mixed-width glyphs and scrolling put actual caret pixels at X=296, 288, 280,
  24 and 32, as required by eight-pixel path cells. Retained screens:
  [editing](copy/edit.png), [verified](copy/verified.png),
  [browser](copy/browser.png), with corresponding raw VIC/VDC files.
- [browser.json](browser.json): all ten browser/drive-panel groups pass with
  the final browser hash. [viewer.json](viewer.json): 683 pages across 64 KiB,
  mouse actions, faults and two complete display round trips pass.
- [desktop.json](desktop.json): launcher controls/coordinates/callbacks pass;
  the actual application filter classifies all 16 built modules and hides Copy.
- [emulator-results.json](emulator-results.json): x128 in C64 mode passed all
  15 companion-display checks. [vdc/](vdc/) retains its log/screens. This run
  used the disk before the copy-only cursor/repaint changes; the core, desktop,
  browser and all apps exercised by that suite have identical final bytes.
  The copy dialog itself requires UCI and is covered by its CPU/hardware tests.

## Final physical C128 run

`python3 -u hw_ultimate_check.py --files` completed with **HW-FILES PASS** and
exit status 0 on the final build. [hardware/report.json](hardware/report.json)
records the entire workflow, including native fixture creation/copy and viewer
regressions before the shipped Copy dialog ran through its normal IEC loader.

The source has a 63-byte basename and a 321-byte absolute OPEN command across
two nested 112-byte directory components. The dialog copied and fully compared
66,053 bytes. Completion was observed after 122.97 seconds, including the initial
30-second quiet period, with sparse RAM observations thereafter. This is a
test-observed time, not an uninterrupted performance benchmark.

The default existing destination was rejected with `$ff` / `FILE EXISTS` and
remained byte-identical. Editing the leaf name across the 255/256 boundary
created `ui-copy.bin`; the dialog reported **Copy verified** only with both
counters at `$00010205` and both handles released. A further copy was cancelled
during transfer with `$00000400` bytes copied and zero checked. Its unverified
file was retained. Return reloaded the browser with the source selected.

After returning to the desktop, independent raw UCI reads compared every byte
of the existing destination, the new desktop copy and the 1,024-byte cancelled
prefix against the host-generated oracle. The complete-file SHA-256 is
`f7b3bdd0b90e566a737be5d51bc052a1de2eeb6ff9f936cfcc64786aad148698`.
Retained screens show [verified copy](hardware/copy-verified.png),
[cancelled copy](hardware/copy-cancelled.png), and
[existing-name rejection](hardware/copy-existing.png). Their raw VIC and paired
VDC captures are stored beside them. [hardware-static-fields.json](hardware-static-fields.json)
also compares every pixel in five fixed fields across all three dialog states.

All four private files and three private directories for this run were removed.
Both CWDs and settings were restored, resident file instructions remained
unchanged, every capture restored its borrowed RAM, and the desktop remained
live. No RAM-read retries were needed. The final
[read-only drive snapshot](hardware/final-drives.json) shows system A at IEC 8
and empty B at IEC 9; SoftwareIEC 10 and disabled printer 4 were not changed.
This run's private root was `/Usb0/uos-files-c6f5c2223b1c`.

## Repaint cost and the first hardware run

The first version drew the path with a proportional font but positioned its
caret with spaces. That drifted on mixed-width names. Both now use matching
eight-pixel cells on VIC; VDC already supplies character cells.

The first physical workflow also exceeded the copy-completion wait (30 seconds
quiet plus 180 seconds polling). Its recovery cancelled the active operation,
returned to the desktop, removed all of that run's private files/directories,
restored both working directories/settings and checked resident instructions.
It had already passed independent native source/copy readback, viewer checks
and desktop existing-name rejection. Evidence is retained in
[before-cursor-fix/hardware/report.json](before-cursor-fix/hardware/report.json)
and [hardware-result.json](before-cursor-fix/hardware-result.json).
There is no successful desktop-copy claim for that run.

Real-graphics CPU measurement showed excessive repaint cost. The final code
accounts for bytes and checks cancellation after every block, but repaints
counters every 4 KiB and at every phase/error/completion. The hardware helper
also observes long operations once per second after the initial quiet period,
with the same completion deadline, to reduce CPU stops caused by RAM DMA.

| Bytes copied and compared | Before, CPU cycles | After, CPU cycles |
|---:|---:|---:|
| 768 | 7,370,873 | 4,987,323 |
| 4,096 | 16,939,685 | 8,626,608 |

[progress-timing.json](progress-timing.json) executes actual graphics, file
client and transport with immediate modeled UCI/VDC readiness. These are CPU
counts, not physical wall times: IRQs, VIC bad lines and host DMA pauses are
excluded. The timeout diagnosis is consistent with these measurements; no
progress snapshot was retained at the first timeout to attribute all its delay.
Both CPU timing versions include aligned path cells; only the progress repaint
frequency differs. The final hardware run completed within the original deadline.

## Scope limits

This is one cartridge-file copy with a typed destination path. Folder picking,
batch/recursive copying, resume, safe partial-file removal, shared Save As,
an IEC adapter and mounted-media identity/recovery remain open. The final
comparison does not guarantee atomic snapshots during concurrent modification
or power-loss durability. The shared service retains its 127-byte creation
component limit and 511+1 USB-sector-write workaround.

The known empty 255-byte-name fixture from the preceding firmware investigation
at `/Usb0/uos-files-d03c9eb71227` remains separate from these tests. Cartridge
lookup cannot address it for removal; direct access to that USB volume is still
needed. None of these tests mutates that directory or unrelated user files.

Native C128 kernel/banking, interactive 80-column desktop, GEOS/Wheels application
parity and broader expansion certification remain required by the
[implementation roadmap](../../IMPLEMENTATION-ROADMAP.md).
