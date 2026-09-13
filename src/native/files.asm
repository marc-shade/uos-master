; File navigator launched from the graphical desktop. GPL v3.
.include "api.inc"
* = N_APPBASE
FILES_PAGES = 93
b_image:
        .text "napp"
        .byte 1,1,10,<(files_module-b_image)
        .word files_module-b_image
        .byte FILES_PAGES,>(files_module-b_image)
        .word b_entry-b_image
        .word 0
        .text "files and apps",0
        .fill N_APPBASE+32-*,0
FD_EMBEDDED = 0
FD_RETURN_TO_DESKTOP = 1
B_COPY = 1
B_GUI = 1
PM_KEYS_OWNED = 1
PM_KEYS_EXTERNAL = 1
.include "file-browser.inc"
.include "files-copy.inc"
.include "files/presentation.inc"
.include "input/keys.inc"
fc_safe_character = b_safe_character
; The suite Files app has no document extents to retain. Its picker fits in
; the same owned app image, with four idle transfer buffers for cache scratch.
files_module:
        .text "nmod"
        .byte 1,1,10,0
        .word files_picker_end-files_module
        .word 0
        .word copy_picker.fd_run-files_module
        .word 0
copy_picker .block
FD_EMBEDDED = 1
B_COPY = 0
B_GUI = 0
FD_NAME_BUFFER = fc_name
FD_SCRATCH0 = fc_data
FD_SCRATCH1 = fc_data+512
FD_SCRATCH2 = fc_data+1024
FD_SCRATCH3 = fc_data+1536
FD_SAFE_CHARACTER = fc_safe_character
.include "file-dialog.inc"
.bend
files_picker_end:
        .cerror * > N_APPBASE+FILES_PAGES*256, "Files picker exceeds the module window"
fc_picker_active = fg_picker_active
fc_picker_get_key = copy_picker.b_get_key
fc_picker_cache = copy_picker.b_cache
fc_picker_cursor = copy_picker.bu_cursor
fc_picker_iec_handle = copy_picker.fd_iec_handle
cloop = b_loop
        .logical files_module
files_gui_module:
        .text "nmod"
        .byte 1,1,10,0
        .word files_gui_end-files_gui_module
        .word 0
        .word fg_gui_entry-files_gui_module
        .word 0
.include "files/gui.inc"
files_gui_end:
        .cerror * > N_APPBASE+FILES_PAGES*256, "Files graphics exceed the module window"
        .here
b_end = files_module
