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
| `$9000` | `APP_CTL_TBL` | control (button) hit-test table |
| `$9b00` | `APP_ID_TBL` | app-id counter (`RegisterApp`) |
| `$9c00` | `uos-reu` | `REU_SIZE/STASH/FETCH/PARAMS` at `$9c00/03/06/09` |
| `$9f00` | `uos-drv1351` | mouse driver, `INIT_MOUSE = $9f03` |
| `$a000-$bfff` | bitmap | 320×200 hires |
| `$c000-$cbff` | `uos-gfx` | graphics engine |
| `$cc00-$cfff` | `uos-vdc` | 8563 driver + 80-column companion API |
| `$d000-$dfff` | I/O | VDC at `$d600/$d601` |

Zero page: `r0`-`r15` word registers at `$02-$21` (`r0L=$02`, `r0H=$03`, …
`r9L=$14`, `r9H=$15`). **`X1/Y1` of the graphics engine ARE `r0/r1`
(`$02-$05`)** — writing a text position destroys a pointer you parked in
`r0`. `$23-$26` are reserved for the VDC driver's caller pointers.

## Boot chain

`uos` (core) loads, in order: `uos-gfx`, `uos-vdc`, `uos-drv1351`,
`uos-sprites`, `uos-reu`, `uos-desktop`, then `VDPREF` loads the settings
record `UOS-SET` (absent file → defaults: mode 2 = both displays, cyan
background), `VDSETUP` brings up the 8563 when the mode allows it, and the
desktop starts. The launcher hides these system components by name
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
| `$082c` | `KEYIN` | `A` = kernal GETIN (0 = no key); the kernal IRQ keeps scanning the keyboard |
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
+0,+1  load address ($7350)   +2..+4 reserved
+5     SETREC_DISP  0 = 40-col only, 1 = 80-col only, 2 = both
+6     SETREC_BG    desktop background colour 0-15
+7,+8  reserved
```
Saved by the settings app via the kernal SAVE (unshifted filename bytes),
read at boot by `VDPREF`. The settings app image is padded up to `$7350`
so loading it overwrites the record with compiled defaults; it re-reads
`UOS-SET` on entry.

## 64tass conventions that bite

* `.text "ABC"` emits **shifted** PETSCII (`$c1…`). Filenames for
  `SETNAM`/DOS commands and key compares must be explicit unshifted
  `.byte`s (`$41…`), or lowercase in `.text`.
* `_label` is local to the preceding global label; a `beq _x` across
  routines fails with "not defined symbol".
* Screen-code text (for VDC RAM or `$0400`) needs `.enc` + `.cdef`; the
  VDC driver's `p2s` maps PETSCII for you, so pass PETSCII to `VDTEXT`.
* Module exports must be fixed jump tables; natural-order addresses drift.

## Build and test

```
./build.sh                                   # 64tass, byte-identical rebuild -> target/ultos.d64
UOS_CI_SKIP_SAVE=1 python3 tests/ci_fm.py    # x64: boot, fmgr actions, settings, shell (14 checks)
python3 tests/ci_vdc.py                      # x128 -go64: 80-column companion display (6 checks)
python3 hw_vdc_check.py                      # real C128: reads the companion display back off the 8563
python3 deploy_hw.py                         # real C128 via the Ultimate II+ REST API
```

Never boot `target/ultos.d64` itself read-write in a test: copy it to a
scratch image first (a settings SAVE otherwise lands in the committed file).
Both CI scripts drive the OS through real code paths: keys through the
kernal keyboard buffer (`$0277/$c6`, 10 bytes at a time), apps through a
one-shot tick-vector trampoline, and they read results from memory (x64
binary monitor) or VDC RAM (x128 text monitor, `bank vdc`).
