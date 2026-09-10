; A file field keeps focus after a picker returns, so the user can edit the
; complete returned name before Open confirmation or the exclusive Save As.
ed_browse:
        lda ed_mode
        sta fd_mode
        lda ed_device
        sta fd_device
        lda ed_format
        sta fd_format
        lda ed_field_len
        sta fd_length
        ; FD_NAME_BUFFER aliases this field; the picker commits it on success.
        jsr fd_run
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
        jsr b_safe_character
        jsr ed_chrout
        inc ed_safe_read+1
        bne ed_safe_read
        inc ed_safe_read+2
        jmp ed_safe_read
ed_safe_done:
        rts
ed_file_type: .byte 0
