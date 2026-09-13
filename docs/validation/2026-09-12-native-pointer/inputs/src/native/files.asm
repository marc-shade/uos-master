; File navigator launched from the graphical desktop. GPL v3.
.include "api.inc"
* = N_APPBASE
b_image:
        .text "napp"
        .byte 1,1,8,0
        .word b_end-b_image
        .byte (b_end-b_image+255)/256,0
        .word b_entry-b_image
        .word 0
        .text "files and apps",0
        .fill N_APPBASE+32-*,0
FD_EMBEDDED = 0
FD_RETURN_TO_DESKTOP = 1
B_COPY = 1
.include "file-browser.inc"
.include "files-copy.inc"
fc_safe_character = b_safe_character
; The suite Files app has no document extents to retain. Its picker fits in
; the same owned app image, with four idle transfer buffers for cache scratch.
copy_picker .block
FD_EMBEDDED = 1
B_COPY = 0
FD_NAME_BUFFER = fc_name
FD_SCRATCH0 = fc_data
FD_SCRATCH1 = fc_data+512
FD_SCRATCH2 = fc_data+1024
FD_SCRATCH3 = fc_data+1536
FD_SAFE_CHARACTER = fc_safe_character
.include "file-dialog.inc"
.bend
fc_picker_active = copy_picker.fd_active
fc_picker_get_key = copy_picker.b_get_key
fc_picker_cache = copy_picker.b_cache
fc_picker_cursor = copy_picker.bu_cursor
fc_picker_iec_handle = copy_picker.fd_iec_handle
cloop = b_loop
b_end:
.cerror * > N_APPLIMIT, "files exceeds the native app window"
