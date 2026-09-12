; Private browser/copy overlay handoff. Both modules enter by one-way jump.
; The app loader leaves these bytes and the browser's CWD/path intact.
COPY_SOURCE = $7c00             ; full selected raw basename, 511 + NUL
COPY_PATH = $7100               ; browser's full current path, 510 + NUL
COPY_HANDOFF = $7e10            ; 'UC', version 1, direction, page, row, device
COPY_DIRECTION = COPY_HANDOFF+3 ; 1 -> copy; 2 -> browser; 0 -> consumed
COPY_BASE = COPY_HANDOFF+4      ; 16-bit directory ordinal
COPY_SELECTED = COPY_HANDOFF+6
COPY_SYSDEV = COPY_HANDOFF+7
