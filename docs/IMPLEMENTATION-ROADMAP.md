# uOS completion roadmap and gap analysis

Updated 2026-09-10. This is the current completion checklist. The older
[visual roadmap](roadmap.html) and [PRD](prd.html) retain the original
milestones and requirements; their dated implementation claims are historical.

The goal remains a complete C128 desktop OS with GEOS/Wheels-class applications,
modern desktop workflows, and integrated control of the Ultimate II+ and
Commodore expansion hardware. The existing shell, text editors, and calculator
do **not** satisfy that goal by themselves. A compatible IEC interface is not
proof that every attached device works. Emulator coverage is not hardware proof.

## Evidence and comparison baseline

The starting revision for this audit is `f606dd4`. Source and test inspection
found a working C64-mode core, VIC bitmap desktop, VDC text companion, mouse and
some C128 extended keys, fixed-address REU services, Ultimate command-interface
networking/clock, and five applications: settings, file manager, shell, editor,
calculator. There is no native C128 kernel, office suite, printer subsystem,
application scheduler, or desktop Ultimate control application in that revision.

Primary references used for the comparison and implementation direction:

* [Ultimate UCI DOS target](https://1541u-documentation.readthedocs.io/en/master/uci/ultimate_dos_target.html)
  and [control target](https://1541u-documentation.readthedocs.io/en/latest/uci/control_target.html):
  cartridge-side storage/control commands. Use the installed firmware's commands
  and responses; new firmware documentation alone cannot prove availability.
* [Ultimate HTTP target](https://1541u-documentation.readthedocs.io/en/latest/uci/http_target.html):
  firmware 3.15 adds target 6. It needs its own capability probe and driver;
  current uOS target-3 socket support does not implement it.
* [C64 OS user guide](https://c64os.com/c64os/usersguide/): comparison requirements
  include reusable UI controls, clipboard, app switching, customizable desktops,
  and consistent file/device management.
* [Click Here Software's GEOS distribution](https://cbmfiles.com/geos/index.php)
  and [application catalog notice](https://www.cbmfiles.com/): GEOS and Wheels
  belong in the application/format comparison, including the office applications
  geoPublish, geoCalc, and geoFile. The website's old “coming soon” notice is not
  a release or download-availability guarantee.
* The local `../mp3-manual-en.pdf`, GEOS application disks, and MegaPatch image
  are comparison fixtures. Their presence does not establish uOS compatibility.

A feature-by-feature Wheels manual audit and repeatable comparison sessions
remain open. Record manual edition/page and observed behavior for every parity
claim; do not infer the entire Wheels feature set from a summary website.
The [MegaPatch 3 manual audit](MEGAPATCH-3-PARITY.md) now maps all fifteen pages
of the supplied 2019/Jan/27 manual to sixteen behavior groups and concrete uOS
acceptance checks. Runtime comparison sessions remain open. Its task manager
pauses inactive applications, so suspended-app switching and background-service
scheduling have separate acceptance requirements.
The [local reference inventory](REFERENCE-FIXTURES.md) records nineteen images,
their hashes and directory listings, including geoWrite, geoPaint, geoSpell
and the write utilities. These are named candidates for the application and
format comparisons; they have not been qualified as running under uOS.

## Kernel, desktop, and application gaps

“Partial” means implementation exists but the complete row still needs work.
Every row below is required for completion unless its hardware capability is
physically unavailable; unavailable capabilities must remain visible as such.

| Requirement | Current evidence | Remaining implementation | Acceptance evidence |
|---|---|---|---|
| FR-A1 discovery and FR-A2 drivers | Static GETCAP lookup repaired; VDC/UCI probes | Versioned per-class registry, bounded probes, resources/conflicts, optional drivers, boot report, persisted configuration | Cold boot with present/absent/conflicting devices; no hangs or writes to unrelated hardware |
| Native C128 platform, FR-M3 | Native boot/kernel, dual-screen memory workspace, file/app browser and calculator at 1 MHz; banked KERNAL gateways | Desktop/remaining app/Ultimate migration; safe 2 MHz regions, ROM/IRQ/DMA ownership and per-model qualification | Real C128 and C128D/DCR tests; bank isolation, I/O at both speeds, both displays live |
| Memory and FR-M1 | Native 426-page allocator with owner/generation checks, bounded transfers and 4 KiB resident Ultimate services; legacy fixed REU snapshot banks | REU/expansion size detection and allocation, larger app heaps, RAM disks, persistence, no-REU desktop fallback | 128 KiB through 16 MiB configurations; alias/wrap and allocation exhaustion tests; unrelated REU data preserved |
| Process/app lifecycle | Native single foreground app: directory discovery, checked manifest/ABI/size/CRC, owned memory and IEC/Ultimate streams, cleanup before app handoff, browser return; legacy failed LOAD recovery | Cooperative scheduling, suspend/resume, app switcher, cleanup across remaining native handle/control backends | Switch among editor, terminal, file copy, clock; preserve buffers and release resources after errors |
| Desktop and FR-S1 | Menu, modal windows, disk-scanned launcher | Keyboard navigation everywhere; launcher scrolling/categories; shortcuts; draggable/resizable windows; focus/z-order; multiple desktops; context menus | Complete mouse and keyboard workflows; no stale controls; overlapping windows repaint correctly |
| Shared desktop services | Shared cartridge Open/Save As library with directory recovery; qualified native IEC/Ultimate picker; qualified ABI 1.6 focused fields; per-app drawing | Widget/event toolkit; selectors for remaining backends; clipboard/scrap exchange; undo; open-with/file associations; progress/cancel; notifications; help | Copy text/image between apps; cancel file operations safely; select files from every backend |
| FR-D1/D2 display | VIC graphics + VDC text mirror; persisted display selection | Full interactive 80-column desktop; mirror/extended roles; live switching; independent focus; clipping and scroll surfaces | Operate all apps using only either monitor, then both; no invisible required controls |
| FR-D3/D4 enhanced video | VDC module and hardware probes | RAM-size detection; bitmap/hires modes; supported FPGA features through model-specific drivers | 16/64 KiB VDC modes; supported monitor timings; fallback on absent features |
| FR-I1 keyboard | GETIN, ESC and dedicated cursors | Event queue, full keypad, TAB/ALT and modifiers, repeat policy, shortcuts, configurable mappings | Type while dragging and doing IEC/UCI I/O; no lost events or phantom keys |
| FR-I2/I3 pointer | 1351 movement, clamping | Two buttons, drag/drop, jitter filter, acceleration, hot plug; joystick and keyboard pointer drivers | Measured latency/jitter; real 1351 and adapters; simultaneous keyboard/serial traffic |
| FR-F1/FR-S2 storage/file manager | Legacy IEC directory/copy and cartridge backend; native owned IEC/Ultimate streams and checked app loading, verified Ultimate writes and 255-byte launch paths, IEC directory pages, ABI 1.5 owned Ultimate cursors/folder navigation and byte viewer; qualified shared picker | Native registry and media identity; faster IEC enumeration; copy/rename/delete and append/replace; sorting/search; multi-select/batch actions; interrupted-copy recovery; REL/VLIR support; folders/partitions; disk info/format/validate; recoverable trash | Large/malformed/empty directories; all file types; byte-exact copies; disk full/unplug/error/cancel; reliable navigation and status |
| FR-F2 devices | Legacy manual 8–11 selection; native browser 8–30 with explicit D64/D71/D81 geometry; system-app source restored after data-device app launch | Inventory, type/capability handshake, hot presence, explicit copy destination, broader physical qualification | Real and emulated drives; absent device returns to UI; last-used device never changes system-app source accidentally |
| FR-F3/F4 advanced storage | Standard KERNAL IEC | CMD/1581 partitions, SD2IEC/IDE64 adapters, REU native RAM disks; C128 burst/JiffyDOS/fastload negotiation | Per-backend workflows and timing benchmarks; safe fallback without the expansion/ROM |
| FR-S3 preferences | Display/background/quarter-hour timezone persisted | Driver/device/boot preferences, atomic versioned records, recovery defaults, DST/calendar policy, appearance/accessibility | Power-cycle each setting; corrupt/old records and failed writes recover predictably |
| FR-S4 shell | Commands, CAT, memory monitor, UCI navigation, HTTP socket GET | Shared FS integration, history/completion, scripts/pipes/redirection, jobs, useful errors, document/app launch | Scripted end-to-end workflow with removable media and network failures |
| FR-S5 editor/calculator | Native banked text editor with 24-bit positions, transactional Open, verified exclusive Save As and qualified shared picker; 768-byte legacy editor; native integer calculator with 32-result banked history and verified SEQ export | Selection/clipboard/undo/find, shared GUI input and document/session recovery; calculator precision/scientific modes and history import/session persistence; standalone terminal | Save/reload documents beyond main RAM; arithmetic edge cases; interactive network/serial sessions |
| FR-S6 SDK | Legacy application guide plus native ABI, manifest/image validator/sealer and calculator example | Broader versioned APIs, docs generated from exports, clean-checkout third-party workflow and portable test tooling | Build and run a third-party app from a clean checkout; no hardcoded developer-home dependencies |
| FR-S7 appearance | Basic background colors | Backdrops, font/theme/pointer selection, screen saver, desktop arrangements and persistence | Change/restart/restore; memory budgets and low-RAM fallback |

## Application parity backlog

These are separate applications and shared formats, not additional commands in
the existing shell. Original GEOS application execution is a separate
compatibility requirement from providing equivalent uOS applications.

| ID | Deliverable | Existing implementation | Completion gate |
|---|---|---|---|
| APP-WRITE | Word processor with fonts/styles, pagination, embedded pictures, search/replace, spelling, printing | Banked plain-text editor; no page layout | Create, save, reopen, edit, preview and print a multipage illustrated document; exchange supported geoWrite formats |
| APP-PAINT | Bitmap editor, drawing tools, color/patterns, selection, zoom, clipboard, undo | Graphics primitives only | Edit and round-trip a picture on both displays; import/export declared GEOS/Commodore image formats |
| APP-SHEET | Spreadsheet with cell types, formulas, references, recalc, formatting, import/export, printing | Absent | Recalculate/save/reopen a useful workbook; formula cycles/errors and memory limits tested; geoCalc exchange matrix |
| APP-DATA | Database/address book with schema, records, sorting/filtering, forms/reports, import/export | Absent | Maintain and report a record set larger than main RAM; geoFile exchange matrix |
| APP-PUBLISH | Page layout with text/image frames, columns, styles, preview, print/export | Absent | Complete a newsletter and reopen it without layout loss; geoPublish comparison fixtures |
| APP-ORGANIZE | Calendar, appointments, alarms, contacts, notes and clock accessories | Clock plus editor | Persistent appointments; alarms while another app is active; timezone/date rollover tests |
| APP-MEDIA | Image/document/text viewers, font browser, photo/text scrap managers, SID/audio player | Shell's short CAT and a paged cartridge hex/ASCII viewer | File association launch, scrolling/zoom, playlist, inter-app scraps, supported format round trips |
| APP-COMMS | Terminal (PETSCII/ANSI), serial/modem and TCP/Telnet, file transfer; network resource browser | Socket driver and small HTTP GET | Real BBS/LAN session, encoding negotiation, transfer integrity, reconnect and cancel |
| APP-PRINT | Printer setup, spooler, preview, job queue and cancel; text/raster/PostScript/PDF where backend supports it | Absent | Print document/picture/table through declared physical and Ultimate printer backends; disk-full/disconnect recovery |
| APP-ARCHIVE | Archive manager, disk-image tools, backup/restore, format conversion | Absent | Recover a backup after reset; malformed/truncated archive tests; byte-exact image/file verification |
| APP-DEVELOP | Assembler/editor integration, monitor/debugger, build/run tools, API help | Shell PEEK/POKE only | Build and debug a small native app from uOS; preserve desktop/app state on exit |
| APP-COMPAT | GEOS sequential/VLIR/Convert formats, document migration, original GEOS app execution or an explicit managed compatibility environment | No compatibility layer | Named applications and documents tested on real C128; preserving GEOS metadata and files is mandatory |
| APP-SYSTEM | Hardware/resource monitor, disk utility, diagnostics, installer/updater/recovery, online/offline help | Computer dialog and deployment scripts | A user installs, diagnoses, updates and recovers uOS from the desktop without a developer workstation |

## Ultimate II+ integration backlog

Use the resident UCI transport already implemented in `uos-net`; the earlier
“REST over a serial listener” proposal is not a required architecture. The
cartridge's REST service is useful for host-side tests and any operations not
exposed over the installed UCI. Features that reset the CPU need explicit state
save/restore; loading a new REU image must not destroy active OS allocations.

| ID | Desktop feature | Current state | Completion gate |
|---|---|---|---|
| UCI-BASE | Hardware/firmware identification, target/version discovery, command queue, timeout/abort, status/error display | Packet streaming, 16-bit command length, explicit clipping, bounded polling/abort; physical DOS/control identification; app-local drive records with bounded reconciliation of the reference cartridge's short reply | Shared capability registry, missing peripheral records, interrupted operations and per-firmware protocol coverage |
| UCI-FILES | USB/flash/temp browser, full paths, directories, file read/write/copy/move/rename/delete/create | Desktop browser, paged binary viewer and exclusive file-copy dialog with progress/cancel/final reopened comparison; shared legacy two-context API with verified writes, 32-bit seeks, handle cleanup and modal Open/Save As; native ABI 1.6 owned app loading, directory cursors/navigation with retained full names, calculator export, editor access, shared picker and focused fields | Shared graphical controls; safe replace/rename/delete workflows, copy resume/partial cleanup/batch/folder picking, mounted-file protection, text/image/media viewers, faster sorted/indexed directories, longer paths, selector integration in other apps, Unicode display |
| UCI-DRIVES | A/B drive inventory, image mount/eject/create, drive type/power/address/ROM controls, write protection, save changes | Browser drive panel, explicit confirmed IEC destinations, fresh identity checks, power-state display, system-disk protection and mount/eject | Per-model D64/D71/D81/G64/G71 compatibility; mounted-media identity, remaining drive settings, write protection, dirty-media handling, system-volume replacement/recovery and unsaved work |
| UCI-MEMORY | REU size/configuration, RAM-disk management, REU image save/load, snapshots and restore | Static DMA services only | Save/restore a session without corrupting kernel-owned banks; live size changes handle active allocations |
| UCI-NET | Network setup/status, DNS, sockets, transfers, firmware HTTP offload | TCP/UDP, SNTP, IP and simple HTTP socket client | Download/upload files; recover DNS/network/server errors; negotiate newer HTTP target where present |
| UCI-TIME | RTC read/write and offline date/time | CIA/SNTP clock and advancing DOS GET_TIME readback; old frozen-RTC diagnosis came from saved configuration fields | Power-cycle/backup retention and offline fallback; distinct system/cartridge clock status in the desktop panel |
| UCI-AUDIO | SID selection/configuration, audio routing/mixer, playback/record capabilities | Absent | Real output and supported chip/model configuration; unavailable hardware excluded by capability checks |
| UCI-PRINT | Printer selection, job status, output-file retrieval | Absent | Desktop print job produces a verified readable output file or physical page |
| UCI-TAPE | Tape image playback/capture and file management | Absent | Start/stop/capture, verify files, preserve desktop before incompatible launches |
| UCI-CART | Cartridge/ROM selection, freezer, DMA/program launch, reset/reboot | Host deployment only | Explicit launch/return lifecycle, unsaved-work handling, no accidental overwrite of resident modules |
| UCI-CONFIG | Discover/edit/save supported firmware settings, profiles, diagnostics, model-specific video/audio features | Host scripts only | Setting read/write/readback and persistence; distinguish II+, II+L and Ultimate 64-only capabilities |

## Hardware coverage ledger

For each concrete device, keep model, firmware/ROM, address, probe method,
conflicts, supported operations, test artifact, and hardware result. “Uses IEC”
or “has a driver slot” is insufficient to mark a device supported.

| Family | Required coverage | Current evidence / next gate |
|---|---|---|
| Base C128 | 8502, MMU, VIC-IIe, 8563/8568, SID, CIAs, keyboard, IEC, user port, cassette, Z80/CP/M handoff | Legacy desktop plus separate native memory workspace; native desktop, speed transitions and handoffs open |
| Memory/acceleration | 1700/1764/1750 REUs; Ultimate/RAD REU emulation; GeoRAM/NeoRAM; RAMLink/RAMDrive; SuperCPU/SuperRAM and compatible accelerators; VDC RAM upgrades | Fixed REU DMA exists; all allocators and model-specific verification open |
| Storage | 1541/1570/1571/1581; CMD HD/FD/RL partitions; SD2IEC; Pi1541; IDE64; Ultimate drives/SoftIEC; Kung Fu Flash; network IEC devices | Partial KERNAL workflows; no blanket device certification |
| Input | 1351 and supported adapters, joystick, keyboard pointer; supported paddles/light pen/tablet; serial/Amiga mouse adapters with appropriate drivers | 1351 path exists; electrical/protocol-specific drivers and tests needed |
| Communications | Ultimate, RR-Net/64NIC+/CS8900A, WiC64, user-port RS-232, SwiftLink/Turbo232 and compatible modems | Ultimate socket driver only |
| Printing/audio | IEC/user-port/parallel printer adapters and compatible printers; Ultimate printer; SID variants, stereo/multi-SID and supported audio/MIDI expansions | No OS printer/audio service yet |
| Other hosts | C64, C128D/DCR; Ultimate 64 family, supported FPGA/emulated machines, PRD-listed ports | C64 emulator fallback exists; each model requires a separate capability/result entry |

Unknown expansions remain backlog entries when identified. I/O overlap,
incompatible operating modes, and absent physical resources need clear capability
reporting; software cannot make conflicting expansions operate simultaneously.

## Build sequence and exit gates

| Stage | Scope | Exit gate |
|---|---|---|
| R1 — storage and correctness | Scrolling, complete directory parser, true copy/error semantics, module boundaries, reliable regression fixtures | Real disk streams and pixel checks; byte-exact large copies both directions; missing/full devices; physical C128 repeat |
| R2 — Ultimate desktop | UCI discovery/service; Ultimate browser; mount/eject and drive settings; network/RTC panel | Full browse → mount → IEC file workflow without leaving desktop; errors and system-disk recovery verified |
| R3 — platform services | Native C128 kernel, memory ownership/REU allocator, shared FS/driver registry, input/events, scheduler, file associations | Native dual-display workflows and safe concurrent app/service operation across memory configurations |
| R4 — desktop toolkit | Both interactive displays, windows/widgets/file dialogs, clipboard, undo, pointer/keyboard, persisted preferences | Every interaction works with mouse or keyboard on either display; shared services used by apps |
| R5 — productivity suite | Write/Paint/Sheet/Data/Publish/Organize; document/file compatibility and printing | Real document workflows, round trips and print fixtures compared with GEOS/Wheels/MegaPatch |
| R6 — communications/media/tools | Terminal/transfers, media, archive/backup, developer/system tools; remaining UCI controls | Failure recovery, content integrity, peripheral output and session restore tests |
| R7 — expansion certification | Hardware-family drivers, native filesystems/fastload, accelerated paths, legacy compatibility | Per-model hardware ledger with artifacts; graceful fallback/conflict handling |
| R8 — distribution and finish | Clean-checkout build/SDK, installer/updater/recovery, manuals/help, versioned images, performance/accessibility/soak testing | Requirement-by-requirement audit passes; independently installable release with all above gates satisfied |

R1 and R2 can expose useful features before the native kernel lands; all such
features must migrate to the shared services. No stage is complete merely because
its stubs compile or one happy-path test passes.

## Current work and continuation

Implemented for R1 on 2026-09-08:

* A 64-entry sliding cache with 16-bit directory ordinals, ten visible rows,
  linked-line parsing, block/type metadata, and empty/absent-device handling.
* Cross-device PRG/SEQ/USR streaming with correct IEC direction changes and
  close/status handling. The former 16 KiB cap is removed. Existing destinations
  are rejected. Large PRG copies have byte-for-byte emulator evidence; SEQ/USR
  and physical cross-device copies still need dedicated coverage.
* Rectangle clearing that does not depend on an REU zero pattern; corrected
  VDC delay loop; pixel restoration and actual VDC character readback checks.
* System-app drive restoration, a full 16-character loader name buffer, and
  return to the live desktop after a failed app load.

The [validation record](validation/2026-09-08-storage/README.md) distinguishes
the physical cache-boundary run from the final build's loader/display checks
and records exact build hashes. It supersedes the old untracked scrolling
experiment notes. Neither R1 nor the full OS is complete: disk-full/unplug/cancel
recovery, REL/VLIR, copy readback/cleanup, performance and broader device testing
remain open.

The first R2 service layer is also implemented: [packet streaming](ULTIMATE-SERVICE.md)
with bounded buffers, full 512-byte file packets, commands through the 896-byte
FIFO limit, explicit clipping, and cancellation. The shell now uses the correct
directory attribute. [UCI validation](validation/2026-09-08-uci/README.md) covers
the CPU/protocol cases, emulator regressions and physical cartridge streams.
Mouse initialization now follows boot I/O after a startup stall in the optional
settings load; repeated cold-boot/serial/input soak testing remains required.

GETCAP now retains the requested ID, scans complete three-byte entries and
returns both address bytes. The CPU regression makes 1,024 calls across all
256 IDs, checking unknown-ID results, stack balance and register/memory
preservation. [GETCAP validation](validation/2026-09-08-getcap/README.md) also
covers all IDs from live x64/x128 desktops and the physical C128, followed by
storage/display/app regressions. It is a static resident-service lookup; a
returned address does not prove an optional peripheral is present.

The [Ultimate browser](ULTIMATE-BROWSER.md) now provides desktop filesystem
navigation, long-name scrolling, eight-entry pages, keyboard/mouse controls,
cancel/retry and separate DOS context 2. CPU tests cover paging beyond entry
255, 511-byte names and invalid replies. The core exposes its existing tick
and mouse-button services for app-owned input loops.
[Browser validation](validation/2026-09-08-browser/README.md) now covers four
emulator suites and the physical C128: registered app-row launch, 32 Next
actions to ordinal 256, complete names and exact VDC cells, Root/Open/Parent,
settings preservation and exit to a live desktop. It also reproduces and fixes
missing launcher controls, full-coordinate hit testing, cross-page filename
pointers, row alignment and VDC register readiness. Host observations now leave
quiet intervals around IEC loads after a partial-load stall.

The browser now retains its frame and redraws changed fields. Twenty-one
actual-graphics comparisons match a fresh VIC/VDC render, including shorter
names, errors, empty pages and unsupported-symbol fallback. The
[redraw validation](validation/2026-09-08-browser-redraw/README.md) records
instruction counts, physical timings and exact build hashes. Repeated scans
and long-name rendering still need further performance work.

The browser now includes a drive panel with local capability records,
confirmation, mount/eject, and system-drive protection. The installed count=4 /
two-record reply is reconciled only for two distinct emulated drives with matching
independent power queries. The missing peripheral records remain unknown. A fresh
inventory must match the displayed selection before an operation is sent; zero,
duplicate, powered-off and protected destinations are rejected. The
[drive validation](validation/2026-09-08-ultimate-drives/README.md) records its
protocol, display, emulator and physical workflow evidence. On the reference
C128, the panel mounts a private D64 on B while retaining the system disk on A;
File Manager copies a PRG to IEC 9; browser eject succeeds; all 129 copied bytes
match through independent cartridge-file readback. The fixture is removed and
both DOS contexts are restored. This certifies that D64/1541 workflow, not the
other image formats or all drive-management/recovery requirements.

The [shared cartridge file backend](ULTIMATE-FILES.md) now underpins a desktop
hex/ASCII viewer. It preserves full browser names and selection across viewing,
owns both DOS contexts independently, and checks complete binary reads and
write read-back. It supports exclusive creation rather than replacing existing
files. Firmware FAT locking is disabled, so destructive file operations require
mounted-media identity/protection and recovery before they can be exposed.
Physical testing also exposed inaccessible long components and corrupt
sector-sized USB writes. Creation now limits each component to 127 bytes;
512-byte writes use 511+1-byte commands and verify the complete readback.
These workarounds and their remaining firmware limits are documented in the
[file-service validation](validation/2026-09-08-ultimate-files/README.md).
The native kernel, shared IEC backend, scheduler, full file dialogs and
productivity applications remain required.

The desktop now has an on-demand file-copy dialog using that shared API.
It accepts a full destination path, retains complete source names, creates only
a new file, and compares both closed/reopened files before showing success.
Copy and verification have separate 32-bit byte counters and cancellation.
Errors retain an unverified destination and preserve failed-handle ownership;
there is no automatic deletion or write retry. Browser page/row, system IEC
device and both DOS working directories survive the overlay transition.
The dialog has a path editor; directory picking, batch copies, resume and safe
partial-file cleanup remain required. See the
[desktop-copy validation](validation/2026-09-08-desktop-copy/README.md) for its
exact evidence and limits.
On the reference C128, the shipped dialog copied and verified 66,053 bytes,
rejected an existing destination without changing it, and cancelled a separate
copy with an exact 1,024-byte retained prefix. Independent raw reads verified
all three outcomes; that run's private fixtures were removed and the desktop,
settings and both DOS contexts were restored.

The shared cartridge selector and editor Save As are implemented; see
[the ABI and current limits](FILE-DIALOGS.md) and
[checkpoint validation](validation/2026-09-09-file-dialogs/README.md).
On the reference C128, Open retained a 735-byte note across modal loads, Save As
created and reopened/verified 738 bytes, and existing-name rejection, cancellation
and dirty-discard protection passed. Independent raw reads matched both files;
the run's exact fixtures were removed, both DOS directories and settings were
restored, and the desktop was live. CPU fault/display suites and x64/x128
integration also passed. Earlier failed attempts and their recoveries remain
in the evidence, including a host observation during an IEC load. Load/input
soak testing, rendering performance, cursor editing, larger documents and an
IEC selector remain open.

The first [native C128 kernel and memory ABI](NATIVE-KERNEL.md) now boots its
own D64 through BASIC 7 and manages 442 pages (113,152 bytes) across both RAM
banks. It provides generation/owner-checked handles, explicit reservations,
bounded read/write/fill and preflighted owner cleanup. Its two-screen memory
workspace is a first native client. The existing graphical desktop and Ultimate
applications still run under the legacy core and require migration. See the
[native checkpoint](validation/2026-09-09-native-kernel/README.md) for CPU,
emulator and physical results and the remaining qualification gates.

The [native application lifecycle](NATIVE-APPS.md) now validates and loads
manifested PRGs into an owned 24 KiB slot, checks exact EOF/CRC, initializes
declared BSS and releases the app's RAM on balanced return or one-way exit.
Loader IEC channels are checked for conflicts and closed before app entry.
The native calculator uses this path, keeps 32 results in bank 1, reports
overflow/divide-by-zero and returns without discarding workspace allocations.
See the [app checkpoint](validation/2026-09-09-native-apps/README.md) for exact
fault/model, emulator and physical evidence for that earlier checkpoint.

The [native IEC file service](NATIVE-FILES.md) now provides two owned streams,
exclusive creation, bounded binary reads/writes, 32-bit positions and file
cleanup before application memory release. Read-only directory/sector-chain
checks establish exact file sizes, including empty and one-byte files. The
calculator exports its oldest-first history to a new named SEQ file and
reopens it for byte comparison. The [file-service checkpoint](validation/2026-09-09-native-files/README.md)
records exact images, passing coverage, retained failures and qualification
limits. This backend does not yet migrate the legacy cartridge services.

The [native Files and Apps browser](NATIVE-BROWSER.md) now consumes ABI 1.2
directory pages, caches up to 296 entries in bank 1, discovers app headers,
launches selected filenames and returns through owned cleanup. It provides
128-byte binary previews on both displays. The calculator inherits the selected
source device/format for verified export. The
[browser checkpoint](validation/2026-09-09-native-browser/README.md) records
the model, emulator and physical qualification separately. Full D81 enumeration
still rewalks directory pages and needs performance work.

The allocator now runs in the reserved low region, preserving public API
addresses and all 442 managed pages. Startup copies it before heap initialization
and makes the managed staging pages available for reuse. Observers use the shared buffer
in bounded chunks instead of writing over the low kernel. The
[resident-growth checkpoint](validation/2026-09-09-native-relocation/README.md)
records exact images and qualification. Main/low growth space is now 1,321/1,082
bytes; larger services still need explicit memory/lifetime records.

The [native banked text editor](NATIVE-EDITOR.md) now uses two owned document
contexts for transactional Open, preserves imported bytes and newline forms,
edits through 24-bit positions, and verifies exclusive Save As by reopening and
comparing every byte. Its 4 KiB allocations span both banks. The document format
addresses up to 96 KiB, subject to available heap and temporary Open capacity;
it does not yet use REU or disk backing. Selection, clipboard, undo/find and
the word processor's layout/printing features remain required.
The [editor checkpoint](validation/2026-09-09-native-editor/README.md) records
the CPU, emulator and physical results, independent whole-disk readback and
the measured standard-IEC performance limit.

The [native Ultimate backend](NATIVE-ULTIMATE.md) adds owned absolute-path
streams to ABI 1.3, with foreign-context guards, checked 32-bit read extents,
verified writes and editor Save As. It reserves 4 KiB of bank 0; the managed
heap is now 426 pages. Both 8 KiB workspace blocks and the app slot remain
available. At that checkpoint the native browser and loader still used IEC.
The [Ultimate storage checkpoint](validation/2026-09-09-native-ultimate/README.md)
records twelve CPU reports, seven emulator suites and the physical C128 workflow,
including a 66,056-byte verified save through cartridge registers. Its measured
Open/verified Save As times are about 38/79 seconds, including hardware-harness
quiet and polling intervals.

The [native editor redraw checkpoint](validation/2026-09-09-native-redraw/README.md)
adds field-row updates, partial document repaint, two cached read pages and
24-bit visible-line offsets. It preserves complete redraw for structural and
viewport changes. The editor uses a 12 KiB allocation, and the kernel,
boot, calculator and browser PRGs retain their previous bytes. Broader shared
input/dialog services and further UI performance work remain required.

The [USB app checkpoint](validation/2026-09-09-native-usb-apps/README.md)
unifies IEC and Ultimate app loading under owned streams in ABI 1.4. The browser
accepts a full USB app path; calculator history is created beside its USB image
and verified after reopening. Source and boot-device contexts remain separate,
and checked cleanup precedes handoff. The change frees 264 main-kernel bytes
without reducing the 426-page heap. The editor and boot images retain their
preceding bytes. This provides direct USB launching, with directory navigation
and shared file dialogs still open.

ABI 1.5 now implements an owned Ultimate directory cursor through the existing
stream entries. The browser consumes one READ_DIR transaction across forward
pages, retains complete names and canonical paths, supports folders/parents
and restores selection by name after app saves reorder the listing. A second
page buffer preserves the previous page after failed/cancelled navigation.
The 426-page heap and boot/calculator/editor PRG bytes remain unchanged.
The [directory checkpoint](validation/2026-09-10-native-directories/README.md)
passes 17 CPU suites plus two targeted follow-ups, ten emulator workflows and
the full physical C128 workflow: 1,096-entry navigation past ordinal 255,
selection after saves reorder pages, nine independently verified files and
complete workspace/resource/desktop restoration. The audit retains an
interrupted harness attempt and two unexplained direct DMA bytes; CPU captures
remain the RAM authority.

The [shared file-dialog checkpoint](validation/2026-09-10-native-file-dialogs/README.md)
keeps the complete editor document allocated while browsing. All 18 CPU suites
and four targeted follow-ups pass, including 11 picker flows and a 66,056-byte
document with both workspace blocks. All ten native emulator workflows and
the complete physical USB/IEC workflows pass. Independent readback matches
nine USB files and four IEC files; five complete document captures match while
the picker has focus. Two interrupted IEC attempts remain archived alongside
the host connection fix and eight tests enforcing the no-replay boundary.
ABI 1.6 [shared focused fields](NATIVE-FIELDS.md) now provide bounded caret
navigation, insertion, forward deletion and independent clipping on both displays.
The [field checkpoint](validation/2026-09-10-native-fields/README.md) passes
all twenty CPU suites, all ten native emulator workflows and complete physical
USB/IEC qualification. App allocations and the 426-page heap remain unchanged.
The physical runs verify 57 USB and 24 IEC frame pairs, all nine USB files and
all four IEC files. A failed IEC boot exposed partial/empty REST uploads from
cartridge temporary-storage exhaustion. The retained recovery verifies the
deployed loader before starting it, restores the original desktop, and reclaims
only exact archived test images. Upload-size checks and reuse of a verified
recovery loader now protect qualification; 24 host fault checks pass.
The shared controls retain a 66,056-byte document and both workspace blocks
through a full 255-byte field edit and picker cancellation. Continue events,
list/viewport services and a larger module architecture, followed by migration
of the existing desktop/Ultimate apps and broader drive qualification. Integrate other selector
backends and complete drive media identity/recovery. Scheduling, 2 MHz/DMA regions, REU and
other expansion allocators, system-disk recovery and application parity remain
required. R3 is partial; the editor milestone does not complete it or the OS.
The [next native platform steps](NATIVE-PLATFORM-NEXT.md) identify the memory
constraints, observer changes and document/service acceptance gates for that work.

Before calling the complete OS finished, audit every FR in the original PRD,
every row above, all named app/hardware/firmware combinations, documentation,
packaging and performance gates. Missing hardware evidence remains unverified;
it does not become support by changing the wording of the roadmap.
