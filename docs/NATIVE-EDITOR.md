# Native banked text editor

Build with `python3 build-native.py`, boot `target/native/uos128.d64`, press
**B**, select **EDITOR** and press Enter. The editor is a checked ABI 1.3
application. It edits a document held in owned allocations across both C128
RAM banks, with a 24-bit byte position and length. Both displays show the
same document and cursor; the 80-column display shows more of each line.

| Key | Action |
|---|---|
| F1 | Open an IEC SEQ file or an absolute Ultimate path |
| F3 | Save As a new file, close it, reopen it and compare every byte |
| F5 | New empty document |
| F7 | Go to a hexadecimal byte offset, including offsets beyond `$ffff` |
| F2 / F4 | Beginning / end of document |
| F6 | Cycle D64, D71, D81 and Ultimate storage |
| F8 | Select IEC device 8–30, or Ultimate DOS context 1–2 |
| Arrow keys | Move by character or logical line; vertical movement retains the desired column |
| Home / Ctrl-E | Beginning / end of the current line |
| Del | Delete the character before the cursor |
| Enter | Insert the document's first observed newline convention; a new document uses CR |
| Esc | Cancel a prompt or return to Files and Apps; during I/O, cancel after a transfer |

Open and Save As accept an IEC filename of at most 16 characters, or an
absolute [Ultimate path](NATIVE-ULTIMATE.md) of at most 255 bytes. Long fields
and document names show their tail with `<` while retaining the complete path.
Enter confirms
a field and Esc cancels it. New, Open and exit ask before discarding a dirty
document. **N** keeps it; **Y** proceeds. An asterisk after the filename means
there are unsaved changes. Save As refuses an existing filename. There is no
overwrite operation in this version.

Imported CRLF, lone CR, lone LF, NUL and other bytes are preserved. CRLF is
one navigation/deletion unit; a Go To position between its bytes advances
past the pair. Nonprintable file bytes appear as dots. Typing inserts printable
single-byte characters; it does not provide a Unicode decoder. Lines remain
logical lines rather than wrapping into the document. The 16-row viewport
scrolls vertically and horizontally to keep the cursor visible; `<` and `>`
indicate clipped text.

The editor inherits the browser's data device and geometry. Changes made with
F6/F8 persist for IEC selections when returning to Files and Apps. The browser
returns to the system boot device/D64 after an Ultimate editor session; it still loads
its system image from the boot device. Choose geometry to match the mounted disk; automatic
drive/media detection remains part of the platform work.

## Memory and storage behavior

[`document.inc`](../src/native/document.inc) implements a gap buffer with two
independent document contexts. Each context owns up to 24 allocations of 4 KiB.
Logical length, cursor and gap boundaries are 24-bit values; local transfers
use at most 512 bytes. The format can address 96 KiB per context, but actual
capacity is lower when the application, workspace allocations, a second
document or fragmentation consume the heap. This is RAM-backed editing;
REU/disk-backed documents remain to be implemented.

Open fills the pending context while retaining the current document. Only
complete input and a successful CLOSE permit the switch. Missing files,
allocation failure, cancelled input and read errors release the pending
context and retain the original document, cursor, name and dirty state.
Consequently, replacing a large document can run out of memory even when
that file could be opened after explicitly choosing New.

Save As clears dirty state and changes the filename only after an exclusive
create, full write, CLOSE, complete reopen comparison and read CLOSE succeed.
A failed or cancelled save retains the document and reports that a partial
file may remain. It neither retries uncertain data nor deletes that file.
An uncertain IEC CLOSE retains the file service's ownership record and can
block subsequent file actions; reset/recovery of those retained resources is
still a platform limitation. It must not be described as a successful save.

The IEC backend uses standard KERNAL calls and walks the file's sector chain
before reading. On the reference C128/Ultimate II+, opening 66,053 bytes took
295.976 seconds through the emulated 1541 and 38.311 seconds through native
Ultimate DOS. Save As of the edited 66,056 bytes, including a complete reopen
comparison, took 523.278 and 78.891 seconds respectively. Reopening the Ultimate
file through DOS context 2 took 38.312 seconds. These are hardware-harness
workflow times, including a 30-second initial quiet interval and 2-second
polling; they exclude entering the path and are not isolated throughput tests.
Esc is polled between data transfers; the IEC extent walk and individual
KERNAL calls remain blocking. Ultimate mode verifies each write before the
editor's full reopen comparison. Faster IEC paths and finer cancellation remain
required.

The preceding Ultimate checkpoint measured about 26 seconds for ten queued
filename characters with a small document and 46 seconds with the cursor beyond
64 KiB. The editor now updates field/status row 6 directly through the native
ROM cursor-positioning call. Field edits, deletion, cancellation and range-error
messages leave the document and its read cache alone. Each field update emits
at most one row per display, including spaces that erase a shortened value.

Ordinary byte edits and cursor moves within the current viewport redraw the old
and new caret rows plus mutable headings/status. Scrolling, line splits/joins,
new documents and file-operation returns use the complete renderer. The two
displays keep the same viewport and byte-preserving document model.

Two 512-byte read pages prevent repeated banked reads around a page boundary;
one uses the existing document output buffer and the other is private app RAM.
Edits and file-operation returns invalidate both pages. A failed cache fill
invalidates them as well. Seventeen 24-bit line offsets describe the visible
rows and their end. Single-byte edits adjust later offsets with carry/borrow;
structural changes rebuild the table. Cursor-only updates retain valid pages.
The [redraw checkpoint](validation/2026-09-09-native-redraw/README.md) records
CPU work counts, complete frame comparisons and physical timing qualification.
On the reference C128, ten queued field characters take 1.230 seconds in the
small document and 1.229 seconds beyond 64 KiB, including a 0.1-second quiet
interval. With the preceding 4-second interval retained, all 31 ordinary
ten-character queues take 4.194–4.198 seconds (median 4.196), compared with
25.705–45.988 seconds (median 26.632) previously. These elapsed times include
host monitoring; they are not isolated keyboard or CPU benchmarks.

Allocation failure occurs before an edit mutates logical bytes. Unexpected
handle/transfer failure poisons that context; subsequent reads/edits/saves
reject it instead of treating uncertain memory as a valid document. Cleanup
retains failed handles for a later release attempt. Ordinary application exit
uses the kernel's owner cleanup for both contexts and the application image.

The current app occupies `$6000..$8fa7` (12,200 payload bytes, 48 heap pages).
The redraw code and cache add five allocated pages (1,280 bytes); document
capacity still depends on the remaining heap and 4 KiB allocation fragmentation.
The kernel reserves 4 KiB for Ultimate services and manages 426 heap pages.
The existing public file entries dispatch both backends; ABI 1.3 adds the
Ultimate path/status mailboxes. Boot, calculator and browser PRGs are unchanged.

## ROM integration

The native ROM normally expands programmable function keys. The editor saves
all 256 bytes of the definition table, installs one returned code per key,
and restores the original table on controlled exit. Table updates mask IRQs
and clear pending expansion state. The tests exercise the real ROM GETIN
expansion path; they do not claim to simulate a physical key switch.
The memory layout and expansion behavior come from Commodore's editor source:
[declarations](https://github.com/mist64/cbmsrc/blob/master/EDITOR_C128/declare.src),
[key definitions](https://github.com/mist64/cbmsrc/blob/master/EDITOR_C128/ed6.src),
and [input/output routines](https://github.com/mist64/cbmsrc/blob/master/EDITOR_C128/ed1.src).

Literal text output clears the ROM quote flag before each CHROUT. This keeps
reverse-video cursor controls working inside quoted text. Complete VIC and VDC
screen comparisons cover that behavior through the actual ROM.

## Qualification and remaining work

The [redraw checkpoint](validation/2026-09-09-native-redraw/README.md) records
the current images and display performance checks. The
[Ultimate checkpoint](validation/2026-09-09-native-ultimate/README.md) records
the unchanged kernel/backend and its initial physical C128 USB timings. The preceding
[IEC editor checkpoint](validation/2026-09-09-native-editor/README.md) records
the initial observation failure with its correction and the IEC timing baseline.

Use an environment with Py65 for the CPU models, and VICE/64tass for emulator
checks:

```sh
python3 tests/ci_native_document.py --report /tmp/native-document.json
python3 tests/ci_native_editor.py --report /tmp/native-editor.json
python3 tests/ci_native_editor_ultimate.py --report /tmp/native-editor-ultimate.json
python3 tests/ci_native_editor_redraw.py --report /tmp/native-editor-redraw.json
python3 -u tests/run_ci.py nativeeditor nativeeditor71 nativeeditor81
python3 -u hw_ultimate_check.py --native-editor
python3 -u hw_ultimate_check.py --native-ultimate
python3 -u hw_ultimate_check.py --native-redraw
```

The physical commands require the reference machine's deployed, idle legacy
desktop and restore that desktop and settings. `--native-editor` mounts a
private test D64 and then reads back the closed test disk through Ultimate DOS.
`--native-ultimate` uses a new private USB directory and independently compares
all five closed source/output files before removing its fixtures.
`--native-redraw` adds field/cursor timing checks to that complete USB workflow.
A completed IEC workflow can resume only its independent readback with
`--native-editor-readback /path/to/report.json`.
Editor metadata is captured by the C128 CPU into bounded low-memory chunks;
the host also retains direct DMA observations for comparison. The earlier IEC
checkpoint recorded a 109-byte direct snapshot matching BASIC ROM. The redraw
checkpoint records two more complete ROM snapshots, of 128 and 587 bytes, while
the corresponding CPU snapshots and screens match the document. The host uses
CPU captures as its editor-state oracle and retains these ROM comparisons.
The native app may use RAM occupied by the inactive legacy settings record.
After rebooting the legacy desktop, the harness checks its active settings fields and restores
the saved record's header and reserved bytes as well.

Selection, clipboard, undo/redo, find/replace, visual file dialogs, document
associations, multiple open tabs and session recovery remain open. Fonts,
styles, pagination, images, spelling and printing belong to the word processor
work. The [completion roadmap](IMPLEMENTATION-ROADMAP.md) retains those
requirements along with the native desktop, Ultimate services and expansion
drivers. This text editor is one application milestone toward that scope.
