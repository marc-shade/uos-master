# Next native platform steps

The browser checkpoint left 139 bytes before the page tables at `$3800`.
The [resident-growth checkpoint](validation/2026-09-09-native-relocation/README.md)
moved the allocator to `$1300`. The native Ultimate backend now reserves an
additional 4 KiB at `$4000..$4fff`; the remaining heap has 426 pages. Public
entry addresses and the `$6000` app slot remain stable. The current main region
has 402 free bytes, the low region has 1,082, and the service region leaves
904 bytes before the retained browser path at `$4a00`. The ABI 1.5 directory
cursor shares the owned stream API and supports native folder navigation.
Shared input/dialog services are next. Scheduling and a larger module
architecture remain required.

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
The [native editor redraw checkpoint](validation/2026-09-09-native-redraw/README.md)
replaces full repaint for fields and ordinary edits/cursor motion with affected
rows. A second read page and cached line offsets remove repeated banked reads.
It retains full repaint for structural changes and viewport movement. Keep the
complete VIC/VDC comparisons for clipping, deletion, cancellation, line-offset
carry/borrow and document cursor movement when extracting these services.
The physical ten-character filename queues now take about 4.20 seconds versus
26–46 seconds previously, with the same 4-second quiet interval. Extra checks
with a 0.1-second quiet interval take about 1.23 seconds in both small documents
and positions beyond 64 KiB. Continue measuring both cases; isolate device
throughput from UI and observation cost before making broader performance claims.
Loader, stream and Ultimate directory ownership are now shared; add media
identity, operation progress/cancel across the remaining backends and recovery
from retained errors.

Acceptance: browse a data drive, return to an intact document, save through
the selected backend, and reopen the system browser from its boot device.
Repeat with missing media, full disks and directory/transfer failures. Measure
large-directory I/O and redraw cost before claiming performance improvements.
The older editor checkpoint recorded roughly 296-second Open and 523-second
verified Save As through standard 1541 IEC. The [native Ultimate backend](NATIVE-ULTIMATE.md)
now supplies raw absolute-path streams and verified writes to the editor.
The browser's absolute-path field now launches USB apps through the shared
backend, and the calculator saves beside its USB image. ABI 1.5 adds owned
directory cursors, complete names, canonical paths, checked cancellation/CWD
restoration and browser folder navigation. Extract a common file picker while
keeping a caller's document allocated. Reduce IEC extent I/O and add cancellation
within long operations. Keep complete byte comparisons and state the harness's
quiet/poll intervals when measuring timing.

The implemented directory contract makes these lifetimes explicit:

* A caller owns its cursor, complete selected name, path and cached records.
  Abbreviated display text must never become an OPEN target.
* A scan owns a DOS context and the active READ_DIR transaction until the final
  packet or checked cancellation. The UCI transport is shared across both DOS
  contexts, so even other-context file calls must wait while packets remain
  pending. File operations and another scan must not reuse the reserved context.
* Capture the selected context's original CWD, restore it on checked CLOSE,
  and retain the owner if restoration is uncertain. EOF alone leaves ownership
  intact; the browser closes its cursor at EOF or when abandoning the scan.
* Bound packet size, entry count and RAM use. Report a partial list explicitly;
  do not treat exhaustion, timeout or malformed response as end of directory.
* Preserve the visible browser page and selection during an incomplete scan.
  Empty/large directories, long and quoted names, parent navigation, cancellation,
  foreign transactions, absent media and failed CWD restoration have dedicated
  CPU cases. A shared dialog must additionally preserve its caller's document.

The service uses existing OPEN/READ/CLOSE entries with format 3/mode 2.
The source
inspection above uses `1541ultimate` revision
`a01c04e8267a0d916b7203cb34dcf1127f75981d`,
[`software/filemanager/dos.cc`](https://github.com/GideonZ/1541ultimate/blob/a01c04e8267a0d916b7203cb34dcf1127f75981d/software/filemanager/dos.cc).
The [documented DOS commands](https://1541u-documentation.readthedocs.io/en/master/uci/ultimate_dos_target.html)
describe the transport operations; physical qualification remains specific to
the recorded cartridge and firmware observations.
FILE_INFO can establish that no file is open; it cannot establish that a
foreign client has no retained directory snapshot. The native service claims
the selected context's idle snapshot for uOS; a future broker must coordinate
that ownership with other clients. It preserves foreign files and active UCI
transactions. See the [full contract](NATIVE-ULTIMATE.md#directory-cursors--abi-15).

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
