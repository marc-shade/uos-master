# Native owned IEC files — ABI 1.1

Native applications can open, read, exclusively create, write and close SEQ,
PRG and USR files through the kernel. Two streams can be open at once, on the
same or different IEC devices. Each handle belongs to an owner and includes a
generation, so a released handle cannot select a later file. Application exit
closes its native files before releasing its executable and banked memory.

The calculator is the first product client: **S** exports up to 32 history
results, oldest first, to a named SEQ file on the native system D64. Each line
ends with CR. It closes, reopens and compares every byte before reporting
`HISTORY SAVED AND VERIFIED`. An existing name is rejected without replacement.
An I/O error can leave a partial new file; the calculator reports that outcome.
**Esc** cancels the filename prompt. This export does not automatically reload
history into a later calculator session.

This is a foreground IEC backend. Native file pickers, directory enumeration,
seek/append/replacement, REL and GEOS/VLIR formats, cartridge filesystem
integration, removable-media identity and the driver registry remain open.
The existing graphical desktop still uses the separate legacy APIs.

## Calls and mailbox

Include [`api.inc`](../src/native/api.inc) and declare required ABI minor **1**
in the application manifest. Kernels with minor 1 also accept minor-0 apps.
Use the active `N_CURRENT` owner for file and memory allocations. File arguments
use their own mailbox; `N_FOWNER` is independent of the heap's `N_OWNER`.

| Entry | Address | Operation |
|---|---|---|
| N_FOPEN | `$1c41` | Open an existing read stream or exclusively create a new file |
| N_FREAD | `$1c44` | Read up to N_FCOUNT bytes into N_BUFFER |
| N_FWRITE | `$1c47` | Submit N_FCOUNT bytes from N_BUFFER |
| N_FCLOSE | `$1c4a` | Close the selected owned handle |
| N_FRELEASE | `$1c4d` | Preflight and close every handle belonging to N_FOWNER |

| Field | Address | Meaning |
|---|---|---|
| N_FOWNER | `$3d80` | Owner 1..254 |
| N_FHANDLE | `$3d81..84` | Slot+1 followed by a little-endian 24-bit generation |
| N_FDEVICE | `$3d85` | IEC device 8..30 |
| N_FNAMELEN | `$3d86` | 1..16 |
| N_FMODE | `$3d87` | 0 read; 1 exclusive create |
| N_FTYPE | `$3d88` | 0 SEQ; 1 PRG; 2 USR |
| N_FCOUNT | `$3d89..8a` | Requested count 1..512, little-endian |
| N_FACTUAL | `$3d8b..8c` | Returned/accepted prefix count |
| N_FEOF | `$3d8d` | 1 after consuming the checked read extent, including an empty file |
| N_FERROR | `$3d8e` | Stable result of this call |
| N_FDOS | `$3d8f` | First nonzero DOS code in this call, when available |
| N_FSTATUS | `$3d90` | Last serial status, retaining the first non-EOI error in this call |
| N_FBUSY | `$3d91` | Private call lock; applications must not write it |
| N_FPOSITION | `$3d92..95` | Returned byte position, little-endian 32-bit |
| N_FFORMAT | `$3d96` | 0 standard D64; 1 D71; 2 root D81; caller must select the actual format |
| N_FNAME | `$3da0..af` | Exact name, no terminating NUL required |

The shared `N_BUFFER` is `$3a00..$3bff`. OPEN uses it as metadata scratch;
prepare write bytes after OPEN succeeds. Heap transfers also use this buffer.
Save handles in application-owned memory when alternating streams. PRG reads
include their stored load-address bytes; the file service never executes them.

Names contain printable bytes `$20..$7e` and exclude `* ? , : / \ @ # $`.
The service adds an explicit type and access suffix. Directory, direct-buffer,
replacement and path syntax are unavailable through an ordinary filename.
Disk images with damaged, open/splat or unsupported file records are rejected.

All calls require the standard native MMU `$0e`, common RAM, zero-page and stack
configuration, interrupts enabled and normal keyboard/screen default channels.
They return A=0/carry clear on success; errors return A=code/carry set. Decimal
and interrupt flags, KERNAL filename/device/bank parameters and message flags
are preserved. A/X/Y and other flags are scratch. Nested file/heap calls are
rejected before changing the active operation's result or lock.

Errors retain the native hexadecimal values: `01` bad argument, `03` no slot, `04` stale or
invalid handle, `05` wrong owner, `06` invalid count/position overflow, `07`
reentry, `08` platform, `09` corrupt descriptor/disk metadata, `11` IEC/DOS
failure and `15` channel conflict. DOS 62 means absent file, and 63 means an
exclusive create found an existing file.

## Length, EOF and error handling

Read OPEN follows the directory and file-sector links using read-only `U1`
commands through a temporary direct buffer. It validates geometry, bounds the
directory walk, checks the declared block count and computes the exact byte
extent from the final sector. Ordinary reads then stream through the KERNAL,
bounded by that extent. The operation issues no raw disk writes.

This check addresses an observed 1541 emulation behavior: a zero-byte file
returned 254 padding bytes through CHRIN, and a one-byte file returned four.
Independent sector inspection confirmed the shorter stored files; c1541
extracted the one-byte files correctly but also returned padding for the empty
file. Replacing CHRIN with ACPTR produced the same responses. Empty
reads therefore return EOF without issuing CHRIN. Only an independently
measured one-byte file may finish without EOI on its first byte. Larger files
require EOI at the exact end; early or missing EOI poisons the handle. No
contents are trimmed by matching a byte pattern.

After EOF, further reads return zero bytes without disk I/O. On a read failure,
N_FACTUAL describes bytes already copied into the buffer. On a write failure,
it describes bytes accepted by the KERNAL before the error; the final IEC byte
may still have been deferred, so this count is **not proof of persisted bytes**.
Close and reopen to compare content before promising a verified save.

Each transferred byte and output flush checks IEC status. DOS status is checked
at OPEN, CLOSE and metadata commands; it is not polled between data chunks.
Always check CLOSE: a successful WRITE means the KERNAL accepted the bytes, and
a drive error may be reported when closing. Repeated intermediate DOS-status
reads caused truncated responses with the tested 1571 emulation. Removing
those reads passed the complete D71 copy/readback test; adding a delay did not
resolve the failure. The underlying firmware/emulator timing cause is not yet
established.

A failed transfer cannot be replayed on its poisoned handle. CLOSE may release
that handle if closing and final status checks succeed. An uncertain close
retains its owner and error; subsequent CLOSE/RELEASE reports that error without
blindly repeating disk operations. If OPEN fails after uncertain cleanup, its
returned handle remains owned. A completely cleaned failed OPEN clears the
output handle. Check carry before using it: preflight rejection need not clear
a previous handle value.

Application cleanup stops on the first file error and retains the app owner,
code slot and banked data, with N_APPSTATE=4. This prevents a later app from
inheriting uncertain channels. There is no general recovery UI yet. Direct raw
KERNAL files remain the application's responsibility.

## Channel ownership and disk scope

Data LFNs are 122/123 with secondary addresses 8/9. Command LFNs 124/125 are
shared per device and remain open until that device's last native stream
closes. LFN 126/secondary 10 is used temporarily during read OPEN. The service
checks the complete KERNAL table before issuing I/O, preserves unrelated files
on other devices and rejects foreign files on the selected device. Closing
command channel 15 can close that device's other files, so it must be last.
The private app loader similarly rejects existing files on its selected device
and closes its own LFNs 120/121 before entering the app.

The geometry selector is explicit, not device discovery. It covers standard
35-track D64, 70-track D71 and unpartitioned/root 80-track D81 layouts. It does
not qualify arbitrary IEC devices, firmware, partitions, enlarged D64 formats,
SD2IEC native directories or media changes during an open stream. More than
two streams and integrating the loader with this backend remain future work.

The read-only block commands and disk layouts follow the original Commodore
[1571 User's Guide, chapters 7 and appendix C](https://s3.amazonaws.com/com.c64os.resources/weblog/sd2iecdocumentation/manuals/1571_Users_Guide.pdf)
and [1581 User's Guide, chapter 6 and appendix C](https://s3.amazonaws.com/com.c64os.resources/weblog/sd2iecdocumentation/manuals/1581_Users_Guide.pdf).
The 1541 chain layout and DOS behavior are also described in
[Inside Commodore DOS](https://www.pagetable.com/docs/Inside%20Commodore%20DOS.pdf).

## Verification

```sh
python3 tests/ci_native_files.py --report /tmp/native-files.json
python3 tests/ci_native_calc.py --report /tmp/native-calculator.json
python3 -u tests/run_ci.py nativefiles nativefiles71 nativefiles81 native
python3 -u hw_ultimate_check.py --native-files
```

The CPU tests require Py65. They execute assembled code against independent
file/sector models and inject transfer, status, channel and cleanup faults.
The emulator tests cold boot the native disk and load a test-only client, then
copy and reopen more than 64 KiB through real KERNAL/drive emulation. The physical
test uses smaller private D64 fixtures and retrieves their complete images
through the cartridge protocol after restoring the legacy desktop. An independent
host reader validates each file's sector chain and exact stored bytes, including
empty files. c1541 provides a second byte comparison for every nonempty file;
its empty-file padding is recorded separately.

See the [dated evidence and qualification limits](validation/2026-09-09-native-files/README.md)
for actual outcomes; a listed test command alone is not a passing result.
