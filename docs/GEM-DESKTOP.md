# GEM desktop (GEMDESK) — v1 specification

Step 7 of the [GEM layer design](GEM-LAYER-DESIGN.md): a TOS-style desktop
built on the [AES](NATIVE-AES.md). It is a new native app beside the current
card launcher (`src/native/desktop.asm`). That launcher stays the default boot
target until GEMDESK's workflows replace its test oracles. This page fixes
v1's scope and acceptance. The status section below records what is built.

## Status (2026-09-26)

The build adds `target/native-desktop/gem.d81`, a D81 with GEMDESK as
`browse`, the card launcher as `cards`, and `aesvc.prg`.
`tests/ci_native_gemdesk.py` (Py65) passes 8 cases against
`tests/native_gemdesk_scene.py`:
- startup: the AES loaded from the boot folder, menu bar and icons;
- icon selection;
- a double-click opening the boot drive's listing window (22 entries);
- arrow scrolling, row selection by click and by cursor keys;
- File:Close (Ctrl-W);
- Desk:About (F1, Return) as an exact alert, with the desktop restored;
- Options:Launcher (Ctrl-L) handing over to `cards`;
- a double-click on a listed file handing it to the dispatcher, which checks
  it is a program.

Built but not yet covered by tests:
- drive 9;
- paging, the thumb, fulled/moved/sized answers;
- several windows at once;
- the error alerts.

Not built yet: the rest of v1 — Show Info, Delete, dragging to Trash, View
sorting, and the Ultimate icon with folders. Trash has an icon but no action.
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
- `View: Name | Type`
- `Options: Launcher^L`

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
- Show Info shows an alert with the name, type and size.
- Delete asks for confirmation in an alert, then deletes through the same
  verified Ultimate path as Files. On IEC it explains that IEC delete is not
  available yet.
- Dragging an entry onto Trash does the same as Delete.
- View sorts the snapshot by name or type.

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
- IEC delete and rename (needs a kernel command-channel service).
- Printing.
