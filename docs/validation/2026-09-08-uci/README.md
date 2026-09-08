# UCI transport and boot validation — 2026-09-08

This increment follows storage commit `ed69fa7`. It implements the
[packet-streaming service](../../ULTIMATE-SERVICE.md); the desktop browser,
capability registry and drive panel remain roadmap work.

## Verified behavior

* [CPU/protocol record](protocol.json): 14 checks execute the assembled network
  driver with Py65, including 1,000 directory packets, binary 512-byte blocks,
  896-byte commands, overflow, empty directories, cancellation/reuse, and
  stuck-command/data timeouts. The original aggregate directory implementation
  produced 534 writes beyond its reply buffer in the baseline reproduction.
* [Final emulator build/result](emulator/report.json): x64 storage, x128 storage,
  VDC and file-manager suites all passed on the final binaries. This includes
  both directory caches and bitmaps, absent/empty devices, app-load error paths,
  clock conversion, settings persistence, control tables and shell regression.
* [Physical cartridge record](hardware-stream.json): DOS/control identify;
  300- and 512-byte binary echoes match every byte; an 896-byte command reaches
  the cartridge, with exactly 512 bytes retained and clipping explicitly set.
  The C128 then receives 1,096 directory packets from `/Usb0/c64/#-a/`, finishes
  the transaction and returns to the live desktop with transport code intact.
* [Final reboot/app/display record](hardware-final/report.json): a second
  hardware boot, exact visible VDC filenames, browsing drive 9 then loading and
  using the calculator from drive 8, and a failed 16-character filename that
  leaves the loader and desktop intact. The final image is running on the C128.
* [Live network/clock record](hardware-clock.json): socket/SNTP synchronization
  succeeded, the runtime RTC advanced and matched the host within one second,
  and the physical VDC showed the correct time with the `ntp` indicator.

The hardware probe's separate capture buffer retained the first 6,268 payload
bytes from that large directory and set its own `capture_full` flag. It continued
receiving all 1,096 packets. This proves physical multipart streaming beyond the
reply buffer; it is not an exhaustive filename comparison of all 1,096 entries.
The DOS working directory was restored after testing, and no directory entries
or file contents were modified. Drive A held the distribution; B was unchanged.

## Firmware inventory limitation

The control target identifies as `CONTROL TARGET V1.1`. Its drive response is
`04 00 08 01 00 09 01`: four declared devices but only two three-byte records.
The report explicitly marks `inventory_complete: false`. The received records
describe powered 1541 emulations at IEC 8 and 9; they do not supply the missing
SoftwareIEC/printer records. No complete drive-discovery or mount/eject gate
is claimed. The exact cartridge firmware release remains unidentified.

The cartridge RTC is working. DOS GET_TIME returned `2026/09/08 15:03:07`
and `2026/09/08 15:03:10`. The earlier "frozen at 2015" diagnosis used saved
REST Clock Settings fields rather than the running RTC. `hw_net_check.py`
now checks two advancing runtime readings against the host clock. Backup-battery
retention and offline boot behavior still need their own checks.

The [final file-manager capture](hardware-final/file-manager.png) is a
monochrome rendering of the physical VIC bitmap; `hardware-final/vdc-final.bin`
contains raw VDC screen codes from the same check.

## Startup failure and correction

The [earlier VDC run](before-boot-order-fix/vdc.log) failed to reach its boot
header; an independent emulator run then passed on those same binaries.
The [physical diagnostic](before-boot-order-fix/hardware.json) caught a startup
stall in the optional `UOS-SET` KERNAL load, before `NET_SYNC`, with the custom
mouse IRQ already installed. Resident module bytes had loaded correctly.

Core setup now installs the mouse IRQ after settings/display/network startup.
The final four emulator suites pass with that order, and the physical machine
reaches the desktop and completes the UCI checks. This is targeted regression
evidence; longer cold-boot and concurrent serial/input soak testing remains open.

## Reproduce

```sh
./build.sh
python3 -m venv .venv-tests
.venv-tests/bin/python -m pip install -r tests/requirements-uci.txt
.venv-tests/bin/python -u tests/ci_uci.py --report /tmp/uci-report.json
python3 -u tests/run_ci.py storage64 storage128 vdc fm
python3 -u hw_uci_check.py
python3 -u hw_storage_check.py --quick
python3 -u hw_net_check.py
```

The hardware script uses the reference cartridge and a bounded read-only
directory traversal to find a large fixture. `--no-boot` continues on an already
booted matching transport. The host hardware/VICE helpers still need the local
`cbm` dependency; the Py65 protocol tests do not.
