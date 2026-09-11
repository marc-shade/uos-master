; A file field keeps focus after a picker returns, so the user can edit the
; complete returned name before Open confirmation or the exclusive Save As.
ed_browse:
        lda ed_picker_token
        ora ed_picker_token+1
        ora ed_picker_token+2
        bne ed_picker_ready
        lda N_MSTATE
        cmp #4
        bne +
        jsr N_MCLOSE           ; explicit retry; an uncertain IEC CLOSE stays retained
        bcs ed_picker_failed
+       lda #10
        sta N_FNAMELEN
        ldx #9
ed_picker_name_copy:
        lda ed_picker_name,x
        sta N_FNAME,x
        dex
        bpl ed_picker_name_copy
        jsr N_MLOAD
        bcs ed_picker_failed
        ldx #2
ed_picker_remember:
        lda N_MTOKEN,x
        sta ed_picker_token,x
        dex
        bpl ed_picker_remember
ed_picker_ready:
        ldx #2
ed_picker_select:
        lda ed_picker_token,x
        sta N_MTOKEN,x
        dex
        bpl ed_picker_select
        lda ed_mode
        sta fd_mode
        lda ed_device
        sta fd_device
        lda ed_format
        sta fd_format
        lda ed_field_len
        sta fd_length
        ; FD_NAME_BUFFER aliases this field; the picker commits it on success.
        jsr N_MCALL
        bcs ed_browse_failed
        lda fd_device
        sta ed_device
        lda fd_format
        sta ed_format
        lda fd_type
        sta ed_file_type
        lda fd_length
        sta ed_field_len
        lda #0
        sta N_UIKEY
        jsr ed_field_call
        bcs ed_input_error
        lda #0
        beq ed_browse_status
ed_browse_failed:
        cmp #0
        beq ed_browse_status
        cmp #N_NOMEM
        beq ed_browse_memory
        cmp #N_NOSLOT
        beq ed_browse_memory
        lda #9
        bne ed_browse_status
ed_picker_failed:
        lda #2
        bne ed_browse_status
ed_browse_memory:
        lda #3
ed_browse_status:
        sta ed_status
        ; The dialog has repainted both displays, but never touched document
        ; cursor/cache/viewport state. Redraw it without resetting those values.
        jsr ed_invalidate_pages
        jsr ed_show
        jmp cloop

; Directory names may contain raw bytes outside the console's printable
; range. Display dots for those bytes while retaining the exact OPEN target.
ed_safe_puts:
        sta ed_safe_read+1
        stx ed_safe_read+2
ed_safe_read:
        lda $ffff
        beq ed_safe_done
        jsr ed_safe_character
        jsr ed_chrout
        inc ed_safe_read+1
        bne ed_safe_read
        inc ed_safe_read+2
        jmp ed_safe_read
ed_safe_done:
        rts
ed_safe_character:
        cmp #$20
        bcc +
        cmp #$7f
        bcc ed_safe_done
+       lda #$2e
        rts
ed_file_type: .byte 0
ed_picker_name: .text "edpick.prg"
ed_picker_token: .fill 3,0
