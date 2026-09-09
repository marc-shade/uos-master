; A shared, modal binary viewer. File operations use only the public API above.
; 96 bytes/page, 12 rows of offset + eight hex bytes + ASCII; all offsets are
; 32-bit. Caller retains its directory, selected filename and cache unchanged.
view_file:
        cpx #1
        bcc view_bad_argument
        cpx #3
        bcs view_bad_argument
        lda UFS_MODE-1,x
        beq view_begin
        lda #UFS_BUSY
        sec
        rts
view_bad_argument:
        lda #UFS_BADARG
        sec
        rts
view_begin:
        stx view_target
        lda r0L
        sta view_name
        lda r0H
        sta view_name+1
        lda #0
        sta view_error
        sta view_held
        sta view_ready
        ldy #3
view_zero:
        sta view_page,y
        dey
        bpl view_zero
        lda #1
        jsr UFS_OPEN
        bcc view_read
        jmp view_failed
view_read:
        lda #0
        sta view_ready
        lda #<$7c00
        sta r0L
        lda #>$7c00
        sta r0H
        lda #96
        sta r1L
        lda #0
        sta r1H
        ldx view_target
        jsr UFS_READ
        bcs view_failed
        lda UFS_COUNT
        sta view_count
        lda UFS_EOF
        sta view_eof
        jmp view_paint
view_failed:
        sta view_error
        lda #0
        sta view_count
        lda #1
        sta view_eof
view_paint:
        lda #0
        sta view_ready
        jsr view_draw
view_loop:
        lda #1
        sta view_ready
        jsr OS_TICK
        jsr KEYIN
        bne view_key
        jsr READ_BUTTON
        bne view_released
        lda #1
        sta view_held
        jmp view_loop
view_released:
        lda view_held
        beq view_loop
        lda #0
        sta view_held
        jsr view_mouse
view_key:
        cmp #$1b
        beq view_exit
        and #$7f
        cmp #$61
        bcc view_normalized
        cmp #$7b
        bcs view_normalized
        and #$df
view_normalized:
        ldx view_error
        bne view_loop
        cmp #$4e
        beq view_next
        cmp #$42
        beq view_previous
        jmp view_loop
view_next:
        lda view_eof
        bne view_loop
        ldx #3
view_next_page:
        lda UFS_POS,x
        sta view_page,x
        dex
        bpl view_next_page
        jmp view_read
view_previous:
        lda view_page
        ora view_page+1
        ora view_page+2
        ora view_page+3
        beq view_loop
        sec
        lda view_page
        sbc #96
        sta r0L
        lda view_page+1
        sbc #0
        sta r0H
        lda view_page+2
        sbc #0
        sta r1L
        lda view_page+3
        sbc #0
        sta r1H
        ldx #3
view_seek_copy:
        lda r0,x
        sta view_page,x
        dex
        bpl view_seek_copy
        ldx view_target
        jsr UFS_SEEK
        bcc view_read_previous
        jmp view_failed
view_read_previous:
        jmp view_read
view_exit:
        lda #0
        sta view_ready
        ldx view_target
        jsr UFS_CLOSE
        bcc view_exit_result
        ldx view_error
        bne view_exit_result
        sta view_error
view_exit_result:
        lda view_error
        sta UFS_RESULT
        cmp #1                 ; C=0/A=0 normal return; original error otherwise
        rts

; Clear just the interior workspace. The desktop clock/header and browser's
; data remain owned by their original modules. The caller redraws its frame.
view_draw:
        lda #<$a150             ; row band 1, column 2 ($a000 + 320 + 16)
        sta view_clear
        lda #>$a150
        sta view_clear+1
        lda #22
        sta view_row
view_clear_band:
        lda view_clear
        sta r0L
        lda view_clear+1
        sta r0H
        lda #0
        sta r1L
        sta r1H
        lda #<288
        sta r2L
        lda #>288
        sta r2H
        jsr CLR_RECT
        clc
        lda view_clear
        adc #<320
        sta view_clear
        lda view_clear+1
        adc #>320
        sta view_clear+1
        dec view_row
        bne view_clear_band
        lda #2
        sta view_row
view_clear_vdc:
        lda view_row
        jsr VDCLR
        inc view_row
        lda view_row
        cmp #24
        bne view_clear_vdc
        lda #1
        jsr GFX_SETCOLOR
        lda #<view_title
        ldx #>view_title
        jsr view_text
        lda #14
        ldx #2
        jsr view_line
        jsr view_blank
        lda view_name
        sta r4L
        lda view_name+1
        sta r4H
        ldy #0
view_name_byte:
        lda (r4),y
        beq view_name_done
        jsr view_ascii
        sta view_buffer,y
        iny
        cpy #34
        bne view_name_byte
view_name_done:
        lda #26
        ldx #3
        jsr view_line
        ldx #3
view_offset_copy:
        lda view_page,x
        sta view_offset,x
        dex
        bpl view_offset_copy
        lda #0
        sta view_row
        sta view_byte
view_rows:
        jsr view_blank
        lda view_byte
        cmp view_count
        bcs view_row_draw
        ldy #0
        ldx #3
view_address:
        stx view_j
        lda view_offset,x
        jsr view_hex
        ldx view_j
        dex
        bpl view_address
        lda #$3a
        sta view_buffer+8
        lda #0
        sta view_j
        ldy #10
view_bytes:
        ldx view_byte
        cpx view_count
        bcs view_bytes_done
        lda $7c00,x
        jsr view_hex
        sty view_y
        ldx view_byte
        lda $7c00,x
        jsr view_ascii
        ldx view_j
        sta view_buffer+27,x
        ldy view_y
        inc view_byte
        inc view_j
        lda view_j
        cmp #8
        bne view_bytes
view_bytes_done:
        clc
        lda view_offset
        adc #8
        sta view_offset
        lda view_offset+1
        adc #0
        sta view_offset+1
        lda view_offset+2
        adc #0
        sta view_offset+2
        lda view_offset+3
        adc #0
        sta view_offset+3
view_row_draw:
        lda view_row
        asl
        sta view_y
        asl
        asl
        clc
        adc view_y
        adc #40
        pha
        lda view_row
        clc
        adc #6
        tax
        pla
        jsr view_line
        inc view_row
        lda view_row
        cmp #12
        beq view_rows_done
        jmp view_rows
view_rows_done:
        lda view_error
        beq view_size
        lda #<view_error_text
        ldx #>view_error_text
        jsr view_text
        ldy #7
        lda view_error
        jsr view_hex
        jmp view_footer
view_size:
        lda #<view_size_text
        ldx #>view_size_text
        jsr view_text
        ldy #5
        ldx #3
view_size_digits:
        stx view_j
        lda UFS_SIZE,x
        jsr view_hex
        ldx view_j
        dex
        bpl view_size_digits
        lda view_eof
        beq view_footer
        lda #$c5
        sta view_buffer+25
        lda #$ce
        sta view_buffer+26
        lda #$c4
        sta view_buffer+27
view_footer:
        lda #162
        ldx #21
        jsr view_line
        lda #<view_buttons
        ldx #>view_buttons
        jsr view_text
        lda #176
        ldx #22
        jmp view_line

view_blank:
        lda #$20
        ldx #34
view_blank_byte:
        sta view_buffer,x
        dex
        bpl view_blank_byte
        lda #0
        sta view_buffer+35
        rts
view_text:
        sta r4L
        stx r4H
        jsr view_blank
        ldy #0
view_text_byte:
        lda (r4),y
        beq view_text_done
        sta view_buffer,y
        iny
        bne view_text_byte
view_text_done:
        rts
view_line:
        stx view_vrow
        sta Y1
        lda #0
        sta Y1+1
        sta X1+1
        lda #24
        sta X1
        jsr view_pointer
        jsr GPUTS
        jsr view_pointer
        lda view_vrow
        ldx #0
        jmp VDTEXT
view_pointer:
        lda #<view_buffer
        sta r9L
        lda #>view_buffer
        sta r9H
        rts
view_hex:
        pha
        lsr
        lsr
        lsr
        lsr
        tax
        lda view_digits,x
        sta view_buffer,y
        iny
        pla
        and #15
        tax
        lda view_digits,x
        sta view_buffer,y
        iny
        rts
view_ascii:
        cmp #$20
        bcc view_dot
        cmp #$7b
        bcs view_dot
        cmp #$61
        bcc view_upper
        and #$df
        rts
view_upper:
        cmp #$41
        bcc view_ascii_done
        cmp #$5b
        bcs view_ascii_done
        ora #$80
view_ascii_done:
        rts
view_dot:
        lda #$2e
        rts

view_mouse:
        php
        sei
        lda $d010
        and #1
        sta view_mx+1
        sec
        lda $d000
        sbc #24
        sta view_mx
        lda view_mx+1
        sbc #0
        sta view_mx+1
        lda $d001
        sec
        sbc #50
        plp
        cmp #176
        bcc view_no_mouse
        cmp #186
        bcs view_no_mouse
        lda view_mx+1
        beq view_low_x
        cmp #1
        bne view_no_mouse
        lda view_mx
        cmp #48
        bcs view_no_mouse
        bcc view_mouse_exit
view_low_x:
        lda view_mx
        cmp #24
        bcc view_no_mouse
        cmp #112
        bcc view_mouse_previous
        cmp #120
        bcc view_no_mouse
        cmp #208
        bcc view_mouse_next
        cmp #216
        bcc view_no_mouse
view_mouse_exit:
        lda #$1b
        rts
view_mouse_previous:
        lda #$42
        rts
view_mouse_next:
        lda #$4e
        rts
view_no_mouse:
        lda #0
        rts

view_title:      .text "File bytes  (hex / ASCII)",0
view_buttons:    .text "B prev      N next      Esc files",0
view_error_text: .text "Error $00 - Esc returns to files",0
view_size_text:  .text "size 00000000h bytes",0
view_digits:     .text "0123456789abcdef"
view_buffer:     .fill 36, 0
view_target:     .byte 0
view_name:       .word 0
view_error:      .byte 0
view_held:       .byte 0
view_ready:      .byte 0
view_count:      .byte 0
view_eof:        .byte 0
view_page:       .fill 4, 0
view_offset:     .fill 4, 0
view_clear:      .word 0
view_row:        .byte 0
view_byte:       .byte 0
view_j:          .byte 0
view_y:          .byte 0
view_vrow:       .byte 0
view_mx:         .word 0
view_end:
