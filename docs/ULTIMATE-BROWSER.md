# Ultimate filesystem browser

Open **Apps → uos-ultimate** from the desktop. The browser shows eight entries
at a time from the cartridge filesystem. A `/` prefix marks directories;
`>` marks the selection. An additional `>` at a shortened name's right edge
means the name continues. The selected name appears below the list.

The browser uses DOS target 2, whose working directory is independent of the
shell's target 1. Reopening the app resumes that browser context. The
[Ultimate DOS specification](https://1541u-documentation.readthedocs.io/en/master/uci/ultimate_dos_target.html)
also permits entering supported disk images as directories. Browsing an image
does not mount it in an IEC drive.

## Controls

| Action | Keyboard | Mouse on the VIC display |
|---|---|---|
| Select | Up/down; continues across page boundaries | Click a row |
| Enter directory or image filesystem | Return | Open |
| Inspect a file as hex and ASCII | V | View in the title |
| Copy a regular file to a new name/path | C | Copy in the title |
| Parent / filesystem root | U / `/` | Up / Root |
| Previous / next page | B / N | Prev / Next |
| Scroll the full selected name | Left/right, 32 bytes per step | `<` / `>` |
| Show full path instead of selected name | P; left/right to scroll | Click the path below the title, then `<` / `>` |
| Refresh after a change or error | R | Leave/reopen, or use navigation controls |
| Open drive panel | D | Drives at the right of the title |
| Cancel an active directory scan | ESC | — |
| Return to desktop | ESC when idle | Exit |

The item range appears below the details. `+` means another page exists.
The VDC mirrors the list, details, range/error and keyboard help. The running
desktop clock continues to update while the browser waits for input.
Return enters directory/image filesystems. **V / View** inspects a regular
file without changing the directory, page, selection or complete cached names.
The viewer shows 96 bytes per page, with 32-bit hexadecimal offsets, hex bytes
and an ASCII column. **N / Next**, **B / Prev** and **Esc / Files** work with
keyboard or VIC mouse. Empty files show an empty page and END. An I/O error
shows its code; Esc returns to the browser. The byte columns retain binary
values even when the ASCII column displays a dot for an unsupported character.

The viewer and **C / Copy** dialog use the [shared file service](ULTIMATE-FILES.md).
The copy dialog accepts an editable full destination path, shows copied/checked
byte counts, and closes/reopens both files for full comparison before reporting
success. Esc cancels; any partial/unverified new file is retained. Esc again
reloads the browser at its saved page and row in the same directory. This refresh
can show newly created files and can shift selection if directory order changed.
See the [copy controls and recovery notes](ULTIMATE-FILES.md#desktop-copy).
Save/file-picker dialogs, text/image/media viewers and file associations remain open.

## Drive panel

Select a disk image, then press **D** or click **Drives**. Choose an IEC drive
with Up/Down or a row click. **M / Mnt** prepares a mount; **E / Ejct** prepares
an eject. The prompt includes the destination IEC number. **Enter / Yes** sends
the operation; **Esc / No** cancels it. Esc again, D, Files or Back returns to
the browser without changing its directory, page or selected file. R refreshes
the drive inventory. The filename/path inspector remains available through
Left/Right and P.

The disk that loaded the app is protected. Its IEC number and any observed
system-drive slot stay locked for this app session, even across refreshes.
Returning to the desktop restores that load device. A second drive can therefore
hold an image while applications continue to load from the system disk.
In File Manager, keys 8/9/0/1 select IEC devices 8/9/10/11 to access their
files. Extending its device selector to the rest of the IEC range remains open.

The panel accepts a filename stem followed by D64/G64/D71/G71/D81 extensions;
actual image compatibility is
decided by the cartridge. It checks a fresh inventory before executing a
confirmed operation. A changed record cancels the request and asks for review.
Powered-off, unsupported, duplicate or invalid destinations cannot receive a
mount/eject command. No implicit/zero drive ID is sent.

The reference cartridge declares four devices but supplies two records. The
panel reconciles this specific short form only when it contains two distinct
emulated-drive IEC addresses and separate A/B power queries agree. It reports
the other devices as unknown. Malformed or clipped responses disable operations.
This does not certify the missing SoftwareIEC or printer records. See the
[service protocol notes](ULTIMATE-SERVICE.md#drive-capability-records).

The success message is **drive command accepted**. The installed UCI API does
not return the mounted image's identity; checking its IEC contents remains a
separate operation. Image creation, power/type/ROM/address changes, write
protection, dirty-media handling and replacing/recovering the system volume
remain open.

## Bounds and recovery

Every cached entry contains its full raw name, up to 511 bytes, plus a zero
terminator. Display conversion does not modify the name sent to the cartridge.
That cache bound does not guarantee the firmware can resolve names of that
length. The reference firmware truncates components at its 128-byte lookup
buffer; see the [file-service limitations](ULTIMATE-FILES.md).
The current font displays ASCII letters and most punctuation. Braces, vertical
bar, tilde, control and non-ASCII bytes appear as dots. Raw names remain intact
when navigating. Unicode font/decoding support remains open.

Directory positions are 16-bit. Each page reopens the directory, skips earlier
packets, keeps eight entries and aborts after finding a ninth. A full list need
not be retained in main RAM. Higher pages take longer to scan, and changes to a
directory between pages can shift positions. This is not a snapshot or sorted
directory index.

Clipped, empty-name, embedded-zero or slash-containing entry packets are
rejected and the page is cleared. Transport failures, firmware errors and
cancellation leave the app available for retry or exit. Status-only packets
do not create entries. Paths longer than the aggregate reply capacity (510
bytes) produce an explicit error; Root/Parent can recover to a shorter path.
After a failed path request, the header retains the last successfully received
path. Navigation still uses the cartridge's current directory.

## Implementation and validation

`src/uos-ultimate.asm` loads at `$5000` and must end before `$6900`. It includes
`src/ultimate-drives.inc` and reserves
these transient areas without padding them into its PRG:

| Range | Use |
|---|---|
| `$6900–$70ff` | First four 512-byte raw-name slots |
| `$7100–$72ff` | Current path |
| `$7400–$7bff` | Last four 512-byte raw-name slots |
| `$7c00–$7eff` | Command construction (currently at most 514 bytes); full copy source during overlay handoff |
| `$7e10–$7e17` | Versioned copy overlay handoff, above the maximum command extent |
| `$60–$6a` | App pointers, lengths and mouse coordinates |

The settings record at `$7350` is preserved. Driver-private scratch at
`$70–$7f` stays with the transport. The app uses fixed core exports
`OS_TICK=$083b`, `KEYIN=$082c` and `READ_BUTTON=$083e` in its input loop;
`ready=1` means input can be accepted, `0` means work is in progress and `$ff`
marks exit. Desktop entry clears stale controls and redraws the screen.
The current browser PRG occupies `$5000–$67ff`, including its static buffers.
`cache_pages` supplies the eight slot addresses; the cache is not contiguous.
The CI tick trampoline at `$7f00`, sprite data and screen matrix are preserved.
While the modal viewer is active, browser `ready` stays zero; the viewer's
`view_ready` byte indicates its idle input loop. Its code is resident at
`$4800`, and file bytes temporarily use `$7c00–$7c5f`. The browser redraws its
frame on return without rereading the directory.
Copy uses a separate disk-loaded module at `$5000`, then reloads the browser.
The directory is refreshed after that return; both one-way entries discard dead
caller stack frames. The system IEC load device remains the original one.

The frame and toolbar are drawn once. Selection changes replace the two row
markers and the selected-name details; name/path scrolling replaces only the
details. Page changes replace the list, path, details and status. Each VDC field
remembers its previous text length so shorter content clears its old tail.
The drive panel reuses the detail inspector and repaints its fields after an
action. Switching panels redraws the frame. VIC erasure includes the full font height, from one pixel above the text origin
through eight pixels below it, including descenders. List text starts at X=40
and its marker at X=24 so their erase areas align with bitmap bytes.

`tests/ci_ultimate.py` runs the assembled browser plus the actual UCI driver
against a filesystem/register model. It checks 1,100-entry paging past ordinal
255, 511-byte names, complete long command operands, empty/error/clipped replies,
cancel/retry, mouse release actions across the VIC X-byte boundary, and memory
guards. It also checks complete/reconciled/invalid inventory, independent power
validation, system-drive locks, duplicate IDs, stale confirmation, cancellation,
514-byte mount requests and firmware errors. The graphics/input adapters deliberately clobber permitted scratch.
The model does not certify physical mouse or cartridge timing.

`tests/profile_browser.py` also executes the assembled VIC graphics and VDC
driver. Its `--check-fresh` mode compares every incremental frame with a fresh
render of the same state, including complete VIC bitmap and VDC character and
attribute memory. It covers long-to-short selections, page changes, empty and
failed directory reads, retry, path/name switching, wide glyphs, descenders,
drive selection, confirmation/cancellation, mount/eject and returning to files.
Instruction counts use immediate VDC readiness after a required poll; they
exclude VIC bad lines, interrupts, DMA pauses and host latency.

The launcher now registers every available app row, up to its six-row limit,
aligns its labels with their controls, and keeps the sixth row clear of Cancel.
Callbacks use complete filename pointers, including across memory pages.
Core hit testing handles the full
VIC X coordinate, including screen pixels 232–255 and controls spanning 256.
`tests/ci_desktop.py` covers those cases. `tests/ci_vdc_protocol.py` requires
the register-ready handshake before VDC data access and checks a bounded
absence probe.

The hardware helper's packet capture now stops at `$7300`, before settings,
and can skip a requested number of packets to capture a later-page oracle.
Its CPU test checks both complete stream consumption and the preference guard.
`hw_ultimate_check.py` boots the distribution, compares complete browser names
and all cells in the VDC list/detail rows, launches through the registered
app-row callback at screen X=240, times selection/page changes, and compares
VIC pixels after a selection round trip with a clock repaint. It navigates
Root/Open/Parent, restores the two DOS paths, and leaves
the desktop live. Its coordinate injection tests compiled hit detection and
dispatch; it does not certify physical pointer movement or button presses.
Its default navigation check does not remount drive B or modify files.
`--drives` creates a private scratch D64, mounts it on an initially empty B,
uses File Manager to copy a system PRG into it, then ejects and checks every
copied byte through the cartridge filesystem. It restores the DOS paths and
removes its own fixture. The VDC capture helper preserves and verifies all
borrowed RAM at `$7400–$7cf4`, which now contains four cached names.
Physical checks leave quiet intervals around IEC I/O because cartridge DMA
observations stop/resume the CPU. The
[validation record](validation/2026-09-08-browser/README.md) preserves the
failing baselines, diagnostic changes and exact build hashes.

The [redraw validation](validation/2026-09-08-browser-redraw/README.md) covers
the preceding browser build: 21 complete-frame comparisons, three emulator suites and
physical navigation through a 1,096-entry directory to ordinal 256. Paired VDC
captures agree on all seven sampled screens, including unused rows after Root.
Preference preservation and exit to a live desktop pass.

The redraw optimization lowered the median of 32 page changes from 14.5 to
7.9 s. The drive-panel build's physical repeat recorded 0.52–0.65 s selection
changes and 6.46–9.35 s pages (median 7.92 s). These timings include host polling.
Initial rendering still paints the complete frame, and
repeated directory scanning and long-name rendering need further performance
work.

The [drive validation](validation/2026-09-08-ultimate-drives/README.md) records
the expanded panel's checks and exact build hashes. The
[completion roadmap](IMPLEMENTATION-ROADMAP.md) tracks the remaining drive
controls, hardware registry, file operations and full interactive VDC desktop.
