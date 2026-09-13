; Native uOS Paint. Owned full-resolution image and undo history, GPL v3.
.include "api.inc"
PM_KEYS_OWNED=1               ; keep shared key ownership across the text picker
* = N_APPBASE
pa_image:
        .text "napp"
        .byte 1,1,10,0
        .word pa_end-pa_image
        .byte (pa_end-pa_image+255)/256,0
        .word pa_entry-pa_image
        .word 0
        .text "paint",0
        .fill N_APPBASE+32-*,0
pa_entry:
        cld
        jsr pd_init
        bcc +
        jmp N_EXIT
+       jsr pa_keys_install
        lda N_BROWSERDEV
        sta pf_device
        lda N_BROWSERFMT
        sta pf_format
        jsr pa_normal_controls
        jsr pa_view_open
        jsr pa_cursor
        jsr pa_console
cloop:
        lda #1
        sta N_READY
        jsr N_KEYIN
        bne pa_key_ready
        jsr pa_mouse
        jmp cloop
pa_key_ready:
        ldx #0
        stx N_READY
        jsr pa_key
        jmp cloop
.include "paint/document.inc"
.include "paint/line.inc"
.include "paint/file.inc"
.include "paint/view.inc"
.include "paint/renderer.inc"
.include "paint/input.inc"
.include "paint/dialog.inc"
.include "paint/console.inc"
pa_scene .block
.include "graphics/scene-rect.inc"
.include "graphics/scene-text.inc"
.include "paint/scene.inc"
.bend
pa_confirm_scene .block
.include "graphics/scene-rect.inc"
.include "graphics/scene-text.inc"
.include "paint/confirm-scene.inc"
.bend
pa_save_scene .block
.include "graphics/scene-rect.inc"
.include "graphics/scene-text.inc"
.include "paint/save-scene.inc"
.bend
.include "paint/buttons.inc"
.include "graphics/buttons.inc"
.include "graphics/graphics-core.inc"
.include "graphics/text-core.inc"
.include "input/pointer.inc"
paint_picker .block
FD_EMBEDDED=1
FD_GUI=1
FD_GUI_SHARED=1
FD_GUI_SURFACE=pa_handle
B_COPY=0
FD_DIRECT_PAGES=6
FD_NAME_BUFFER=pf_name
FD_SCRATCH0=pf_compare
FD_SCRATCH1=pa_scratch
FD_SCRATCH2=pa_scratch+512
FD_SCRATCH3=pa_scratch+512
FD_SAFE_CHARACTER=pa_safe_character
.include "file-dialog.inc"
.bend
pa_picker_active=paint_picker.fd_active
pa_picker_get_key=paint_picker.b_get_key
pa_scratch: .fill 1024,0
pa_end:
.cerror pa_end>N_APPLIMIT, "paint exceeds native app slot"
