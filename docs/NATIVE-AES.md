# Native AES component

The AES is the shared service behind the [GEM layer](GEM-LAYER-DESIGN.md).
It now provides a persistent bank-1 component that apps load once and later
apps attach to (step 1), GEM-style alert boxes (step 2, AES minor 1) and an
`evnt_multi`-style event wait with an application message queue (step 3,
minor 2) and a GEM menu bar (step 4, minor 3). Windows and desk accessories
are later steps.

## What persists

`AESVC.PRG` is an NBK1 image loaded at bank-1 `$9000` (`AE_BASE`) and owned
by owner 30 (`N_AESOWNER`). App cleanup releases only owner 32, so the image
and its state stay resident after `N_EXIT`. The next app attaches to the same
bytes instead of loading them again. `ae_unload` frees the image and returns
its pages. With alerts, events, menus and the shared graphics library
the component is 38 pages (9,475 bytes) of its 48-page region.

The component's identity block sits at image offset 32: `NAES`, major and
minor version, capability bits. The AES version is independent of the kernel
ABI (`src/native/aes-api.inc`).

## Client

Include `api.inc`, `aes-api.inc` and `aes-client.inc` in the retained app
core. The client is a second, block-scoped instance of the
[banked executor](NATIVE-BANKED.md) configured for owner 30 at `$9000`, so
it coexists with an app's own `$6000` component.

| Entry | Contract |
|---|---|
| `ae_attach` | Adopt the resident AES and register this app. Carry set with `A=N_BADHANDLE`: none is resident. `A=N_BADIMAGE`: the resident image failed validation. |
| `ae_load` | Load `AESVC.PRG` from the owner-32 stream in `N_FHANDLE`, then register. `ae_stream_taken` is nonzero when the loader took the stream (it then closes it); zero means the caller still owns it. A failed load frees any partial image. |
| `ae_call` | `A` = operation, packet in `N_BUFFER`; returns the AES's `A`/carry. |
| `ae_detach` | Forget the attachment before exit; the AES stays resident. |
| `ae_unload` | Free the AES image and its pages. |

Register (`AE_OP_ATTACH`, 0) passes the executor's app cookie (app slot and
allocation generation). The reply in `N_BUFFER` is: major, minor,
capabilities, 0, attach count (word), distinct app count (word), a byte that
is 1 when this attach changed the foreground app, and the current cookie.
`AE_OP_STATUS` (1) returns the same reply without registering.

## Alerts

`ae_alert_open` shows a GEM `form_alert` over the app's VIC surface: set
`ae_surface` to the surface handle, pass the string address in A/X and the
default button (0–3) in Y. The string is ASCII:
`[icon][line|line][button|button]`. Icon 0 is none, 1 note (!), 2 question,
3 stop. Up to 5 lines of 30 characters and 1–3 buttons of 1–10 characters are
accepted, and the alert must fit 250 cells (38 columns wide at most).
Anything else is refused with `N_BADARG` before the surface changes.

The alert is centred on the 40×25 cell grid:
- one-cell margin, the icon in a 2×2-cell area plus a gap column;
- the text lines, a blank row, and a two-row button bar;
- buttons are label+2 cells wide, one cell apart and centred;
- blue ink on white paper with a double frame;
- the default button has a second frame line, and the focused button uses
  the suite's yellow focus colour.

Call `ae_alert_step` for each input: A is the key (0 for none), and the
pointer is in `ae_pointer_x` (word), `ae_pointer_y` and `ae_pointer_buttons`
(bit 0). Keys:

| Key | Effect |
|---|---|
| Tab, cursor right | Move focus right, wrapping |
| Cursor left | Move focus left, wrapping |
| Return | Choose the focused button |
| Escape | Choose the last button |
| 1–3 | Choose that button |

A press over a button focuses it. Releasing over the same button chooses it;
releasing elsewhere does nothing.

Both calls reply in `N_BUFFER`: the chosen button (0 while open), the focused
button, and four bytes of dirty cell rows (bit `r&7` of byte `r>>3`) for an
app that mirrors the surface to the VDC.

Opening saves the covered bitmap and colour bytes into an owner-30
allocation. Choosing a button writes them back exactly and frees it; a failed
restore keeps the alert open for another step. One alert may be open at a
time. When a different app attaches, an open alert's buffer is freed without
restoring, because the old surface no longer exists. The input loop stays in
the app because bank-1 code cannot call `N_KEYIN`.

## Events

`ae_event` waits like GEM `evnt_multi`. Fill `ae_ev_params` (16 bytes) and
call it; the result is in `ae_ev_result` (15 bytes).

Parameter bytes:

| Bytes | Meaning |
|---|---|
| 0 | Event mask: keyboard 1, button 2, rectangle 1 4, rectangle 2 8, message 16, timer 32 |
| 1 | Clicks wanted (1–3) |
| 2, 3 | Button mask and wanted state (bit 0 = left) |
| 4–8 | Rectangle 1: flag (0 = fire inside, 1 = fire outside), then x, y, w, h in cells |
| 9–13 | Rectangle 2, same layout |
| 14–15 | Timer, in jiffies |

Result bytes:

| Bytes | Meaning |
|---|---|
| 0 | Mask of the events that fired |
| 1 | Key |
| 2–3 | Pointer x |
| 4 | Pointer y |
| 5 | Buttons |
| 6 | Click count |
| 7–14 | Message |

The first sample is taken at the call, so the timer runs from the call.
A button already in the wanted state fires at once, as in GEM. Presses into
the wanted state are counted until the wanted number arrives or a 20-jiffy
double-click window closes; the count is reported. Rectangle bounds are
half-open cells. Several events can fire together. At most one message is
delivered per wake.

`ae_post` queues an 8-byte message (`appl_write`). The queue holds 16; a
17th is refused with `N_NOMEM`. When a different app attaches, its queue and
wait state are cleared.

Between samples the client calls `N_KEYIN` with `N_READY` published, so the
app stays responsive to the kernel's idle contract. The pointer comes from
the app's `pm_poll` when it sets `AE_POINTER=1` and includes the 1351 module,
otherwise from `ae_pointer_*`. Time comes from the ROM jiffy clock
(`$a0..$a2`). Each sample is one banked call, so waiting is not free: the
cost per sample has not been measured.

## Menus

`ae_menu_install` draws a GEM menu bar on cell row 0 of `ae_surface`. Pass
the address of a NUL-terminated ASCII spec in A/X. The spec lists menus
separated by `;`; each is a title, `:`, then items separated by `|`. For
example:

`Desk:About...;File:New^N|Open...^O|-|Quit^Q`

In an item, a `^` suffix gives a Ctrl-letter shortcut and `-` alone is a
separator line.

Limits (anything else is refused with `N_BADARG`):
- up to 8 menus and 48 items, 12 items per menu;
- 16 characters per item;
- 400 bytes of text in total;
- every drop-down must fit the 38-column / 250-cell overlay limit;
- an empty spec removes the menu.

The bar's pixels stay on the app's surface, so the app must keep row 0 for
it.

`ae_menu_set` sets an item's state: A = menu, X = item, Y = flags
(1 checked, 2 disabled).

Menu input arrives through `ae_event`; the AES sees each sample before the
app's events:

| Input | Effect |
|---|---|
| F1 | Open the first menu |
| Press on a title | Open that menu |
| Hover | Highlight enabled items |
| Release on an item, or Return | Choose it |
| Cursor up/down | Move over enabled items, wrapping |
| Cursor left/right | Switch menus |
| Escape, or a press outside | Close the menu |
| An enabled item's Ctrl shortcut | Choose it without opening anything |

A disabled item's shortcut reaches the app as an ordinary key. While a menu
is open it owns input, as GEM's screen manager does: no other events are
reported. A choice closes the drop-down and queues `MN_SELECTED` (10), with
the menu in byte 3 and the item in byte 4. The app receives it as a
`MU_MESAG` event.

Drop-downs sit under their titles and are moved left when they would pass
column 40. They have a blank cell row above and below the items, so the
one-pixel frame never crosses item text. They use the same exact save-under
as alerts. Checked items show a check glyph; disabled items and separators
are grey. Every sample reports the cell rows it redrew in result bytes
15–18, and the client ORs them into `ae_dirty` for apps that mirror their
surface to the VDC.

## Validation on attach

Attach finds the single owner-30 allocation at bank 1 page `$90` in the
handle table and reads its first 40 bytes through the heap service. It
requires the NBK1 header rules the loader enforces (format, ABI, flags, bank,
page count, entry range, exit stub, zero reserved bytes), the `NAES` identity
and major version, matching page tags, and a nonzero callback import. The
loader writes that import only after the body, CRC and source close have all
succeeded, so a zero import marks an interrupted load. The image cannot be
CRC-checked on attach because the import is live state; a stray write that
keeps the header intact is not detected. Attach then points the import at
the attaching app's executor.

## Example and test

`examples/native-aes` builds `AESDEMO.PRG` and `AESVC.PRG`. The demo attaches
or loads, shows the counters on both screens, and offers status (Return),
exit leaving the AES resident (Esc) and unload (U).

```sh
~/.venvs/uos-tests/bin/python -B tests/ci_native_aes.py --report /tmp/aes.json
```

The demo's A key shows `[3][Delete NOTES.TXT?|This cannot be undone.]
[Delete|Cancel]` over a fresh surface. The test renders every expected alert
frame independently (`tests/native_aes_scene.py`) and compares complete
surfaces. It covers focus movement with row masks, every choosing key,
pointer press/release, exact restoration of arbitrary pixels and colours,
and refusal of malformed or oversized strings. Planted bugs in the paper
colour, button spacing and restore path each fail it.

The demo's M key installs
`Desk:About AES...;File:New^N|Open...^O|-|Quit^Q;Options:Grid|Snap` with
Open... disabled; Options:Grid toggles its check. The menu cases compare
complete surfaces against `tests/native_aes_scene.py` for:
- F1 and cursor navigation that skips disabled rows and wraps;
- Return;
- enabled and disabled shortcuts;
- pointer open, hover, release-select and press-outside;
- the check mark after a set;
- Escape.

Planted bugs that make disabled rows selectable, or move the separator one
pixel, each fail the test.

The demo's E key waits with the parameters in `ae_ev_params` (default:
keyboard or 60 jiffies) and P posts a message. The event cases cover:
- the key;
- the timer at exactly 60 jiffies across a 16-bit carry, not at 59;
- single clicks and the already-in-state rule;
- a double-click inside the window, and a single click when it closes;
- rectangle enter/leave at the half-open bound;
- ordered messages and the 17th refused;
- the queue cleared for a new app.

Planted bugs in the click window, the rectangle bound and the timer
comparison each fail the test.

The test runs several apps in one machine and checks:
- the first app loads the component, which survives its exit;
- a second app attaches without loading and sees the persisted counters;
- unload returns every page;
- a wrong identity and a zero callback import are refused with `N_BADIMAGE`;
- an occupied `$9000` range is refused cleanly;
- corrupt and missing `AESVC.PRG` files leave nothing resident.

Not yet verified: the AES alongside VDSVC in one app, and physical hardware.

The [qualification record](validation/2026-09-25-native-aes-persistent/README.md)
keeps the reports and the byte-identity evidence.
