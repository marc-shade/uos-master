# Shared Ultimate files, viewer and copy dialog

`uos-files` is the first shared cartridge file backend. The browser's **V / View**
action uses it to inspect files on both displays. It also provides bounded
binary reads, exclusive creation, verified writes, 32-bit seeks, position/size
queries and handle cleanup for other applications. The browser's **C / Copy**
action opens a dialog that uses this service to create and verify a new copy.
The editor now uses [shared Open and Save As](FILE-DIALOGS.md), with a modal
folder selector and final reopened verification. An IEC backend, overwrite,
rename and deletion remain required.

The resident allocation is `$4100–$4fff`; the file API starts at `$4100`, and
the viewer starts at `$4800`. GETCAP ID 6 returns `$4100`, including without
an attached cartridge. `$4115` contains API version 1. The command buffer owns
`$8080–$83ff` (896 bytes); the two existing pointer sprites retain `$8000–$807f`.
The desktop must end below `$4100`. See [ultimate-files.inc](../src/ultimate-files.inc)
for the authoritative exports and errors.

## File API

All calls are synchronous, with decimal mode clear. X selects DOS context 1
or 2. They may clobber A/X/Y, public zero-page registers `r0–r15`, flags and
NET scratch. Do not call from an IRQ, a transport callback, or another file
call. Service `OS_TICK` between transactions. C clear / A zero means success;
C set / A nonzero means failure. A is authoritative even when acquisition
fails before updating the result record.

| Address | Call | Arguments / result |
|---|---|---|
| `$4100` | `UFS_OPEN` | r0 points to a NUL-terminated raw filename; A=1 reads an existing file, A=7 exclusively creates a new file with read/write access |
| `$4103` | `UFS_CLOSE` | Close only a service-owned handle and restore its pending selector directory, if any |
| `$4106` | `UFS_READ` | r0 destination, r1 requested length 1–512; COUNT actual bytes, EOF when the known size is reached |
| `$4109` | `UFS_WRITE` | r0 source, r1 length 1–512; only files created by this service; verify all bytes by seeking back and reading them |
| `$410c` | `UFS_SEEK` | r0/r1 hold a 32-bit little-endian offset, from zero through the known file size |
| `$410f` | `UFS_TELL` | Export the selected owned handle's tracked size and position |
| `$4112` | `UFS_CLOSEALL` | Attempt both owned handles; return the first error with its firmware status; retain ownership of failed closes |

Names contain 1–893 bytes; OPEN's three-byte header plus the complete name
must fit 896 bytes. Input strings must remain in `$5000–$7fff`; raw bytes and
case are unchanged, and no NUL is sent to the cartridge. Both absolute and
current-directory-relative names work. **Creation requires every component
to be at most 127 bytes**, separated by slash or backslash; longer components
fail before any cartridge command. The inspected firmware resolves paths
through `FileInfo(128)` and can create a longer name which it then cannot
reopen or delete. A physical 255-byte creation reproduced that problem before
this guard was added. Read-only names retain the full transport bound and
report firmware lookup failures without truncation. The browser's full-name
caches remain unchanged. Long paths with shorter components are supported.
Ordinary file calls leave working directories unchanged. Closing a file
returned by the [shared selector](FILE-DIALOGS.md#working-directory-cleanup)
also restores the directory borrowed for that selection.

Binary buffers must lie wholly in `$5000–$734f` or `$7359–$7fff`. The settings
record, sprites and resident modules cannot be destinations. Returned bytes
are binary: there is no extra terminator, including for a full 512-byte block.
Discard data and COUNT whenever a call fails. READ at known EOF returns zero
bytes without issuing a zero-length cartridge command.

The result fields are RESULT `$4116`, COUNT word `$4117`, SIZE dword `$4119`,
POS dword `$411d`, EOF byte `$4121`, two mode bytes `$4122`, and a 32-byte
NUL-terminated firmware status copy at `$4124`. SIZE is the snapshot taken at
open, extended by verified writes; POS is tracked through successful operations.
Close and reopen to observe an externally changed file size. EOF is meaningful
for an owned handle after a successful read, seek or tell.

Modes are 0 unowned, 1 read, 7 new read/write, and `$ff` uncertain. Before
opening an unowned context, FILE_INFO must explicitly report no open file.
FILE_INFO's no-file status is **85**; CLOSE uses **84** when there is no file
to close. These distinct replies must not be interchanged. An already-open
foreign file is left untouched. Applications must not mix raw
OPEN/READ/SEEK/CLOSE commands with a service-owned context. Both contexts may be
owned at once for streamed copies; each has an independent position and size.

## Integrity and recovery

The [official DOS protocol](https://1541u-documentation.readthedocs.io/en/master/uci/ultimate_dos_target.html)
specifies empty success status for READ_DATA. The service accepts that form
only for reads, after verifying packet bounds and the expected byte count.
It accepts numeric zero status too. A short read before the known end is an
error, not EOF. Fragmented replies are accumulated with a 512-byte total bound;
clipped or excess data is rejected.

The reference II+ corrupts a raw 512-byte `WRITE_DATA` to USB while returning
success. A separate raw-protocol test reproduces this after close/reopen and
confirms that 511 bytes followed by one byte saves the complete payload.
The service therefore splits a 512-byte write into those two commands, then
seeks back and verifies all 512 bytes. Shorter writes use one command. A failure
in either part quarantines the handle; the first part is never replayed.

The source explains a likely cause: FAT sends complete sectors directly from
the command FIFO at `IOBASE+$44800`, while partial sectors pass through a RAM
cache. The USB memory controller has a 26-bit address, below `IOBASE=$04000000`.
This is a source-based diagnosis; the installed firmware build is unknown.

The inspected firmware source is the local 1541ultimate checkout at
`a01c04e8267a0d916b7203cb34dcf1127f75981d`. `software/filemanager/dos.cc`
overwrites its file pointer on OPEN, does not return a WRITE byte count, and
does not report `fclose`'s result in its CLOSE reply. Its file read error branch
can leave the status pointer unchanged. These observations motivate the
ownership probe, size checks and read-back verification. They describe that
source revision; the exact release on the reference cartridge remains unknown.

A successful WRITE means its requested contents were read back through the
same handle. It is not a power-loss durability promise. Save/copy workflows
must close, reopen, and verify the final file before reporting copy/save completion.
No open, read or write is replayed automatically. Transport, read, seek or write failures
quarantine an owned handle; only CLOSE may recover it. A failed creation can
leave a partial new file. The API does not delete it automatically.

Errors `$e0–$e8` mean invalid argument, no owned file, busy/foreign handle,
read-only, protocol violation, short transfer, differing read-back, offset range,
and uncertain handle. Other errors retain the firmware's numeric status or the
transport's `$fc–$ff` codes. `UFS_STATUS` is diagnostic; success comes from the
return contract. Some firmware filesystem errors are plain text; the transport
returns `$ff` for these and the raw text is retained. They are failures, never
accepted as the empty success form of READ. Desktop entry and application replacement attempt CLOSEALL,
but applications must handle failed operations and cleanup themselves.

The same firmware checkout has `FF_FS_LOCK=0` in its full FAT configuration;
file-manager delete/rename wrappers do not provide an equivalent open-file
guard. Safe overwrite, rename and deletion therefore require mounted-media
identity/protection and recovery work. Exclusive creation rejects existing names.

## Desktop copy

Select a regular file in **Apps → uos-ultimate**, then press **C** or click
**Copy**. The destination defaults to `copy.bin` in the current directory.
Edit the full path to choose another directory or name. Left/right move the
cursor, Home moves to the beginning, Del removes the preceding byte, and
Ctrl-U clears the field. The field scrolls to keep the cursor visible.
On the VIC display, path characters and the caret share eight-pixel cells so
wide and narrow glyphs remain aligned; VDC character cells provide the same alignment.
Unshifted letters enter lowercase ASCII; shifted letters enter uppercase.
Press **Enter / Copy** to start; an existing destination is rejected.

The copied and checked byte counters are 32-bit hexadecimal numbers, marked
with `h`. **Copy verified** appears only after both files have been closed,
reopened, checked for the original size, compared byte for byte, and closed
successfully again. The clock/input loop runs between transactions. Esc cancels
at a transaction boundary during either copying or verification. It closes the
owned handles and labels the destination unverified. A partial or unverified
new file is retained; there is no automatic deletion or write retry.
Counters advance after each block; the screen updates every 4 KiB and at phase
changes, errors, cancellation and completion to keep graphics from slowing I/O.

After an error, its code and cartridge diagnostic are shown. **E** returns to
path editing once all service handles are released; use a different new name
if the previous attempt created a file. **R** retries a failed close, and **Esc**
returns to the browser. The resident ownership guard remains active after an
unsuccessful close. The app does not close foreign cartridge handles.

Destination paths must start with `/`, contain at most 893 bytes, and meet the
service's 127-byte component limit. Source names retain the browser's full
511-byte bound. DOS 2 opens the source relative to the unchanged browser CWD;
DOS 1 opens the absolute destination without changing the shell CWD.
This is a single-file copy, with a typed destination path. Folder selection,
batch/recursive copy, resume and safe partial-file removal remain open. The
editor's Save As uses the separate shared selector. Concurrent source/media
changes and power-loss durability are not guaranteed: final comparison observes
both files through the cartridge API.

The `uos-copy` module is loaded on demand at `$5000` and hidden from the Apps
list. Its code must end below `$6900`; its buffers are destination
`$6900–$6c7d`, source block `$6d00–$6eff`, and verification block `$6f00–$70ff`.
The browser hands over its current path at `$7100`, full selected basename at
`$7c00–$7dff`, and an eight-byte versioned record at `$7e10–$7e17`.
See [ultimate-copy.inc](../src/ultimate-copy.inc). The app preserves the settings
record and uses only app-private `$60–$65` scratch alongside public registers.
Both overlay entries reset the stack because their callers cannot return.
They balance app registration and use the core loader on the original system
IEC device. Failed LOAD goes to the desktop. Return reloads and refreshes the
browser at its saved page and row; filesystem changes can shift directory
ordinals, as with any browser refresh.

## Modal viewer

`UFS_VIEW=$4800` takes X=context and r0=filename. It requires an unowned context,
opens read-only and closes on exit. It borrows `$7c00–$7c5f`, draws in the VIC
app interior and VDC rows 2–23, and leaves the caller to repaint on return.
Its loop keeps the desktop clock serviced. N/B page through 96-byte blocks;
Esc returns. The full browser filename caches, working directory, page and
selection survive. Unsupported ASCII glyphs become dots only in the display.
Its first filename line is a preview; the browser retains full-name inspection.

`tests/ci_files.py` executes the assembled backend and transport, including
large binary reads/copies, long names, two handles and failure injection.
`tests/ci_file_view.py` exercises browser integration, 64 KiB crossings, mouse
actions and whole VIC/VDC frame restoration. `tests/ci_files_probe.py` checks
the independent native hardware workflow client. `hw_ultimate_check.py --files`
runs that client on the C128, independently reads back the private USB files,
and verifies the desktop viewer and capture restoration. It also drives the
shipped copy dialog through existing-name rejection, a verified copy, in-progress
cancellation, and return to the browser, with independent full/prefix readback.
`tests/ci_file_copy.py` executes the core overlay loader, dialog, service and
transport. Its faults include post-close corruption, source size changes, final
close failure and cancellation during verification; it also compares whole
VIC/VDC frames and checks long paths, mouse actions and repeated overlay entry.
