# Atari TOS feature parity

The uOS completion bar is feature parity with Atari TOS: the GEM Desktop, the
GEM AES and VDI services applications use, desk accessories, and the GEMDOS,
BIOS and XBIOS system services. This document is the acceptance matrix. A row
is **Have** only when a checked build, a repeatable test and a validation
record exist; "the code is there" is not enough.

The matrix targets the native C128 track (`src/native/**`,
`build-native-desktop.py`). Legacy C64-mode features (`src/uos*.asm`) count
only after they are migrated. Status was surveyed from source and docs on
2026-09-25 and changes only with a linked validation record.

Status: **Have**, **Partial** (named piece missing), **Missing**, or
**Mapped** (ST hardware without a C128 equivalent; the row names the analog).

## Architectural constraints that shape the plan

- One foreground app runs in a 96-page (24 KiB) slot at `$6000..$bfff`. The
  desktop is itself an app that is unloaded while another app runs
  ([NATIVE-APPS](NATIVE-APPS.md)). Desk accessories, a Desk menu over other
  apps, and app switching need a resident or banked accessory design.
- The resident kernel has single-digit free bytes per region
  ([NATIVE-KERNEL](NATIVE-KERNEL.md)). New system services go in banked
  components or module windows, not in the resident image.
- The D64 suite has 16 free blocks; the D81 suite is the full-system medium
  (2,512 free blocks). New desktop features target the D81 build.

## A. GEM Desktop

| TOS feature | Status | uOS evidence / missing piece |
|---|---|---|
| Drive icons on the desktop | Missing | Desktop is a 7-card app launcher (`src/native/desktop.asm`) |
| Trash can (drag to delete) | Missing | No native delete exists yet |
| Open drive/folder in a window | Partial | Files is a full-screen list with Ultimate folder navigation; not a window |
| Several directory windows at once | Missing | Needs the window manager (C) |
| Icon view / text view | Partial | Text list only |
| Sort by name, date, size, type | Missing | |
| Drag-and-drop copy and move | Partial | Button copy with verified comparison, progress and cancel (`src/native/files-copy.inc`); no drag, no move |
| Rubber-band and multiple selection | Missing | |
| Show Info (size, date, rename, read-only) | Partial | Name/type/blocks and a byte viewer; no rename, date or attribute |
| New Folder | Partial | Ultimate paths ([NATIVE-FOLDERS](NATIVE-FOLDERS.md)); IEC has no directories |
| Delete file / folder | Partial | Ultimate Ctrl-D with a checked result ([NATIVE-FOLDERS](NATIVE-FOLDERS.md)); IEC scratch, trash and delete confirmation open |
| Rename file | Partial | Ultimate Ctrl-R, also folders, checked with `FILE_STAT`; IEC rename open |
| Format disk | Missing | |
| Disk copy (drive onto drive) | Missing | |
| Install Application (document type → app) | Partial | Fixed `.TXT/.SEQ` → Editor and UPNT → Paint (`src/native/files/open-with.inc`) |
| Install Icon | Missing | |
| Set Preferences (confirm delete/copy/overwrite) | Missing | Overwrite is always refused |
| Save Desktop (DESKTOP.INF) | Missing | Only the selected card survives an app return |
| Show File (view/print) | Partial | Byte viewer and Editor open; no print |
| Print Screen | Missing | No printer service |
| Launch programs, parameter dialog (TTP) | Partial | Checked app loader; no parameter dialog |
| Menu keyboard shortcuts | Have | Desktop letters, Files/Editor/Sheet control keys |
| Desktop pattern and colors | Missing | Fixed theme (legacy Settings had a persisted color) |

## B. GEM AES services

| TOS feature | Status | uOS evidence / missing piece |
|---|---|---|
| File selector (`fsel_input`) | Have | Shared IEC/Ultimate picker ([NATIVE-PICKER-GUI](NATIVE-PICKER-GUI.md)) |
| Clipboard / scrap (`scrp_*`) | Partial | Session text clipboard ([NATIVE-CLIPBOARD](NATIVE-CLIPBOARD.md)); no image scraps |
| Alert boxes (`form_alert`) | Partial | Shared [AES alert](NATIVE-AES.md#alerts) with icons, 1–3 buttons, keyboard/pointer and exact restoration, CPU-qualified; suite apps still use their own confirm scenes |
| Dialogs (`form_do`) | Partial | Shared editable fields ([NATIVE-FIELDS](NATIVE-FIELDS.md)); no radio buttons or checkboxes |
| Object trees / resource files | Missing | Controls are coded per app |
| Menu bar with drop-downs, checks, disabled items | Partial | [AES menu bar](NATIVE-AES.md#menus) with shortcuts, keyboard and pointer, CPU-qualified; no suite app uses it yet |
| Event library (`evnt_multi`: key, button, rectangle, message, timer) | Partial | [AES event wait](NATIVE-AES.md#events) with all five sources, click counting and GEM state rules, CPU-qualified; suite apps still poll directly |
| Application messages (`appl_write/read`) | Partial | AES 16-message queue; one foreground app, so messages come from itself or future accessories |
| Window library (title, close, full, move, size, scroll bars, overlapping, redraw lists) | Partial | [AES windows](NATIVE-AES.md#windows): 7 overlapping windows, every GEM frame element, exact damage, `WM_REDRAW`, visible-rectangle lists, CPU-qualified; clicking/dragging gadgets not yet |
| Graphics library (rubber/drag box, grow/shrink, slider, busy pointer) | Partial | 1351 pointer, hover, click and drag inside apps |
| Shell library (`shel_write`, environment) | Partial | `N_REPLACE` chains to another app; no environment |

## C. Desk accessories

| TOS feature | Status | uOS evidence / missing piece |
|---|---|---|
| Accessories usable while another app runs | Missing | Single foreground app; the persistent [AES component](NATIVE-AES.md) that will host them now survives app changes |
| Control Panel (key repeat, double-click, colors, clock, click/bell) | Partial | Ultimate app sets the clock and drives; no input/sound/color settings |
| VT52 terminal | Missing | Claude client uses its own protocol |
| Install Printer | Missing | |
| RS-232 configuration | Missing | SwiftLink used only inside Claude |
| XControl / CPX modules | Missing | |

## D. GEMDOS services

| TOS feature | Status | uOS evidence / missing piece |
|---|---|---|
| Open/create/read/write/close | Have | `N_FOPEN`..`N_FCLOSE` ([NATIVE-FILES](NATIVE-FILES.md)) |
| Seek, append, replace | Missing | |
| Delete, rename | Partial | Ultimate `DELETE_FILE`/`RENAME_FILE` in Files; no app-level service or IEC path |
| Attributes, date/time stamps | Missing | |
| Directory search (`Fsfirst/Fsnext`, wildcards) | Partial | Directory pages and substring search; no wildcards |
| Folders: create, delete, current path | Partial | Ultimate create and paths; no delete |
| Free space (`Dfree`) | Missing | |
| Program execution and exit codes (`Pexec/Pterm`) | Partial | Checked launch and exit codes; no command tail or nesting |
| Memory (`Malloc/Mfree/Mshrink`) | Have | Owned heap and REU arena; no shrink |
| Date and time | Partial | Ultimate RTC get/set; no system clock service |
| Console I/O | Partial | `N_KEYIN` and KERNAL output; no redirectable console |
| Printer and serial character I/O | Missing | |
| Handle redirection (`Fdup/Fforce`) | Missing | |

## E. BIOS / XBIOS services

| TOS feature | Status | uOS evidence / missing piece |
|---|---|---|
| Keyboard device | Partial | Owned ROM scan; no shift-state or key-table API |
| Mouse | Have | 1351 driver with clamp, filter and reconnect |
| Real-time clock | Have | Ultimate RTC |
| Screen base and resolution | Partial | Owned VIC surface and banked VDC service; no live mode switching |
| Palette / color registers | Missing | |
| Sound (`Dosound`), bell and key click | Missing | No SID service |
| Random numbers | Missing | |
| Timer tick callbacks | Partial | Jiffy clock readable; no callback |
| Exception vectors / crash handling | Partial | Load/cleanup errors reported; no BRK trap |
| Floppy/sector read, write, format, verify | Partial | File-level IEC only |
| Serial configuration (`Rsconf`) | Missing | |
| Printer output and screen dump (`Prtblk`) | Missing | |
| Cookie jar (capability registry) | Partial | `N_UQUERY` for Ultimate facts |
| Supervisor mode (`Super/Supexec`) | Mapped | The 8502 has no privilege levels; kernel entry points are the equivalent |
| Blitter | Mapped | REU DMA (`src/native/reu.inc`) is the transfer engine |
| MIDI ports | Mapped | No built-in MIDI on the C128; a MIDI cartridge driver would be an expansion |

## F. System behavior

| TOS feature | Status | uOS evidence / missing piece |
|---|---|---|
| Text console for text programs (VT52) | Missing | |
| System fonts in several sizes | Partial | 8×8 and 5-pixel fonts; no font service |
| AUTO folder programs at boot | Missing | |
| Accessories loaded at boot | Missing | |
| Desktop configuration loaded at boot | Missing | |
| Crash display with return to desktop ("bombs") | Partial | Loader errors only; mapped to a BRK/NMI trap |
| Warm reset key combination | Missing | |
| Keyboard mouse emulation (Alt+cursor) | Missing | |
| Hard disk partitions | Partial | Ultimate USB/SD paths; no CMD/SD2IEC partitions |
| Resolution switching | Mapped | VIC 320×200 and VDC 640×200 are both driven |

## Delivery order

1. **File operations:** delete, rename, Show Info, free space, wildcards,
   format. These are prerequisites for trash, drag-and-drop and the desktop.
2. **AES toolkit:** shared alert service, radio/checkbox controls, menu bar,
   event service.
3. **Window manager and GEM desktop:** overlapping windows with scroll bars;
   desktop with drive icons, trash and folder windows.
4. **Accessories:** banked accessory slot, Desk menu, Control Panel, VT52.
5. **System:** preferences and saved desktop, AUTO folder, crash trap, sound,
   keyboard mouse, printer and serial services.

Each step lands with a validation record under [validation](validation/) and
updates the status column above. Steps 2–4 follow the
[GEM layer design](GEM-LAYER-DESIGN.md).
