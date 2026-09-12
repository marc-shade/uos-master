; Modal cartridge file selector, ABI 1. GETCAP 7 -> UFP_PICK.
; A=1 Open / 7 Save As (exclusive creation), X=DOS context 1 or 2.
; r0=optional default ASCII leaf for Save As (0 or NUL string below $6200).
; Caller code, document and return addresses must stay below $6200.
; Loads uos-picker from the current system IEC device without replacing the
; caller. Borrows $6200..$734f and $7359..$7fff; preserves SETREC.
; C=0/A=0: selected file is OPEN through UFS, with its directory borrowed
; until UFS_CLOSE. C=1: A is an error, $e9 cancel, $ea library load failure.
; Every call clobbers public r0..r15, private $50..$57, A/X/Y and NET scratch.
; D must be clear. Calls through PICK also replace the core LOAD filename.
; Not reentrant; never use from an IRQ, tick or transport callback.
UFP_PICK        = $4c80
UFP_RECOVER     = $4c83  ; restore pending CWD only once its owned file is closed
UFP_VERSION     = $4c86
UFP_RESULT      = $4c87
UFP_PENDING     = $4c88  ; 0 none, 1 borrowed, 2 restore failed (OPEN blocked)
UFP_CONTEXT     = $4c89
UFP_CWDLEN      = $4c8a  ; private saved CHANGE_DIR command length
UFP_PATHLEN     = $4c8c  ; returned absolute path length (word)
UFP_ACTIVE      = $4c8e  ; private: library running
UFP_MODE        = $4c8f  ; private requested OPEN mode
UFP_DEFAULT     = $4c90  ; private caller default pointer
UFP_CWD         = $4e00  ; private recovery command; survives app replacement
UFP_LIBRARY     = $6200
UFP_LEAF        = $7200  ; filename editor, max 127 bytes + NUL
UFP_DIRECTORY   = $7400 ; returned CWD, max 510 bytes + NUL
UFP_NAME        = $7600 ; returned complete selected name, max 511 + NUL
UFP_PATH        = $7800 ; returned absolute path, max 1021 + NUL
UFP_CANCELLED   = $e9
UFP_LOAD        = $ea
