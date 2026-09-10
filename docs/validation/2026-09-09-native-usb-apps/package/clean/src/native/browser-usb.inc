; Checked application launch by absolute Ultimate path. This field preserves
; the IEC browser's cache/selection; directory navigation is a separate service.
b_usb_begin:
        lda #2
        sta b_prompt
        lda #0
        sta b_usb_error
        jmp b_usb_refresh
b_usb_key:
        cmp #27
        beq b_usb_cancel
        cmp #13
        beq b_usb_enter
        cmp #9
        beq b_usb_context
        cmp #21
        beq b_usb_clear_field
        cmp #20
        beq b_usb_delete
        cmp #32
        bcc cloop
        cmp #127
        bcs cloop
        ldx b_usb_length
        cpx #255
        beq cloop
        sta b_usb_path,x
        inc b_usb_length
        jmp b_usb_changed
b_usb_delete:
        lda b_usb_length
        beq cloop
        dec b_usb_length
        jmp b_usb_changed
b_usb_context:
        lda b_usb_device
        eor #3
        sta b_usb_device
        jmp b_usb_changed
b_usb_clear_field:
        lda #0
        sta b_usb_length
b_usb_changed:
        lda #0
        sta b_usb_error
b_usb_refresh:
        jsr b_usb_draw
        jmp cloop
b_usb_cancel:
        lda #0
        sta b_prompt
        beq b_usb_refresh
b_usb_enter:
        lda b_usb_length
        beq b_usb_invalid
        lda b_usb_path
        cmp #$2f
        beq b_usb_launch
b_usb_invalid:
        lda #1
        sta b_usb_error
        bne b_usb_refresh
b_usb_launch:
        lda b_usb_length
        sta N_NAMELEN
        lda b_usb_device
        sta N_DEVICE
        lda #3
        sta N_APPFORMAT
        ldx #0
b_usb_copy:
        lda b_usb_path,x
        sta N_UPATH,x
        inx
        cpx b_usb_length
        bne b_usb_copy
        jmp N_REPLACE

; Only rows 20/21 change while this field is active. Each row leaves its last
; column blank, avoiding KERNAL linked-line wrapping on either display.
b_usb_draw:
        lda #0
        sta b_screen
b_usb_screen:
        lda $d7
        rol
        lda #0
        rol
        cmp b_screen
        beq +
        jsr $ff5f
+       lda #39
        ldx b_screen
        beq +
        lda #79
+       sta b_usb_width
        lda #20
        sta b_usb_row
b_usb_clear_row:
        ldx b_usb_row
        ldy #0
        clc
        jsr $fff0
        lda b_usb_width
        sta b_usb_blank
b_usb_clear:
        lda #32
        jsr b_usb_chrout
        dec b_usb_blank
        bne b_usb_clear
        inc b_usb_row
        lda b_usb_row
        cmp #22
        bne b_usb_clear_row
        lda b_prompt
        beq b_usb_screen_done
        ldx #20
        ldy #0
        clc
        jsr $fff0
        lda #<b_usb_label
        ldx #>b_usb_label
        jsr b_puts
        lda b_usb_device
        ora #$30
        jsr b_usb_chrout
        lda #$3a
        jsr b_usb_chrout
        lda #32
        jsr b_usb_chrout
        lda #0
        sta b_usb_at
        lda b_usb_width
        sec
        sbc #7                 ; 32 or 72 path characters
        sta b_usb_limit
        lda b_usb_length
        sec
        sbc b_usb_limit
        bcc b_usb_text
        beq b_usb_text
        clc
        adc #1                 ; leave one character for the leading '<'
        sta b_usb_at
        lda #$3c
        jsr b_usb_chrout
b_usb_text:
        ldx b_usb_at
        cpx b_usb_length
        beq b_usb_controls
        lda b_usb_path,x
        jsr b_usb_chrout
        inc b_usb_at
        bne b_usb_text
b_usb_controls:
        ldx #21
        ldy #0
        clc
        jsr $fff0
        lda #<b_usb_help
        ldx #>b_usb_help
        ldy b_usb_error
        beq +
        lda #<b_usb_bad_path
        ldx #>b_usb_bad_path
+       jsr b_puts
b_usb_screen_done:
        inc b_screen
        lda b_screen
        cmp #2
        bne b_usb_screen
        rts
b_usb_chrout:
        pha
        lda #0
        sta $f4                ; filenames cannot leave ROM quote mode active
        pla
        jmp $ffd2

b_usb_label: .text "usb",0
b_usb_help: .text "enter run tab dos ctrl-u clr esc",0
b_usb_bad_path: .text "absolute path required",0
b_usb_length: .byte 6
b_usb_device: .byte 1
b_usb_error: .byte 0
b_usb_width: .byte 0
b_usb_row: .byte 0
b_usb_blank: .byte 0
b_usb_at: .byte 0
b_usb_limit: .byte 0
b_usb_path: .byte $2f,$55,$73,$62,$30,$2f
        .fill 250,0
