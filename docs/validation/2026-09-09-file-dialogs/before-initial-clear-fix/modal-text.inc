; Compact dual-display text rows shared by modal apps. mt_line is PETSCII,
; at most 36 cells. A=row 0..16 -> VIC y16+10*row, VDC row2+row.
; Fixed eight-pixel cells keep editable text and caret positions aligned.
mt_text:
        pha
        ldy #0
mt_text_copy:
        lda (r9),y
        sta mt_line,y
        beq mt_text_end
        iny
        cpy #36
        bne mt_text_copy
        lda #0
        sta mt_line,y
mt_text_end:
        pla
mt_draw:
        sta mt_row
        asl
        sta mt_y
        asl
        asl
        adc mt_y
        adc #16
        sta mt_y
        ; Clear all ten scanlines, including descenders, without touching
        ; neighbouring rows or the bottom desktop clock.
        sec
        sbc #1
        sta mt_scan
        lda #10
        sta mt_left
mt_clear_scan:
        lda mt_scan
        and #7
        clc
        adc #16
        sta r0L
        ; Compute band*320 + $a000 + 16 + scanline using a small table.
        ldx mt_scan
        txa
        lsr
        lsr
        lsr
        tax
        lda mt_bandsL,x
        clc
        adc r0L
        sta r0L
        lda mt_bandsH,x
        adc #0
        sta r0H
        ldx #36
        ldy #0
mt_clear_cell:
        lda #0
        sta (r0),y
        clc
        lda r0L
        adc #8
        sta r0L
        bcc mt_clear_next
        inc r0H
mt_clear_next:
        dex
        bne mt_clear_cell
        inc mt_scan
        dec mt_left
        bne mt_clear_scan
        lda #0
        sta mt_cell
mt_cell_next:
        ldx mt_cell
        lda mt_line,x
        beq mt_vdc
        cmp #$20
        beq mt_cell_skip
        sta mt_glyph
        lda #0
        sta X1+1
        sta Y1+1
        lda mt_cell
        asl
        asl
        asl
        rol X1+1
        clc
        adc #16
        sta X1
        bcc mt_cell_y
        inc X1+1
mt_cell_y:
        lda mt_y
        sta Y1
        lda #<mt_glyph
        sta r9L
        lda #>mt_glyph
        sta r9H
        jsr GPUTS
mt_cell_skip:
        inc mt_cell
        jmp mt_cell_next
mt_vdc:
        lda mt_row
        clc
        adc #2
        jsr VDCLR
        lda #<mt_line
        sta r9L
        lda #>mt_line
        sta r9H
        lda mt_row
        clc
        adc #2
        ldx #0
        jmp VDTEXT
mt_clear:
        lda #0
        sta mt_line
        sta mt_whole
mt_clear_loop:
        lda mt_whole
        jsr mt_draw
        inc mt_whole
        lda mt_whole
        cmp #17
        bne mt_clear_loop
        lda #19
mt_clear_vdc_tail:
        pha
        jsr VDCLR
        pla
        clc
        adc #1
        cmp #24
        bne mt_clear_vdc_tail
        rts
mt_ascii:
        cmp #$20
        bcc mt_dot
        cmp #$7b
        bcs mt_dot
        cmp #$61
        bcc mt_upper
        and #$df
        rts
mt_upper:
        cmp #$41
        bcc mt_ascii_done
        cmp #$5b
        bcs mt_ascii_done
        ora #$80
mt_ascii_done:
        rts
mt_dot:
        lda #$2e
        rts
mt_key_ascii:
        cmp #$41
        bcc mt_key_done
        cmp #$5b
        bcs mt_key_upper
        ora #$20
        rts
mt_key_upper:
        cmp #$c1
        bcc mt_key_done
        cmp #$db
        bcs mt_key_done
        and #$7f
mt_key_done:
        rts
mt_bandsL: .for i in range(25)
        .byte <($a000+i*320)
        .endfor
mt_bandsH: .for i in range(25)
        .byte >($a000+i*320)
        .endfor
mt_row: .byte 0
mt_y: .byte 0
mt_scan: .byte 0
mt_left: .byte 0
mt_cell: .byte 0
mt_whole: .byte 0
mt_glyph: .byte 0,0
mt_line: .fill 37,0
