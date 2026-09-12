; Shared Ultimate file service ABI, version 1. GETCAP id 6 -> UFS_OPEN.
; X = DOS context 1 or 2. D must be clear. Synchronous, not reentrant.
; C=0/A=0 success; C=1/A=error. UFS_RESULT retains A after an acquired call.
; Public r0..r15, A/X/Y and NET_* scratch may change. Never call from an IRQ
; or a NET_STREAM callback. The caller owns the DOS context while a file is
; open; do not issue raw file commands to it. Paths/case/bytes are unchanged.
UFS_OPEN        = $4100  ; r0 -> NUL name (1..893 bytes), A=1 read / 7 create new read-write
                        ; creation requires every slash/backslash component <=127 bytes
UFS_CLOSE       = $4103  ; closes only a service-owned (including uncertain) handle
UFS_READ        = $4106  ; r0 -> app buffer, r1=1..512; COUNT actual, EOF at known size
UFS_WRITE       = $4109  ; r0 -> app bytes, r1=1..512; read-back verification before success
UFS_SEEK        = $410c  ; r0/r1 = 32-bit LE offset, within known file size
UFS_TELL        = $410f  ; copy owned handle's tracked SIZE/POS to public result
UFS_CLOSEALL    = $4112  ; release owned contexts; first failure returned, failed owner retained
UFS_VERSION     = $4115  ; byte = 1
UFS_RESULT      = $4116
UFS_COUNT       = $4117  ; word; caller must discard buffer/count when C=1
UFS_SIZE        = $4119  ; 32-bit LE; size at open or after verified writes
UFS_POS         = $411d  ; 32-bit LE; tracked position, valid only after success
UFS_EOF         = $4121  ; byte; successful READ reached known end (also set by TELL/SEEK)
UFS_MODE        = $4122  ; two bytes: 0=unowned, 1=read, 7=create read-write, $ff=close required
UFS_STATUS      = $4124  ; 32-byte NUL-terminated copy of last firmware status for this call
UFS_COMMAND     = $8080  ; 896 private bytes, through $83ff; sprites use only $8000..$807f
UFS_VIEW        = $4800  ; r0 -> filename, X=context; modal hex/ASCII viewer, Esc returns
                        ; borrows $7c00..$7c5f, owns VIC interior + VDC rows 2..23
                        ; caller repaints on return; preserves directory/name caches

UFS_BADARG      = $e0
UFS_NOTOPEN     = $e1
UFS_BUSY        = $e2    ; context owned, foreign file open, or nested call
UFS_READONLY    = $e3
UFS_PROTOCOL    = $e4
UFS_SHORT      = $e5    ; fewer bytes than known size/request says must be available
UFS_VERIFY     = $e6    ; write read-back differs
UFS_RANGE      = $e7    ; seek past known end / position overflow
UFS_UNCERTAIN  = $e8    ; retry CLOSE; never continue from an uncertain stream position
; Other errors: firmware 1..99; transport $fc..$ff. No error triggers replay
; of OPEN/WRITE/SEEK. Success is not a power-loss durability guarantee.
