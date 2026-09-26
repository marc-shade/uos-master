# GEM desktop (GEMDESK) — v1 specification

Step 7 of the [GEM layer design](GEM-LAYER-DESIGN.md): a TOS-style desktop
built on the [AES](NATIVE-AES.md). It is a new native app beside the current
card launcher (`src/native/desktop.asm`). That launcher stays the default boot
target until GEMDESK's workflows replace its test oracles. This page fixes
v1's scope and acceptance. The status section below records what is built.

## Status (2026-09-26)

The build adds `target/native-desktop/gem.d81`, a D81 with GEMDESK as
`browse`, the card launcher as `cards`, and `aesvc.prg`.
`tests/ci_native_gemdesk.py` (Py65) passes 27 cases against
`tests/native_gemdesk_scene.py` ([first build](validation/2026-09-26-gemdesk/README.md),
[files and views](validation/2026-09-26-gemdesk-files/README.md)).

Built and tested:
- startup with the AES loaded from the boot folder;
- icon selection;
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
  Trash skip the question) and the sort order (radio buttons, the same as
  View). The settings last until GEMDESK is reloaded.
- Delete (Ctrl-D) and dropping a row on Trash. Both ask first, with Cancel
  as the default. The file is scratched with
  [`dos-command.inc`](NATIVE-DOS-COMMANDS.md), the drive's count of scratched
  files is checked, and every window of that drive is listed again. A locked
  file the drive skips is reported. Names with DOS pattern characters are
  refused, and so is a drive whose command channel the kernel holds.
- File:Close, Desk:About, Options:Launcher, and launching a listed file;
- the drive and full-window error alerts.

Built but not yet covered by tests: fulled, moved and sized answers.

Not built yet: the Ultimate icon with folder windows. Other limits:
- dragging shows no outline;
- Show Info cannot change read-only;
- IEC free space is not shown.

Nothing has run in VICE or on hardware.

## v1 scope

**Desktop.** At start, GEMDESK:
- presents the VIC surface and installs the 1351 pointer;
- attaches to the AES, or loads `AESVC.PRG` from its own folder;
- installs the menu bar;
- draws icons on the desktop: drive 8, drive 9, the Ultimate USB root when
  a command interface answers, and Trash.

Desktop icons are redrawn on `WM_REDRAW` for handle 0.

**Menu.**
- `Desk: About uOS...`
- `File: Open^O | Show Info^I | - | Delete^D | - | Close^W`
- `View: Name | Type | Size | Unsorted`
- `Options: Preferences... | Launcher^L`

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
