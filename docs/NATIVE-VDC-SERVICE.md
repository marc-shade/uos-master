# Shared native VDC service

Desktop, Calculator and Ultimate load the same `VDSVC.PRG` from their original app
source. It supplies both the native 640×200 desktop layout and the incremental
VIC-to-VDC presenter used by Calculator and Ultimate, including Ultimate's
file picker. The blue interface, app icons, focus colors and pointer behavior
remain consistent. All three apps can save their original
VDC screen in an available REU, with main RAM as the fallback.

The component is included on both D64/D81 suite and workspace disks. When
copying Desktop, Calculator or Ultimate to another IEC disk or Ultimate directory, copy
`VDSVC.PRG` beside it. A data-device selection or file-dialog path does not
redirect component loading. Ultimate paths retain the original directory,
including spaces and case, in either source context. A missing, damaged or
unavailable component leaves the VIC controls and VDC text fallback usable.

## Memory and lifetime

[`vdc-service.asm`](../src/native/vdc-service.asm) is a 7,592-byte NBK1
component, reserved in 30 bank-1 pages at `$6000..$7dff`. The retained
[`vdc-client.inc`](../src/native/graphics/vdc-client.inc) uses the
[checked banked loader and executor](NATIVE-BANKED.md). It closes the component
stream before executing any provider code. The resident kernel and 426-page
managed heap are unchanged.

| Allocation while graphics are open | Desktop | Calculator | Ultimate |
|---|---:|---:|---:|
| Bank-0 app | 35 pages | 49 pages | 96 pages |
| Bank-1 component | 30 pages | 30 pages | 30 pages |
| VIC surface | 36 pages | 36 pages | 36 pages |
| History | 0 | 2 pages | 0 |
| Free main-RAM pages with REU backing | 325 | 309 | 264 |
| Free main-RAM pages with 16 KiB VDC RAM backing | 261 | 245 | 200 |
| Free main-RAM pages with 64 KiB VDC RAM backing | 253 | 237 | 192 |

Moving the display code saved eight pages in Desktop and Calculator's executable allocations.
The separate component adds 30 pages while loaded; this is code-space headroom
for further app migration, not a reduction in total RAM use on every machine.
Editor documents, its module window and other app views still require separate
backing-store work before they can adopt the component.

Ultimate keeps one component and saved VDC screen while its picker borrows the
same VIC surface. Its picker allocates four scratch pages only while open and
releases them after closing its cursors and cache. No provider reload or VDC
restoration occurs between the panel, picker and confirmation dialog.

Input, application logic and the VIC surface stay in bank 0. Calls clear
`N_READY` before preparing the mailbox or changing banks. The normal app input
loop publishes readiness again. The checked executor temporarily exposes
16 KiB of bottom common RAM; native callbacks restore the kernel's standard
mapping for the duration of the service. The REU probe buffer is in physical
bank 1; DMA transfers through `N_BUFFER` use physical bank 0.

Close restores all owned VDC memory and registers before releasing its snapshot,
REU arena and executable allocation. Display and REU recovery failures retain
the component and block app handoff until restoration succeeds. A clean VDC
setup refusal immediately releases the unused component. An uncertain source
close retains the native file record and executable; repeated exits do not
retry I/O through a poisoned stream or discard its owner.

## Internal call contract

This is the suite's internal component interface under native ABI 1.12. Calls
use `bk_call` with A equal to an operation and return the native A/carry result.
The parent retrieves status after each completed operation. A checked-executor
failure leaves a conservative recovery phase until cleanup can be verified.

| Operation | Meaning |
|---|---|
| 0 | Check empty state; refuses an owned display or active REU recovery |
| 1 | Open and initially present; binds mode and surface once |
| 2 | Present changed mirror rows or the desktop selection/error |
| 3 | Update the clipped pointer |
| 4 | Restore and close, retaining recovery on failure |
| 5 | Copy the 41-byte status record into `N_BUFFER` |

Operations 1–3 consume this packet in bank-0 `N_BUFFER`:

| Offset | Bytes | Value |
|---|---:|---|
| 0 | 1 | Mode: 0 incremental VIC mirror, 1 native Desktop scene |
| 1 | 4 | Owned VIC surface handle; bound by operation 1 |
| 5 | 1 | Desktop selection, 0–5 |
| 6 | 1 | Desktop launch error, zero for no error |
| 7 | 1 | Pointer visibility in bit 0 |
| 8 | 2 | Little-endian shared pointer X, 0–319 |
| 10 | 1 | Pointer Y, 0–199 |
| 11 | 25 | Mirror dirty-row flags; consumed only in mode 0 |

The surface and mode remain bound until close. Mirror presentation clears the
parent's dirty flags only after success, including the initial full upload.
Desktop error glyphs are read from the owned VIC status row, preserving the
native VDC layout without storing a second font in the component.

Status offsets 0–6 are phase/live/color/fault/saved-stack/base-high/pages;
7–10 hold the snapshot handle; 11–24 hold fourteen saved VDC registers;
25–28 hold pointer visibility/X/Y; 29 selects REU backing; 30–37 hold its token;
38–39 report REU active/probe-recovery state; 40 reports pending mirror rows.
These values are observations of the retained component, not authority to
release its storage independently.

## Checks

`ci_native_vdc_service.py` runs the actual provider through the checked loader
and banked executor, comparing complete bitmaps, attributes, status glyphs,
pointer clipping and exact VDC/REU restoration. `ci_native_vdc_client.py` checks
app-source loading, absent/corrupt components, allocation refusal and uncertain
source-close ownership. Existing Desktop, Calculator and REU workflows exercise
the loaded apps and recovery paths.

The VICE pointer workflow reads the component only after checking its live
heap token, page owners and patched NBK1 header. It compares original screen
backups with complete VRAM at the bank-1 restore checkpoint before handoff.
The breakpoint condition checks the MMU configuration so an identical bank-0
program address cannot satisfy the observation. Cold-boot and disk-chain
checks cover all six generated images. These are software checks; this
component has not been deployed to or qualified on physical hardware.
