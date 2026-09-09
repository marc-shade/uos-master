# Next native platform steps

The browser checkpoint left 139 bytes before the page tables at `$3800`.
The [resident-growth checkpoint](validation/2026-09-09-native-relocation/README.md)
now moves the allocator to `$1300`, leaving 1,321 main-region bytes and 1,082
low-region bytes for further resident code/data. It retains the public ABI and
442-page heap. The native banked text editor now uses that heap; shared desktop
services are next. Scheduling and a larger module architecture remain required.

## 1. Resident growth and its remaining limits

The `$1c20` entry table, `$3800` ownership tables, `$3a00` transfer buffer,
`$3d00` mailboxes and `$6000` app entry remain stable. Future assignments still
need an interval audit covering KERNAL workspaces, both displays, boot staging
and observers; use the generated `target/native/layout.json` as the current map.

The low region is bank 0 `$1300..$1bff`, 2,304 bytes excluded from the heap.
Commodore identifies that range for machine-language routines used with BASIC.
[Commodore 128 Programmer's Reference Guide](https://www.pagetable.com/docs/Commodore%20128%20Programmer%27s%20Reference%20Guide.pdf)

The observer now borrows the shared transfer buffer for 512-byte chunks,
restores its contents and checks that the low kernel remains intact. Its old
`$1400` output path must not be used with this kernel. Host captures reject
RAM0 sources overlapping their borrowed output or probe workspace.

The BASIC entry remains intact. Startup copies five pages from declared
staging at `$3e00..$42ff` into the low region before initializing the heap.
The heap can then reuse `$4000..$42ff`; those pages are not resident reservations.
Further growth must continue accounting for both final and peak boot footprints.
Longer-term modules need their own owner/lifetime records; this small range
alone is not a memory architecture for the complete OS.

The checkpoint records the section bounds, startup/IRQ/staging tests, existing
native workflows and revised observer qualification. No test may save and
restore memory over active kernel code. The two small resident regions are a
next-step capacity increase, not the complete scheduler/driver memory architecture.

## 2. Extend the banked document model and native editor

The [native editor](NATIVE-EDITOR.md) uses the existing heap/file ABI for owned
4 KiB chunks, with 24-bit logical length separate from capacity. It preserves
CRLF/lone CR/lone LF and other imported bytes, provides cursor/viewport editing,
retains the original document after a failed Open and verifies Save As by a
complete reopen comparison. Both contexts and the app share an explicit owner.

Add selection, clipboard, undo/find and session recovery next to the shared
dialog/input work. REU/disk backing is still required for documents exceeding
available base RAM. The word processor's layout/format/printing requirements
remain separate.

The base workflow crosses a 64 KiB logical offset, saves and reopens the edited
bytes, and preserves unrelated allocations. Keep those checks when extending it.
Compare saved bytes independently, include allocation and transfer failures,
and retain document ownership across reusable dialogs. An uncertain CLOSE
currently quarantines the owner; provide an explicit recovery path before
claiming media-failure recovery is complete.

## 3. Share input, dialogs and backend state

Extract reusable field/list/viewport behavior from real applications rather
than adding unused kernel stubs. Define events and focus for both displays,
then an Open/Save As contract that keeps the caller's document allocated.
Unify loader and stream backend ownership; add persistent directory cursors,
media identity, operation progress/cancel and recovery from retained errors.

Acceptance: browse a data drive, return to an intact document, save through
the selected backend, and reopen the system browser from its boot device.
Repeat with missing media, full disks and directory/transfer failures. Measure
large-directory I/O and redraw cost before claiming performance improvements.
The editor's physical 66 KB workflow also records roughly 296-second Open and
523-second verified Save As through standard 1541 IEC. Reduce repeated extent
I/O, add cancellation within long operations and integrate the native Ultimate
file backend; keep the complete byte comparisons when measuring improvements.

## 4. Migrate the desktop and Ultimate services

Move the existing graphical desktop, cartridge file/control service, drive
panel, network/RTC behavior and applications onto the versioned native services.
Then add scheduling, REU/expansion allocation and the productivity suite using
the full [completion roadmap](IMPLEMENTATION-ROADMAP.md) as the acceptance
checklist. Keep the existing legacy images available until their native
workflows have matching functional and physical evidence.

Each step requires its own exact-image checkpoint. A successful prototype or
one tested expansion does not complete the application, desktop or hardware
rows in the broader roadmap.
