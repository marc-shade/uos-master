# UltOS application SDK (fork: marc-shade/uos-master)

How to write a program that runs under uOS on a C128 (C64 mode) with an
Ultimate II+. Everything here is taken from the sources in `src/` and the
build output; addresses are the fixed ABI the core and drivers export.

The separate [native C128 ABI](NATIVE-KERNEL.md) provides native boot and banked
memory services, checked [native apps](NATIVE-APPS.md) and [owned IEC files](NATIVE-FILES.md).
ABI 1.2 adds directory pages and application handoff, used by the
[native file/app browser](NATIVE-BROWSER.md).
ABI 1.3 adds [Ultimate file streams](NATIVE-ULTIMATE.md), used by the
[native editor](NATIVE-EDITOR.md) for USB Open and verified Save As.
ABI 1.5 adds owned directory cursors, ABI 1.6 provides shared focused fields,
and the ABI 1.7 candidate adds checked app-bound modules. The buildable
[native module example](../examples/native-module/README.md) demonstrates
manifests, token reuse, explicit load retry and both native consoles using
the public native API. Its separate CPU workflows pass; the ABI 1.7 system
images are still undergoing physical qualification.
Its `$1c20` jump table and memory map are separate from this
legacy desktop ABI. ABI 1.9 adds the desktop session-selection mailbox at
`$3d2f`; the current app/module validators accept requirements through 1.9.
Desktop/app migration remains in progress.

## Memory map (from `build.sh` output and `src/routines.inc`)

| Range | Owner | Notes |
|---|---|---|
| `$0801-$0fff` | core `uos` | **must end below `$1000`** (the desktop loads there); check `Data: … $0801-$0fxx` after any core edit |
| `$1000-$406c` | desktop `uos-desktop` | resident; assembly must end before `$4100`. `DESK_START = $1000` is the one-way re-entry point |
| `$4100-$4fff` | shared Ultimate files / viewer / selector gateway | `uos-files`; file API at `$4100`, modal viewer at `$4800`, selector gateway at `$4c80`; GETCAP IDs 6/7 |
| `$5000-$7fff` | app code/data, subject to reservations below | `APP_START = $5000`; one app at a time. The legacy `APP_END=$8fff` snapshot extent is not a grant of all that RAM to apps |
| `$7350-$7358` | settings record | `SETREC`; the settings app image is padded up to it, see below |
| `$7f00` | tick trampoline (CI only) | free for apps at run time |
| `$8000-$807f` | sprites | two pointer shapes; `$87f8` = sprite pointer (colour-RAM fills clobber it) |
| `$8080-$83ff` | file service command buffer | 896 private bytes; unavailable to apps or additional sprite shapes |
| `$8400-$87ff` | screen matrix / colour cells | hires colour |
| `$8800-$89ff` | `NET_DATA` | uos-net's 512-byte reply buffer (socket payload at `+2`) |
| `$8a00-$8cce` | UCI transport | resident code/private state, part of the `uos-net` PRG; must end before `$9000` |
| `$9000-$90ff` | `APP_CTL_TBL` | control (button) hit-test table, 25 ten-byte slots (`APP_CTL_END = $9100`) |
| `$9100-$9979` | network/clock services | fixed UCI/network ABI at `NET_BASE=$9100`; must end before `$9b00` |
| `$9b00` | `APP_ID_TBL` | app-id counter (`RegisterApp`) |
| `$9c00` | `uos-reu` | `REU_SIZE/STASH/FETCH/PARAMS` at `$9c00/03/06/09` |
| `$9e00` | `uos-drv1351` | mouse driver + keyboard extension: `INIT_MOUSE = $9e03`, `KEYIN_EXT = $9e09`, `KEY_EXTSEEN = $9e0c` |
| `$a000-$bfff` | bitmap | 320×200 hires |
| `$c000-$cbff` | `uos-gfx` | graphics engine |
| `$cc00-$cfff` | `uos-vdc` | 8563 driver + 80-column companion API |
| `$d000-$dfff` | I/O | VDC at `$d600/$d601` |

The 80-column companion display: row 0 = header + clock (time + source),
row 1 = the menu hint, rows 2-23 = the app area (windows, listings), and
**row 24 = a status line** the desktop draws on entry and refreshes on the
clock tick: `YYYY-MM-DD  ip A.B.C.D  <source>` (date/ip/source from uos-net;
`no ip` and `no ultimate`/`no network` when offline).

Zero page: `r0`-`r15` word registers at `$02-$21` (`r0L=$02`, `r0H=$03`, …
`r9L=$14`, `r9H=$15`). **`X1/Y1` of the graphics engine ARE `r0/r1`
(`$02-$05`)** — writing a text position destroys a pointer you parked in
`r0`. `$23-$26` are reserved for the VDC driver's caller pointers.

## Boot chain

`uos` (core) loads, in order: `uos-gfx`, `uos-vdc`, `uos-drv1351`,
`uos-sprites`, `uos-reu`, `uos-net`, `uos-files`, `uos-desktop`, then `VDPREF` loads the
settings record `UOS-SET` (absent file → defaults: mode 2 = both displays,
cyan background), `VDSETUP` brings up the 8563 when the mode allows it,
`NET_SYNC` sets the clock from the network (see *Network and clock*), and
the desktop starts. The launcher hides these system components by name
(`syscomps` in `uos-desktop.asm`) and lists every other `uos-*` file on the
disk as an application, up to its current six-row limit.
The internal `uos-copy` overlay and `uos-picker` modal library are also hidden.
The browser loads the copy overlay through the core; it returns by reloading
the browser. The
[copy handoff and memory contract](ULTIMATE-FILES.md#desktop-copy) are private
to those two modules. Both reset the stack at their one-way entry points.
The selector instead returns to its retained caller through the resident
[modal gateway](FILE-DIALOGS.md#application-abi-version-1), preserving the stack.

## Core jump table (`$0811`…, `src/routines.inc`)

| Slot | Name | Contract |
|---|---|---|
| `$0811` | `MAINLOOP` | core loop: mouse/click dispatch + once-per-second tick through `($033c)` |
| `$0814` | `FIND_CTL` | control hit-test |
| `$0817/$081a/$081d` | `FS_APP/FS_SCREEN/FS_RECT` | REU stash/fetch of app / screen / rect |
| `$0820` | `CLR_RECT` | |
| `$0823` | `LOAD_IMM` | inline `$00`-terminated filename follows the `jsr` (see `loadfiles` in `uos.asm`) |
| `$0826` | `APP_LOADER` | KERNAL LOAD of the file buffer; carry clear on success, set on failure. `LOADERR` resets for each attempt and latches the KERNAL error |
| `$0829` | `FILLFILE` | `r0` → `$00`-terminated name → file buffer (dynamic loading); at most 16 name bytes plus a terminator |
| `$082c` | `KEYIN` | `A` = key event (0 = none): kernal GETIN **plus** the C128 keys the C64-mode kernal cannot see (`KEYIN_EXT` in drv1351 scans the VIC-IIe extended matrix: ESC → `$1b`, dedicated cursor keys → `$91/$11/$9d/$1d`, one event per press) and RUN/STOP → `$1b` for C64 keyboards |
| `$082f` | `GETCAP` | X = ID (1 gfx, 2 vdc, 3 reu, 4 keyin, 5 fillfile, 6 files, 7 selector) → A/X = entry lo/hi; unknown ID → 0/0. Preserves Y, zero page, non-stack RAM and D/I flags; other flags clobbered |
| `$0832` | `LAUNCH_APP` | Core-resident LOAD then `jmp APP_START` on success, `jmp DESK_START` on failure; the safe entry for an app replacing itself |
| `$0835` | `VDTEXT` | 80-col: `A` = row 0-24, `X` = col 0-79, `r9` → PETSCII text; no-op without a VDC |
| `$0838` | `VDCLR` | 80-col: `A` = row → 80 spaces; no-op without a VDC |
| `$083b` | `OS_TICK` | Service the registered callback once per second. Callback register/scratch clobbers apply; call outside UCI transactions |
| `$083e` | `READ_BUTTON` | A = 0 if either mouse fire button is down, nonzero when released; preserves X/Y and the interrupt/decimal flags |

`GETCAP` is a static lookup for resident software, not a hardware probe or
version negotiation. IDs 1–7 return `$c000`, `$cc00`, `$9c00`, `$082c`, `$0829`, `$4100`, `$4c80`
respectively, including on a machine without the corresponding peripheral.
Check the driver's documented presence result before optional hardware access.
The earlier dispatch defect is fixed; `tests/ci_core.py` covers every 8-bit ID,
and the storage suites exercise the public entry from the live desktop.

Apps with their own keyboard loops can call `OS_TICK`, `KEYIN` and
`READ_BUTTON`; keep a release-edge latch to turn button state into clicks.
The Ultimate browser demonstrates this and propagates the borrow when converting
the nine-bit VIC sprite X coordinate to screen coordinates. Its buffer and input
contracts are documented in the [browser guide](ULTIMATE-BROWSER.md).
Its drive panel has private capability records and confirmation state. The
browser now uses split filename caches at `$6900–$70ff` and `$7400–$7bff`, path
storage at `$7100`, and commands at `$7c00`; do not assume the old contiguous
cache at `$6000`. The host VDC capture helper borrows `$7400–$7cf4` only while
the app is idle and restores that entire region, with a byte comparison, before
input resumes. Apps executing code in that region cannot use this helper.
The VIC capture helper separately borrows `$7400–$7bcf` and the cassette
buffer `$0340–$03fb`, preserving and checking both on return. Both helpers
require an idle app, with no injected input or file transaction in progress.
They no longer use space following the resident desktop.

The [shared file API](ULTIMATE-FILES.md) owns handles in DOS contexts 1 and 2,
streams up to 512 binary bytes per call, and verifies writes to exclusively
created files. The desktop viewer uses it directly. `LAUNCH_APP` and desktop
entry call `UFS_CLOSEALL`; failed closes retain ownership for another attempt.
Apps must still close and handle errors explicitly. The [shared selector](FILE-DIALOGS.md)
loads at `$6200`, retaining caller code and document below that address. It returns
an open handle; CLOSE also restores its borrowed directory. The editor uses it
for Open and verified Save As. An IEC backend, scheduler and general replace
remain required.

Core control hit testing uses inclusive left/top and exclusive right/bottom
edges, compares the complete nine-bit X coordinate, and scans all 25 slots
while ignoring freed entries. Reload an app count after `CreateButton` before
testing it: control registration may change X. The launcher uses complete
filename pointers per row; consecutive buffers need not share a high byte.

Graphics (`$c000`…): `GFX_INIT $c000`, `GFX_ON $c006` (`A` = colour byte
fg<<4|bg; `$00` means *skip the clear*), `GFX_OFF $c009`, `GFX_SETCOLOR
$c00c` (1 = write, 0 = erase), `GFX_SETPIXEL $c00f`, `GFX_LINE $c015`,
`GFX_CIRCLE $c018`, `GPUTC $c01b` (`A` = char at `X1/Y1`), `GPUTS $c01e`
(`r9` → text at `X1/Y1`), `GFX_DRAWBYTEPATTERN $c021`. Text uses the
current pen: **pen 1 sets glyph bits, pen 0 clears them**. Drawing twice
with pen 1 does not erase anything. Clear the affected strip before drawing
replacement text. **`GPUTS`/`GPUTC` clobber X and Y** — save a loop index before the call (the launcher's row
loop lost its index this way for a long time).

VDC driver (`$cc00`…, fixed jump table; never mirror routine addresses by
hand): `VDC_GETREG $cc00` (`X` = reg → `A`), `VDC_SETREG $cc03`,
`VDC_SEEK $cc06`, `VDC_PUTS $cc09` (string at `vdcbp`, cell at `vdcdp`),
`VDC_PUTCHR $cc0c`, `VDC_CLS $cc0f`, `VDC_FONTUP $cc12`, `VDC_INIT $cc15`,
`VDC_PRESENT $cc18` (`A` = 1 if an 8563 answers), `VDC_TEXT $cc1b`,
`VDC_CLR $cc1e`, `VDC_BANNER $cc21`, `VDC_LIVE $cc24` (byte, 1 once the
display is up). Apps use `VDTEXT/VDCLR` (or the driver slots directly) to
mirror their state on the 80-column screen; rows 0-1 belong to the header,
rows 2-23 to the running app, row 23 is used for key hints by convention.
Runtime register helpers select the register, wait for bit 7 of `$d600`, then
access `$d601`, as specified in the
[Commodore 128 Programmer's Reference Guide](https://www.pagetable.com/docs/Commodore%20128%20Programmer%27s%20Reference%20Guide.pdf)
(printed pages 296 and 306). Presence detection uses a bounded wait so a missing
VDC returns false. Runtime waits remain unbounded after presence is established;
cold initialization retains its separate register sequence.

## Application skeleton (what the fmgr, shell and settings do)

```asm
.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "kernal.inc"

* = APP_START
        #RegisterApp                  ; bump APP_ID_TBL
        #DrawRect 16,8,304,180,1      ; window outline
        #Text 24, 14, title           ; GPUTS at x,y
        ; 80-column companion: blank rows 2-23, then your header/hint
        ...
loop:   jsr KEYIN                     ; OWN the keyboard: a private loop
        beq loop                      ; (the core loop's key read would race you)
        cmp #$1b                      ; ESC -> back to the desktop
        beq back
        ...                           ; handle keys, clear strips before redrawing
        jmp loop
back:   jmp DESK_START                ; one-way: DESK_START resets the stack
                                      ; and re-enters MAINLOOP (never RTS)
title:  .text "My app", 0
```

Rules learned on hardware and in CI:

* **Start other apps only through `LAUNCH_APP`** (set the name with
  `FILLFILE` first). A `jsr APP_LOADER` from inside the app being replaced
  returns into freshly loaded bytes. `LAUNCH_APP` returns to the desktop
  if LOAD fails; it does not execute the old or partially loaded app.
  App manifests and load-address validation remain to be implemented.
* **Leave through `jmp DESK_START`.** It clears the bitmap, restores the
  pointer sprite, resets the stack and `jmp`s to `MAINLOOP`.
* `RTS` from `DESK_START` (or from any one-way entry) pops an empty stack
  and kills the tick dispatch.
* After any serial-bus work, `cli` (the fmgr/shell `sendcmd` does this).
* Key compares: `#'D'` in 64tass assembles to the **shifted** code `$c4`;
  a real keypress is `$44`. Use `#$44`.
* Drive commands go through channel 15 (`sendcmd` in the shell/fmgr):
  `S0:name`, `R0:new=old`, `C0:new=0:old`. The shell reads the drive's
  status line back into `stbuf` and shows it unless it says `00, OK` or
  `01, FILES SCRATCHED`.

### Once-per-second tick

`MAINLOOP` calls `jmp ($033c)` once per second. The desktop installs its
clock there (`APP_TICK`). An app that runs its own `KEYIN` loop never sees
the tick — do not rely on it for input (that race is documented in the
git history: settings used to lose D/B/ESC to the core loop).

### Settings record (`SETREC = $7350`, file `UOS-SET`)

```
+0,+1  load address ($7350)
+2     SETREC_VER    2 = the zone bytes are valid (format-0 records carry 0)
+3     SETREC_TZ     time zone, signed quarter-hours from UTC (-48..+56); default -16 = UTC-4
+4     SETREC_TZMAG  $a5 once the OS wrote the zone
+5     SETREC_DISP   0 = 40-col only, 1 = 80-col only, 2 = both
+6     SETREC_BG     desktop background colour 0-15
+7,+8  reserved
```
Saved by the settings app via the kernal SAVE (unshifted filename bytes),
read at boot by `VDPREF`. The settings app image is padded up to `$7350`
so loading it overwrites the record with compiled defaults; it re-reads
`UOS-SET` on entry. `NET_SYNC` normalises `+2..+4` (a format-0 record or
garbage → the default zone) before anything reads them.

## Network and clock (`uos-net`, `NET_BASE = $9100`)

The driver speaks the Ultimate II+ **command interface** (`$df1c-$df1f`,
cartridge setting "Command Interface = Enabled"): targets `$01` Ultimate
DOS and `$03` network, the protocol of xlar54's ultimateii-dos-lib and the
firmware's `command_intf.cc`. Every wait is bounded (~11 s), so a missing
or wedged cartridge returns instead of hanging.

| Slot | Name | Contract |
|---|---|---|
| `$9100` | `NET_PRESENT` | `A` = 1 when `$df1d` reads `$c9` twice |
| `$9103` | `NET_CMD` | `r0` → command bytes (target first), `A` = length → `A` = status code (`"00,OK"` → 0), `C` = 1 absent/timeout; reply in `NET_DATA`/`NET_LEN`, status text in `NET_STAT` |
| `$9106` | `NET_GETIP` | `A` = 1 when an interface has an address → `NET_IP` (4), `NET_IPSTR` (dotted, 0-terminated) |
| `$9109` | `NET_OPEN` | `A` = 7 tcp / 8 udp, `r0` → host name (ASCII, the Ultimate resolves it), `r1` = port → `A` = socket, `C` = 1 failed |
| `$910c` | `NET_CLOSE` | `A` = socket |
| `$910f` | `NET_READ` | `A` = socket, `r1` = max (≤ 508) → payload at `NET_DATA+2`, `NET_LEN`; `A` = 0 data, 1 nothing yet (40 ms window), 2 closed, 3 error |
| `$9112` | `NET_WRITE` | `A` = socket, `r0` → data, `X` = length (1..200) → `A` = status code |
| `$9115` | `NET_SYNC` | the self-setting clock: interface present? address? SNTP (`pool.ntp.org`, UDP 123) → zone from the record → CIA #1 TOD (12 h BCD + PM, the 6526's hour-12 AM/PM inversion corrected by read-back) → the Ultimate's RTC (DOS `SET_TIME`). `A` = `NET_STATE` |
| `$9118` | `NET_APPLYNTP` | a 48-byte NTP reply at `NET_DATA+2` → `NET_HOUR/MIN/SEC`, `NET_YEAR/MON/DAY/WDAY`, TOD; `A` = 0, or 1 for a zero timestamp |
| `$911b` | `NET_RTCTIME` | the running Ultimate RTC as `"YYYY/MM/DD HH:MM:SS"` in `NET_DATA`; use DOS GET_TIME for live readback, not saved REST Clock Settings fields |
| `$9164` | `NET_STREAM` | `r0` → command, `r1` = length 2–896, `r3` → per-packet callback (0 = aggregate). See [UCI service contract](ULTIMATE-SERVICE.md) for binary data, cancellation, and overflow |
| `$911e` | `NET_TZSHIFT` | `A` = signed quarter-hours → shifts the running TOD (settings `+`/`-`, no network round trip) |

`NET_CMD` also drives the DOS directory commands (target `$01`): `CD` =
`$01 $11 <path>`, `PWD` = `$01 $12` (path → `NET_DATA`), `LS` = `$01 $13`
then `$01 $14` with `NET_DIRMODE` (`$9162`) set so each reply block (one
entry: attribute byte + name) is kept null-separated and counted in
`NET_DIRN` (`$9163`). The FAT directory attribute is bit 4 (`$10`), now used
by the shell. Aggregate directory results retain only complete leading entries
and set `NET_TRUNC` if the buffer fills. Use `NET_STREAM` to process larger
directories without collecting the whole reply in this buffer.

Data bytes (`NET_STATE = $9121`, then hour, min, sec, year word, month,
day, weekday (0 = Sunday), zone, IP, IPSTR, LEN, SOCK, STAT) are plain RAM:
`tests/ci_vdc.py` and `hw_net_check.py` read them back. `NET_STATE`:
`$ff` not tried, 0 synced, 1 no NTP reply, 2 no network address, 3 no
command interface, 4 host unresolved / socket open failed. The desktop
shows the state next to the clock on the 80-column row 0 and in the
Computer window; the shell has `CAT file` (view the first 512 bytes of a
disk file as text in the rows region + 80-column rows 9-16), `PEEK addr`
and `POKE addr val` (hex, a memory monitor), `CD path` / `PWD` / `LS`
(navigate the Ultimate II+ filesystem via the DOS directory commands over
the command interface: CHANGE_DIR/GET_PATH/OPEN_DIR/READ_DIR), `HELP`
(full command list in the rows region), `TIME [SYNC]`, `IP` and `GET host
path`
(an HTTP/1.0 GET whose status line lands on the response line and whose
next eight lines fill the rows region, mirrored on rows 9-16).

Limits, stated plainly: no DST rule (adjust the zone in settings twice a
year); the date is not re-derived when the zone is shifted (the next sync
fixes it); the calendar is exact for 1900-2199; one SNTP sample, no
round-trip compensation (the request/reply takes well under a second on a
LAN, so the clock is set to the second).

## Controls, windows and menus (`APP_CTL_TBL = $9000`)

Every clickable thing is a 10-byte slot in a 25-slot table at `$9001-$90fa`
(`APP_CTL_CTR` at `$9000` counts them): app-id, button-id, callback (lo/hi),
x1 (word), y1, x2 (word), y2. `CreateButton` fills the first free slot
(`FIND_CTL` with id `$ff`) and **skips the write when the table is full**
(it used to store the record at `$00xx`, i.e. into zero page).
`TESTCLICK` scans **all 25 slots** and **skips any slot whose app-id is
`$ff`** — until 2026-09-06 it scanned `APP_CTL_CTR` slots (a counter nothing
ever initialised: RAM garbage of 122-135 on real boots, so the scan walked
off the table into driver code) and matched on coordinates only, so a
"removed" button stayed clickable until its slot was reused.

**Layers by app-id.** The app-id is a *layer*, not an application:

| app-id | layer | created by | freed by |
|---|---|---|---|
| 0 | desktop base: menu bar `(0,0)`, computer icon `(0,1)` | `DESK_START` after `clr_ctls` | never (rebuilt on every desktop entry) |
| 1 | the open window or dialog: title-bar close box `(1,0)`, its content buttons (launcher rows `(1,20..25)`, Cancel `(1,29)`, quit Yes/No `(1,1)/(1,2)`) | `CreateWindow` / the dialog | `ON_CLOSE` → `rm_app_ctls 1` |
| 2 | the ultos popup menu items `(2,1..5)` | `MNU_ULTOS` | `closemenu` → `rm_app_ctls 2` |

Layers stack LIFO (menu → closes itself before a window opens), so freeing
a layer never strands a live slot behind a freed one. The old scheme reused
app-id 0 for everything and, for example, `closemenu`'s `RemoveButton 0,1`
removed the *first* `(0,1)` — the computer icon — and never removed quit.

**One close path.** `ON_CLOSE` (desktop) is where every window and dialog
ends: `FetchScreen` (the desktop's full-screen REU stash from `DESK_START`
erases any modal window, so no per-window rect is needed), `rm_app_ctls 1`,
`vd_reset` (80-column rows back to `desktop`), and a forced clock redraw
(`minute = $ff`, the stash carried a stale time). The title-bar X, the
launcher's Cancel, the quit dialog's No and the old `WIN_OK` all `jmp
ON_CLOSE`. It used to `#CloseWindow` the Computer window's hardcoded rect,
so the X on the Applications window restored the wrong pixels, and nothing
ever freed the close box.

`DESK_START` calls `clr_ctls` first (counter 0, all slots `$ff`), so a window
or app that was open when the desktop was left cannot leave ghost click
targets. Launching a row from the Applications window goes through
`LAUNCH_APP` (cleared screen), and the window's controls die with the next
desktop entry.

## The calculator (`uos-calc`)

The calculator component of FR-S5; the standalone terminal remains open.
Integer, 16-bit unsigned: digits build the entry, `+ - * /` chain
immediate-execution (no precedence), `=`/RETURN folds the chain, `DEL`
backspaces the entry, `C` clears, ESC exits. While an error is latched
only `C` is accepted. Errors: `DIV/0` and `OVF` (multiply overflow past
65535 — the accumulator keeps the low 16 bits); subtraction wraps
(unsigned, documented). 16/16 division is a shift-subtract with the 17th
remainder bit checked, so divisors above 32768 are exact; the display is
drawn on both screens. Launchable from the Applications menu (popup
"calculator" entry + the disk-scanning launcher), from the file manager
(RETURN), and from the shell (`RUN UOS-CALC`).

In a 16-bit shift/subtract divider, include the high byte in each shift
(`asl low` / `rol high`) and retain the seventeenth remainder bit. Carry
conventions must agree between every function and caller.

## The file manager: browsing, file information, and copying

The ten visible rows scroll through a 64-entry RAM cache. `cachebase` is a
16-bit absolute directory ordinal; `fmrow` and `scroll` index that cache.
At a cache edge the next scan retains the preceding nine visible entries.
The cache bounds RAM consumption without limiting the directory to 64 files.
The IEC parser follows linked BASIC lines and zero terminators, stores both
block-count bytes and three type bytes, and accepts zero-block entries.
It stops on EOF, a zero link, a serial error, or an overlong/malformed line.
Empty/absent devices return to the input loop; actions cannot dereference an
empty row. `fmready` is set after scanning and both display paints, allowing
regressions to wait for real input readiness instead of the first LOAD bytes.
On entry, `sysdev` remembers the device which loaded the app. ESC returns to
the resident desktop and restores that device for subsequent app loads.

`8`, `9`, `0`, `1` select devices 8, 9, 10, 11. `C` uses drive-side
`C0:new=old`; `B` streams to the paired device (8/9 or 10/11). The latter
preserves PRG/SEQ/USR type and every data byte, including PRG load addresses.
REL copying still needs a record-aware implementation. The source block
count bounds malformed streams; there is no successful truncation at 16 KiB.

Each page direction change calls `CLRCHN`, then `CHKIN` or `CHKOUT` again.
Counters live in RAM because those KERNAL calls overwrite X. Check OPEN and
channel-selection carry, per-byte serial status, EOF on the final byte, and
drive status after opening and closing the destination. Read channel 15 via
TALK/TKSA/ACPTR/UNTLK without closing it while data channels are open.
An existing destination is an error. Copy/rename handlers return to their
caller instead of leaking a stack frame on each action.

The regression extracts both copied files from private disk images and
compares all 18,439 bytes. A directory entry alone cannot prove persistence
or file integrity. Interrupted/failed copies may leave partial files;
transactional staging/cleanup and copy-time readback verification remain
roadmap work. No REL, arbitrary IEC-address, or physical cross-device-copy
certification is implied by the PRG emulator test.

`CLR_RECT` now zeros RAM without an REU zero-pattern dependency. Its arguments
are `r0 = address`, `r2 = length`; zero length is a no-op, and `r0/r2` are
consumed. The macro preserves coordinates. Its rectangles round outward to
8-pixel bands, so list clears must stop below the status line's band.
Full-screen/window snapshots still use the REU.

## The text editor (`uos-edit`)

The Applications menu launches a 768-byte ASCII note editor. Type to append,
RETURN inserts LF, and DEL removes the last byte. F3 opens the shared cartridge
selector, F1 saves to a new cartridge filename, F5 starts a new document, and
ESC exits. Unsaved text requires confirmation before Open, New or exit. Both
displays follow the end of the document; VIC text uses fixed eight-pixel cells.

The document occupies `$5f00–$61ff`, below the modal library. Open validates the
complete staged text and closes its file and directory lease before replacing
the document. Save As verifies writes, closes/reopens the file, compares every
byte and closes again before clearing the dirty flag. Existing names are
rejected. Failed new saves retain the created file and unsaved document.

Startup still imports `NOTES.T` read-only from the system IEC disk, converting
PETSCII/CR to ASCII/LF. It bounds the directory existence check and file read,
uses separate logical files, and rejects serial errors, oversized notes and
invalid text. It never scratches or rewrites the legacy note. See the
[selector guide](FILE-DIALOGS.md) for its ABI, key handling, error semantics and
remaining editing/IEC requirements.

## 64tass conventions that bite

* `.text "ABC"` emits **shifted** PETSCII (`$c1…`). Filenames for
  `SETNAM`/DOS commands and key compares must be explicit unshifted
  `.byte`s (`$41…`), or lowercase in `.text`.
* `_label` is local to the preceding global label; a `beq _x` across
  routines fails with "not defined symbol".
* Screen-code text (for VDC RAM or `$0400`) needs `.enc` + `.cdef`; the
  VDC driver's `p2s` maps PETSCII for you, so pass PETSCII to `VDTEXT`.
* Module exports must be fixed jump tables; natural-order addresses drift.
* **Character literals compile with the current `.enc`.** This project's
  default encoding maps `.text` (and `#'A'`) to SHIFTED PETSCII (`'A'` =
  `$c1`), but `KEYIN`/`GETIN` return ASCII (`'A'` = `$41`). Compare typed
  input against explicit ASCII codes (`cmp #$41`), not `cmp #'A'` — the
  latter silently rejected every A-F hex digit in the PEEK/POKE parser.
  Digits `$30-$39` and punctuation `$20-$3f` are identical in both, so only
  letters bite.
* **`X1`/`Y1`/`X2` ARE `r0`/`r1`/`r2` — and `GFX_SETPIXEL` computes the
  pixel address from the FULL 16-bit `Y1+1:Y1`.** Anything that clobbers
  `r0`–`r2` between draws poisons the next draw's coordinate: the
  `ClrRect` macro used to leave the clear-pattern address in `r1`, so
  callers that only set `Y1`'s low byte plotted thousands of rows past
  the bitmap (the file manager's list was invisible on the 40-col
  screen, and the shell's response line grew ghost glyphs). The macro
  now saves/restores `r0`–`r2` around the clears — keep any direct
  `CLR_RECT` caller doing the same, and never rely on another routine
  leaving `Y1+1` zero.
* Text is not XOR-drawn: use pen 0 to erase a known glyph or `#ClrRect`
  to replace a whole strip. Clear boundaries must respect adjacent widgets.
* VDC text uses three write passes plus readback repair. The inter-pass
  delay is one 256-iteration loop (~1.3 ms at 1 MHz); an accidental nested
  loop previously delayed each pass by roughly 327 ms.

## Build and test

```
./build.sh                                   # 64tass, byte-identical rebuild -> target/ultos.d64
UOS_CI_SKIP_SAVE=1 python3 tests/ci_fm.py    # x64: boot, fmgr actions, settings, shell incl. CAT/PEEK/POKE/CD/PWD/LS/IP/TIME/GET (18 checks)
python3 tests/ci_vdc.py                      # x128 -go64: companion display, clock, keys, controls, launcher, offline browser (15 checks)
python3 tests/ci_edit.py                     # x64: legacy import/edit, unavailable Save As preserves text, discard/exit (5 checks)
python3 tests/ci_calc.py                     # x64: the calculator (uos-calc) arithmetic, chains, OVF/DIV/0, backspace, exit (12 checks)
python3 tests/ci_copy.py                     # x64: >16 KiB PRG copies both ways, type/byte checks, existing destination rejection
python3 tests/ci_storage.py                  # x64: directory/cache scrolling, bitmap restoration, empty/missing devices
python3 tests/ci_storage.py --machine x128   # same, with VDC readback
python3 tests/run_ci.py storage64 storage128 fm vdc copy edit calc # retained logs + exact build hashes
python3 hw_storage_check.py                  # real C128: private test disk, scrolling, VIC/VDC readback, boot distributable
python3 -m pip install -r tests/requirements-uci.txt # use a virtual environment
python3 tests/ci_core.py                      # assembled core: all 256 GETCAP IDs, registers/stack/RAM
python3 tests/ci_desktop.py                   # assembled launcher: 0-6 apps, control callbacks and complete X-coordinate hit testing
python3 tests/ci_vdc_protocol.py              # assembled VDC driver: register readiness, exact text/attributes, absent probe
python3 tests/ci_vdc_capture.py               # IRQ capture: exact bytes, address drift/retry, timeout, guards and IRQ restoration
python3 tests/ci_uci.py                       # assembled UCI driver: 15 protocol/CPU checks, no VICE needed
python3 tests/ci_ultimate.py                  # browser/drive panel: paging, inventory, protection, mount/eject, bounds
python3 tests/ci_file_copy.py                 # core-loaded copy dialog, binary verification, faults, cancellation and full frames
python3 tests/ci_picker.py                    # shared selector, pages, complete paths, ownership and directory recovery
python3 tests/ci_editor_files.py              # editor verified Save As/Open, legacy import, dirty state and faults
python3 tests/ci_file_dialog_display.py       # actual VIC/VDC frames, caret, modal erasure and return
python3 tests/ci_irq_state.py                 # foreground sampler: register/stack/flag preservation
python3 tests/ci_capture_host.py              # borrowed VDC-capture RAM restored on success and observation/probe failure
python3 tests/profile_browser.py --out /tmp/browser-render --check-fresh # actual graphics: cycles and fresh-frame comparison
python3 hw_uci_check.py                      # real C128: identification, inventory, long echo, directory streaming
python3 hw_ultimate_check.py                 # real C128: browser navigation, complete names, VDC readback, path restoration
python3 hw_ultimate_check.py --drives        # real C128: private D64 mount, IEC copy, byte verification and eject on empty B
python3 hw_ultimate_check.py --files         # real C128: shared files, viewer and copy dialog, independent byte/prefix readback
python3 hw_ultimate_check.py --editor        # real C128: shared selector, verified Save As, cancel and independent file reads
python3 tests/screens.py                     # x128: capture every screen (vdc-emu-out/screens.png) to eyeball fit
python3 hw_vdc_check.py                      # real C128: reads the companion display back off the 8563
python3 hw_calc_check.py                     # real C128: calculator LOADs and draws its display (boot-stub probe)
python3 hw_net_check.py                      # real C128: driver sync, advancing DOS GET_TIME RTC, VDC clock
python3 deploy_hw.py                         # real C128 via the Ultimate II+ REST API
```

Never boot `target/ultos.d64` itself read-write in a test: copy it to a
scratch image first (a settings SAVE otherwise lands in the committed file).
The emulator scripts drive the OS through real code paths: keys through the
kernal keyboard buffer (`$0277/$c6`, 10 bytes at a time), apps through a
one-shot tick-vector trampoline, and they read results from memory (x64
binary monitor) or VDC RAM (x128 text monitor, `bank vdc`).
