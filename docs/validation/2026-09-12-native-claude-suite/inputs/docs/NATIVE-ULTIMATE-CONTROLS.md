# Native Ultimate information panel

Open **Ultimate** with U on the native desktop. The app is included as
`ULTIMATE` on both desktop suite disks and uses ABI 1.10. It shows hardware
and interface identification, effective drive inventory, configured network
addresses, and a refreshable cartridge clock reading on both text displays.

| Key | Page/action |
|---|---|
| I | Hardware and target identification |
| D | Drive types, IEC addresses and power flags |
| N | Network interface IP, mask and gateway |
| T | Cartridge RTC snapshot |
| Left/right | Select target or network interface |
| R | Refresh |
| Escape | Return to desktop |

Partial drive inventories are labeled as partial. Invalid lengths, fields,
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

The implementation occupies 147 previously padded bytes at `$4b00..$4b92`.
It adds no resident allocation and retains the 426-page heap. The information
app occupies 11 pages and releases them on return. Source command definitions
were checked against Ultimate firmware revision
`a01c04e8267a0d916b7203cb34dcf1127f75981d` in `control_target`,
`network_target`, and `dos`; the drive type enum is in `c1541.h`.

`tests/ci_native_query.py` exercises literal command bytes, argument rejection,
packet lengths/statuses, ownership, IRQ/decimal state, timeouts and coexistence
with files/directories. `tests/ci_native_controls.py` compares full consoles and
invalid-response behavior. VICE qualifies absent-device pages and app return.
Native physical queries, configuration changes, mounting controls and broader
device management remain separate work.

The [combined suite evidence](validation/2026-09-12-native-claude-suite/README.md)
retains the exact query/panel binaries and reports, together with the added
Claude app and five-entry desktop.
