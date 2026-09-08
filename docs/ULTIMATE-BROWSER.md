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
The current browser PRG occupies `$5000–$5dbd`, including its static buffers.

The frame and toolbar are drawn once. Selection changes replace the two row
markers and the selected-name details; name/path scrolling replaces only the
details. Page changes replace the list, path, details and status. Each VDC field
remembers its previous text length so shorter content clears its old tail.
VIC erasure includes the full font height, from one pixel above the text origin
through eight pixels below it, including descenders. List text starts at X=40
and its marker at X=24 so their erase areas align with bitmap bytes.

`tests/ci_ultimate.py` runs the assembled browser plus the actual UCI driver
against a filesystem/register model. It checks 1,100-entry paging past ordinal
255, 511-byte names, complete long command operands, empty/error/clipped replies,
cancel/retry, mouse release actions across the VIC X-byte boundary, and memory
guards. The graphics/input adapters deliberately clobber permitted scratch.
The model does not certify physical mouse or cartridge timing.

`tests/profile_browser.py` also executes the assembled VIC graphics and VDC
driver. Its `--check-fresh` mode compares every incremental frame with a fresh
render of the same state, including complete VIC bitmap and VDC character and
attribute memory. It covers long-to-short selections, page changes, empty and
failed directory reads, retry, path/name switching, wide glyphs and descenders.
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
It does not remount drive B or modify files.
Physical checks leave quiet intervals around IEC I/O because cartridge DMA
observations stop/resume the CPU. The
[validation record](validation/2026-09-08-browser/README.md) preserves the
failing baselines, diagnostic changes and exact build hashes.

The [redraw validation](validation/2026-09-08-browser-redraw/README.md) covers
the current build: 21 complete-frame comparisons, three emulator suites and
physical navigation through a 1,096-entry directory to ordinal 256. Paired VDC
captures agree on all seven sampled screens, including unused rows after Root.
Preference preservation and exit to a live desktop pass.

Observed physical selection changes took 0.52–0.64 s. The median of 32 page
changes fell from 14.5 to 7.9 s; the current range was 6.46–9.24 s. These timings
include host polling. Initial rendering still paints the complete frame, and
repeated directory scanning and long-name rendering need further performance
work.

The [completion roadmap](IMPLEMENTATION-ROADMAP.md) tracks the remaining drive
panel, hardware registry, file operations and full interactive VDC desktop.
