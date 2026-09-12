# Native desktop migration and remaining gaps

The [native graphical desktop](NATIVE-GRAPHICS.md) now has a separate direct-boot
disk, owned VIC presentation, clipped drawing, VDC text controls and keyboard
app handoff. The diagnostic text workspace remains available. This document
retains the migration analysis and qualification history; pointer/window
events, persistent desktop state, native cartridge panels and an app switcher
remain open. The legacy desktop has a separate memory layout and build.

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
The current VIC surface uses 32 pages for bitmap storage and four pages for
its matrix, reserved by the desktop through the kernel heap API. The table
below retains the original concurrent-storage estimate. Sprites, additional
driver code, event records and repaint scratch still need explicit entries.

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

## First placement and interrupt experiment

The [retained native VIC experiment](reference/2026-09-11-native-vic-placement/README.md)
places a bitmap at bank-0 `$c000..$dfff` and its matrix at `$e000..$e3ff`.
A separate 468-byte client reserves these 36 pages through `N_RESERVE` and
initializes them through `N_FILL`. Two full surface comparisons and two
320×200 rendered-pixel checks pass in VICE with 16 KiB VDC RAM. Jiffies advance
during presentation. The client's explicit teardown restores both text
consoles after `N_EXIT` and normal return. An existing workspace allocation
overlapping the proposed surface causes a checked reservation failure.

The native text workspace uses raster interrupts. The installed C128 KERNAL
rewrites display registers according to `$d8`; the experiment temporarily
selects its skip state while retaining IRQ service. The first client also
exposed a separate visibility problem: correct RAM bytes still displayed
character ROM in the lower bitmap. Applying the KERNAL's bitmap processor-port
sequence removes that overlay, and the original client fails the new pixel
oracle. Register reads alone are therefore insufficient evidence for a surface.

This result settles one emulator placement and explicit client-return path.
It does not implement a kernel display lifetime. Production must keep teardown
available before freeing or replacing the app, and prevent a visible surface
from silently becoming another owner's allocation. Failure after later
reservations, replacement/failed launch, graphics during file operations,
VDC graphics and physical observations remain part of the gate below. The
diagnostic workspace's top bank-0 allocation overlaps this candidate surface;
production must account for that lifetime instead of assuming both fit.

## First implementation gate: owned presentation and return

The [isolated display lifetime candidate](validation/2026-09-11-native-display-lifetime/README.md)
now implements checked `N_VSHOW`/`N_VCLOSE` gates and resident teardown before
surface release or app cleanup. It keeps the 426-page heap and unchanged app
images. All 25 CPU suites, ten ordinary emulator workflows and five dedicated
graphics workflows pass. The latter include complete pixel comparisons, a
513-byte IEC read during graphics, explicit exit, normal return, visible-surface
release, and successful/missing app replacements. The source patch and raw
evidence are retained separately from production. Physical qualification
remains open; the
candidate's underlying USB transport is still under investigation.

The separate [clipped drawing and text prototype](validation/2026-09-11-native-graphics-text/README.md)
adds pixel/color rectangles, 8×8 glyphs and bounded ASCII labels through the
owned-heap API. Its 2,022-byte library includes an original 95-character font.
All 607 CPU cases and five emulator lifecycles pass, including complete
surface/pixel comparisons and clipped text at screen edges. Its twelve-page
demo allocation is separate from the 36-page display surface. The prototype
remains outside the production images.
The subsequent [transfer optimization](validation/2026-09-11-native-graphics-fastpaths/README.md)
passes 697 CPU cases and the same five emulator lifecycles with unchanged
pixels. Complete bands and aligned cells reduce the measured example instruction
counts by 7.385–8.893 times. Its library is 2,342 bytes and its demo declares
thirteen app pages. These are modeled instruction reductions.

The [window clipping and layout candidate](validation/2026-09-11-native-graphics-clipping/README.md)
passes 1,243 CPU cases and five complete emulator display lifecycles. Its
2,685-byte library clips pixels, glyphs and labels to a signed window rectangle;
attribute writes stay inside complete cells within that rectangle. A CPU model
using the actual editor, heap, module and file code retains a 66,056-byte edited
document, 36-page display surface and eight-page picker cache with 31 heap pages
free. The renderer fits the editor's existing module window. Picker replacement,
stale module rejection, verified Save As, graphics reload and full cleanup pass.
This concurrent workflow models calls from the retained editor core; it is not
yet an interactive graphical editor. A fragmented surface refusal leaves the
document unchanged. Masked band processing cuts the preceding identical layout
scene from 17,729,767 to 4,738,938 modeled instructions. The final clipping scene
adds operations and takes 5,197,786 instructions. Physical graphics, drawing
time, VDC bitmap presentation and desktop input/focus remain open.

The subsequent [native launcher candidate](validation/2026-09-11-native-desktop-launcher/README.md)
now provides keyboard selection and real Calculator, Editor and Files launches,
with VDC text controls and a direct desktop boot image. The existing dispatcher
releases the eighteen-page launcher and 36-page surface before opening an app,
then reloads the desktop on return. Nine launcher CPU workflows pass on each of
the two private kernels; five additional kernel CPU suites and five VICE
workflows pass. Missing app/desktop files, dirty-document cancellation, Files
return and allocation fallback are covered. Independent capture checks match
26 complete surfaces, 1,664,000 pixels and 29 app/workspace screen pairs. This
provides a working native launcher; physical graphics, pointer/window input,
VDC bitmap presentation, persistent desktop state and Ultimate panels remain
outside that checkpoint. Production integration followed as described below.

The [physical desktop preparation](validation/2026-09-11-native-desktop-hardware/README.md)
retains three versions with 383, 385 and 386 inputs, all reproducing the same
boot disk exactly. Five VICE
preflight workflows qualify the CPU observer during graphics, an explicit
11,971-byte immutable-kernel audit, and the exact proposed hardware native
sequence. The latter returns from Calculator, Editor and Files and releases
all 426 pages and 32 handles. The revised observer also captures CPU mode
registers directly. The first physical attempt failed in the legacy preflight
before native code ran; its cause remains unproven. The original desktop,
settings and drives were restored, and the failed attempt and recovery are
archived. The second attempt verified desktop selection, Calculator and Editor,
then stopped on a strict observer metadata comparison after Editor returned.
Its original deployment was restored and both private uploads were verified
and removed. The differing metadata bytes were not retained, leaving the
cause unclassified. The third run retained all before/after borrower bytes and also failed: seven
restored-buffer bytes differed, and one capture chunk contained 71 unexpected
bytes. Its original deployment was restored and both private uploads were
verified and removed. The cause remains unproven. Physical qualification is
incomplete; a focused capture-transport investigation precedes another full run.

The [production build integration](validation/2026-09-12-native-desktop-integration/README.md)
reorganizes the same graphics sources under `src/native`, builds direct-desktop
and diagnostic disks in distinct output directories, and passes eighteen
desktop CPU workflows, 1,243 drawing cases and six VICE workflows. It reproduces
the sealed images from a clean tree without prototype directories. This
integration supplies the current source and separate desktop build target.
Physical qualification remains separately reported; software passes do not
erase the three retained hardware interruptions.

The [focused capture experiment](validation/2026-09-12-native-capture-transport/README.md)
adds exact RAM-write receipts and bounded pause/resume batches. Its physical
run stopped on a saved-MMU guard despite 856 complete write acknowledgements
and exact borrower restoration. Original deployment and private-file cleanup
were verified. A CPU model executing the actual ROM demonstrates that a nested
IRQ can legitimately save MMU `$00`, which this guard rejects.

The [subsequent context qualification](validation/2026-09-12-native-capture-context/README.md)
retains 48 CPU cases, 60 host controls, the focused VICE sequence, and forced
nested RAM/VDC captures with complete foreground returns. The
[pinned Commodore source comparison](COMMODORE-SOURCE-REFERENCE.md) independently
matches the relevant IRQ/CLI excerpts to the local ROM. A physical run with
the corrected private observer accepted both saved mappings and captured exact
boot VIC/VDC payloads. It stopped on three ABI differences: the fill-value
argument, consumed-key counter and last key. The allocator tables matched.
Original deployment and both temporary-file deletions were verified. The
physical input source and the earlier payload/buffer differences remain
unresolved. Two controlled cursor-down events reproduce the exact three-byte
pattern in VICE; the strict comparison correctly rejects it and is retained.

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
