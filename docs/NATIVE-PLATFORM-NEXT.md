# Next native platform steps

The browser checkpoint left 139 bytes before the page tables at `$3800`.
The [resident-growth checkpoint](validation/2026-09-09-native-relocation/README.md)
moved the allocator to `$1300`. The native Ultimate backend now reserves an
additional 4 KiB at `$4000..$4fff`; the remaining heap has 426 pages. Public
entry addresses and the `$6000` app slot remain stable. The current main region
has 1,256 free bytes, the low region has 1,082, and the service region leaves
1,527 bytes between its code and command buffer. Shared directory/loader/dialog
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
staging at `$5000..$54ff` into the low region before initializing the heap.
The heap can then reuse all five staging pages. `$4000..$4fff` remains reserved
for Ultimate services. The bank-0 workspace block occupies `$c000..$dfff`
beneath ROM and is accessed through the CPU's native bank gateways.
Further growth must continue accounting for both final and peak boot footprints.
Longer-term modules need their own owner/lifetime records; this small range
alone is not a memory architecture for the complete OS.

The checkpoint records the section bounds, startup/IRQ/staging tests, existing
native workflows and revised observer qualification. No test may save and
restore memory over active kernel code. These resident regions are a
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
Replace full-screen redraw on every field/document character with bounded
updates to the changed rows. In the native Ultimate hardware harness, ten
queued filename characters took about 26 seconds for a small document and
46 seconds with the cursor beyond 64 KiB.
That measurement includes monitoring and is not an isolated keyboard benchmark;
the full redraw in each field-append path is explicit in the current source.
Measure both cases after the change and retain complete VIC/VDC comparisons
for long-field clipping, deletion, cancellation and document cursor movement.
Unify loader and stream backend ownership; add persistent directory cursors,
media identity, operation progress/cancel and recovery from retained errors.

Acceptance: browse a data drive, return to an intact document, save through
the selected backend, and reopen the system browser from its boot device.
Repeat with missing media, full disks and directory/transfer failures. Measure
large-directory I/O and redraw cost before claiming performance improvements.
The older editor checkpoint recorded roughly 296-second Open and 523-second
verified Save As through standard 1541 IEC. The [native Ultimate backend](NATIVE-ULTIMATE.md)
now supplies raw absolute-path streams and verified writes to the editor.
Add native Ultimate directory cursors and a common file picker, then route
application loading through the shared backend ownership model. Reduce IEC
extent I/O and add cancellation within long operations. Keep complete byte
comparisons and state the harness's quiet/poll intervals when measuring timing.

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
