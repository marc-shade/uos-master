# GEM desktop (GEMDESK) — v1 specification

Step 7 of the [GEM layer design](GEM-LAYER-DESIGN.md): a TOS-style desktop
built on the [AES](NATIVE-AES.md). It is a new native app beside the current
card launcher (`src/native/desktop.asm`). That launcher stays the default boot
target until GEMDESK's workflows replace its test oracles. This page fixes
v1's scope and acceptance. The status section below records what is built.

## Status (2026-09-26)

The build adds `target/native-desktop/gem.d81`, a D81 with GEMDESK as
`browse`, the card launcher as `cards`, and `aesvc.prg`.
`tests/ci_native_gemdesk.py` (Py65) passes 32 cases against
`tests/native_gemdesk_scene.py` ([first build](validation/2026-09-26-gemdesk/README.md),
[files and views](validation/2026-09-26-gemdesk-files/README.md),
[persistence and format](validation/2026-09-26-gemdesk-persistence/README.md)).

Built and tested:
- startup with the AES loaded from the boot folder;
- icon selection, and the 8 and 9 keys, which open that drive's window;
- drive windows for the boot drive and drive 9, four at once (a fifth is
  refused), staggered, topped by a click;
- scrolling by arrow, track (a page) and thumb; row selection by click and by
  cursor keys;
- View sorting: name (the default), type, size (largest first) and unsorted,
  with the current item checked;
- Show Info for an entry, as a [dialog](NATIVE-FORMS.md) with the name
  editable (OK renames the file with `R0:NEW=OLD`; the drive's refusal, such
  as 63 FILE EXISTS, is shown), type, blocks and read-only. For a drive icon,
  it shows files and blocks used in an alert.
- Options:Preferences, a dialog: Confirm deletes (a checkbox; off, Delete and
  Trash skip the question), the sort order (radio buttons, the same as View),
  and the desktop colour (blue, grey, black; the AES repaints the desktop).
- Persistence. Before GEMDESK launches a program or hands over to the card
  launcher, it writes a 64-byte desktop record to the AES session:
  preferences, colour, and each window's drive, rectangle, scroll and
  selection. When GEMDESK starts again with the AES resident, it reopens
  those windows, the top one last. With a fresh AES it reads the same record
  from DESKTOP.INF on the boot drive, which Options:Save Desktop writes
  (scratch, then an exclusive create). A window whose drive cannot be read
  now is skipped without an alert.
- File:Format: a dialog for drive 8 or 9, name and ID, then a confirmation
  (Cancel is the default). It sends `N0:NAME,ID` and lists the drive's
  windows again.
- Delete (Ctrl-D) and dropping a row on Trash. Both ask first, with Cancel
  as the default. The file is scratched with
  [`dos-command.inc`](NATIVE-DOS-COMMANDS.md), the drive's count of scratched
  files is checked, and every window of that drive is listed again. A locked
  file the drive skips is reported. Names with DOS pattern characters are
  refused, and so is a drive whose command channel the kernel holds.
- File:Close, Desk:About, Options:Launcher, and launching a listed file;
- the drive and full-window error alerts;
- Desk:Control Panel: key repeat (all keys, cursor keys only, none) and
  double-click speed 1–5, applied at once and kept with the desktop
  (record version 2);
- the keyboard mouse from the AES client: ALT or C= with the cursor keys
  moves the pointer, and with Return clicks.

Built but not yet covered by tests: fulled, moved and sized answers.

- USB storage: a USB icon appears when the Ultimate's DOS (target 1) answers
  an identify query. Its window lists DOS context 1 from `/` through a
  directory cursor. Folders (`DIR`) open in the same window; the close box goes
  up a level, as in TOS, and closes the window at the root. A file launches
  through the dispatcher with its full path, re-read from the cursor, so names
  longer than the 16 characters shown still work.
- USB delete (and Trash): after the same confirmation, `DELETE_FILE` with the
  entry's full path, then `FILE_STAT`; only DOS 82 with an empty reply proves
  the removal, otherwise an alert says so. A full folder is refused by the
  drive, and the refusal is shown.
- Documents: an IEC SEQ file, or a USB file ending in `.TXT` or `.SEQ`, opens
  in the Editor through the [document contract](NATIVE-DOCUMENT-LAUNCH.md).
  Closing the Editor returns to GEMDESK, and its windows come back. Other
  files go to the dispatcher, which runs native programs.
- A listing holds up to 195 entries: the snapshot is 16 pages, sorted in a
  bank-0 workspace at `$5000` reserved like Files'. Larger directories show
  their first 195.

Not built yet, or limited:
- USB rename and Show Info say "not available"; Files has them.
- Paint pictures (UPNT) do not open from GEMDESK yet.
- USB windows are not kept in the desktop record or session.
- Drive 9 is always read as a D64.
- Dragging shows no outline, and Show Info cannot change read-only.

Emulator: [the VICE run](validation/2026-09-26-gemdesk-vice/README.md) boots
`gem.d81` on an emulated 1581. It opens drive 8 with the 8 key, launches
Calculator, and returns with the window restored; every surface matches the
CPU oracle. Pointer workflows and the dialogs have run only in the CPU model.
Nothing has run on hardware.

Memory: GEMDESK is a core plus one module window (NAPP bytes 7 and 11). The
dialogs are in two modules, each with its own copy of the forms library:
`GDDLG.PRG` (Show Info, Format) and `GDSET.PRG` (Preferences, Control
Panel). The one a dialog needs is loaded from the desktop's folder, replacing
the other ([NATIVE-MODULES](NATIVE-MODULES.md)). If it is missing, an alert
says so and the desktop goes on. The core ends at `$a569`; the modules end at
`$b29c` and `$b1be` of the `$c000` limit.

## v1 scope

**Desktop.** At start, GEMDESK:
- presents the VIC surface and installs the 1351 pointer;
- attaches to the AES, or loads `AESVC.PRG` from its own folder;
- installs the menu bar;
- draws icons on the desktop: drive 8, drive 9, the Ultimate USB root when
  a command interface answers, and Trash.

Desktop icons are redrawn on `WM_REDRAW` for handle 0.

**Menu.**
- `Desk: About uOS... | - | Control Panel...`
- `File: Open^O | Show Info^I | - | Delete^D | Format... | - | Close^W`
- `View: Name | Type | Size | Unsorted`
- `Options: Preferences... | Save Desktop | Launcher^L`

Choosing Launcher returns to the card launcher (`N_EXIT`).

**Folder windows.** Opening a drive icon opens a window with the drive's
listing. It has the name, close, full, move, size, up/down and
vertical-slider gadgets. Up to four folder windows may be open at once.
- Each window keeps a directory snapshot. IEC uses `N_DIRPAGE`; Ultimate
  scans the directory cursor once and closes it.
- The work area shows one entry per text row: name, type and blocks (IEC)
  or size (Ultimate), drawn clipped to the visible rectangles on
  `WM_REDRAW`.
- Arrows scroll a row, the track a page, and the thumb positions the list.
- The app answers moved, sized, fulled, topped and closed messages with
  `wind_set`.

**Selection and actions.**
- A click selects an entry (inverse row). A double-click, or Open, acts on it:
  - a native app (NAPP manifest) launches through the dispatcher;
  - a folder (Ultimate) opens in place;
  - anything else shows an info alert.
- Show Info shows an alert with the name, type and size (and read-only).
- Delete asks for confirmation in an alert. On IEC it scratches the file
  through [`dos-command.inc`](NATIVE-DOS-COMMANDS.md) and checks the drive's
  count; on Ultimate it will use the same verified path as Files.
- Dragging an entry onto Trash does the same as Delete.
- View sorts the snapshot by name, type or size, or keeps directory order.

**Keyboard.** The menu's shortcuts, plus cursor keys and Return in the top
folder window.

## Acceptance

- CPU tests (Py65, `DisplayBus`, IEC and Ultimate fixtures) compare complete
  surfaces against an oracle that composes the AES window oracle with the
  desktop's icons and listing text. They cover:
  - open, scroll, select, open an app, Show Info;
  - delete with confirmation, and Trash by drag;
  - the error paths: a missing drive, a failed delete, a missing
    `AESVC.PRG`.
- A VICE workflow: boot the D81 suite, start GEMDESK, open drive 8, launch
  Calculator, return to the desktop.
- Planted-bug checks for the listing oracle, as for the AES.

## Not in v1

- Icon view.
- Multiple selection and rubber-band selection.
- Copy and move by drag between windows.
- Install Application, and saved desktop configuration.
- Desk accessories.
- Keyboard pointer emulation.
- Printing.
