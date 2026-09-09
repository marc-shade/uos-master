# Native applications and checked loading

The native workspace now loads a separate calculator from its IEC disk.
Press **C** to launch it. The application runs in native C128 mode, uses the
kernel's owned RAM services and returns to the existing workspace allocations.
The graphical desktop and remaining Ultimate/productivity apps still need
migration. This lifecycle supports one foreground application; scheduling and
app switching remain open.

## Calculator

The native calculator accepts unsigned integers 0..65535 and the four basic
operations. **Enter** or **=** evaluates, **Del** removes the last entry digit,
**C** clears the current calculation and **Esc** returns to the workspace.
Operations execute in entry order: `5+6*7=` gives `77`. Multiplication/addition
overflow and subtraction below zero show `OVF`; division by zero shows `DIV/0`.
Clear the calculation to continue after an arithmetic error. Esc and history
navigation remain available while an error is displayed.

The last 32 evaluated results are retained in a 512-byte allocation in RAM
bank 1. Eight are visible at once, newest first; **N/B** moves to older/newer
results. Clear keeps the history. Returning from the application releases both
its code allocation and history; reopening starts a new session. Both complete
40- and 80-column screens present the same controls and values. History export,
larger/signed/fractional/scientific arithmetic and graphical controls remain
application work.

## Build a native app

`python3 build-native.py` assembles and seals `target/native/calc.prg`, then
adds it as `CALC` to the native disk alongside the kernel file `U` and the
reserved native boot sector. The app PRG is 1,648 bytes plus its two-byte load
address; it requests 16 pages (4 KiB) for code/data and separately allocates
two bank-1 pages for its history.

Use [`src/native/calc.asm`](../src/native/calc.asm) as an example. Include
[`api.inc`](../src/native/api.inc), assemble at `$6000` with the manifest below,
and seal the resulting image:

```sh
64tass -a myapp.asm -o myapp-unsealed.prg
python3 native_image.py myapp-unsealed.prg myapp.prg
python3 native_image.py myapp.prg
```

The last command validates without writing. The sealer rejects inconsistent
sizes, unsupported ABI/flags, invalid entry points and non-printable title
bytes. Add the sealed PRG to a disk using its normal PRG file type. The current
workspace's shortcut selects `CALC`; other native callers can use `N_LAUNCH`
with an explicit device and filename. A general app browser remains required.

The PRG starts with little-endian load address `$6000`, followed by this
32-byte manifest. Offsets are relative to `$6000`, excluding the load address.

| Offset | Size | Meaning |
|---|---|---|
| 0 | 4 | Unshifted bytes `NAPP` (`4e 41 50 50`) |
| 4 | 1 | Image format: 1 |
| 5 | 1 | Native kernel ABI major: 1 |
| 6 | 1 | Required ABI minor: 0 |
| 7 | 1 | Flags: 0 |
| 8 | 2 | Image byte count, including the manifest, excluding the PRG address |
| 10 | 1 | Total allocated pages, 1..96 |
| 11 | 1 | Reserved: 0 |
| 12 | 2 | Entry offset from `$6000`; at least 32 and below image length |
| 14 | 2 | CRC16-CCITT, little-endian |
| 16 | 16 | Printable PETSCII/ASCII title with zero padding |

All words are little-endian. The image must contain at least one executable
byte after its manifest, fit its declared allocation and end exactly at the
declared byte count. CRC16 uses polynomial `$1021`, initial `$ffff`, no final
XOR, over the entire declared image with checksum bytes 14/15 treated as zero.
The checksum detects damaged images; it is not an application signature.

## Launch, execution and return

`N_LAUNCH` at `$1c38` takes `N_DEVICE` (8..30), `N_NAMELEN` (1..16) and
`N_APPNAME`. Names must be printable and cannot contain wildcards or DOS path/
command separators. The read-only loader requests `,P,R`, uses native SETBNK
for its filename and streams bytes through CHRIN. It never passes an unchecked
PRG address to KERNAL LOAD.

The kernel checks the manifest before reserving code memory. The fixed slot
is bank 0 `$6000..$bfff`, up to 24 KiB, entirely below native editor/KERNAL ROM.
It reserves the declared range through the heap, initializes all declared pages
to zero, copies only the bounded image, requires EOF at its exact end and
checks the CRC before entering any app instruction. Existing allocations in
the requested range cause allocation failure and remain intact.

The loader requires the normal native MMU/common/zero-page/stack configuration,
enabled interrupts and the keyboard/screen as default input/output. It reserves
logical files 120/121, data secondary address 7 and command channel 15 on the
requested device. Existing logical-file or same-device channel conflicts are
rejected. Unrelated open files are retained. Only loader-owned channels are
closed, and filename/device/bank/message parameters are restored before app
entry. DOS status is checked after opening and when closing the data file.

The app enters with MMU `$0e`, decimal mode clear and owner ID in `N_CURRENT`.
Use that owner for every heap call. ID 32 is reserved for the current app in
this initial implementation; owner 16 belongs to the workspace. The code
allocation is itself owned by the app. APIs and execution are foreground-only,
and nested launches are rejected. Direct KERNAL file use by an application
still requires that app to close its own files: the shared native filesystem
handle service is not yet implemented.

Return with a balanced **RTS**, A holding the application's result, or use
**JMP N_EXIT** (`$1c3e`) to return from any app call depth. N_EXIT restores the
saved caller stack. The kernel then releases every allocation owned by the
app, including code and any banked data. Owner cleanup preflights all records;
if corruption prevents cleanup, the owner and slot remain retained and further
launches are rejected. This is resource discipline, not memory isolation from
arbitrary machine code. Apps must respect the native ABI and private regions.

`N_LAUNCH` returns carry clear/A=0 after successful loading and lifecycle
cleanup. The app's own result is separate in `N_EXITCODE`; the workspace shows
it when the loader itself succeeded. Loader/cleanup failures return carry set
and their error in A and `N_APPERROR`. Decimal and interrupt flags are preserved;
masked-interrupt callers are rejected before I/O. A/X/Y are otherwise scratch.

`N_KEYIN` at `$1c3b` calls native GETIN, returns A=0 when there is no key, and
accounts for consumed keys in `N_KEYS`/`N_LASTKEY`. Applications set `N_READY=1`
only when idle and accepting input, and clear it while processing. These are
foreground observation fields, not an event queue or scheduler.
N_KEYIN clears N_READY before publishing a consumed key, so a new key count
cannot be mistaken for completion using the previous iteration's ready flag.

| Address | Field |
|---|---|
| `$3d20` | N_CURRENT: active owner, or zero |
| `$3d21..$3d22` | N_DEVICE, N_NAMELEN |
| `$3d23` | N_APPSTATE: 0 idle, 1 loading, 2 running, 3 cleanup, 4 retained cleanup error |
| `$3d24` | N_EXITCODE: last app return value |
| `$3d25` | N_DOSCODE: first nonzero DOS error when available |
| `$3d26` | N_IOSTATUS: last observed serial status; may reflect subsequent cleanup |
| `$3d27` | N_APPERROR: stable loader/cleanup result |
| `$3d40..$3d4f` | N_APPNAME |
| `$3d60..$3d7f` | N_APPHEADER: last manifest read; valid for a running app |

Existing heap errors retain their values. Loader errors are hexadecimal:
`10` bad image/ABI/address, `11` IEC/DOS failure, `12` premature EOF,
`13` declared end without EOF, `14` checksum mismatch and `15` channel/default
I/O conflict. N_APPERROR stays separate from the heap's N_ERROR so subsequent
statistics or cleanup do not erase the loader result.

## Verification and remaining scope

```sh
python3 tests/ci_native_apps.py --report /tmp/native-apps.json
python3 tests/ci_native_calc.py --report /tmp/native-calc.json
python3 -u tests/run_ci.py native
python3 -u hw_ultimate_check.py --native
```

CPU tests need Py65. They cover the 24 KiB bound, malformed/short/long/damaged
images, channel conflicts and I/O faults, BSS initialization, owner cleanup,
stack-restoring exit, calculator arithmetic/history and complete text screens.
The emulator loads the real app through the native disk/KERNAL path. Hardware
testing retains live workspace allocations while running the calculator,
reads its bank-1 history independently, rejects a damaged app, checks a valid
app's return error and reloads the good calculator before restoring the legacy
desktop. See the [checkpoint evidence](validation/2026-09-09-native-apps/README.md).

Dynamic app discovery, multiple executable banks, cooperative scheduling,
shared filesystem handles, display/input widgets, persistent histories and
banked document editing remain work. These services are the next foundation
for migrating the existing desktop and Ultimate applications.
