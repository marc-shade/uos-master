; Native C128 ABI 1.6. This is separate from the C64-mode $0811 jump table.
N_ABI_MAJOR = 1
N_ABI_MINOR = 6
; Call from bank-0 code with system KERNAL and I/O visible. The standard
; bottom 1 KiB common area, zero page and stack mappings must remain in force.
; Foreground calls only; no IRQ/NMI callbacks or reentrant use.
; C=0/A=0 success, C=1/A=error. D/I are preserved; A/X/Y otherwise clobbered.
N_ALLOC         = $1c20
N_FREE          = $1c23
N_READ          = $1c26
N_WRITE         = $1c29
N_FILL          = $1c2c
N_STATS         = $1c2f
N_RELEASE       = $1c32
N_RESERVE       = $1c35
N_LAUNCH        = $1c38          ; checked PRG through owned IEC/Ultimate streams
N_KEYIN         = $1c3b          ; native GETIN with shared key-event accounting
N_EXIT          = $1c3e          ; one-way app exit, A=app result; restores saved stack
N_FOPEN         = $1c41          ; owned read/create stream or Ultimate directory cursor
N_FREAD         = $1c44          ; up to 512 file bytes, or one complete directory entry
N_FWRITE        = $1c47          ; up to 512 bytes from N_BUFFER
N_FCLOSE        = $1c4a          ; close only this owned file
N_FRELEASE      = $1c4d          ; close every file owned by N_FOWNER
N_DIRPAGE       = $1c50          ; one normalized directory page; no live stream on success
N_REPLACE       = $1c53          ; leave app, request dispatcher launch with source fields
N_WORKSPACE     = $1c56          ; leave app, request return to the memory workspace
N_FEDIT         = $1c59          ; edit the active app's bounded field, no input polling
N_FDRAW         = $1c5c          ; draw that focused field at the current console position

; Allocation: OWNER=1..254, PAGES=1..255, BANK=0/1/$ff (automatic).
; Automatic allocation uses bank 1 first, preserving bank-0 code space.
; RESERVE additionally takes PAGE and requires an explicit bank.
; A successful allocation returns a four-byte handle: slot+1, generation LE24.
; Free/read/write/fill require both the handle and its owner.
; READ/WRITE/FILL: OFFSET and COUNT within the allocation; COUNT=1..512.
; READ/WRITE transfer through BUFFER; FILL uses VALUE. No unchecked far pointer.
; RELEASE releases all handles belonging to OWNER. Allocation does not clear
; RAM; callers initialize their allocations explicitly. No REU is touched.
N_OWNER         = $3d00
N_PAGES         = $3d01
N_BANK          = $3d02
N_PAGE          = $3d03
N_HANDLE        = $3d04          ; four bytes
N_OFFSET        = $3d08          ; word
N_COUNT         = $3d0a          ; word
N_VALUE         = $3d0c
N_ERROR         = $3d0d
N_FREE0         = $3d0e          ; free 256-byte pages, bank 0
N_FREE1         = $3d0f          ; free 256-byte pages, bank 1
N_SLOTS         = $3d10          ; reusable descriptor slots
N_BUSY          = $3d11
N_READY         = $3d12
N_KEYS          = $3d13          ; word: consumed keyboard events
N_LASTKEY       = $3d15
N_RESULT        = $3d16          ; workspace's last command result
N_CURRENT       = $3d20          ; active app owner; 0 when no app owns the slot
N_DEVICE        = $3d21          ; launch IEC device 8..30, or Ultimate DOS context 1/2
N_NAMELEN       = $3d22          ; IEC launch name 1..16; Ultimate path length 1..255
N_APPSTATE      = $3d23          ; 0 idle, 1 loading, 2 running, 3 cleanup, 4 retained error
N_EXITCODE      = $3d24          ; last application's A on return/EXIT
N_DOSCODE       = $3d25          ; DOS error code (decimal), when available
N_IOSTATUS      = $3d26          ; first failed loader stream's nonzero transport status
N_APPERROR      = $3d27          ; stable launch result, separate from heap ERROR
N_ACTION        = $3d28          ; completed app request: 0 normal, 1 replace, 2 workspace
N_BROWSERDEV    = $3d29          ; workspace/browser preferences (not file-call arguments)
N_BROWSERFMT    = $3d2a
N_BROWSERERROR  = $3d2b          ; last dispatcher error shown when the browser returns
N_APPFORMAT     = $3d2c          ; launch/source backend: 0 D64 / 1 D71 / 2 D81 / 3 ULT
N_BOOTDEVICE    = $3d2d          ; boot IEC device; independent of app source
N_BROWSERLEN    = $3d2e          ; ABI 1.5: persistent Ultimate browser path length
N_BROWSERPOS    = $3d30          ; dword: selected Ultimate directory ordinal
N_BROWSERNAME_LEN = $3d34        ; ABI 1.5: selected raw name length, 0 when empty
; ABI 1.6 field state is eight bytes inside the active app allocation:
; length, caret, maximum, buffer address LE16, VIC view, VDC view, filter.
; Buffer reserves maximum+1 bytes in the same allocation; it cannot overlap
; the state. Filter: 0 printable, 1 decimal, 2 hexadecimal, 3 IEC filename.
; FEDIT key 0 initializes caret/views and the terminator after external input.
; Other keys: LEFT/RIGHT, HOME/CTRL-A, CTRL-E end, DEL backspace,
; CTRL-D forward delete, CTRL-U clear, INS insert space, printable insertion.
; FDRAW uses WIDTH=3..79 cells on the current display, including two clipping
; markers. Both APIs require a running foreground app and enabled IRQs.
N_UIPTR         = $3d35          ; word: field-state address
N_UIKEY         = $3d37
N_UIWIDTH       = $3d38
N_UIFLAGS       = $3d39          ; successful edit: bit 0 content, bit 1 caret changed
N_UIERROR       = $3d3a
N_UIBUSY        = $3d3b
UI_LENGTH       = 0
UI_CARET        = 1
UI_MAXIMUM      = 2
UI_BUFFER       = 3
UI_VIEW40       = 5
UI_VIEW80       = 6
UI_FILTER       = 7
UI_STATE_BYTES  = 8
N_BROWSERNAME   = $3e00          ; 256 bytes; restore selection after directory edits
N_APPNAME       = $3d40          ; 16-byte filename, no wildcard/DOS syntax
N_APPHEADER     = $3d60          ; validated 32-byte native image manifest
N_BUFFER        = $3a00          ; 512 bytes, bank 0, reserved

; Foreground streams. Two handles shared by IEC/Ultimate; slot+1 + generation LE24.
; IEC names: 1..16 printable bytes without wildcards or DOS command separators.
; MODE 0 reads, 1 creates a new file; IEC TYPE 0 SEQ, 1 PRG, 2 USR.
; ABI 1.5: Ultimate MODE 2 opens a directory cursor, using one shared handle.
; PRG streams include their two-byte load address. No implicit conversion.
N_FOWNER        = $3d80
N_FHANDLE       = $3d81          ; four bytes
N_FDEVICE       = $3d85          ; IEC 8..30 or Ultimate DOS context 1/2
N_FNAMELEN      = $3d86
N_FMODE         = $3d87
N_FTYPE         = $3d88
N_FCOUNT        = $3d89          ; requested word, 1..512
N_FACTUAL       = $3d8b          ; returned word; may be a prefix on I/O error
N_FEOF          = $3d8d          ; read handle has consumed its checked extent
N_FERROR        = $3d8e
N_FDOS          = $3d8f          ; IEC first error; Ultimate most recent numeric status
N_FSTATUS       = $3d90          ; IEC serial error; Ultimate transport/verification detail
N_FBUSY         = $3d91
N_FPOSITION     = $3d92          ; LE32 byte position, or directory entries consumed
N_FFORMAT       = $3d96          ; 0 D64, 1 D71, 2 D81, 3 Ultimate DOS
; Ultimate streams use DEVICE=1/2 (DOS context), FNAMELEN=1..255 and
; UPATH (raw bytes, no terminator). File streams leave both DOS CWDs alone.
; TYPE has no effect on raw Ultimate files. DIRPAGE remains IEC-only.
; ABI 1.4: N_LAUNCH/N_REPLACE with APPFORMAT=3 read N_UPATH using
; N_NAMELEN and N_DEVICE=1/2; N_APPNAME is ignored for Ultimate loading.
; Directory READ requires FCOUNT=512 and returns [attribute, name bytes],
; FACTUAL=2..256 or zero at EOF; names are complete and have no terminator.
; Successful directory OPEN returns the canonical path in UPATH/FNAMELEN.
; One cursor may exist. Pending directory packets reserve the shared UCI
; transport. CLOSE cancels only its own transaction and verifies restoration
; of the original CWD (1..255 bytes); uncertain cleanup retains ownership.
; EOF does not close the cursor. FRELEASE closes owned directories first.
N_UPATH         = $4e00          ; 256-byte path mailbox, bank 0, reserved
N_BROWSERPATH   = $4a00          ; ABI 1.5: persistent browser path, 1..255 raw bytes
N_USTATUS       = $4f00          ; last Ultimate status text, at most 31 bytes + NUL
N_DPAGE         = $3d97          ; zero-based directory page, bounded by geometry
N_DNEXT         = $3d98          ; next page ordinal, or $ff at directory end
N_DCOUNT        = $3d99          ; 0 or 8 records returned in N_BUFFER
; Directory records: 32 bytes; +0 type (0 deleted, 1 SEQ, 2 PRG, 3 USR,
; 4 REL, other values backend-specific), +1 flags ($80 closed/$40 locked),
; +2..17 exact PETSCII name padded with $a0, +18..19 blocks LE16.
; +20..31 are reserved. Page reads share the file owner/device/format/error
; mailbox and need one free stream slot. Uncertain cleanup retains its handle.
N_FNAME         = $3da0          ; 16 bytes
NFILES          = $3dc0          ; private: two 16-byte descriptors
; owner, device (IEC 8..30 / Ultimate context 1..2), mode, flags
; (EOF/failed/close-uncertain/known-size), generation LE24, sticky transfer error,
; position LE32, command slot+1 (0 for Ultimate), remaining bytes LE24.
; Ultimate retains the fourth remaining byte in its private resident state.
NFCMDS          = $3de0          ; private: two device bytes, two state bytes (0/1/2)

N_OK            = 0
N_BADARG        = 1
N_NOMEM         = 2
N_NOSLOT        = 3
N_BADHANDLE     = 4
N_WRONGOWNER    = 5
N_RANGE         = 6
N_REENTRANT     = 7
N_PLATFORM      = 8
N_CORRUPT       = 9
N_BADIMAGE      = $10            ; invalid manifest/load address/ABI
N_IOERROR       = $11            ; IEC or DOS failure (see DOSCODE/IOSTATUS)
N_SHORTIMAGE    = $12            ; EOF before declared length
N_LONGIMAGE     = $13            ; declared length reached without EOF
N_CHECKSUM      = $14            ; image CRC16 does not match
N_CHANNELS      = $15            ; reserved channels conflict / redirected console

N_APPBASE       = $6000          ; bank 0 application executable slot
N_APPLIMIT      = $c000          ; exclusive: keep native editor/KERNAL visible
N_APPOWNER      = 32             ; one foreground app in this initial lifecycle

; Private allocation tables. Apps must not write these or MMU registers.
N_LOWBASE       = $1300          ; resident kernel section, initialized before heap use
N_LOWLIMIT      = $1c00          ; exclusive; below the BASIC entry stub
N_RELOCBASE     = $5000          ; boot-only staging, reusable after relocation
N_SERVICEBASE   = $4000          ; resident Ultimate services and mailboxes
N_SERVICELIMIT  = $5000
NPAGES0         = $3800          ; page -> slot+1, 0 free, $ff reserved
NPAGES1         = $3900
NHANDLES        = $3c00          ; 32 records of eight bytes
; record: owner, bank, first page, page count, generation LE24, reserved
NSLOTS          = 32
N_FIRST0        = $50            ; bank 0 $5000..$feff: 175 pages
N_FIRST1        = $04            ; bank 1 $0400..$feff: 251 pages
; $ff00..$ffff holds MMU registers and native interrupt stubs/vectors.
; Bank-1 $0000..$03ff aliases the common area and cannot be allocated.
