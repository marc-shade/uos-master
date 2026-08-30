# UltOS — a modern graphical OS for the Commodore 128 (Ultimate II+ family)

Fork of [xlar54/uos-master](https://github.com/xlar54/uos-master) — Scott Hutter's
work-in-progress graphical operating system written specifically for the
[Ultimate 64 / Ultimate II+](https://1541u-documentation.readthedocs.io) cartridge line.

uOS already boots and runs on **real hardware**: a Commodore 128 with an Ultimate II+,
16 MB REU, 1541/1581 drives and *both* displays (VIC-II 40-col + 8563 VDC 80-col) wired up.
The upstream project is a young alpha (desktop + settings, mouse-driven); this fork
builds it out into a complete C128 OS — see [docs/roadmap.html](docs/roadmap.html)
(gap analysis + M0–M6 milestones, hardware-gated) and [docs/prd.html](docs/prd.html)
(product requirements across the whole 2026 Commodore hardware universe).

## What's new in this fork (v0.2, verified on real C128 hardware)

- **Real Applications launcher** — the "Apps submenu" placeholder is gone: the desktop
  scans the system disk directory for `uos-*` apps (system components filtered out),
  lists each as a selectable row, and any row launches through the core loader.
- **Core export `FILLFILE`** (new jump-table entry at `$0829`): pass a pointer to any
  null-terminated filename to fill the loader buffer — apps can load by *name at runtime*
  instead of only inline strings. This is the primitive the file manager needs.
- **`build.sh`** — Linux build (the upstream shipped only a Windows `build.bat`),
  proven byte-identical to the upstream artifacts before any code changes.

## Building

```
./build.sh          # needs 64tass + c1541 (VICE) on PATH
```

Creates `target/ultos.d64` with the full system. Run it on:

- **Real C128/C64 + Ultimate II+** — mount the D64 on drive A, then
  `LOAD"UOS",8,1` + `RUN` (or post `target/uos.prg` to the U2+ REST
  `runners:run_prg` endpoint, which boots straight into C64 mode).
- **VICE x128** — `x128 -autostart target/ultos.d64` (add `-80col` for an
  80-column-booted test; uOS itself currently renders 40-col).

Requirements on real hardware: a 17xx-compatible REU (Ultimate REU emulation is
fine) and a 1351-protocol mouse (Commodore 1351, Tom+/micromys, mouSTer).

## Hardware verification

Everything in this fork marked "verified" was run on the physical reference
machine (C128 + U2+): signed commits, hardware-gated milestones, and probes
kept in [`probes/`](probes/) — e.g. the VDC register-access probe series
(`probes/vdcprobe*`) that backs the coming 80-column dual-display work.

## Upstream

All credit for UltOS itself goes to Scott Hutter. This fork tracks
`upstream` = xlar54/uos-master; our `main` carries the fork's increments and
they are intended to be upstreamable (small, documented, hardware-proven).
License: GPL-3.0, as upstream.
