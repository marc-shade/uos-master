# Ultimate browser redraw — 2026-09-08

This increment follows `8ea40ee`. The browser keeps its frame, toolbar and
help text in place while navigation updates the fields that changed. VDC text
replacement pads only to a field's previous length. VIC list text is aligned
with bitmap bytes, and a small scanline eraser replaces the former expanded
whole-window clear. The browser shrinks from 3,750 to 3,520 PRG bytes; its last
loaded byte is `$5dbd`, below the `$6000` filename cache.

Selection changes update only the former/current row prefixes and the name
details. Name/path scrolling updates the details. Page changes update all
mutable fields. Invalid keys and navigation at the final page do not redraw.
The VDC driver's existing repeated writes and readback repairs remain in use.

## Correctness

The actual graphics test exposed a stale descender when changing from a long
name containing `g` to a short name. Its ink reached Y+8, below an eight-row
erase. Font data also places the dollar sign at Y−1. Text erasure now includes
Y−1 through Y+8, while the initial frame uses eight-row strips. Every GPUTS
call explicitly sets the full Y coordinate after using public scratch.

The wider character case then found that braces, vertical bar and tilde were
being passed through despite having no matching VIC glyph. Some values read
past the font table and drew into the status row. The
[failing model record](before-glyph-fallback/report.json) and its
[VIC bitmap](before-glyph-fallback/printable-glyphs.vic.bin) preserve that case.
These symbols now use the existing dot fallback on both displays, alongside
control and non-ASCII bytes. A navigation test checks that the original raw
bytes still reach the cartridge in the change-directory command.

All six [browser CPU groups](cpu.json) pass, including paging through 1,100
entries, full 511-byte names, raw fallback-character operands, mouse actions,
errors/cancellation and memory guards. All 14 PRGs in the
[disk readback](disk.json) match the built files byte for byte.

`tests/profile_browser.py --check-fresh` executes the assembled browser,
transport, core, VIC graphics and VDC driver against register models. Each
incremental result is compared byte for byte with a fresh frame of the same
state: 8,000 VIC bitmap bytes and 4,096 VDC character/attribute bytes. All 21
cases pass in the [final model record](model/after.json). Cases
include long and short selections, name scrolling, path view, partial and
empty pages, directory errors, retry, wide glyphs, printable filename bytes
and rejected Open. This checks drawing behavior independently of the browser
tests that replace graphics calls with text adapters.

All three [final emulator suites](emulator/report.json) pass: x64 storage,
x128 storage, and all 15 VDC/clock/input checks. These include registered
sixth-row launch, the browser's [offline response](emulator/offline.png),
preference preservation and return to a dispatching desktop. Only the browser
PRG changes in this increment; the resident modules and other apps retain
their preceding hashes.

The [earlier physical comparison](clock-comparison-failure/report.json) passed
all four selection/VDC checks but failed its VIC assertion. That helper had
not retained the returned bitmap, so the exact differences from that attempt
are unavailable. Its comparison included the desktop clock's redraw area:
`ClrRect 280,191,39,8` clears complete bitmap bands at X=280–319, Y=184–199.
This overlaps the browser's lower-right shadow. The helper now saves both
bitmaps before asserting, records every changed byte, and excludes only that
clock rectangle. It also forces the existing clock repaint by invalidating
the cached minute, without changing the clock's time. Reserving the desktop
footer cleanly remains part of the shared clipping/window work.

A subsequent run passed the selection round trip and all 32 pages, but its
[root VDC capture](vdc-capture-shift/root.vdc.bin) shifted the remaining stream
left by one byte. The selected name, status and unchanged help line each
match exactly one byte before their expected row origin; the
[analysis](vdc-capture-shift/analysis.json) records those independent checks.
The [failed run](vdc-capture-shift/report.json) remains separate from passing
evidence. Adding a one-second quiet interval did not prevent another
[paired-capture failure](quiet-capture-failure/report.json): one dump was
shifted while its immediate successor read the unchanged screen correctly.
The quiet interval alone therefore does not establish the cause or a fix.

The capture probe now seeks each byte explicitly and verifies the resulting
address increment through registers 18/19 before accepting it. This follows
the register behavior described in the
[Commodore 128 Programmer's Reference Guide](https://www.pagetable.com/docs/Commodore%20128%20Programmer%27s%20Reference%20Guide.pdf),
printed page 327. Unexpected increments cause a bounded address reset and
retry; three failed attempts stop the capture with an error. The probe reports
the resynchronization count. Its [nine CPU cases](capture-cpu.json) cover exact
2,000-byte output, injected drift at several offsets and both sides of a page
boundary, persistent drift, absent hardware, output guards and IRQ/stack/ZP
restoration. The hardware helper allows two seconds before DMA observation
and still requires two independently acquired app areas to agree. The exact
electrical cause of the earlier shifted read is unconfirmed. No production
VDC code was changed.

Eight consecutive [physical captures](capture-hardware/report.json) then
matched the expected desktop app area and a stable footer. All completed
without an address resynchronization, and the IRQ chain returned to a live
desktop. Separately, the retained
[first-page VIC/model comparison](vdc-capture-shift/first-vic-model.json)
matches every byte in the browser interior at X=24–295, Y=8–183. Its ASCII
fixture comes from VDC names already checked against the packet oracle.

## CPU measurement

The model uses immediate VDC readiness after a required poll. It excludes VIC
bad lines, interrupts, DMA pauses and host latency; cycle counts are not
physical elapsed times. The first four actions use the same 18-entry directory
as the [baseline](model/before.json), with a 299-byte selected name on page one.

| Action | Baseline cycles | Updated cycles | Change |
|---|---:|---:|---:|
| Initial display | 7,719,610 | 7,802,118 | 1.1% more |
| Down to a short name | 6,542,191 | 732,581 | 88.8% fewer |
| Next page | 6,344,999 | 1,422,060 | 77.6% fewer |
| Previous page to long name | 7,719,698 | 2,677,819 | 65.3% fewer |

Initial display still clears and paints the complete window. The improvement
applies to subsequent navigation. Higher directory pages still rescan all
earlier packets, and selecting a longer name still costs more to render.

## Physical browser result

The [final C128 run](hardware/report.json) passes with the same production
hashes as the CPU and emulator records. It reused the desktop booted from this
build during the earlier attempt, then loaded the browser through its registered
sixth Applications row. All 32 Next actions reach ordinal 256 in the
1,096-entry directory. Complete names match the independent packet oracle on
the first and ordinal-256 pages.

All seven sampled app areas have two matching VDC captures: the first page,
four selection changes, ordinal 256 and Root. Every list/detail row includes
its blank tail in the comparison. No capture needed an address resynchronization
or a host RAM-read retry. Root clears the unused rows; selecting Usb0, Open
and Parent all succeed. Preferences are preserved, ESC returns to a dispatching
desktop, and DOS targets 1 and 2 return to `/` and `/Usb0/c64/#-a/` respectively.
Drive B was not remounted and no filesystem files were modified.

The [first bitmap](hardware/first.png) and
[selection round trip](hardware/selection-return.png) are identical in this
final run, including the clock area. The earlier clock-repaint case retained
49 changed bytes, all inside the documented clock rectangle, with no browser
residue. The [ordinal-256 image](hardware/ordinal-256.png) and adjacent raw VDC
captures preserve the later page.

| Physical observation | Previous build | Current build |
|---|---:|---:|
| Median of 32 page changes | 14.497 s | 7.903 s |
| Page-change range | 12.917–15.966 s | 6.455–9.239 s |
| Four selection changes | Not measured | 0.516–0.644 s; median 0.642 s |

The [timing summary](hardware/timing-summary.json) records a 45.48% reduction
in median observed page time. Timings include host polling and its pauses;
capture time is outside each timed action. The synthetic model uses shorter
ordinary names than this physical directory, so its percentage reduction is
not the physical speedup. Initial-load timing and longer soak coverage remain
open. A separate startup attempt encountered an API timeout before navigation;
the API responded to the next health check, and this final run needed no retries.

## Reproduction

```sh
./build.sh
python3 -m venv .venv-tests
.venv-tests/bin/python -m pip install -r tests/requirements-uci.txt
.venv-tests/bin/python -u tests/ci_ultimate.py --report /tmp/browser.json
.venv-tests/bin/python -u tests/profile_browser.py --out /tmp/browser-render --check-fresh
.venv-tests/bin/python -u tests/ci_vdc_capture.py --report /tmp/capture.json
python3 -u tests/run_ci.py storage64 storage128 vdc
python3 -u hw_ultimate_check.py --no-boot --capture-only
python3 -u hw_ultimate_check.py
```

Do not rebuild during validation: the emulator and hardware helpers use the
current target PRGs and listings. Physical checks leave the existing quiet
intervals around IEC loads because cartridge RAM observations pause/resume the
CPU. Hardware timings include host observation overhead.

The [completion roadmap](../../IMPLEMENTATION-ROADMAP.md) still requires the
drive panel, capability discovery, file operations and viewers, native C128
services and the remaining application/expansion work.
