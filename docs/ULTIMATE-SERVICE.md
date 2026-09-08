# Ultimate command service

The resident `uos-net` module now offers packet streaming alongside the
existing aggregate interface. The [desktop browser](ULTIMATE-BROWSER.md) uses
it for filesystem navigation. Drive control and other desktop integrations
remain on the completion roadmap.

The [Ultimate register specification](https://1541u-documentation.readthedocs.io/en/latest/uci/core_uci_architecture.html)
defines 896-byte command/data FIFOs and a 256-byte status FIFO. The uOS response
buffer is smaller, so its API explicitly reports data loss. The
[DOS target](https://1541u-documentation.readthedocs.io/en/master/uci/ultimate_dos_target.html)
returns one attribute/name packet per directory entry. Its directory attribute
is `$10`. Firmware target identification strings identify the service; they
are not proof of an exact cartridge firmware release.

## Calls and results

`NET_CMD` at `$9103` accepts `r0 = command pointer`, `A = length` (2–255).
It collects up to 510 data bytes at `NET_DATA=$8800`, with length `NET_LEN`
at `$913f` and status text at `NET_STAT=$9142` (31 characters plus terminator).
It clears any previous streaming callback on every call.

With `NET_DIRMODE=$9162` set, the aggregate result contains complete leading
directory records, each followed by a zero byte. `NET_DIRN=$9163` counts only
those records, and `NET_LEN` includes their separators. Empty/status-only
packets do not add an entry. A partially received record and every subsequent
record are discarded; the retained prefix stays parseable and bounded.

`NET_STREAM` at `$9164` accepts:

| Register | Input |
|---|---|
| `r0` | Command pointer; target is the first byte |
| `r1` | 16-bit command length, 2–896 |
| `r3` | Callback address, or zero to use aggregate collection |

When a callback is supplied, each packet starts afresh at `NET_DATA` and
`NET_DIRMODE` is ignored. Before acknowledging that packet, the driver calls
the callback with `NET_LEN` bytes available. It retains up to 512 bytes of
one packet, allowing complete 512-byte file-read blocks. A packet of exactly
512 bytes has **no zero terminator**; use its length. Shorter packets have an
extra zero for string callers. Packet contents, including zero-valued attributes
and bytes above `$7f`, remain binary.

| Export | Meaning |
|---|---|
| `NET_TRUNC=$9167` | Some response data was discarded in this transaction |
| `NET_PACKET_TRUNC=$9168` | This packet was clipped; inspect inside the callback |
| `NET_PACKETS=$9169` | 16-bit count of received packets, including status-only packets |

The callback may clobber A/X/Y and `r0`–`r15`. Return carry clear to continue
or set to abort. It must preserve the driver-private scratch at `$70`–`$7f`
and must not call another UCI command. Copy/cache the needed data before
returning: the following packet replaces the buffer. A browser can stop after
filling a page and restart a directory read to reach another page.

Both calls return the two-digit firmware status in A with carry clear when
the transaction completes. A nonzero status is still an operation failure.
Malformed status text returns `$ff` with carry clear. Transport failures return
carry set:

| A | Meaning |
|---|---|
| `$fc` | Invalid command length; nothing was sent |
| `$fd` | Callback requested cancellation; ABORT was issued |
| `$fe` | Command interface absent |
| `$ff` | Timeout or packet-count limit; ABORT was issued |

The response/status queues are drained even when storage fills. Polling is
bounded during waits and queue reads; packet-count overflow aborts the request.
The next command waits for the cartridge to acknowledge an abort.
Consumers must check both operation status and truncation before using a
filename/path or accepting file contents.

## Memory and verification

The PRG starts at `$8a00` with the transport and retains its public table at
`$9100`. Its boot load spans the control-table page at `$9000`; core setup
initializes that table after all modules load. This module is loaded during
boot, and must not be reloaded over a live desktop. Assembly assertions bound
the transport below `$9000` and the network/clock portion below `$9b00`.

`tests/ci_uci.py` executes the assembled driver with Py65 against a register
and FIFO model. It checks long/binary packets, 1,000-entry streaming, a full
buffer beside resident instructions, long/invalid commands, empty directories,
callback cancellation/reuse, and stuck-command/data timeouts. It reproduced
534 writes beyond the old reply buffer for a 100-entry directory before the
fix. The model supplements real cartridge tests; it is not timing certification.

`hw_uci_check.py` boots the distribution on the C128, queries DOS/control and
drive inventory, checks generated binary echo bytes, and streams real
directories. It restores the original DOS path and leaves the desktop live.
Drive A holds the distribution during the check; drive B is unchanged.

The [2026-09-08 validation record](validation/2026-09-08-uci/README.md)
includes a physical 1,096-entry stream and the exact build hashes. The installed
control target reports four devices but returns only two records
(`04 00 08 01 00 09 01`). This is an incomplete inventory, not a valid four-device
response. The desktop service must reject or explicitly reconcile it before
using it to authorize mount/eject choices. The two visible records alone do not
certify SoftwareIEC or printer discovery.

The browser now implements long-name selection and paginated browsing. The next
layer needs capability records, explicit drive choice, and system-volume recovery
before mount/eject workflows. The [completion roadmap](IMPLEMENTATION-ROADMAP.md)
continues to track those requirements and the rest of the OS.
