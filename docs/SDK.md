# UltOS application SDK (fork: marc-shade/uos-master)

How to write a program that runs under uOS on a C128 (C64 mode) with an
Ultimate II+. Everything here is taken from the sources in `src/` and the
build output; addresses are the fixed ABI the core and drivers export.

## Memory map (from `build.sh` output and `src/routines.inc`)

| Range | Owner | Notes |
|---|---|---|
| `$0801-$0fff` | core `uos` | **must end below `$1000`** (the desktop loads there); check `Data: … $0801-$0fxx` after any core edit |
| `$1000-$4023` | desktop `uos-desktop` | resident (`routines.inc` still says `DESK_END = $2fff`; the build output is the truth); `DESK_START = $1000` is the one-way re-entry point |
| `$5000-$8fff` | the running app | `APP_START = $5000`; one app at a time, loaded over the previous one |
| `$7350-$7358` | settings record | `SETREC`; the settings app image is padded up to it, see below |
| `$7f00` | tick trampoline (CI only) | free for apps at run time |
| `$8000` | sprites | pointer sprite; `$87f8` = sprite pointer (colour-RAM fills clobber it) |
| `$8400-$87ff` | screen matrix / colour cells | hires colour |
| `$8800-$89ff` | `NET_DATA` | uos-net's 512-byte reply buffer (socket payload at `+2`) |
| `$9000-$90ff` | `APP_CTL_TBL` | control (button) hit-test table, 25 ten-byte slots (`APP_CTL_END = $9100`) |
| `$9100-$9aff` | `uos-net` | Ultimate II+ command interface: network + SNTP clock (`NET_BASE = $9100`, jump table + data bytes, see below) |
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
`uos-sprites`, `uos-reu`, `uos-net`, `uos-desktop`, then `VDPREF` loads the
settings record `UOS-SET` (absent file → defaults: mode 2 = both displays,
cyan background), `VDSETUP` brings up the 8563 when the mode allows it,
`NET_SYNC` sets the clock from the network (see *Network and clock*), and
the desktop starts. The launcher hides these system components by name
(`syscomps` in `uos-desktop.asm`) and lists every other `uos-*` file on the
disk as an application.

## Core jump table (`$0811`…, `src/routines.inc`)

| Slot | Name | Contract |
|---|---|---|
| `$0811` | `MAINLOOP` | core loop: mouse/click dispatch + once-per-second tick through `($033c)` |
| `$0814` | `FIND_CTL` | control hit-test |
| `$0817/$081a/$081d` | `FS_APP/FS_SCREEN/FS_RECT` | REU stash/fetch of app / screen / rect |
| `$0820` | `CLR_RECT` | |
| `$0823` | `LOAD_IMM` | inline `$00`-terminated filename follows the `jsr` (see `loadfiles` in `uos.asm`) |
| `$0826` | `APP_LOADER` | kernal LOAD of the file named in the file buffer; `LOADERR` latches the kernal error |
| `$0829` | `FILLFILE` | `r0` → `$00`-terminated name → file buffer (dynamic loading) |
| `$082c` | `KEYIN` | `A` = key event (0 = none): kernal GETIN **plus** the C128 keys the C64-mode kernal cannot see (`KEYIN_EXT` in drv1351 scans the VIC-IIe extended matrix: ESC → `$1b`, dedicated cursor keys → `$91/$11/$9d/$1d`, one event per press) and RUN/STOP → `$1b` for C64 keyboards |
| `$082f` | `GETCAP` | `X` = capability id (1 gfx, 2 vdc, 3 reu, 4 keyin, 5 fillfile) → `A/X` = driver base lo/hi, `0/0` absent |
| `$0832` | `LAUNCH_APP` | file buffer → LOAD + `jmp APP_START`, **core-resident** — the only safe way for an app to start another app (the load overwrites the caller) |
| `$0835` | `VDTEXT` | 80-col: `A` = row 0-24, `X` = col 0-79, `r9` → PETSCII text; no-op without a VDC |
| `$0838` | `VDCLR` | 80-col: `A` = row → 80 spaces; no-op without a VDC |

Graphics (`$c000`…): `GFX_INIT $c000`, `GFX_ON $c006` (`A` = colour byte
fg<<4|bg; `$00` means *skip the clear*), `GFX_OFF $c009`, `GFX_SETCOLOR
$c00c` (1 = write, 0 = erase), `GFX_SETPIXEL $c00f`, `GFX_LINE $c015`,
`GFX_CIRCLE $c018`, `GPUTC $c01b` (`A` = char at `X1/Y1`), `GPUTS $c01e`
(`r9` → text at `X1/Y1`), `GFX_DRAWBYTEPATTERN $c021`. Text is an **XOR
engine**: drawing a string twice erases it — keep the string you drew
(`oldbuf` pattern in the shell) and redraw it to erase. **`GPUTS`/`GPUTC`
clobber X and Y** — save a loop index before the call (the launcher's row
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
        ...                           ; handle keys, redraw with XOR discipline
        jmp loop
back:   jmp DESK_START                ; one-way: DESK_START resets the stack
                                      ; and re-enters MAINLOOP (never RTS)
title:  .text "My app", 0
```

Rules learned on hardware and in CI:

* **Start other apps only through `LAUNCH_APP`** (set the name with
  `FILLFILE` first). A `jsr APP_LOADER` from inside the app being replaced
  returns into freshly loaded bytes.
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
| `$911b` | `NET_RTCTIME` | the Ultimate's RTC as `"YYYY/MM/DD HH:MM:SS"` in `NET_DATA` (diagnostic: that RTC read 2015 before the driver started setting it) |
| `$911e` | `NET_TZSHIFT` | `A` = signed quarter-hours → shifts the running TOD (settings `+`/`-`, no network round trip) |

`NET_CMD` also drives the DOS directory commands (target `$01`): `CD` =
`$01 $11 <path>`, `PWD` = `$01 $12` (path → `NET_DATA`), `LS` = `$01 $13`
then `$01 $14` with `NET_DIRMODE` (`$9162`) set so each reply block (one
entry: attribute byte + name) is kept null-separated and counted in
`NET_DIRN` (`$9163`). DIR entries have attribute bit 6.

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

## The text editor (`uos-edit`)

A note editor launched from the Applications menu: type text, RETURN for a
new line, DEL to backspace, F1 to save, ESC to exit; it loads `NOTES.T` on
entry. Both displays are drawn (40-column proportional + 80-column mirror).
Save/load use a SEQ file over the KERNAL. Two 1541 traps learned here:

* **Closing the command channel (secondary 15) closes every open file on
  the drive.** So the "does NOTES.T exist?" check can't open 15 alongside
  the file. `ed_exists` instead pattern-lists `"$0:NOTES.T"` on its own
  logical file and counts quote characters (a matching file adds a second
  quoted entry). Use a *different logical file* from the one you reopen
  next, or the real drive returns stale/garbled data.
* **A missing SEQ file reads `$00` forever with `ST=$00` on the real 1541
  (Ultimate),** and its command channel reads back empty — neither ST nor
  the status channel flags the miss the way VICE does. Bound every file
  read with a hard page/byte counter, not a 16-bit compare, and gate the
  read on the directory check above.
* **SEQ file *data* writes do not persist to the .d64 image under this
  box's VICE** (the same gate as the settings kernal SAVE); the write
  sequence itself is proven clean (`probes/seqwrite.asm` -> CHKOUT ST=$00)
  and lands on real hardware.

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

## Build and test

```
./build.sh                                   # 64tass, byte-identical rebuild -> target/ultos.d64
UOS_CI_SKIP_SAVE=1 python3 tests/ci_fm.py    # x64: boot, fmgr actions, settings, shell incl. CAT/PEEK/POKE/CD/PWD/LS/IP/TIME/GET (18 checks)
python3 tests/ci_vdc.py                      # x128 -go64: companion display, clock/SNTP conversion, zone, C128 ESC key, control-table integrity, status line (14 checks)
python3 tests/ci_edit.py                     # x64: the text editor (uos-edit) load/edit/save-runs/exit (5 checks)
python3 tests/screens.py                     # x128: capture every screen (vdc-emu-out/screens.png) to eyeball fit
python3 hw_vdc_check.py                      # real C128: reads the companion display back off the 8563
python3 hw_net_check.py                      # real C128: clock synced (driver bytes, Ultimate RTC via REST, row 0)
python3 deploy_hw.py                         # real C128 via the Ultimate II+ REST API
```

Never boot `target/ultos.d64` itself read-write in a test: copy it to a
scratch image first (a settings SAVE otherwise lands in the committed file).
Both CI scripts drive the OS through real code paths: keys through the
kernal keyboard buffer (`$0277/$c6`, 10 bytes at a time), apps through a
one-shot tick-vector trampoline, and they read results from memory (x64
binary monitor) or VDC RAM (x128 text monitor, `bank vdc`).
