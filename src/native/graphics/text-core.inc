; Fixed 8x8 ASCII labels; bounded input lives inside the calling app.
; gfx_text_buffer[0..gfx_text_length) is at most 64 bytes. Nonprintable
; bytes draw '?'. Uses gfx_pen 0..3 and x0/y0; advances x0, saturating at
; 32767. Colors are unchanged. D/I preserved; other graphics args clobbered.
.weak
GFX_TEXT_STORAGE=0
.endweak
gfx_text:
        php
        cld
        jsr gfx_guard
        bcs gfx_text_failed
        lda gfx_bound
        bne +
        lda #N_BADHANDLE
        bne gfx_text_failed
+       lda gfx_pen
        cmp #4
        bcs gfx_text_badarg
        lda gfx_text_length
        cmp #65
        bcc +
gfx_text_badarg:
        lda #N_BADARG
gfx_text_failed:
        jmp gfx_finish
+       sta gfx_text_left
        lda #0
        sta gfx_text_index
        lda gfx_text_left
        beq gfx_text_done
gfx_text_next:
        ldx gfx_text_index
        lda gfx_text_buffer,x
        cmp #32
        bcc gfx_text_unknown
        cmp #127
        bcc gfx_text_code
gfx_text_unknown:
        lda #63
gfx_text_code:
        sec
        sbc #32
        ldx #0
        stx gfx_text_high
        asl
        rol gfx_text_high
        asl
        rol gfx_text_high
        asl
        rol gfx_text_high
        clc
        adc #<gfx_font
        sta gfx_text_load+1
        lda gfx_text_high
        adc #>gfx_font
        sta gfx_text_load+2
        ldx #7
gfx_text_load:
        lda gfx_font,x
        sta gfx_bits,x
        dex
        bpl gfx_text_load
        jsr gfx_glyph
        bcs gfx_text_failed
        clc
        lda gfx_x0
        adc #8
        sta gfx_x0
        lda gfx_x0+1
        adc #0
        bvs gfx_text_saturate
        sta gfx_x0+1
        jmp gfx_text_advance
gfx_text_saturate:
        lda #$ff
        sta gfx_x0
        lda #$7f
        sta gfx_x0+1
gfx_text_advance:
        inc gfx_text_index
        dec gfx_text_left
        bne gfx_text_next
gfx_text_done:
        lda #0
        jmp gfx_finish

gfx_text_length:.byte 0
.if GFX_TEXT_STORAGE
gfx_text_buffer=GFX_TEXT_STORAGE
.else
gfx_text_buffer:.fill 64,0
.endif
gfx_text_left:  .byte 0
gfx_text_index: .byte 0
gfx_text_high:  .byte 0
gfx_font:
        .binary "font8.bin"
gfx_text_end:
