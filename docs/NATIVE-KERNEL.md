# Native C128 kernel and banked memory

The separate `target/native/uos128.d64` boots through the C128 KERNAL into
BASIC 7 and enters the native kernel. It never enters C64 mode. This first
native image provides a memory workspace, application-facing allocator and a
[disk-loaded native calculator](NATIVE-APPS.md) with verified history export
through [owned IEC files](NATIVE-FILES.md), plus a
[file/app browser and byte viewer](NATIVE-BROWSER.md). The graphical desktop,
Ultimate services and remaining application suite still require migration.
The existing `target/ultos.d64` remains the graphical desktop build.

## Build and use

```sh
python3 build-native.py
x128 -default -8 target/native/uos128.d64 -drive8true -drive8type 1541
```

The build requires Python 3, 64tass and VICE's c1541. It creates the native
kernel, boot-sector and two app PRGs, D64 and image hash manifest in `target/native/`.
`layout.json` records resident, metadata and boot-staging bounds; `uos128.sym`
exports the assembled runtime addresses. The kernel PRG remains loaded at `$1c01`.
Track 1/sector 0 is reserved in the BAM before adding file `U`; ordinary file
allocation therefore cannot consume the boot block. The boot sector feeds
`RUN"U"` to native BASIC, which enters the kernel through its SYS stub.

On a C128, mount this disk on drive 8 and reset into native mode, or use the
native BASIC `BOOT` command. The Ultimate `runners:run_prg` endpoint used by
the legacy deployment script enters C64 mode; native deployment uses disk
mount and machine reset. This workspace needs neither a mouse nor an REU.

Both screens show the same workspace. Press **1/2** to choose RAM bank 0/1,
**A** to allocate 8 KiB in that bank, **W** to initialize the complete block
with a bank-specific pattern, **V** to compare every byte and **F** to release
it. Both allocations may remain live together. Free-page and handle counts
are hexadecimal. A result of `00` means success, `04` means no valid selected
handle and `0A` means the workspace found different data. The remaining error
codes are listed below. To return to the graphical desktop, mount
`target/ultos.d64` and use its existing C64-mode boot path.
Press **C** to launch the native calculator and **Esc** there to return while
retaining the workspace's allocations. Its app lifecycle and additional ABI
entries are documented in the [native app guide](NATIVE-APPS.md).
Press **B** for Files and Apps. It discovers native applications on the selected
IEC disk and returns to the browser after each application exits. **Esc** in
the file list returns to the workspace with its allocations preserved.

## Memory and execution contract

This ABI runs bank-0 code with MMU configuration `$0e`: RAM below `$c000`,
system editor/KERNAL ROM above it and I/O visible. The standard bottom 1 KiB
common area, bank-0 zero page and bank-0 stack remain in place. Initialization
preserves the native SYS stack frame. The kernel takes over application RAM;
returning to the suspended BASIC program is not supported.

| Region | Purpose |
|---|---|
| Bank 0 `$0000..$12ff` | Native system workspace, vectors, screen and boot area |
| Bank 0 `$1300..$1bff` | Resident low kernel and growth space; never application scratch |
| Bank 0 `$1c01..$37ff` | Native kernel, workspace and reserved growth space |
| Bank 0 `$3800..$39ff` | Two page-ownership tables |
| Bank 0 `$3a00..$3bff` | Shared 512-byte transfer buffer |
| Bank 0 `$3c00..$3cff` | 32 eight-byte allocation records |
| Bank 0 `$3d00..$3fff` | API mailbox and reserved system space |
| Bank 0 `$4000..$feff` | 191 managed pages, 48,896 bytes |
| Bank 1 `$0000..$03ff` | Common-area alias; excluded from allocation |
| Bank 1 `$0400..$feff` | 251 managed pages, 64,256 bytes |
| Both banks `$ff00..$ffff` | MMU register window and native interrupt stubs/vectors; excluded |

The two pools provide **442 pages / 113,152 bytes (110.5 KiB)** from stock
128 KiB RAM. Allocation is contiguous within one bank. Automatic placement
tries bank 1 first, preserving bank-0 executable space. Fixed graphics or DMA
regions must be reserved before general allocations can use them. There is no
REU allocation, size probe, RAM disk or expansion-memory support in this ABI yet.
Main kernel code/data ends at `$32d7` exclusive, leaving 1,321 bytes before
the page tables. The allocator occupies `$1300..$17c5`, leaving 1,082 bytes in
the low region for further resident code/data. Public API entries and the app
load address remain unchanged; boot, calculator and browser binaries match the
preceding browser checkpoint.

The 9,985-byte kernel PRG includes a five-page copy of the low section at
`$3e00..$42ff`. Startup copies those 1,280 bytes to `$1300..$17ff` before heap
initialization. The copy includes 58 padding bytes after the allocator. The
source is boot-only staging: `$3e00..$3fff` subsequently remains reserved scratch,
and `$4000..$42ff` becomes ordinary managed memory. No live code executes there.
The workspace's first bank-0 allocation reuses those three staging pages.
Cold entry requires a freshly loaded kernel image. Reentering SYS after that
staging memory has been reused is unsupported; reset and boot reload the image.

Native test observers borrow the existing `$3a00..$3bff` transfer buffer for
at most 512 bytes per IRQ, assembling larger captures on the host and restoring
the buffer afterward. They never write into the resident low region. Foreground
calls and user input must remain idle while that shared buffer is borrowed.

Transfers call the native KERNAL `INDFET`/`INDSTA` gateways at `$ff74/$ff77`.
Their common-RAM routines switch to full RAM `$3f/$7f` for one byte, then
restore the previous configuration. The wrapper preserves `$fb/$fc` and the
gateway's patched pointer operand. IRQs are masked only around each borrowed
pointer/bank operation and can run between bytes. Native IRQ/NMI entry has an
additional saved MMU byte; its ROM/RAM restore stub must remain intact.

The implementation stays at **1 MHz** with both displays enabled. Safe 2 MHz
regions, burst IEC, DMA arbitration and executable bank switching are still
required. Calls from interrupt handlers are forbidden. The allocator lock
detects reentry; it is not a scheduler. Standard native KERNAL interrupts remain
active, and the workspace uses native GETIN, CHROUT and screen switching.

## ABI 1

Include [`src/native/api.inc`](../src/native/api.inc). Call from foreground
bank-0 code with the mapping above. Carry clear and A=0 indicate success;
carry set and A=error indicate failure. Decimal and interrupt flags are
preserved. A/X/Y and arithmetic flags are otherwise scratch. The shared
mailbox/buffer must remain exclusive to the foreground caller until return.

| Entry | Address | Inputs and result |
|---|---|---|
| `N_ALLOC` | `$1c20` | OWNER, PAGES, BANK (0/1/`$ff` automatic); returns HANDLE, actual BANK/PAGE |
| `N_FREE` | `$1c23` | OWNER and HANDLE; releases one allocation |
| `N_READ` | `$1c26` | OWNER, HANDLE, OFFSET, COUNT; copies into N_BUFFER |
| `N_WRITE` | `$1c29` | Same; copies from N_BUFFER |
| `N_FILL` | `$1c2c` | Same, plus VALUE; initializes the requested range |
| `N_STATS` | `$1c2f` | Returns FREE0, FREE1 and reusable SLOTS |
| `N_RELEASE` | `$1c32` | OWNER; validates all its records before releasing any |
| `N_RESERVE` | `$1c35` | OWNER, PAGES, explicit BANK/PAGE; reserves an exact range |

OWNER is 1..254. PAGES is 1..255, subject to contiguous availability. A handle
is four bytes: slot+1 followed by a little-endian 24-bit generation. Each reuse
advances the generation. A slot is retired after generation `$ffffff` instead
of reissuing an old handle. An owner must match even when the generation is
valid. Allocation retains existing RAM contents; initialize them before use.

OFFSET and COUNT are unsigned little-endian 16-bit values. COUNT must be
1..512; offset plus count must fit completely within the allocation without
overflow. Validation precedes data changes. Each transfer/free also checks the
descriptor's bank, range and page tags. Failed validation leaves the allocation
and data unchanged. Owner-wide release preflights every matching record so a
corrupt later record cannot leave an earlier one already freed.

| Mailbox | Field |
|---|---|
| `$3d00..$3d03` | OWNER, PAGES, BANK, PAGE |
| `$3d04..$3d07` | HANDLE |
| `$3d08..$3d0b` | OFFSET word, COUNT word |
| `$3d0c..$3d0d` | VALUE, ERROR |
| `$3d0e..$3d10` | FREE0, FREE1, SLOTS |
| `$3d11` | BUSY; private lock, read-only to callers |
| `$3d12..$3d16` | Workspace READY, KEYS word, LASTKEY, last command RESULT |
| `$3a00..$3bff` | N_BUFFER |

ERROR reflects the latest completed API operation. A reentrant attempt returns
7 in A/carry without replacing the active ERROR or lock. The workspace keeps
its command RESULT separately because its subsequent statistics call also
updates ERROR. Apps must not modify the allocation tables or MMU registers.
FREE0, FREE1 and SLOTS are snapshots from `N_STATS`; allocation and release
do not automatically refresh them.
Owner checks provide API discipline, not hardware memory isolation against
arbitrary machine code.

| Error | Meaning |
|---|---|
| 0 | Success |
| 1 | Invalid owner, page count or bank argument |
| 2 | No contiguous free range, or requested reservation overlaps |
| 3 | No reusable handle slot |
| 4 | Invalid, freed or stale handle |
| 5 | Owner does not match |
| 6 | Invalid reservation/transfer range or count |
| 7 | Reentrant call |
| 8 | Unsupported execution/MMU/common/zero-page/stack mapping |
| 9 | Corrupt allocation record or page ownership |

## Validation and references

```sh
python3 tests/ci_native_heap.py --report /tmp/native-heap.json
python3 tests/ci_native_capture.py --report /tmp/native-capture.json
python3 tests/ci_native_relocation.py --report /tmp/native-relocation.json
python3 -u tests/run_ci.py native
python3 -u hw_ultimate_check.py --native
```

The three CPU tests need Py65 from the test requirements. The heap model executes
assembled instructions and the installed C128 ROM's actual bank gateways; it
models only the memory configurations used here. x128 separately cold-boots the
real disk and compares independent RAM-bank contents and complete screens.
The hardware workflow requires the deployed legacy desktop to be idle first,
boots the native disk, uses a native IRQ observer for RAM1/VDC readback, then
restores the legacy desktop. It does not write cartridge files or change drive B.
Probe RAM and IRQ state are restored and checked after each observation.

The [checkpoint record](validation/2026-09-09-native-kernel/README.md) records
exact images, test limits and physical results. Per-model C128D/DCR/ROM coverage,
long-running load/input/NMI soak, REU/DMA coexistence and speed transitions remain
separate acceptance gates.
The [resident-growth checkpoint](validation/2026-09-09-native-relocation/README.md)
records the current layout, startup copy, staging reuse and revised observer.

Hardware contracts follow the Commodore *C128 Programmer's Reference Guide*,
printed pp. 453–455 (banked KERNAL access), 467–470 (common RAM/page relocation)
and the MMU memory map; see the [Commodore manual scan](https://www.pagetable.com/docs/Commodore%20128%20Programmer%27s%20Reference%20Guide.pdf).
Jim Butterfield's original [COMPUTE! part 4](https://www.atarimagazines.com/compute/issue78/035_1_Commodore_128_Machine_Language.php)
and [part 5](https://www.atarimagazines.com/compute/issue79/Commodore_128_Machine_Language.php)
explain the native per-byte gateways and their cost. The CPU evidence records
the installed ROM filename and SHA-256; emulator and hardware observations
check the actual native state independently.
