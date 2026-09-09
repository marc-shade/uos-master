# Next native platform steps

The browser checkpoint left 139 bytes before the page tables at `$3800`.
The [resident-growth checkpoint](validation/2026-09-09-native-relocation/README.md)
now moves the allocator to `$1300`, leaving 1,321 main-region bytes and 1,082
low-region bytes for further resident code/data. It retains the public ABI and
442-page heap. Native document editing and shared desktop services are the next
implementation steps; scheduling and a larger module architecture remain required.

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

## 2. Build a banked document model and native editor

Use the existing heap/file ABI for document chunks, with explicit logical
length separate from allocated capacity. Define byte-preserving CR/LF handling,
cursor/viewport positions, dirty state and allocation-failure behavior before
adding selection, clipboard and undo. Start with a bounded plain-text editor;
the word processor's layout/format/printing requirements remain separate.

Acceptance: open, edit, save, close and reopen documents beyond the legacy
768-byte limit, then cross a 64 KiB logical offset using multiple allocations.
Compare complete saved bytes independently. Existing files, cancelled operations
and dirty documents must have explicit outcomes; do not label KERNAL-accepted
output as verified storage. Retain document ownership across reusable dialogs.

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
