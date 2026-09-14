# Packed native app startup

The desktop suite stores the launcher and six apps as standard NAPP files
with a checked LZSA2 startup wrapper. The D64 suite has **147 free blocks**
instead of one; D81 has **2,643**. The thirteen disk entries, resident kernel,
426-page heap and application allocations are unchanged. The diagnostic native
disks continue to use their original app files.

The kernel validates the complete outer file and closes its source before
executing the wrapper. Startup expands the original app body into its owned
allocation, verifies its complete length and CRC16, releases temporary memory
and enters the original program. A failed check returns through normal app
cleanup before any original program instruction executes.

| Suite program | Original PRG bytes | Packed PRG bytes | App pages |
|---|---:|---:|---:|
| Desktop | 8,835 | 7,362 | 35 |
| Calculator | 12,430 | 9,275 | 49 |
| Editor | 13,128 | 7,579 | 96 |
| Files | 12,984 | 7,993 | 96 |
| Ultimate | 22,678 | 14,011 | 89 |
| Claude | 11,059 | 7,298 | 75 |
| Paint | 24,525 | 15,125 | 96 |

PRG sizes include the two-byte load address. This saves 36,996 file bytes and
146 disk blocks. Packing creates disk space; the expanded apps retain their
existing code and document limits. The remaining graphical VDC app views and
larger document backing still require their own implementation work.

## Allocation and recovery

Startup checks the running-app state, structural manifest, parent descriptor
and every parent page tag before reserving scratch. Its decoder occupies four
temporary bank-0 pages at `$5000..$53ff`. The compressed input uses a separate
owned allocation, preferring bank 1 and falling back to bank 0. Its page count
depends on the app and is recorded under `packed_apps` in `deployment.json`.
No REU or VDC state is needed for decompression.

The complete compressed input is staged through `N_WRITE` before the app body
is overwritten. Decoder refills use bounded `N_READ` calls. Every backreference
starts within the body already produced; every output byte is bounded by the
original program's end. Refills preserve the decoder's carry and register
counts. Interrupts remain enabled and normal native bank gateways preserve
the caller's mapping and borrowed scratch.

A cleanup routine uses 48 unused bytes at the end of the app allocation.
For Editor and Files this is part of the module window before its first load.
The other programs have sufficient trailing padding; Claude's linker map
checks that its BSS and C stack end before the cleanup area. The routine
releases the decoder only after control has left it, then releases the input
allocation. Neither temporary allocation remains when the original app starts.

Allocation, transfer, malformed-stream and checksum failures unwind the
decoder stack into that same cleanup routine. It returns the startup error as
the app exit code; the normal kernel cleanup reclaims remaining app-owned RAM.
An outer-file checksum or extent failure is a loader error and never enters
the wrapper. Foreign allocations and open files are retained.

The four contiguous decoder pages and two temporary handle slots must be
available at startup. These are temporary requirements, including on machines
without an REU; they do not reduce memory available after startup.

## Image and module identity

The outer file remains native format 1 with the app's existing ABI requirement,
title, allocation size and module-window origin. Its entry starts the wrapper;
its declared file length and checksum describe the actual packed file. The
kernel's cached header remains that outer identity after expansion.

The `NPZ2` metadata after the NAPP header contains the original header, runtime
extent, cleanup location and packed payload extent. `native_app_pack.decode`
reconstructs and validates the original complete PRG for independent comparison.
The production wrapper retains its own compiled bounds and CRC checks.

Editor and Files modules retain their exact code and layout. The builder
reseals their parent and module checksums against the packed app's identity.
Copy each app together with its matching modules; Desktop and Calculator also
need `VDSVC.PRG` beside them. Unpacking an app for development requires resealing
its modules against that unpacked parent.

## Build and checks

`python3 -B build-native-desktop.py` builds raw programs, wraps the seven suite
apps, reseals the four app-bound modules and writes both disk formats. Runtime
assembly listings retain the original program addresses. Additional
`*-pack.lst` and `*-pack.sym` files describe each startup wrapper. Packing uses
the existing pinned LZSA compressor and licensed decoder source; it requires
the same host C compiler as native boot compression.

`ci_native_app_pack.py` executes the actual kernel loader, allocation and bank
gateways. It checks complete original bodies, cleanup before entry, IRQ/NMI
delivery, bank-0 input fallback, allocation and transfer failures, malformed
streams, changed allocation declarations and both checksum layers.
`ci_native_app_pack_slots.py` checks exhausted handle tables. Existing app,
module, media and VICE workflows exercise the packaged suite.

This is software qualification. The packed suite has not been deployed to or
qualified on the physical C128.
