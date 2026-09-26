; Shared AES service constants (docs/GEM-LAYER-DESIGN.md). The AES version is
; independent of the kernel ABI; apps check AE_MAJOR and their required minor.
N_AESOWNER = 30                ; persistent AES code and data; survives app exit
N_ACCOWNER = 29                ; desk accessory slot (reserved for a later step)
AE_BASE = $8800                ; 56 pages to $bfff; VDSVC ($6000, 39 pages) ends at $86ff
AE_LIMIT = $c000
AE_DATA = $5000                ; owner-30 RAM tables, reserved on first attach
AE_DATA_PAGES = 16
AE_MAJOR = 1
AE_MINOR = 4
AE_CAP_ALERT = 1              ; capability bit 0: form_alert (minor 1)
AE_CAP_EVENT = 2              ; capability bit 1: evnt_multi/appl_write (minor 2)
AE_CAP_MENU = 4               ; capability bit 2: menu bar (minor 3)
AE_CAP_WINDOW = 8             ; capability bit 3: windows (minor 4)
AE_OP_ATTACH = 0                  ; N_BUFFER[0..3] = app cookie -> version/status
AE_OP_STATUS = 1                  ; version/status without registering an attach
AE_OP_ALERT = 2                ; surface(4), default, "[i][lines][buttons]"
AE_OP_STEP = 3                 ; key, x(word), y, buttons -> chosen, focus, rows(4)
AE_OP_EVENT = 4                ; one input sample against an event mask
AE_OP_POST = 5                 ; queue an 8-byte message
AE_OP_MENU = 6                 ; surface(4), "Title:item|item^K;..." (empty removes)
AE_OP_MENU_SET = 7             ; title, item, flags (1 checked, 2 disabled)
AE_OP_WINDOW = 8               ; N_BUFFER[0] sub-op: create/open/close/delete/set/get/find/fill/surface
AE_OP_SHUTDOWN = 9             ; discard overlays, free the data segment (before unload)
AE_OP_COUNT = 10
