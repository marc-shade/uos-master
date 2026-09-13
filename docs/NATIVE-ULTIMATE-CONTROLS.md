# Native Ultimate controls

Open **Ultimate** with U on the native desktop. The app is included as
`ULTIMATE` on both desktop suite disks and uses ABI 1.11. The VIC display uses
the blue suite controls, yellow focus and the shared 1351 mouse. The VDC keeps
the text controls; when the bitmap is unavailable, both text displays work.
The four pages show identification, drive inventory, configured network
addresses and a refreshable cartridge clock reading.

| Key | Page/action |
|---|---|
| I | Hardware and target identification |
| D | Drive types, IEC addresses and power flags |
| N | Network interface IP, mask and gateway |
| T | Cartridge RTC snapshot |
| Tab / Enter | Focus / activate a visible control |
| Left/right | Select target, drive or network interface |
| Up/down on Drives | Select a drive |
| M / E on Drives | Choose an image to mount / request eject |
| R | Refresh |
| Escape | Return to desktop |

The image picker temporarily uses both text displays, then restores the blue
controls. It accepts an absolute Ultimate DOS path from either context. The
confirmation shows the destination IEC address and complete image path, with
**Cancel** initially selected. Tab chooses Confirm; Enter activates the selected
button. Escape cancels. Supported suffixes are D64, D71, D81, G64 and G71,
case insensitive. Names up to 255 bytes are retained and transmitted in full.
The text view normalizes ASCII case and substitutes dots for bytes its font
cannot show; the command retains the original name bytes.

Mount/eject requires a supported, powered drive with a valid, unambiguous IEC
address. The boot IEC address, the IEC app source and every slot observed with
either system address stay protected for this app session. An address duplicated
by an off drive is also ambiguous. Confirmation refreshes the inventory and
requires the displayed count, records and selection to agree exactly before
sending a command. A changed inventory requires a new choice and confirmation.
KERNAL/native open files and a foreign file in either DOS context prevent the
operation. The app never closes a foreign file to make the operation possible.

An accepted request is reported as **Request accepted**. This firmware's mount
and eject handlers do not propagate the subsystem operation result, so a `00`
reply cannot establish that the image mounted or ejected. Refresh checks the
drive inventory; it does not verify the mounted image. A failed or uncertain
operation is never replayed automatically.

Partial drive inventories are labeled as partial. The observed count=4,
length=7 form contains only two records; those A/B records require independent
power replies to agree before either can enable an operation. The remaining
peripheral records stay unknown. Invalid lengths, fields,
clock dates and failed requests replace the previous page's data with an
error. An unused identification target may return `NO TARGET`. Network
addresses describe configuration; they do not prove connectivity.

## Shared query service

`N_UQUERY = $1c6e` uses the same ownership checks, file lock, packet transport,
bounded timeout and owned-abort completion as native Ultimate file operations.
It refuses a foreign UCI transaction or a pending native directory packet.
It does not change files, paths, mounted images, configuration or the clock.

Set `N_FOWNER` to the active app owner, `N_UOP` at `$3d3c` to an operation below,
and `N_UARG` at `$3d3d` when needed. Call from the foreground with IRQs enabled.
On return, `N_FACTUAL` counts the response prefix in the 512-byte `N_BUFFER`.
`N_FERROR`, `N_FDOS`, `N_FSTATUS` and `N_USTATUS` retain the transport/target
result. A nonzero numeric target status is an I/O error. The application
validates the meaning and length of returned bytes before displaying them.

| Operation | Value | Argument | Wire command |
|---|---:|---|---|
| Identify | 0 | Target 1–15 | `target 01` |
| Hardware model | 1 | — | `04 28 00` |
| Effective drive inventory | 2 | — | `04 29 01` |
| Drive A power | 3 | — | `04 34` |
| Drive B power | 4 | — | `04 35` |
| Network interface count | 5 | — | `03 02` |
| Interface MAC | 6 | Index | `03 04 index` |
| Interface IP/mask/gateway | 7 | Index | `03 05 index` |
| RTC | 8 | — | `01 26` |

## Shared command service

`N_UCOMMAND = $1c71` accepts a target/command header in `N_BUFFER[0:2]` and
`N_FCOUNT` following body bytes, for a total of 2–512 bytes. `N_FCOUNT` is
**0–510**, not the total packet length. The service rejects overlong lengths
and 16-bit wrap before sending. It uses the query service's ownership,
IRQ, locking, foreign-transaction, pending-directory, reply and abort contract.
The reply replaces the request buffer. `N_FACTUAL` counts its retained prefix.
No automatic retry is performed.

The command service serializes packets; callers remain responsible for command
semantics and affected resources. The Ultimate app adds the drive policy above
and sends only FILE_INFO probes (`context 07`), mount
(`context 23 IEC full-path`) and eject (`context 24 IEC`). The fixed query API
remains read only and continues rejecting operation numbers 9–255.

The 56-byte command entry occupies existing reserved space after the query
service. Relocating the 25-byte keyboard-input wrapper into presentation padding
keeps the resident heap at 426 pages. The app currently occupies 89 pages and
uses a separate 36-page bitmap, released on return. Its [graphical file
picker](NATIVE-PICKER-GUI.md) shares the display, font and pointer. Source command definitions
were checked against Ultimate firmware revision
`a01c04e8267a0d916b7203cb34dcf1127f75981d` in `control_target`,
`network_target`, and `dos`; the drive type enum is in `c1541.h`.

## Qualification

`tests/ci_native_query.py` exercises literal command bytes, argument rejection,
packet lengths/statuses, ownership, IRQ/decimal state, timeouts and coexistence
with files/directories. `tests/ci_native_command.py` covers the generic packet
contract, including full 512-byte requests and overlong/wrapped lengths.
`tests/ci_native_drives.py` checks drive policy and literal mount/eject packets
against independent device state. `tests/ci_native_controls.py` retains full
console and invalid-response checks. `tests/ci_native_controls_gui.py` exercises
the graphical controls, full bitmap/text comparisons, picker, confirmations,
faults and input/display teardown.

The [frozen software record](validation/2026-09-13-native-ultimate-drives/README.md) retains the CPU,
full mouse/keyboard VICE, serial shutdown and rebuild evidence. No physical
drive operation has been attempted with these images. Native
physical qualification, settings changes, network services and broader device
management remain open. A physical suite run also requires a qualified
observer that reads Claude shutdown state before its allocation is released.

The [combined suite evidence](validation/2026-09-12-native-claude-suite/README.md)
retains the exact query/panel binaries and reports, together with the added
Claude app and five-entry desktop.
