; Owned hires surface primitives, GPL v3. Foreground calls only.
; BIND takes N_OWNER/N_HANDLE and validates a 9216-byte logical surface.
; RECT uses signed LE16 x0,y0,x1,y1 half-open pixel bounds; pen 0/1/2
; clears/sets/XORs. COLORS uses the same bounds in 40x25 character cells.
; Both clip to the surface; empty/inverted rectangles perform no transfer.
; GLYPH draws gfx_bits[8] at signed gfx_x0/y0. Pen 3 replaces all clipped
; glyph pixels; pens 0/1/2 change only ink pixels. It sets x1/y1 internally.
; A/carry are the result; D/I preserved. BUFFER and heap arguments clobbered.
gfx_bind:
        php
        cld
        jsr gfx_guard
        bcs gfx_finish
        lda #0
        sta gfx_bound
        lda N_OWNER
        sta gfx_owner
        ldx #3
gfx_bind_handle:
        lda N_HANDLE,x
        sta gfx_handle,x
        dex
        bpl gfx_bind_handle
        lda #$ff
        sta N_OFFSET
        lda #$23
        sta N_OFFSET+1
        lda #1
        sta N_COUNT
        lda #0
        sta N_COUNT+1
        jsr N_READ
        bcs gfx_finish
        lda #1
        sta gfx_bound
        lda #0
gfx_finish:
        sta gfx_error
        plp
        lda gfx_error
        beq gfx_success
        sec
        rts
gfx_success:
        clc
        rts
gfx_guard:
        lda N_BUSY
        ora N_FBUSY
        ora N_UIBUSY
        beq gfx_success
        lda #N_REENTRANT
        sec
        rts

gfx_rect:
        php
        cld
        lda #0
        beq gfx_begin
gfx_colors:
        php
        cld
        lda #1
        bne gfx_begin
gfx_glyph:
        php
        cld
        jsr gfx_guard
        bcs gfx_glyph_failed
        lda gfx_bound
        bne +
        lda #N_BADHANDLE
        bne gfx_glyph_failed
+       lda gfx_pen
        cmp #4
        bcc +
        lda #N_BADARG
gfx_glyph_failed:
        jmp gfx_finish
+       ; Reject fully invisible origins before adding eight. Signed
        ; extreme coordinates must never wrap into the visible surface.
        ldx #0
gfx_glyph_origin:
        lda gfx_x0+1,x
        bmi gfx_glyph_negative
        cmp gfx_glyph_bounds+1,x
        bcc gfx_glyph_add
        bne gfx_glyph_empty
        lda gfx_x0,x
        cmp gfx_glyph_bounds,x
        bcs gfx_glyph_empty
        bcc gfx_glyph_add
gfx_glyph_negative:
        cmp #$ff
        bne gfx_glyph_empty
        lda gfx_x0,x
        cmp #$f9
        bcc gfx_glyph_empty
gfx_glyph_add:
        clc
        lda gfx_x0,x
        adc #8
        sta gfx_x1,x
        lda gfx_x0+1,x
        adc #0
        sta gfx_x1+1,x
        inx
        inx
        cpx #4
        bne gfx_glyph_origin
        lda #2
        bne gfx_begin
gfx_glyph_empty:
        lda #0
        jmp gfx_finish
gfx_begin:
        sta gfx_operation
        jsr gfx_guard
        bcs gfx_finish
        lda gfx_bound
        bne +
        lda #N_BADHANDLE
        bne gfx_finish
+       lda gfx_operation
        cmp #1
        beq gfx_color_limits
        cmp #2
        beq gfx_pixel_limits
        lda gfx_pen
        cmp #3
        bcc +
        lda #N_BADARG
        bne gfx_finish
+
gfx_pixel_limits:
        lda #64
        sta gfx_limits
        lda #1
        sta gfx_limits+1
        lda #200
        bne gfx_limits_y
gfx_color_limits:
        lda #40
        sta gfx_limits
        lda #0
        sta gfx_limits+1
        lda #25
gfx_limits_y:
        sta gfx_limits+2
        lda #0
        sta gfx_limits+3
        ldx #0
gfx_clip_next:
        txa
        and #2
        tay
        lda gfx_x0+1,x
        bmi gfx_clip_zero
        cmp gfx_limits+1,y
        bcc gfx_clip_copy
        bne gfx_clip_limit
        lda gfx_x0,x
        cmp gfx_limits,y
        bcc gfx_clip_copy
gfx_clip_limit:
        lda gfx_limits,y
        sta gfx_clipped,x
        lda gfx_limits+1,y
        bpl gfx_clip_high
gfx_clip_zero:
        lda #0
        sta gfx_clipped,x
        beq gfx_clip_high
gfx_clip_copy:
        lda gfx_x0,x
        sta gfx_clipped,x
        lda gfx_x0+1,x
gfx_clip_high:
        sta gfx_clipped+1,x
        inx
        inx
        cpx #8
        bne gfx_clip_next
        lda gfx_clipped+1
        cmp gfx_clipped+5
        bcc gfx_nonempty_x
        bne gfx_empty
        lda gfx_clipped
        cmp gfx_clipped+4
        bcs gfx_empty
gfx_nonempty_x:
        lda gfx_clipped+2
        cmp gfx_clipped+6
        bcs gfx_empty
        sta gfx_y
        lda gfx_operation
        cmp #1
        beq gfx_color_rows
        jmp gfx_bitmap_setup
gfx_empty:
        lda #0
        jmp gfx_finish

gfx_color_rows:
        ; y*40 + x + 8192; both coordinates have already been clipped.
        lda #0
        sta gfx_offset
        lda #$20
        sta gfx_offset+1
        ldx gfx_y
        beq gfx_color_x
gfx_color_multiply:
        clc
        lda gfx_offset
        adc #40
        sta gfx_offset
        bcc +
        inc gfx_offset+1
+       dex
        bne gfx_color_multiply
gfx_color_x:
        clc
        lda gfx_offset
        adc gfx_clipped
        sta gfx_offset
        bcc +
        inc gfx_offset+1
+       sec
        lda gfx_clipped+4
        sbc gfx_clipped
        sta gfx_span
        lda #0
        sta gfx_span+1
        jsr gfx_select
        lda gfx_color
        sta N_VALUE
        jsr N_FILL
        bcs gfx_failed
        inc gfx_y
        lda gfx_y
        cmp gfx_clipped+6
        bne gfx_color_rows
        beq gfx_empty
gfx_failed:
        jmp gfx_finish

gfx_bitmap_setup:
        lda gfx_clipped
        and #7
        tax
        lda gfx_left_masks,x
        sta gfx_left
        lda gfx_clipped+4
        and #7
        tax
        lda gfx_right_masks,x
        sta gfx_right
        sec
        lda gfx_clipped+4
        sbc #1
        sta gfx_span
        lda gfx_clipped+5
        sbc #0
        sta gfx_span+1
        lda gfx_span
        and #$f8
        sta gfx_span
        lda gfx_clipped
        and #$f8
        sta gfx_xbyte
        sec
        lda gfx_span
        sbc gfx_xbyte
        sta gfx_span
        lda gfx_span+1
        sbc gfx_clipped+1
        sta gfx_span+1
        ; byte-column count is span/8+1; span itself then includes the
        ; final addressed byte. The longest transfer is 313 bytes.
        lda gfx_span+1
        lsr
        lda gfx_span
        ror
        lsr
        lsr
        clc
        adc #1
        sta gfx_columns
        inc gfx_span
gfx_bitmap_row:
        lda gfx_y
        and #$f8
        lsr
        lsr
        tay
        clc
        lda gfx_rows,y
        adc gfx_xbyte
        sta gfx_offset
        lda gfx_rows+1,y
        adc gfx_clipped+1
        sta gfx_offset+1
        lda gfx_y
        and #7
        clc
        adc gfx_offset
        sta gfx_offset
        bcc +
        inc gfx_offset+1
+       jsr gfx_select
        jsr N_READ
        bcs gfx_failed
        lda gfx_operation
        cmp #2
        bne gfx_bitmap_loaded
        jsr gfx_glyph_row
gfx_bitmap_loaded:
        lda #>N_BUFFER
        sta gfx_load+2
        sta gfx_store+2
        lda gfx_columns
        sta gfx_remaining
        ldx #0
gfx_column:
        lda #$ff
        cpx #0
        bne gfx_mask_last
        ldy gfx_remaining
        cpy gfx_columns
        bne gfx_mask_last
        lda gfx_left
gfx_mask_last:
        ldy gfx_remaining
        cpy #1
        bne +
        and gfx_right
+       sta gfx_mask
        sta gfx_cover
        lda gfx_operation
        cmp #2
        bne gfx_load
        lda gfx_remaining
        cmp gfx_columns
        beq gfx_glyph_first
        lda gfx_second
        jmp gfx_glyph_ink
gfx_glyph_first:
        lda gfx_first
gfx_glyph_ink:
        and gfx_mask
        sta gfx_mask
gfx_load:
        lda N_BUFFER,x
        sta gfx_old
        lda gfx_pen
        beq gfx_clear
        cmp #1
        beq gfx_set
        cmp #3
        beq gfx_copy
        lda gfx_old
        eor gfx_mask
        jmp gfx_store
gfx_clear:
        lda gfx_mask
        eor #$ff
        and gfx_old
        jmp gfx_store
gfx_set:
        lda gfx_old
        ora gfx_mask
        jmp gfx_store
gfx_copy:
        lda gfx_cover
        eor #$ff
        and gfx_old
        ora gfx_mask
gfx_store:
        sta N_BUFFER,x
        dec gfx_remaining
        beq gfx_write_row
        txa
        clc
        adc #8
        tax
        bcc gfx_column
        inc gfx_load+2
        inc gfx_store+2
        bne gfx_column
gfx_write_row:
        jsr gfx_select
        jsr N_WRITE
        bcs gfx_failed
        inc gfx_y
        lda gfx_y
        cmp gfx_clipped+6
        bne gfx_bitmap_row
        jmp gfx_empty

gfx_glyph_row:
        sec
        lda gfx_y
        sbc gfx_y0
        tay
        lda gfx_bits,y
        sta gfx_first
        lda #0
        sta gfx_second
        lda gfx_x0
        and #7
        tay
        beq gfx_glyph_shifted
gfx_glyph_shift:
        lsr gfx_first
        ror gfx_second
        dey
        bne gfx_glyph_shift
gfx_glyph_shifted:
        lda gfx_x0+1
        bpl +
        lda gfx_second
        sta gfx_first
+       rts

gfx_select:
        lda gfx_owner
        sta N_OWNER
        ldx #3
gfx_restore_handle:
        lda gfx_handle,x
        sta N_HANDLE,x
        dex
        bpl gfx_restore_handle
        lda gfx_offset
        sta N_OFFSET
        lda gfx_offset+1
        sta N_OFFSET+1
        lda gfx_span
        sta N_COUNT
        lda gfx_span+1
        sta N_COUNT+1
        rts

gfx_x0:         .word 0
gfx_y0:         .word 0
gfx_x1:         .word 0
gfx_y1:         .word 0
gfx_pen:        .byte 1
gfx_color:      .byte $e6
gfx_error:      .byte 0
gfx_bound:      .byte 0
gfx_owner:      .byte 0
gfx_handle:     .fill 4,0
gfx_limits:     .fill 4,0
gfx_clipped:    .fill 8,0
gfx_operation:  .byte 0
gfx_y:          .byte 0
gfx_offset:     .word 0
gfx_span:       .word 0
gfx_xbyte:      .byte 0
gfx_columns:    .byte 0
gfx_remaining:  .byte 0
gfx_left:       .byte 0
gfx_right:      .byte 0
gfx_mask:       .byte 0
gfx_old:        .byte 0
gfx_cover:      .byte 0
gfx_first:      .byte 0
gfx_second:     .byte 0
gfx_bits:       .fill 8,0
gfx_glyph_bounds:.word 320,200
gfx_left_masks: .byte $ff,$7f,$3f,$1f,$0f,$07,$03,$01
gfx_right_masks:.byte $ff,$80,$c0,$e0,$f0,$f8,$fc,$fe
gfx_rows:
        .word $0000,$0140,$0280,$03c0,$0500,$0640,$0780,$08c0
        .word $0a00,$0b40,$0c80,$0dc0,$0f00,$1040,$1180,$12c0
        .word $1400,$1540,$1680,$17c0,$1900,$1a40,$1b80,$1cc0,$1e00
gfx_end:
