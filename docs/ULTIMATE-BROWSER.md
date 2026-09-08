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
| Parent / filesystem root | U / `/` | Up / Root |
| Previous / next page | B / N | Prev / Next |
| Scroll the full selected name | Left/right, 32 bytes per step | `<` / `>` |
| Show full path instead of selected name | P; left/right to scroll | Click the path below the title, then `<` / `>` |
| Refresh after a change or error | R | Leave/reopen, or use navigation controls |
| Cancel an active directory scan | ESC | — |
| Return to desktop | ESC when idle | Exit |

The item range appears below the details. `+` means another page exists.
The VDC mirrors the list, details, range/error and keyboard help. The running
desktop clock continues to update while the browser waits for input.
Opening a regular file currently reports the cartridge's directory error;
viewer/association launch, file operations and drive mount/eject are subsequent
roadmap work.

## Bounds and recovery

Every cached entry contains its full raw name, up to 511 bytes, plus a zero
terminator. Display conversion does not modify the name sent to the cartridge.
The current font displays ASCII letters and punctuation; unsupported control
or non-ASCII bytes appear as dots. Unicode font/decoding support remains open.

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

`src/uos-ultimate.asm` loads at `$5000` and must end before `$6000`. It reserves
these transient areas without padding them into its PRG:

| Range | Use |
|---|---|
| `$6000–$6fff` | Eight 512-byte raw-name slots |
| `$7000–$71ff` | Current path |
| `$7400–$77ff` | Command construction (currently at most 513 bytes) |
| `$60–$6a` | App pointers, lengths and mouse coordinates |

The settings record at `$7350` is preserved. Driver-private scratch at
`$70–$7f` stays with the transport. The app uses fixed core exports
`OS_TICK=$083b`, `KEYIN=$082c` and `READ_BUTTON=$083e` in its input loop;
`ready=1` means input can be accepted, `0` means work is in progress and `$ff`
marks exit. Desktop entry clears stale controls and redraws the screen.
The current browser PRG occupies `$5000–$5ea3`, including its static buffers.

`tests/ci_ultimate.py` runs the assembled browser plus the actual UCI driver
against a filesystem/register model. It checks 1,100-entry paging past ordinal
255, 511-byte names, complete long command operands, empty/error/clipped replies,
cancel/retry, mouse release actions across the VIC X-byte boundary, and memory
guards. The graphics/input adapters deliberately clobber permitted scratch.
The model does not certify physical mouse or cartridge timing.

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
and physical VDC rows, launches through the registered app-row callback at
screen X=240, navigates Root/Open/Parent, restores the two DOS paths, and leaves
the desktop live. Its coordinate injection tests compiled hit detection and
dispatch; it does not certify physical pointer movement or button presses.
It does not remount drive B or modify files.
Physical checks leave quiet intervals around IEC I/O because cartridge DMA
observations stop/resume the CPU. The
[validation record](validation/2026-09-08-browser/README.md) preserves the
failing baselines, diagnostic changes and exact build hashes.

The reference C128 run passed 32 Next actions through a 1,096-entry directory
to ordinal 256, complete cached-name comparisons, exact VDC rows on both sampled
pages, Root/Open/Parent, preference preservation and exit to a live desktop.
All four emulator suites also pass. The physical page changes took 12.9–16.0 s
including host polling. Full redraws and repeated directory scanning still need
performance work.

The [completion roadmap](IMPLEMENTATION-ROADMAP.md) tracks the remaining drive
panel, hardware registry, file operations and full interactive VDC desktop.
