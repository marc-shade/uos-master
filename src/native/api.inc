; Native C128 ABI 1. This is separate from the C64-mode $0811 jump table.
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
N_LAUNCH        = $1c38          ; run a checked native PRG from IEC, then clean up
N_KEYIN         = $1c3b          ; native GETIN with shared key-event accounting
N_EXIT          = $1c3e          ; one-way app exit, A=app result; restores saved stack

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
N_DEVICE        = $3d21          ; launch IEC device, 8..30
N_NAMELEN       = $3d22          ; launch filename length, 1..16
N_APPSTATE      = $3d23          ; 0 idle, 1 loading, 2 running, 3 cleanup, 4 retained error
N_EXITCODE      = $3d24          ; last application's A on return/EXIT
N_DOSCODE       = $3d25          ; DOS error code (decimal), when available
N_IOSTATUS      = $3d26          ; last serial status byte
N_APPERROR      = $3d27          ; stable launch result, separate from heap ERROR
N_APPNAME       = $3d40          ; 16-byte filename, no wildcard/DOS syntax
N_APPHEADER     = $3d60          ; validated 32-byte native image manifest
N_BUFFER        = $3a00          ; 512 bytes, bank 0, reserved

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
NPAGES0         = $3800          ; page -> slot+1, 0 free, $ff reserved
NPAGES1         = $3900
NHANDLES        = $3c00          ; 32 records of eight bytes
; record: owner, bank, first page, page count, generation LE24, reserved
NSLOTS          = 32
N_FIRST0        = $40            ; bank 0 $4000..$feff: 191 pages
N_FIRST1        = $04            ; bank 1 $0400..$feff: 251 pages
; $ff00..$ffff holds MMU registers and native interrupt stubs/vectors.
; Bank-1 $0000..$03ff aliases the common area and cannot be allocated.
