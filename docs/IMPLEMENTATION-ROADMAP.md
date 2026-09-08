# uOS completion roadmap and gap analysis

Updated 2026-09-08. This is the current completion checklist. The older
[visual roadmap](roadmap.html) and [PRD](prd.html) retain the original
milestones and requirements; their dated implementation claims are historical.

The goal remains a complete C128 desktop OS with GEOS/Wheels-class applications,
modern desktop workflows, and integrated control of the Ultimate II+ and
Commodore expansion hardware. The existing shell, small editor, and calculator
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

## Kernel, desktop, and application gaps

“Partial” means implementation exists but the complete row still needs work.
Every row below is required for completion unless its hardware capability is
physically unavailable; unavailable capabilities must remain visible as such.

| Requirement | Current evidence | Remaining implementation | Acceptance evidence |
|---|---|---|---|
| FR-A1 discovery and FR-A2 drivers | Static GETCAP lookup repaired; VDC/UCI probes | Versioned per-class registry, bounded probes, resources/conflicts, optional drivers, boot report, persisted configuration | Cold boot with present/absent/conflicting devices; no hangs or writes to unrelated hardware |
| Native C128 platform, FR-M3 | Everything boots in C64 mode | Native boot/kernel, 128 KiB bank management, KERNAL/MMU gateways, 2 MHz safe regions, ROM/IRQ/DMA ownership | Real C128 and C128D/DCR tests; bank isolation, I/O at both speeds, both displays live |
| Memory and FR-M1 | Fixed REU banks for bitmap/app/rectangle snapshots | Non-destructive size detection, ownership allocator, bounds checks, app heaps, RAM disks, persistence, no-REU fallback | 128 KiB through 16 MiB configurations; alias/wrap and allocation exhaustion tests; unrelated REU data preserved |
| Process/app lifecycle | One loaded app, resident desktop, fixed tick vector; failed LOAD returns to desktop | Manifest/ABI and load-address validation, cooperative scheduling, suspend/resume, app switcher, cleanup of handles/controls | Switch among editor, terminal, file copy, clock; preserve buffers and release resources after errors |
| Desktop and FR-S1 | Menu, modal windows, disk-scanned launcher | Keyboard navigation everywhere; launcher scrolling/categories; shortcuts; draggable/resizable windows; focus/z-order; multiple desktops; context menus | Complete mouse and keyboard workflows; no stale controls; overlapping windows repaint correctly |
| Shared desktop services | Per-app drawing and ad hoc prompts | Widget/event toolkit; file pickers; clipboard/scrap exchange; undo; open-with/file associations; progress/cancel; notifications; help | Copy text/image between apps; cancel file operations safely; select files from every backend |
| FR-D1/D2 display | VIC graphics + VDC text mirror; persisted display selection | Full interactive 80-column desktop; mirror/extended roles; live switching; independent focus; clipping and scroll surfaces | Operate all apps using only either monitor, then both; no invisible required controls |
| FR-D3/D4 enhanced video | VDC module and hardware probes | RAM-size detection; bitmap/hires modes; supported FPGA features through model-specific drivers | 16/64 KiB VDC modes; supported monitor timings; fallback on absent features |
| FR-I1 keyboard | GETIN, ESC and dedicated cursors | Event queue, full keypad, TAB/ALT and modifiers, repeat policy, shortcuts, configurable mappings | Type while dragging and doing IEC/UCI I/O; no lost events or phantom keys |
| FR-I2/I3 pointer | 1351 movement, clamping | Two buttons, drag/drop, jitter filter, acceleration, hot plug; joystick and keyboard pointer drivers | Measured latency/jitter; real 1351 and adapters; simultaneous keyboard/serial traffic |
| FR-F1/FR-S2 storage/file manager | Linked directory parser, sliding cache, metadata, PRG/SEQ/USR copy implementation; large PRG copies verified in VICE | Reusable file service; append/verify; sorting/search; multi-select/batch actions; interrupted-copy recovery; REL/VLIR support; folders/partitions; disk info/format/validate; recoverable trash | Large/malformed/empty directories; all file types; byte-exact copies; disk full/unplug/error/cancel; reliable navigation and status |
| FR-F2 devices | Manual 8–11 selection; restores system-app device on exit | Inventory, configurable IEC addresses, type/capability handshake, hot presence, explicit copy destination | Real and emulated drives; absent device returns to UI; last-used device never changes system-app source accidentally |
| FR-F3/F4 advanced storage | Standard KERNAL IEC | CMD/1581 partitions, SD2IEC/IDE64 adapters, REU native RAM disks; C128 burst/JiffyDOS/fastload negotiation | Per-backend workflows and timing benchmarks; safe fallback without the expansion/ROM |
| FR-S3 preferences | Display/background/quarter-hour timezone persisted | Driver/device/boot preferences, atomic versioned records, recovery defaults, DST/calendar policy, appearance/accessibility | Power-cycle each setting; corrupt/old records and failed writes recover predictably |
| FR-S4 shell | Commands, CAT, memory monitor, UCI navigation, HTTP socket GET | Shared FS integration, history/completion, scripts/pipes/redirection, jobs, useful errors, document/app launch | Scripted end-to-end workflow with removable media and network failures |
| FR-S5 editor/calculator | Small text editor; integer calculator | Larger banked documents, selection/clipboard/undo/find; calculator precision and scientific modes; standalone terminal | Save/reload documents beyond main RAM; arithmetic edge cases; interactive network/serial sessions |
| FR-S6 SDK | Fixed ABI and application guide | Versioned APIs, examples, app manifests, ABI/memory validation, docs generated from exports, portable test tooling | Build and run a third-party app from a clean checkout; no hardcoded developer-home dependencies |
| FR-S7 appearance | Basic background colors | Backdrops, font/theme/pointer selection, screen saver, desktop arrangements and persistence | Change/restart/restore; memory budgets and low-RAM fallback |

## Application parity backlog

These are separate applications and shared formats, not additional commands in
the existing shell. Original GEOS application execution is a separate
compatibility requirement from providing equivalent uOS applications.

| ID | Deliverable | Existing implementation | Completion gate |
|---|---|---|---|
| APP-WRITE | Word processor with fonts/styles, pagination, embedded pictures, search/replace, spelling, printing | Small plain-text editor only | Create, save, reopen, edit, preview and print a multipage illustrated document; exchange supported geoWrite formats |
| APP-PAINT | Bitmap editor, drawing tools, color/patterns, selection, zoom, clipboard, undo | Graphics primitives only | Edit and round-trip a picture on both displays; import/export declared GEOS/Commodore image formats |
| APP-SHEET | Spreadsheet with cell types, formulas, references, recalc, formatting, import/export, printing | Absent | Recalculate/save/reopen a useful workbook; formula cycles/errors and memory limits tested; geoCalc exchange matrix |
| APP-DATA | Database/address book with schema, records, sorting/filtering, forms/reports, import/export | Absent | Maintain and report a record set larger than main RAM; geoFile exchange matrix |
| APP-PUBLISH | Page layout with text/image frames, columns, styles, preview, print/export | Absent | Complete a newsletter and reopen it without layout loss; geoPublish comparison fixtures |
| APP-ORGANIZE | Calendar, appointments, alarms, contacts, notes and clock accessories | Clock plus editor | Persistent appointments; alarms while another app is active; timezone/date rollover tests |
| APP-MEDIA | Image/document/text viewers, font browser, photo/text scrap managers, SID/audio player | Shell's short CAT viewer | File association launch, scrolling/zoom, playlist, inter-app scraps, supported format round trips |
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
| UCI-BASE | Hardware/firmware identification, target/version discovery, command queue, timeout/abort, status/error display | Packet streaming, 16-bit command length, explicit clipping, bounded polling/abort; physical DOS/control identification | Capability registry and UI; resolve malformed drive inventory; interrupted operations and per-firmware protocol coverage |
| UCI-FILES | USB/flash/temp browser, full paths, directories, file read/write/copy/move/rename/delete/create | Desktop browser with eight-entry pages, long-name selection, keyboard/mouse controls and retry; physical browsing past ordinal 255 in a 1,096-entry directory | Responsive redraws, file operations/viewers, sorted/indexed listings, longer paths, shared file picker, Unicode display |
| UCI-DRIVES | A/B drive inventory, image mount/eject/create, drive type/power/address/ROM controls, write protection, save changes | Absent from desktop | Mount supported D64/D71/D81/G64/G71 images from desktop; verify cartridge and IEC view; recover system disk and unsaved work |
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
| Base C128 | 8502, MMU, VIC-IIe, 8563/8568, SID, CIAs, keyboard, IEC, user port, cassette, Z80/CP/M handoff | C64-mode reference machine; native mode and handoffs open |
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

Next implementation: reduce full-browser redraws and measure responsiveness;
build the drive panel and complete Ultimate file workflows, with capability
records and system-volume preservation. Observed page changes took 12.9–16.0 s
including host polling; this is correctness evidence, not a performance gate.
The installed control target also reports four drives while sending only two
records. Treat that inventory as incomplete. Mount/eject operations must validate
the actual destination: the firmware may fall back to a different drive for an
unknown IEC address. Native kernel and application parity work remain required
after these initial desktop/storage increments.

Before calling the complete OS finished, audit every FR in the original PRD,
every row above, all named app/hardware/firmware combinations, documentation,
packaging and performance gates. Missing hardware evidence remains unverified;
it does not become support by changing the wording of the roadmap.
