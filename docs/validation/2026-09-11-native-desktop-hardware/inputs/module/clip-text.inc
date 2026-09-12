draw_clip_text:
        ldx #7
clip_text_bounds:
        lda clip_box,x
        sta gfx_x0,x
        dex
        bpl clip_text_bounds
        jsr gfx_set_clip
        bcs clip_text_return
        lda #28
        sta gfx_x0+0
        lda #0
        sta gfx_x0+1
        lda #104
        sta gfx_x0+2
        lda #0
        sta gfx_x0+3
        lda #3
        sta gfx_pen
        lda #16
        sta gfx_text_length
        ldx #15
clip_text_copy:
        lda clip_label,x
        sta gfx_text_buffer,x
        dex
        bpl clip_text_copy
        jmp gfx_text
clip_text_return:
        rts
clip_box: .sint 40,88,144,136
clip_label: .byte 87,105,110,100,111,119,32,99,108,105,112,32,116,101,115,116
