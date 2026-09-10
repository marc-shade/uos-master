# Native file dialogs

The editor's Open and Save As fields now offer **Tab** to browse files. The
picker uses the same navigation source as Files and Apps, including D64,
D71, D81 and Ultimate directories. **Enter** selects a file or enters an
Ultimate folder; **P** goes to its parent, **N/B** page, **F** changes backend,
**D** selects an IEC device and **Tab** switches Ultimate DOS contexts.
In Save As, **S** chooses the current folder/device and keeps the proposed
basename. Empty folders can be selected this way.

Selection returns to the editable filename field. Open still asks before
discarding dirty work, and Save As still creates exclusively and compares
every byte after reopening. The picker itself does not launch applications
or write file contents. **Esc** returns to the original field. The document,
cursor and viewport remain allocated while the picker has focus.

This is a source library used by two applications, not a new resident ABI
entry or a dynamically loaded GUI service. Kernel ABI 1.5 provides its owned
directory/file and heap operations. The editor now requires minor version 5.
Desktop and dialog navigation share `file-browser.inc`, `browser-ui.inc`,
`browser-usb.inc` and `browser-ultimate.inc`; `FD_EMBEDDED` excludes application
discovery, launch and binary-preview code from the editor.

## Caller contract

`file-dialog.inc` exports `fd_run`. Set `fd_mode` to 1 for Open or 2 for Save
As, `fd_device`/`fd_format` to the data backend, and `fd_name`/`fd_length` to
the proposed name (0–255 bytes). `FD_NAME_BUFFER` supplies a writable 256-byte
bank-0 field. Calls are foreground only, with interrupts enabled and a valid
active app owner. Decimal and interrupt flags are preserved.

Carry clear/A=0 returns a candidate filename and its backend. `fd_type`
identifies SEQ/PRG/USR for IEC Open, preserving raw PRG load-address bytes.
Save As chooses SEQ; Ultimate files remain raw. Carry set/A=0 cancels;
carry set/A=an ABI error reports failure. Input fields change only after
successful selection and checked cleanup. Complete raw names are retained;
the editor displays dots for bytes that are unsafe as console controls.

The dialog borrows and restores the desktop browser's path, ordinal, complete
selected name and preferences. Its last directory is separate from that
desktop state. File and heap argument mailboxes may change. Cleanup closes
only cursors opened by the picker and frees only its cache handles; it never
releases the caller's entire owner. Uncertain cursor cleanup prevents a
successful selection and retains the handle for a later checked cleanup.

## Memory

The caller supplies four distinct idle 512-byte buffers through `FD_SCRATCH0`
through `FD_SCRATCH3`. The editor lends its input, output, second read-page and
save-verification buffers. These are temporary transfer/cache bytes, separate
from document chunks. It invalidates both read caches before repainting on
return. The document contents and line-position state are not reused.

Ultimate records use 256 bytes plus a separate name-length array in the
picker. Two pages of eight complete entries require 4 KiB. Half uses the
borrowed buffers; the other half uses eight heap pages. Cache allocations
are lazy, in blocks of at most four pages, and can use either RAM bank.
IEC retains its 32-byte records and can require more cache space for a full
296-entry D81 listing. Allocation failure must return to an intact document.

The editor's image is capped at 79 pages. New workspace bank-0 allocations
use `$df00..$feff`, the top 32 managed pages, leaving the remaining high RAM
contiguous for document chunks. The total heap remains 426 pages. This layout
passes the CPU workflow with both 8 KiB workspace blocks, a document over
64 KiB, directory navigation and a complete verified save. All three editor
emulator geometries and the physical USB/IEC workflows also pass.

## Qualification and remaining work

All 18 CPU suites passed before the final six-byte F8 preference fix; the
editor, Ultimate editor, redraw and file-dialog suites passed again afterward.
The 11 picker flows cover all three IEC geometries, cancellation, raw PRG Open,
Save As, quoted Ultimate folders, empty folders, complete raw filenames,
296-entry D81 directories, 255-byte paths, memory exhaustion and retained-close
recovery. They also retain a 66,056-byte document through 300-entry navigation
with both workspace blocks. All ten native emulator workflows pass, including
complete document captures while the picker has focus on D64, D71 and D81.
The [picker checkpoint](validation/2026-09-10-native-file-dialogs/README.md)
also passes complete physical C128 USB and IEC workflows. Independent readback
matches nine USB files and all four files on the IEC data disk. The USB picker
pages beyond ordinal 255 while retaining the complete document; both physical
workflows capture all seventeen document chunks with the picker active.
The archive retains two interrupted IEC attempts and the host connection fix,
with eight fault-injection cases proving that sent writes are never replayed.
D71/D81 results are emulator evidence; the physical IEC run uses Ultimate
emulated 1541 drives. Shared GUI events, dynamic modules, scheduling and the
full OS roadmap remain open.
