# Shared Ultimate files and byte viewer

`uos-files` is the first shared cartridge file backend. The browser's **V / View**
action uses it to inspect files on both displays. It also provides bounded
binary reads, exclusive creation, verified writes, 32-bit seeks, position/size
queries and handle cleanup for other applications. It does not yet provide
desktop copy/save dialogs, a shared IEC backend, overwrite, rename or deletion.

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
| `$4103` | `UFS_CLOSE` | Close only a service-owned handle; an unowned context is a no-op |
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
The service never changes either DOS context's working directory.

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
No operation is replayed automatically. Transport, read, seek or write failures
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
runs that client on the C128, independently reads back both private USB files,
and verifies the desktop viewer and capture restoration.
