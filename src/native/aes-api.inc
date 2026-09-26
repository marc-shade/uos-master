; Shared AES service constants (docs/GEM-LAYER-DESIGN.md). The AES version is
; independent of the kernel ABI; apps check AE_MAJOR and their required minor.
N_AESOWNER = 30                ; persistent AES code and data; survives app exit
N_ACCOWNER = 29                ; desk accessory slot (reserved for a later step)
AE_BASE = $9000
AE_LIMIT = $c000
AE_MAJOR = 1
AE_MINOR = 1
AE_CAP_ALERT = 1              ; capability bit 0: form_alert (minor 1)
AE_OP_ATTACH = 0                  ; N_BUFFER[0..3] = app cookie -> version/status
AE_OP_STATUS = 1                  ; version/status without registering an attach
AE_OP_ALERT = 2                ; surface(4), default, "[i][lines][buttons]"
AE_OP_STEP = 3                 ; key, x(word), y, buttons -> chosen, focus, rows(4)
AE_OP_COUNT = 4
