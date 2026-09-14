# UltOS — a modern graphical OS for the Commodore 128 (Ultimate II+ family)

Fork of [xlar54/uos-master](https://github.com/xlar54/uos-master) — Scott Hutter's
work-in-progress graphical operating system written specifically for the
[Ultimate 64 / Ultimate II+](https://1541u-documentation.readthedocs.io) cartridge line.

uOS already boots and runs on **real hardware**: a Commodore 128 with an Ultimate II+,
16 MB REU, 1541/1581 drives and *both* displays (VIC-II 40-col + 8563 VDC 80-col) wired up.
The upstream project is a young alpha (desktop + settings, mouse-driven); this fork
builds it out into a complete C128 OS — see [docs/roadmap.html](docs/roadmap.html)
(gap analysis + M0–M6 milestones, hardware-gated), [docs/prd.html](docs/prd.html)
(product requirements across the whole 2026 Commodore hardware universe) and
[docs/SDK.md](docs/SDK.md) (application SDK: memory map, jump tables, app lifecycle,
80-column companion API, CI).

The current [completion roadmap and gap analysis](docs/IMPLEMENTATION-ROADMAP.md)
tracks the remaining kernel, GEOS/Wheels application parity, Ultimate desktop
integration, and expansion-hardware work. uOS is still under development;
the basic editor and calculator are only the beginning of the application suite.

A separate [native C128 kernel and memory workspace](docs/NATIVE-KERNEL.md)
now boots in native mode, manages both RAM banks with owner-checked handles,
and displays its memory controls on both screens. Build it with
`python3 build-native.py`; the resulting disk is `target/native/uos128.d64`.
The native desktop suite below builds on this kernel; broader desktop and
application migration remains in progress.
Press **C** in the native workspace for the [native calculator](docs/NATIVE-APPS.md),
loaded through a checked app manifest with automatic resource cleanup. It retains
32 calculation results in bank 1, exports them to a new SEQ file with **S** and
returns with Esc. [Native IEC file services](docs/NATIVE-FILES.md) provide owned
streams and byte-verified history export.
Press **B** for [Files and Apps](docs/NATIVE-BROWSER.md): browse an IEC root
directory, discover native apps by their image header, launch them, and inspect
file bytes on both displays. Device selection covers 8–30 with an explicit
D64/D71/D81 format. Returning from a launched app reopens the browser.
Select **EDITOR** there for the [native banked text editor](docs/NATIVE-EDITOR.md):
cursor editing across both RAM banks, Open with dirty-document protection,
and Save As with a complete reopen comparison. Documents can cross a 64 KiB
byte offset; available heap memory limits capacity.
ABI 1.3 also provides [native Ultimate files](docs/NATIVE-ULTIMATE.md): select
**ULT** with F6 in the editor to open absolute USB paths and save with complete
readback verification. ABI 1.4 also loads apps through owned Ultimate streams:
press **L** in Files and Apps for an absolute USB app path, **Tab** to choose
DOS context 1/2 and **Enter** to launch. A USB-loaded calculator saves verified
history beside its image. ABI 1.5 adds USB directories: **F** selects ULT,
**Enter** opens a folder or file, **P** goes to the parent and **G** enters a
directory path. App returns retain the folder and full selected filename even
when a save reorders the listing. The editor's Open and Save As fields now
offer **Tab** for a [shared file picker](docs/NATIVE-FILE-DIALOGS.md), keeping
the document allocated while browsing IEC or Ultimate storage. The
[picker checkpoint](docs/validation/2026-09-10-native-file-dialogs/README.md)
passes CPU, emulator and physical USB/IEC qualification. ABI 1.6 now adds
[shared field editing](docs/NATIVE-FIELDS.md) to all three native apps, with
caret navigation, insertion, forward deletion and clipping on both displays;
the [field checkpoint](docs/validation/2026-09-10-native-fields/README.md) passes
20 CPU suites, ten emulator workflows and physical USB/IEC qualification.
ABI 1.8 adds a [native graphical desktop and drawing library](docs/NATIVE-GRAPHICS.md).
Run `python3 -B build-native-desktop.py` to build
`target/native-desktop/uos128.d64`. The desktop starts in native mode with
blue graphical launchers on both displays: 320×200 VIC and
[640×200 VDC](docs/NATIVE-VDC-DESKTOP.md). It launches Calculator, Editor,
Files, Ultimate, Claude and Paint with keyboard selection or a port-1 1351 mouse. Escape opens the diagnostic workspace; B returns to the
desktop on this disk. Unsupported graphics leave usable text controls.
The same build also creates `target/native-desktop/uos128.d81` for a 1581,
with 2,630 free blocks for documents and future apps. ABI 1.12 remembers the
system volume's format across app launches and data-disk browsing. Use the
matching D64 or D81 image; see [native boot media](docs/NATIVE-BOOT-MEDIA.md).
Boot still uses IEC. Shared window/widget input, the remaining VDC app views,
persistent desktop state and the broader OS roadmap remain open. Physical desktop
qualification of ABI 1.9 passed in the [physical record](docs/validation/2026-09-12-native-desktop-abi19-hardware/README.md).
ABI 1.11 adds a shared Ultimate command service and graphical drive controls.
The current suite, including Claude serial and the new drive operations,
still requires native physical qualification.

The blue native desktop is the interface being developed for the unified app
suite. The older green desktop remains a separate legacy build; restoring that
installed build after a test does not change the native desktop's direction.
The green native memory workspace is also retained for diagnostics: Escape
from the blue launcher opens it, and B returns to the suite desktop.
[Calculator](docs/NATIVE-CALCULATOR.md), [Paint](docs/NATIVE-PAINT.md),
[Files](docs/NATIVE-FILES-GUI.md), [Editor](docs/NATIVE-EDITOR-GUI.md) and
[Ultimate](docs/NATIVE-ULTIMATE-CONTROLS.md) and
[Claude](docs/NATIVE-CLAUDE-GUI.md) use the blue bitmap and yellow
controls inside their apps. Paint adds connected mouse
strokes, a visible keyboard brush, colors, undo, and verified picture files.
Files adds graphical lists, byte viewing, editable paths and verified copy
controls. Editor adds mouse caret placement, graphical Open/Save As and
Find/Replace while keeping banked documents and verified saves. The
[shared picker](docs/NATIVE-PICKER-GUI.md) carries those controls through file
selection. Claude adds Connect, Repaint, Desktop and status paging beside its
full VDC terminal. The VDC launcher shows yellow selected cards with 64 KiB
of video RAM; a 16 KiB VDC uses white graphics on blue and a selection arrow.
Desktop, Calculator, Ultimate and Paint load the [shared VDC component](docs/NATIVE-VDC-SERVICE.md)
from their original source. Its [native REU backing](docs/NATIVE-REU.md) saves
main RAM for their VDC screen backups, with ordinary RAM as the fallback.
Keep `VDSVC.PRG` beside each app when copying it. Other apps and document
storage still need expansion-memory integration.
Calculator shows its keypad, history and save dialog graphically on the VDC.
Ultimate shows its panels, picker and drive confirmation there. Paint shows its
picture viewport, tools, keyboard brush and file dialogs on both displays.
The shared display layer updates changed rows and retains the saved screen
if restoration needs a retry. Editor, Files and Claude VDC views remain text while their
graphical migration continues. A checked compressed kernel boot file keeps the
complete suite on D64 without reducing application RAM. The bounded LZSA2 boot
wrapper makes room for the shared component. [Packed app startup](docs/NATIVE-APP-PACK.md)
now leaves 134 free D64 blocks while preserving application allocations and
the 426-page heap. Native disk builds need a host C compiler (`cc` or `CC`) for
the bundled compressor.

The suite [Files app](docs/NATIVE-BROWSER.md#copying-from-the-suite-files-app)
copies selected files across IEC drives and Ultimate paths. Press **C** in
Files, choose/edit the destination, then Enter. Tab moves between controls;
F7 opens the destination picker and returns to the blue copy dialog.
New files are closed, reopened
and compared byte for byte; Esc cancels. Zero-byte IEC output remains unsupported
and is rejected before creating a destination.

The [Claude app](apps/claude/README.md) is included on both native desktop suite
disks. Press **A** on the desktop and **Return** in the app to open the modem,
then start the supplied Linux bridge using your Claude login and project. F8 returns
to uOS (the native app supplies single-key ROM definitions and restores them on exit); Escape is forwarded to Claude during the session. Building this client
also requires cc65. The [Ultimate panel](docs/NATIVE-ULTIMATE-CONTROLS.md), opened
with **U**, shows hardware identification, drive inventory, network addresses
and the cartridge clock through shared native services. Its Drives page adds
an image picker and confirmed mount/eject, with fresh destination checks and
protection for the boot disk. A firmware acceptance reply is shown as a request
accepted, since it does not verify the mounted image.

The [Claude lifecycle update](docs/validation/2026-09-12-native-claude-lifecycle/README.md)
adds acknowledged F8 shutdown with a bounded fallback and starts the Linux
process only after the C128 handshake. Its software tests and independent
rebuild pass; native physical serial testing remains open.
The [shared suite workflow](docs/validation/2026-09-12-native-suite-workflow/README.md)
checks all five apps and both Claude exit paths together in VICE. Its physical
attempt stopped before app launch after uncommanded input during a capture;
the original deployment was restored and private uploads were removed.

## Storage and loader update (2026-09-08)

The file manager now scrolls beyond its 64-entry cache, shows file metadata,
selects devices 8–11, and streams copies beyond 16 KiB. App loading restores the
system device after browsing another drive and returns to the desktop on error.
See the [test and hardware evidence](docs/validation/2026-09-08-storage/README.md)
for the exact checks, build hashes, screenshots and remaining limitations.

The [Ultimate command service](docs/ULTIMATE-SERVICE.md) now streams reply
packets without overrunning the fixed buffer, supports longer commands, and
reports clipping. A physical C128 test streamed 1,096 directory entries.
The desktop launcher now includes **uos-ultimate**, an eight-row USB/filesystem
browser with keyboard and mouse navigation, long-name scrolling, and directory
paging beyond entry 255. See the [browser guide](docs/ULTIMATE-BROWSER.md).
Navigation now redraws changed fields, with complete VIC/VDC frame comparisons
and physical timing recorded in the
[redraw validation](docs/validation/2026-09-08-browser-redraw/README.md).
Press **D** in the browser for drive selection and confirmed mount/eject.
The system disk is protected, and a bounded reconciliation handles the reference
cartridge's incomplete inventory. The [drive validation](docs/validation/2026-09-08-ultimate-drives/README.md)
records the CPU, display, emulator and physical workflow checks. Further drive
settings, file operations and the rest of the OS remain on the roadmap.

Press **V / View** to inspect a cartridge file as paged hex and ASCII on both
displays; **N / B** page and **Esc** returns to the same browser selection.
The [shared file service](docs/ULTIMATE-FILES.md) supports binary reads,
exclusive creation, verified writes and 32-bit seeks. **C / Copy** opens an
editable destination path with progress and cancellation. A copy is reported
verified only after closing, reopening and comparing both files completely.
Existing destinations are rejected; cancelled or failed new files are retained.
[Legacy Open and Save As](docs/FILE-DIALOGS.md) keep the editor in memory
while browsing folders. Saves are closed, reopened and compared before success.
The [native graphical Editor](docs/NATIVE-EDITOR-GUI.md) now combines banked
documents with IEC/Ultimate selection and the blue desktop controls. The shared
[graphical picker](docs/NATIVE-PICKER-GUI.md) carries those controls through
Editor, Files, Paint and Ultimate. Broader app and desktop features remain on the roadmap.
The [file-service validation](docs/validation/2026-09-08-ultimate-files/README.md)
records exact physical create/copy/readback, viewer restoration and firmware limits.
The [desktop-copy validation](docs/validation/2026-09-08-desktop-copy/README.md)
records the shipped dialog's C128 copy, cancellation, independent readback and
recovery checks, including an earlier timeout and the progress repaint fix.

## What's new in this fork (v0.2, verified on real C128 hardware)

- **Networking** (`uos-net`, 2026-09-06) — a driver for the Ultimate II+ command
  interface: TCP/UDP sockets by host name, socket read/write, the cartridge's address.
  Shell verbs `IP`, `TIME [SYNC]` and `GET host path` (HTTP over the Ultimate's socket).
- **Self-setting clock** — at boot the OS checks the network and sets the CIA time-of-day
  clock from SNTP (`pool.ntp.org`), in the time zone kept in the settings record
  (`+`/`-` in Settings), then pushes date/time into the Ultimate's own RTC. The 80-column
  row 0 and the Computer window say how the clock was set (`ntp`, `no network`, ...).
- **The C128 ESC key works in C64 mode** — it is not on the C64 matrix, so the kernal
  never saw it; `KEYIN` now scans the VIC-IIe extended matrix (ESC + the dedicated cursor
  keys) and treats RUN/STOP as ESC on a C64.
- **Real Applications launcher** — the "Apps submenu" placeholder is gone: the desktop
  scans the system disk directory for `uos-*` apps (system components filtered out),
  lists each as a selectable row, and any row launches through the core loader.
- **Core export `FILLFILE`** (new jump-table entry at `$0829`): pass a pointer to any
  null-terminated filename to fill the loader buffer — apps can load by *name at runtime*
  instead of only inline strings. This is the primitive the file manager needs.
- **`build.sh`** — Linux build (the upstream shipped only a Windows `build.bat`),
  proven byte-identical to the upstream artifacts before any code changes.

## Building

```
./build.sh          # needs 64tass + c1541 (VICE) on PATH
```

Creates `target/ultos.d64` with the full system. Run it on:

- **Real C128/C64 + Ultimate II+** — mount the D64 on drive A, then
  `LOAD"UOS",8,1` + `RUN` (or post `target/uos.prg` to the U2+ REST
  `runners:run_prg` endpoint, which boots straight into C64 mode).
- **VICE x128** — `x128 -autostart target/ultos.d64` (add `-80col` for an
  80-column-booted test; uOS itself currently renders 40-col).

Requirements on real hardware: a 17xx-compatible REU (Ultimate REU emulation is
fine) and a 1351-protocol mouse (Commodore 1351, Tom+/micromys, mouSTer).

## Hardware verification

Everything in this fork marked "verified" was run on the physical reference
machine (C128 + U2+): signed commits, hardware-gated milestones, and probes
kept in [`probes/`](probes/) — e.g. the VDC register-access probe series
(`probes/vdcprobe*`) that backs the coming 80-column dual-display work.

## Upstream

All credit for UltOS itself goes to Scott Hutter. This fork tracks
`upstream` = xlar54/uos-master; our `main` carries the fork's increments and
they are intended to be upstreamable (small, documented, hardware-proven).
License: GPL-3.0, as upstream.
