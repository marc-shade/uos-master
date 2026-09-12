.include "api.inc"
* = 37070
module_image:
        .text "nmod"
        .byte 1,1,8,0
        .word module_end-module_image
        .word 0
        .word module_entry-module_image
        .word 0
module_entry:
        cld
        jsr draw_scene
        bcs +
        jsr N_VSHOW
+       rts
.include "scene.inc"
.include "text-scene.inc"
.include "graphics-core.inc"
.include "text-core.inc"
module_end:
.cerror module_end > $af00, "graphics module exceeds the editor window"
