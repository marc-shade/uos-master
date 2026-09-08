# Resident capability lookup — 2026-09-08

This increment follows `95f1aaf`. GETCAP at `$082f` now uses the requested
ID, steps through three-byte records and returns the entry address in A/X
(low/high). Unknown IDs return zero in both registers. The old routine returned
`$06cc` even for ID 0; the [failing baseline](before.json) records that defect
on the previous core's exact hash.

The lookup preserves Y, zero page, non-stack RAM and the decimal/interrupt
flags. Its compact implementation saves 36 bytes. Core data occupies
`$0801–$0fd7`, leaving 40 bytes before the resident desktop at `$1000`.
All other resident and application PRGs match the preceding UCI checkpoint.

## Evidence

* [CPU regression](cpu.json): 1,024 calls through the public JMP slot, all 256
  IDs in ascending and descending order, varied A/flags and stack positions
  including stack-page wrap. Tests assert results, preserved registers/memory,
  balanced returns, bounded execution and no I/O access.
* [Emulator record](emulator/report.json): both x64 and x128 storage suites
  pass. Each calls all 256 IDs from the live desktop, then verifies directory
  scrolling, cache boundaries, bitmap restoration, empty/missing devices and
  successful/failed app loading. The x128 run also reads the VDC selection.
* [Physical C128 record](hardware/report.json): all 256 IDs return correctly;
  the desktop remains live. Scrolling and exact visible VDC filenames pass,
  browsing drive 9 still permits calculator loading from drive 8, `1+2=3`
  works, and a missing 16-character app name preserves the loader and desktop.
  The final distribution is running on the C128; drive B was unchanged.

The three `getcap*.bin` captures contain 256 low bytes followed by 256 high
bytes, indexed by capability ID. [The hardware image](hardware/file-manager.png)
renders the physical VIC bitmap; `hardware/vdc-final.bin` holds raw screen codes.
Raw logs retain the original device-output spacing.

## Scope and reproduction

This is a static resident-software lookup. It does not establish peripheral
presence, driver ABI versions or a dynamic capability registry. Those remain
in the [completion roadmap](../../IMPLEMENTATION-ROADMAP.md), along with the
Ultimate browser and drive panel. Hardware cold-boot and serial/input soak
coverage remains open.

```sh
./build.sh
python3 -m venv .venv-tests
.venv-tests/bin/python -m pip install -r tests/requirements-uci.txt
.venv-tests/bin/python -u tests/ci_core.py --report /tmp/core-report.json
python3 -u tests/run_ci.py storage64 storage128
python3 -u hw_storage_check.py --quick
```

The CPU check is independent of VICE and the local `cbm` helper. The emulator
and hardware scripts retain those existing dependencies. Do not rebuild while
tests are using the target PRGs/listings; reports record exact binary hashes.
