# Shared Open and Save As

The text editor uses a shared cartridge file selector. **F3 Open** chooses an
existing text file. **F1 Save As** chooses a directory and creates a new file.
The editor stays in memory while the selector loads and runs.

In the selector, up/down choose a row and Enter opens a directory or selected
file. In Save As, **F1 / Name** edits the new filename in the current folder.
Enter creates it. Existing names are rejected, with the cartridge diagnostic
shown on screen. Esc first leaves filename entry, then cancels the selector.
The toolbar also supports mouse clicks, including rows beyond VIC x255.

**U** moves to the parent, **/** to root, **N/B** move between directory pages,
and **R** retries a listing. **P** switches the detail area between the complete
selected name and current path; left/right scroll by 32 bytes. **O** attempts
to enter the selected item as a directory, including an image filesystem.
Names are retained in full. A page holds up to eight entries; long names reduce
that count. Previous rescans page boundaries from the start, so navigation
needs no finite history stack. Directory ordinals are 16-bit. Esc cancels a
scan; retry explicitly reloads it.

Filename entry supports left/right, Home, Del and Ctrl-U. Cursor and text use
matching eight-pixel VIC cells. Unshifted letters enter lowercase ASCII;
shifted letters enter uppercase. A new leaf contains at most 127 printable
ASCII bytes, excludes FAT separators/reserved punctuation, and cannot end in
a space or dot. Creation passes the complete absolute path to UFS, which also
enforces its 127-byte limit on every parent component.

## Editor behavior

The editor holds up to **768 bytes**. Cartridge Open accepts printable ASCII,
CR and LF; other bytes and larger files are rejected without replacing the
current document. Existing CR/LF bytes are preserved; CRLF displays as one
newline. Typed Return inserts LF. Unsupported font glyphs display as dots;
their file bytes remain intact. Editing currently appends text or removes the
last byte with Del, and the view follows the end of a long note.

On entry, the editor still imports `NOTES.T` from the system IEC disk if it
finds a valid bounded note. It converts PETSCII letters and CR to ASCII and LF.
This import is read-only: the old scratch-and-rewrite save path is removed.
Serial error, format and length failures leave an empty editor.

Open reads into a separate staging buffer. The old document is replaced only
after the complete text passes validation and its handle and temporary working
directory are released. Save As uses verified writes, closes the file, reopens
its absolute path, compares size and every byte, and closes again before
showing **Saved and verified**. A failure after creation retains the new file
and marks the document unsaved. Only CLOSE is retried; writes are never replayed.
This verifies observed cartridge contents, not power-loss durability.

**F5 New**, Open and Esc/Back ask before discarding unsaved text. Y discards;
any other key returns to the note. Cancelling a file selector keeps the note.
Cursor editing, selection, clipboard, undo, larger documents, an IEC selector
backend and safe replacement of existing files remain required.

## Application ABI, version 1

Include [file-dialog.inc](../src/file-dialog.inc). GETCAP ID **7** returns
`$4c80`; `$4c86` is version 1. It locates resident software even without a
cartridge. This is a synchronous modal API, with decimal mode clear. Do not
call from an IRQ, tick, transport callback or another active file-service call.

| Entry | Contract |
|---|---|
| `UFP_PICK=$4c80` | A=1 Open or 7 exclusive Save As; X=DOS context 1 or 2; r0=0 or a default ASCII leaf below `$6200` |
| `UFP_RECOVER=$4c83` | Restore a pending working directory after its owned file is closed; does not close a live handle itself |

Carry clear / A=0 from PICK returns a file already opened through
[UFS](ULTIMATE-FILES.md). Carry set means failure: `$e9` cancelled, `$ea` module
load/version failure, or a file/protocol error. A is authoritative. An acquired
PICK retains it at `$4c87`; a rejected nested call does not overwrite active
state. The caller reads/writes with UFS and must **UFS_CLOSE** the returned file.

PICK loads the trusted `uos-picker` module from the current system IEC device
through APP_LOADER, then calls it at `$6200`. Restore the system device in
`$ba` before calling. Caller code, document, return addresses and any retained
data must fit below `$6200`. The library preserves the stack; it does not
register another application. It replaces the core LOAD filename. The caller
repaints its window on return.

| Memory | Ownership |
|---|---|
| `$4c80–$4dff` | Resident gateway, public state and recovery code |
| `$4e00–$4fff` | Resident saved CHANGE_DIR command, private |
| `$6200–$71ff` | Modal library allocation; reusable after return |
| `$7200–$734f` | Modal scratch, including filename editor at `$7200` |
| `$7350–$7358` | Settings record, preserved |
| `$7359–$7fff` | Modal scratch, complete-name cache and result paths |
| `$50–$57` | Selector-private zero-page scratch, clobbered |

Calls also clobber A/X/Y, public r0–r15 and NET scratch. On successful PICK,
`$7400` holds the current directory, `$7600` the complete basename, and `$7800`
the absolute path, each NUL-terminated. `$4c8c` is the absolute path length.
Directory data is bounded at 510 bytes including its trailing slash; a read
name may be 511 bytes, so the returned path can be 1021 bytes. Read selection
submits the complete relative basename without imposing UFS's absolute-name
bound on the combined path. Firmware lookup limits still apply: 511-byte
components are a model/protocol test, not a physical support claim. A caller
wishing to reopen an absolute path must respect the backend's 893-byte limit.
Save As's shorter leaf keeps its absolute path within that limit.

## Working-directory cleanup

Only one selector directory lease can exist at a time. The library checks for
a foreign file before changing directories and saves the original path in
resident memory. Successful selection keeps the chosen directory borrowed
while the caller uses the file. This avoids changing an image-filesystem
directory underneath an open file.

`UFP_PENDING=$4c88` is 0 for none, 1 for borrowed and 2 for a failed restore.
`UFP_CONTEXT=$4c89` identifies the DOS context. After the selector returns,
closing that context through UFS also restores its original directory. A close
failure retains uncertain file ownership and the saved path. A directory
restore failure retains pending state 2, returns `$e8`, and blocks new OPENs
on that context until recovery succeeds. The other DOS context stays usable.
Repeated CLOSE on the released context can retry its pending directory restore
without closing a foreign handle. `UFP_RECOVER` is also available explicitly.
Raw DOS clients must honor this lease too: do not change that context's working
directory while a selector file or failed restoration remains pending.
Migration of the remaining raw-DOS applications to the shared service is still
required; this ABI alone does not enforce their cooperation.

While the selector runs, its internal CLOSE calls leave the chosen directory
in place so a rejected filename can be corrected in the same folder.
Cancellation explicitly closes its owned handle and restores the directory.
Desktop entry and application replacement attempt CLOSEALL and RECOVER. The
saved path survives application replacement and reuse of all modal workspace.
These are in-session recovery semantics; cold-boot/power-loss recovery and
mounted-media identity protection are separate roadmap requirements.

The editor retains its document at `$5f00–$61ff` and uses `$6e00–$70ff` as
staging after the selector returns. Its startup module ends before `$6200`.
The selector is hidden from Apps and included in both build scripts and the
system disk.

## Validation entry points

`tests/ci_picker.py` executes the gateway, library, UFS and UCI driver against
a cartridge model. `tests/ci_editor_files.py` covers complete save/open paths,
legacy import, bounded text and transfer/corruption failures.
`tests/ci_file_dialog_display.py` executes VIC/VDC drivers and compares whole
frames, caret pixels and the editor document/clock on modal return.
`tests/ci_edit.py` covers legacy import and unavailable-cartridge behavior in
x64. `python3 -u hw_ultimate_check.py --editor` boots the distributable and
checks private files on the physical C128 with independent raw-protocol reads.
The [checkpoint evidence](validation/2026-09-09-file-dialogs/README.md) records
the exact binaries, fault cases, display captures and hardware limits.
