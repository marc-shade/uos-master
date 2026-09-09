# Next native platform steps

The browser checkpoint leaves 139 bytes between resident code/data and the
page tables at `$3800`. The existing ABI, two-bank allocator and checked app
slot already support additional foreground applications, but cannot accommodate
a scheduler, driver registry and shared desktop toolkit as resident additions
without changing how the kernel is laid out. This is an implementation plan;
none of the proposed memory changes below are enabled by the browser build.

## 1. Establish resident growth without moving the public ABI

Keep the `$1c20` entry table, `$3800` ownership tables, `$3a00` transfer buffer,
`$3d00` mailboxes and `$6000` app entry stable. Audit the complete interval map,
including KERNAL workspaces, both displays, boot staging and test observers,
before assigning another resident region.

One candidate is bank 0 `$1300..$1bff`, 2,304 bytes currently excluded from the
heap. Commodore identifies that range for machine-language routines used with
BASIC. That makes it a candidate for this design, not proof that a changed
uOS boot/observer path works. [Commodore 128 Programmer's Reference Guide](https://www.pagetable.com/docs/Commodore%20128%20Programmer%27s%20Reference%20Guide.pdf)

The current native observer writes up to 2,000 bytes at `$1400`, so that range
cannot be assigned to resident code while retaining the present observer.
A growth experiment must provide explicit scratch ownership or bounded
captures elsewhere and preserve all interrupted CPU/MMU/IRQ state.

Keep the BASIC entry and PRG loading assumptions intact during the first
experiment. A relocated resident section needs a bounded startup copy from
declared staging storage, before the staging pages become available to the
heap. Account for both its final reservation and its peak boot footprint.
Longer-term modules need their own owner/lifetime records; this small range
alone is not a memory architecture for the complete OS.

Acceptance: assert every section bound in the build, check initialization on
CPU and cold boot, preserve current public addresses and usable heap accounting,
run all existing native workflows, and use a revised independent observer on
the physical C128. No test may save and restore memory over active kernel code.

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
