draw_scene:
        jsr gfx_bind
        bcs scene_return
        lda #<scene_commands
        sta scene_read+1
        lda #>scene_commands
        sta scene_read+2
        lda #9
        sta scene_remaining
scene_next:
        ldx #7
scene_copy:
        jsr scene_read
        sta gfx_x0,x
        dex
        bpl scene_copy
        ldx #8
        jsr scene_read
        bne scene_colors
        inx
        jsr scene_read
        sta gfx_pen
        jsr gfx_rect
        jmp scene_result
scene_colors:
        inx
        jsr scene_read
        sta gfx_color
        jsr gfx_colors
scene_result:
        bcs scene_return
        clc
        lda scene_read+1
        adc #10
        sta scene_read+1
        bcc +
        inc scene_read+2
+       dec scene_remaining
        bne scene_next
        jmp draw_text_scene
scene_return:
        rts
scene_read:
        lda scene_commands,x
        rts
scene_remaining:.byte 0
scene_commands:
        .word $fffb,$fffd,325,203
        .byte 0,0
        .word 4,4,316,196
        .byte 0,1
        .word 12,12,308,188
        .byte 0,0
        .word 18,22,152,76
        .byte 0,1
        .word 140,60,330,150
        .byte 0,2
        .word 0,0,1,1
        .byte 0,1
        .word 319,199,320,200
        .byte 0,1
        .word 2,2,18,10
        .byte 1,$73
        .word 38,23,44,27
        .byte 1,$f0
