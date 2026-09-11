# Native desktop migration: concrete blockers and first acceptance gate

This is an implementation plan, not a native graphical-desktop qualification.
The native kernel currently boots the two-screen text workspace. The graphical
desktop and its pointer, drawing and cartridge panels still use the legacy
core. The module loader supplies one part of their migration, but does not
supply display ownership, window events or an app switcher.

## Existing code cannot keep its legacy memory layout

The following addresses come from the current source, rather than an assumed
C64/C128-compatible layout.

| Existing component | Source behavior | Native conflict |
|---|---|---|
| [VIC drawing](../src/uos-gfx.asm) | Code at `$c000`; bitmap at `$a000..$bfff`; matrix clears at `$8400..$87ff` | Matrix and bitmap overlap the native editor/picker; drawing code and the rest of the bitmap overlap managed document RAM |
| VIC pixel writes | Borrow zero page `$0a..$20`, change `$01`, then execute `CLI` | Native services use C128 MMU/bank gateways and preserve caller interrupt state; the old mapping sequence is not a native transfer contract |
| [VDC driver](../src/uos-vdc.asm) | Code at `$cc00`, fixed zero-page scratch, direct register access and runtime ready waits | Its code overlaps managed RAM; its scratch, register ownership and failure handling require native contracts |
| [Native app loader](../src/native/apps.inc) | One foreground owner, checked cleanup, original return stack and browser dispatch | It has no persistent desktop process, suspension record or window/focus registry |
| [Native text UI](../src/native/uos128.asm) | KERNAL console switching and character output; 1 MHz | Text apps and field drawing need an explicit presentation transition before a bitmap desktop can call or replace them |

Moving those PRG origins alone would leave the mapping, scratch and lifecycle
conflicts. Native drawing must operate on owned surfaces through checked bank
transfers or a separately qualified bounded mapping gateway. Neither a legacy
REU snapshot nor a direct DMA sample proves ownership of native RAM.

## Keep display storage in the memory budget

The production desktop need not keep the diagnostic workspace's two 8 KiB
blocks allocated. They remain a useful separate allocator/IRQ regression.
A provisional VIC surface budget is 32 pages for bitmap storage and four
pages for its matrix. These are accounting sizes, not assigned addresses or
a verified VIC mode. Sprites, fonts, driver code, event records and repaint
scratch still need their own explicit entries.

| Proposed concurrent storage | Pages |
|---|---:|
| Existing editor core and module window | 79 |
| Seventeen document chunks for the 66,056-byte workflow | 272 |
| Existing picker cache at its tested peak | 8 |
| Provisional bitmap and matrix | 36 |
| Unassigned remainder of the 426-page heap | 31 |

The remainder is only 7,936 bytes before the other desktop requirements.
Total free bytes also do not prove that an aligned surface or executable
region is available. The next layout audit must check bank placement, largest
contiguous extents, VIC visibility, ROM/I/O banking, boot staging, common RAM
and observer scratch. It must include rollback after a later reservation
fails. App suspension and additional complete windows will need a separate
backing-store/lifetime design; this budget does not implement them.

## First implementation gate: owned presentation and return

Build the initial native display client against the public heap/file/module
services. Keep optional graphics executable code in the app allocation or a
declared module window. Before changing display registers, reserve all required
surface storage and retain the configuration needed to return to both text
consoles. The caller must remain able to report an allocation or driver error.

Define presentation ownership and cleanup before making this the boot desktop.
Normal return, `N_EXIT`, replacement and failed application launch must all
restore a usable display through the same lifecycle. Teardown must remain
available after foreground resources are released; it cannot depend on loading
another module from the device that just failed. Preserve native IRQ service,
the keyboard/function-key state and unrelated heap/file owners. Any additional
resident code needs a fresh interval audit: the current resident holes are
small and the qualified document workload cannot absorb an uncounted reserve.

Qualification for this first gate must include:

* Complete bitmap/matrix byte comparisons for clipped text, fills and edges;
  bank-boundary and refused-allocation cases must leave unrelated bytes intact.
* Actual emulator display/register observations with both native consoles
  restored after exit, failed load and a mode-change failure.
* A physical C128 run with normal IRQ/keyboard service during drawing and
  IEC/UCI operations, followed by independent surface and settings readback.
* The existing large-document/picker workflows on the resulting kernel, plus
  the new desktop allocation pattern. State which display modes and VDC RAM
  configurations have actually been exercised.

After that gate, migrate keyboard focus, pointer events, clipped widgets and
the launcher, then the drive/browser/control panels. Retain complete app names
and original system-app sources across data-device operations. Add desktop
return and package-version checks from [Wheels parity](WHEELS-PARITY.md) and
the explicit app-switching requirements from [MegaPatch parity](MEGAPATCH-3-PARITY.md).
The application suite, printing, clipboard, scheduling and expansion support
remain separate rows in the [completion roadmap](IMPLEMENTATION-ROADMAP.md).
