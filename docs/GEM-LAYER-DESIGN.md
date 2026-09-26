# GEM layer design (AES, window manager, accessories, desktop)

Design of record for the [TOS parity](TOS-PARITY.md) GEM rows: a shared AES
service, a window manager, desk accessories and a GEM-style desktop. Written
2026-09-25 from the current source and docs; nothing here is implemented yet.
Each delivery step below lands with its own validation record.

## Constraints that shape the design

- The resident kernel and the `$3d00..$3dff` mailbox are full
  (`target/native-desktop/layout.json`, [NATIVE-KERNEL](NATIVE-KERNEL.md)).
  New services cannot live in the resident image.
- Module windows are bound to one parent app's CRC and pages
  ([NATIVE-MODULES](NATIVE-MODULES.md)), so they cannot host shared services
  or accessories.
- The banked executor (`src/native/banked.inc`) is single-instance, fixed at
  `BK_BASE=$6000` and owned by the foreground app. Bank-1 code sees only bank-0
  RAM below `$4000` and may not call `N_LAUNCH`, `N_KEYIN` or `N_EXIT`. AES
  inputs therefore arrive as `N_BUFFER` packets, surface access goes through
  heap callbacks, and the event loop stays in bank 0.
- The VDC shows a 640×200 mirror of the 320×200 VIC surface
  (`src/native/graphics/vdc-mirror.inc`), so the window manager targets one
  320×200 surface and reports dirty rows for the mirror.
- The D64 suite has 16 free blocks. The AES and GEM desktop are D81-only.

## Where the AES lives

`AESVC.PRG` is a persistent NBK1 component at bank-1 `$8800..$bfff`
(56 pages) owned by owner 30. It was planned at `$9000` (48 pages); after
alerts, events and menus it filled 38 pages, so the base moved down into the
unused space above VDSVC, which ends at `$86ff`. Like the clipboard's owner 31, owner 30 survives
foreground cleanup. A 10-page owner-30 allocation above `$c000` holds
menu/alert save-under (9 pages) and the session record (1 page). Idle cost is
58 pages, 74 with an accessory open. That cost cannot coexist with the
qualified no-REU large-document workload (423 of 426 pages), so the desktop
offers an AES unload before launching memory-heavy non-AES apps.

Bank-1 map:

| Range | Use |
|---|---|
| `$0400..$4fff` | General heap |
| `$5000..$5fff` | AES RAM-table data segment, owner 30 (planned as the accessory slot; the window manager's cell maps needed it) |
| `$6000..$87ff` | Per-app banked component window (VDSVC uses 39 pages, one spare) |
| `$8800..$bfff` | AESVC, owner 30, persistent |
| `$c000..$feff` | General heap plus the owner-30 save-under/session pages |

Clients find the AES without new mailbox bytes by checking the private handle
tables for owner 30 / bank 1 / page `$88`, then the NBK1 header and
an identity block (`"NAES"`, major, minor, capabilities) at image offset 32.
The executor's base, limit and owner become `.weak` parameters so a second
instance can serve the AES while existing banked clients stay byte-identical.

Apps include `src/native/aes/aes-client.inc` (`ae_` prefix). The calling
convention matches the clipboard and banked clients: foreground only, IRQs
enabled, `A` = operation, packet in `N_BUFFER`, result in `A`/carry. Drawing
results return a 25-bit dirty-row mask that the client merges into the VDC
mirror update. AES versioning is independent of the kernel ABI; an app whose
required AES minor is absent keeps its local UI.

| Op | Purpose |
|---|---|
| 0–1 | Attach (binds surface and app generation) / status |
| 2–3 | Alert open / step |
| 4 | Event step |
| 5–6 | Menu install / set item state |
| 7–13 | Window create, open, close, delete, set, get, update |
| 14–15 | Object form open / step |
| 16 | Message to an application or accessory |
| 17 | Session record read/write |
| 18–19 | Accessory open / dispatch |

When attach sees a new app generation, the AES discards the previous app's
windows, menu and queue and sends `AC_CLOSE` to accessories.

## Desk accessories

*Revised 2026-09-25:* `$5000..$5fff` now holds the AES data segment, so the
accessory slot needs another directly addressable home (for example the
`$4000..$4fff` range, or swapping the accessory image through the REU).
The rest of this section is the original plan.


An accessory is an NBK1 image (`"NACC"`, at most 16 pages) loaded at bank-1
`$5000`. The AES calls it directly inside bank 1 (init, message, timer
entries). The accessory reaches the AES through a jump table at `AE_BASE+40`.
One accessory is resident at a time; up to four `DESK*.ACC` entries from the
boot device are listed in the Desk menu and loaded on demand.

Scheduling is cooperative, as in GEM: accessories run only while the
foreground app is inside the AES event call, and only AES-linked apps show a
Desk menu. Accessories must not keep file streams between dispatches (the AES
releases owner 29 streams after each dispatch), may not use zero page beyond
`$06..$08`, and cannot own the NMI while the foreground app does.

Across an app change, the AES keeps its code and settings, the accessory
registry, the loaded accessory and its data, and the desktop session record.
The app's windows, menu, surface and queued messages are discarded.

The VT52 terminal is built first as a foreground app reusing the Claude
client's SwiftLink pattern. A polled accessory version follows once ACIA RTS
flow control is verified on the Ultimate modem emulation.

## Window manager

Windows are placed on the 40×25 cell grid; row 0 is the menu bar. Cell
geometry keeps VIC color attributes per window consistent, uses the aligned
fast paths in `graphics-core.inc` and keeps region arithmetic in 8 bits.

- **Records:** 8 × 48 bytes: flags; GEM kind bits (name, closer, fuller,
  mover, sizer, arrows, sliders); current, previous and maximum rectangles;
  slider positions and sizes; app tag; title (copied into the record).
- **Z-order:** an 8-entry stack; at most 7 windows plus the desktop (id 0).
- **Cell ownership map:** 1,000 bytes naming the top window in each cell,
  rebuilt bottom-up. Hit testing is one lookup. Damage is every cell whose
  owner changed plus the visible area of a moved or resized window.
- **Redraw iteration:** `WF_FIRSTXYWH`/`NEXTXYWH` walk the map and emit row
  runs merged downward as rectangles. The AES draws frames; the app receives
  `WM_REDRAW` and clips with the existing `gfx_set_clip` per rectangle.
- **Save-under:** only for drop-down menus and alerts, each at most 250 cells.
- **Move/resize:** XOR outline drag, then one redraw.
- **Messages:** GEM numbering in a 16-entry ring of 8-byte records
  (`MN_SELECTED` 10, `WM_REDRAW` 20 … `WM_MOVED` 28, `AC_OPEN` 40,
  `AC_CLOSE` 41).

## GEM desktop

A new D81 build profile (`GEMDESK`) is built beside the current launcher
(`src/native/desktop.asm`), which stays the default until the new desktop's
workflows replace the launcher's oracles.

- **Icons:** IEC drives, the two Ultimate DOS contexts, trash, and optional
  app shortcuts.
- **Folder windows:** cached directory snapshots in bank-1 allocations
  (at most 16 pages per window, 4 windows). IEC reads use `N_DIRPAGE`.
  Ultimate reads scan the directory cursor and close it, as Files does.
  Icon and text views, sorted by name, type or size (date on Ultimate).
- **Actions:** open apps with `N_REPLACE` and documents with
  `N_DOCREQUEST` and the `files/open-with.inc` rules. Trash, Show
  Info/rename and New Folder reuse the verified Ultimate command code from
  `src/native/files/new-folder.inc`, extracted into a shared include. Deletes
  are confirmed with an alert. Moves within one filesystem use RENAME_FILE;
  other moves are a verified copy and a delete. *Revised 2026-09-26:* IEC
  delete uses the app-side [DOS command library](NATIVE-DOS-COMMANDS.md)
  instead of a kernel service (the kernel has no free bytes); it refuses
  while the kernel holds the drive's command channel.
- **Budget:** about 50 core pages plus a 24-page module window for copy,
  info and open, inside the 96-page slot. Frames, menus and alerts live in
  the AES; caches live in the bank-1 heap. Window state is saved in the AES
  session record before handoff and restored by rescanning on return.

## Delivery sequence

Every step keeps the heap, apps, banked, VDC, desktop, pointer, graphics,
clipboard, Files and folder CPU suites and the `native`, `nativedesktop*` and
`nativepointer*` VICE workflows passing.

1. **Persistent executor and AES skeleton:** parameterized executor, ops 0–1.
   Test: the AES survives app exit, a second app attaches, corrupt identity
   and wrong owner are refused, VDSVC coexists, unload returns all pages, and
   existing banked images are byte-identical.
2. **Alerts:** icon, up to 5 lines, 1–3 buttons, keyboard and pointer,
   save-under with exact restoration and dirty-row masks.
3. **Events:** key, button with click count, two rectangles, timer and
   message queue, with idle `N_READY` publication.
4. **Menu bar:** drop-downs, checks, disabled items, shortcuts, keyboard
   menu mode.
5. **Window manager:** randomized comparison with a Python oracle for the
   cell map, redraw rectangles and messages; then a VICE drag workflow.
6. **Objects:** radio buttons, checkboxes, default/cancel buttons, text
   fields bridged to `N_FEDIT`. *Revised 2026-09-26:* built as the app-side
   [forms library](NATIVE-FORMS.md) instead of AES ops 14–15, because the
   AES image is full. It polls input itself, so the menu bar is inactive
   while a form is open.
7. **GEM desktop profile:** drive windows, launch and return with restored
   windows, trash and info on Ultimate.
8. **Accessory slot, Desk menu and Control Panel:** key repeat, double-click,
   mouse speed, colors and clock; settings survive app handoff.
9. **VT52:** foreground app first, then the polled accessory.
10. **Migrations:** Files, Editor and Paint dialogs/menus onto the AES as
    budgets allow; desktop configuration saved to disk.

## Risks

- Redraw speed through the per-byte heap gateway at 1 MHz is unmeasured;
  instruction counts are recorded from step 2.
- The 12 KiB AES code estimate is unproven; a build-time guard enforces it.
- VDSVC has one page of growth before `$8800`; beyond that its fixed load
  fails cleanly while the AES is resident.
- Reading the private handle tables to find the AES is not a formal ABI.
- An attached AES image cannot be CRC-checked because it is self-modifying;
  only the identity/header check detects stray writes.
- To be confirmed: key-repeat control, PAL/NTSC jiffy rate, ACIA RTS flow
  control on the Ultimate, VDSVC pointer handling with AES-dirtied rows.
