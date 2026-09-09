# Native Files and Apps

Press **B** in the native memory workspace to browse files and launch native
applications. The same file list and byte viewer appear on the complete
40- and 80-column screens. Build with `python3 build-native.py` and boot
`target/native/uos128.d64`; it contains `U`, `CALC` and `BROWSE`.

## Controls

| Key | Action |
|---|---|
| Up / Down | Select the previous / next file |
| N / B | Move forward / back eight entries |
| A | Select the next discovered native application, wrapping at the end |
| Enter | Launch a selected APP, otherwise inspect the file |
| I | Inspect file bytes, including a native application's PRG header |
| R | Refresh the root directory |
| D | Enter an IEC device number, 8–30; Enter accepts, Del edits, Esc cancels |
| F | Cycle the explicit D64 / D71 / D81 format |
| Esc | Return from the file list to the memory workspace |

The list shows the stored name, file type and allocated block count. `*` marks
an unclosed file and `<` marks a locked file. Choose the actual disk format;
the selector does not identify hardware or guarantee support for every IEC
device. Root directories on standard D64, D71 and unpartitioned D81 images
are supported. Folders and partitions require further backend work.
The stream API accepts printable filenames without wildcard or DOS command
syntax. Other stored names remain visible, but opening them reports an error.
Only trailing shifted-space padding is removed; an embedded shifted-space
must never select a different file with a shorter name.

The byte viewer reads closed SEQ, PRG and USR files, showing up to 128 bytes
per page as hex with a safe PETSCII column. Control and high bytes appear as
dots; the hex values preserve their exact values. PRG load-address bytes are
included. The header shows a 32-bit byte offset; row labels show its low
16 bits. **Enter/N** reads the next page and **Esc** returns to the selected
file. Empty files and a final short page report end of file and close their
streams. A read failure shows the accepted prefix and an error. The current
viewer is forward-only; seek, previous-page navigation and editing remain open.

## Discovering and returning from applications

A closed PRG is labelled APP when its first 34 bytes are readable and begin
with the `$6000` load address and `NAPP` magic. This is discovery only. The
[application loader](NATIVE-APPS.md) validates the full manifest, ABI, declared
length and checksum before execution. A damaged or incompatible image can
therefore appear as APP and be rejected when launched.

Launching releases the browser's code allocation and directory cache before
loading the selected app. A normal app return reopens the browser from the
boot disk. The selected data device and format survive; the row selection
starts at the first file. Load errors with completed cleanup also return to
the browser and display the error. Uncertain resource cleanup retains the
owner and returns an error to the workspace; recovery still needs a dedicated UI.

For example, a calculator PRG named `NUMBER` on device 9/D71 can be discovered
and launched without adding a fixed launcher entry. Its **S** command writes
and verifies history on that source device/format. **Esc** returns to BROWSE
on the boot disk while keeping the device-9/D71 file list preference.

## Resources and current limits

BROWSE is a 3,416-byte image plus its two-byte PRG address. It reserves 16
bank-0 pages for code/data and 37 bank-1 pages for 296 compact directory
records. Its 16-bit count and selection cover the complete root-D81 capacity.
Workspace allocations remain owned across browser/app handoffs. Exit closes
owned files before releasing memory. Neither a mouse nor an REU is required.

The [directory API](NATIVE-FILES.md#directory-pages) rewalks from the root for
each page. Reading all 37 D81 pages can require 703 directory-sector reads,
plus file extent/header probes for PRGs. A persistent cursor and performance
work are needed for large directories. Enumeration has geometry bounds, but
there is no removable-media identity check or resumable background scan.

This application adds a native file list, app discovery and byte inspection.
Native copy/rename/delete, shared file dialogs, file associations, document
editing, GUI controls, scheduling and migration of the Ultimate desktop
services remain on the [completion roadmap](IMPLEMENTATION-ROADMAP.md).

## Validation

```sh
python3 tests/ci_native_directory.py --report /tmp/native-directory.json
python3 tests/ci_native_browser.py --report /tmp/native-browser.json
python3 -u tests/run_ci.py nativebrowse nativebrowse71 nativebrowse81
python3 -u hw_ultimate_check.py --native-browser
```

CPU tests require Py65. The emulator workflows use true 1541/1571/1581 drive
emulation, compare both complete screens and independently extract saved bytes.
The physical test uses a private D64 on the reference C128/Ultimate II+,
restores the legacy desktop, then reads back the complete closed disk through
Ultimate DOS for independent file comparisons. It does not qualify physical
D71/D81 drives. See the [dated evidence](validation/2026-09-09-native-browser/README.md)
for exact builds, outcomes and retained failed observations.
