# Native banked text editor

Build with `python3 build-native.py`, boot `target/native/uos128.d64`, press
**B**, select **EDITOR** and press Enter. The editor is a checked ABI 1.2
application. It edits a document held in owned allocations across both C128
RAM banks, with a 24-bit byte position and length. Both displays show the
same document and cursor; the 80-column display shows more of each line.

| Key | Action |
|---|---|
| F1 | Open a named SEQ file on the selected IEC device |
| F3 | Save As a new SEQ file, close it, reopen it and compare every byte |
| F5 | New empty document |
| F7 | Go to a hexadecimal byte offset, including offsets beyond `$ffff` |
| F2 / F4 | Beginning / end of document |
| F6 | Cycle D64, D71 and D81 geometry |
| F8 | Select IEC device 8–30 |
| Arrow keys | Move by character or logical line; vertical movement retains the desired column |
| Home / Ctrl-E | Beginning / end of the current line |
| Del | Delete the character before the cursor |
| Enter | Insert the document's first observed newline convention; a new document uses CR |
| Esc | Cancel a prompt or return to Files and Apps; during I/O, cancel after a transfer |

Open and Save As accept a filename of at most 16 characters. Enter confirms
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
F6/F8 persist when returning to Files and Apps. The system browser image still
loads from the boot device. Choose geometry to match the mounted disk; automatic
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

The current backend uses standard KERNAL IEC and walks the file's sector chain
before reading. On the reference Ultimate drive in 1541 mode, the 66 KB Open
took about 296 seconds and Save As with verification about 523 seconds under
the hardware harness. Esc is polled between data transfers; the initial extent
walk and individual KERNAL calls remain blocking. A native Ultimate file backend,
faster IEC paths and finer cancellation are still needed.

Allocation failure occurs before an edit mutates logical bytes. Unexpected
handle/transfer failure poisons that context; subsequent reads/edits/saves
reject it instead of treating uncertain memory as a valid document. Cleanup
retains failed handles for a later release attempt. Ordinary application exit
uses the kernel's owner cleanup for both contexts and the application image.

The current app occupies `$6000..$87d4` (10,197 payload bytes, 40 heap pages).
The kernel, boot, calculator and browser PRGs are unchanged from the resident
relocation checkpoint. The stock disk adds EDITOR; no public ABI entry changed.

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

The [editor checkpoint](validation/2026-09-09-native-editor/README.md) records
exact images, CPU and emulator checks, physical C128 readback and the initial
observation failure with its correction.

Use an environment with Py65 for the CPU models, and VICE/64tass for emulator
checks:

```sh
python3 tests/ci_native_document.py --report /tmp/native-document.json
python3 tests/ci_native_editor.py --report /tmp/native-editor.json
python3 -u tests/run_ci.py nativeeditor nativeeditor71 nativeeditor81
python3 -u hw_ultimate_check.py --native-editor
```

The physical command requires the reference machine's deployed, idle legacy
desktop. It mounts a private test D64, restores that desktop and settings, and
then reads back the closed test disk through Ultimate DOS. A completed native
workflow can resume only its independent readback with
`--native-editor-readback /path/to/report.json`.
Editor metadata is captured by the C128 CPU into bounded low-memory chunks;
the host also retains direct DMA observations for comparison. During physical
qualification a complete 109-byte direct snapshot matched BASIC ROM at the
requested application RAM address, while the CPU snapshot and screens matched
the document. Direct cartridge reads are therefore not the editor-state oracle.
The native app
may use RAM occupied by the inactive legacy settings record. After rebooting
the legacy desktop, the harness checks its active settings fields and restores
the saved record's header and reserved bytes as well.

Selection, clipboard, undo/redo, find/replace, visual file dialogs, document
associations, multiple open tabs and session recovery remain open. Fonts,
styles, pagination, images, spelling and printing belong to the word processor
work. The [completion roadmap](IMPLEMENTATION-ROADMAP.md) retains those
requirements along with the native desktop, Ultimate services and expansion
drivers. This text editor is one application milestone toward that scope.
