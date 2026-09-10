; Reusable foreground file picker, sharing navigation with Files and Apps.
; Include with FD_EMBEDDED=1 in an ABI 1.5 app; call fd_run with interrupts on.
; Inputs: fd_mode=1 Open/2 Save As, fd_device/format and fd_name/length.
; C=0/A=0 returns a candidate in those fields. No file is opened or written.
; C=1/A=0 cancels; C=1/A=error fails. Input fields survive either outcome.
; Caller code, document allocations and streams remain owned by the caller.
; Desktop browser preferences are borrowed only while the picker has focus.
fd_run:
        lda fd_active
        beq +
        lda #N_REENTRANT
        sec
        rts
+       php
        tsx
        stx fd_sp
        cld
        lda #1
        sta fd_active
        lda #0
        sta N_READY
        sta fd_error
        sta fd_result
        ldx #11
fd_save_preferences:
        lda N_BROWSERDEV,x
        sta fd_preferences,x
        dex
        bpl fd_save_preferences
        ldx #0
fd_save_paths:
        lda N_BROWSERPATH,x
        sta fd_desktop_path,x
        lda N_BROWSERNAME,x
        sta fd_desktop_name,x
        inx
        bne fd_save_paths
        lda N_CURRENT
        beq fd_bad_argument
        sta b_owner
        lda fd_mode
        beq fd_bad_argument
        cmp #3
        bcs fd_bad_argument
        lda fd_format
        cmp #4
        bcs fd_bad_argument
        sta N_BROWSERFMT
        cmp #3
        beq fd_check_dos
        lda fd_device
        cmp #8
        bcc fd_bad_argument
        cmp #31
        bcs fd_bad_argument
        bcc fd_device_valid
fd_check_dos:
        lda fd_device
        beq fd_bad_argument
        cmp #3
        bcs fd_bad_argument
        sta b_usb_device
fd_device_valid:
        sta N_BROWSERDEV
        jsr fd_close_cursors
        bcs fd_failure
        lda N_BOOTDEVICE
        sta bu_iec_device
        lda fd_format
        cmp #3
        beq +
        lda fd_device
        sta bu_iec_device
+       lda #0
        sta b_prompt
        sta b_total
        sta b_total+1
        sta b_selected
        sta b_selected+1
        sta b_busy
        sta b_error
        sta b_launch_error
        sta bu_count
        sta bu_row
        sta bu_side
        sta bu_more
        sta bu_pending_key
        sta N_BROWSERERROR
        sta N_BROWSERNAME_LEN
        ldx #3
fd_zero_position:
        sta N_BROWSERPOS,x
        sta bu_base,x
        dex
        bpl fd_zero_position
        lda fd_last_length
        beq fd_input_path
        sta N_BROWSERLEN
        ldx #0
fd_last_path_copy:
        lda fd_last_path,x
        sta N_BROWSERPATH,x
        inx
        cpx fd_last_length
        bne fd_last_path_copy
fd_input_path:
        lda fd_format
        cmp #3
        bne fd_start
        lda fd_length
        beq fd_start
        lda fd_name
        cmp #$2f
        bne fd_start
        ldx fd_length
fd_input_parent:
        dex
        lda fd_name,x
        cmp #$2f
        bne fd_input_parent
        inx
        stx N_BROWSERLEN
        ldx #0
fd_input_parent_copy:
        lda fd_name,x
        sta N_BROWSERPATH,x
        inx
        cpx N_BROWSERLEN
        bne fd_input_parent_copy
fd_start:
        jsr bu_path_validate
        jmp b_format_valid
fd_bad_argument:
        lda #N_BADARG
        jmp fd_failure

; Cache records never cross a four-page boundary. Allocate blocks lazily,
; using either RAM bank, so a large caller document need not be moved/freed.
fd_cache_select:
        lda #0
        sta fd_direct
        lda N_OFFSET+1
        cmp #8
        bcs fd_banked_cache
        inc fd_direct
        and #6
        tax
        lda N_OFFSET
        clc
        adc fd_scratch,x
        sta fd_pointer
        lda N_OFFSET+1
        and #1
        adc fd_scratch+1,x
        sta fd_pointer+1
        rts
fd_banked_cache:
        sec
        sbc #8
        sta N_OFFSET+1
        lda N_OFFSET+1
        and #$fc
        tax
        stx fd_cache_at
        lda N_OFFSET+1
        and #3
        sta N_OFFSET+1
        lda b_cache,x
        bne fd_cache_handle
        lda #4
        cpx #28
        bcc +
        lda #1
+       sta N_PAGES
        lda #$ff
        sta N_BANK
        jsr N_ALLOC
        bcs fd_failure
        ldx fd_cache_at
        ldy #0
fd_keep_cache:
        lda N_HANDLE,y
        sta b_cache,x
        inx
        iny
        cpy #4
        bne fd_keep_cache
        ldx fd_cache_at
fd_cache_handle:
        ldy #0
fd_copy_cache_handle:
        lda b_cache,x
        sta N_HANDLE,y
        inx
        iny
        cpy #4
        bne fd_copy_cache_handle
        rts

; Four caller-supplied idle 512-byte buffers provide the first eight cache
; pages. The caller invalidates its read caches after the dialog returns.
; Only transient bytes are borrowed; document chunks are never repurposed.
fd_read_cache:
        lda fd_direct
        bne +
        jmp N_READ
+       lda fd_pointer
        sta fd_local_read+1
        lda fd_pointer+1
        sta fd_local_read+2
        lda #<N_BUFFER
        sta fd_local_write+1
        lda #>N_BUFFER
        sta fd_local_write+2
        jmp fd_local_copy
fd_write_cache:
        lda fd_direct
        bne +
        jmp N_WRITE
+       lda fd_pointer
        sta fd_local_write+1
        lda fd_pointer+1
        sta fd_local_write+2
        lda #<N_BUFFER
        sta fd_local_read+1
        lda #>N_BUFFER
        sta fd_local_read+2
fd_local_copy:
        lda N_COUNT
        sta fd_left
        lda N_COUNT+1
        sta fd_left+1
        ldx #0
fd_local_read:
        lda $ffff,x
fd_local_write:
        sta $ffff,x
        inx
        bne +
        inc fd_local_read+2
        inc fd_local_write+2
+       lda fd_left
        bne +
        dec fd_left+1
+       dec fd_left
        lda fd_left
        ora fd_left+1
        bne fd_local_read
        clc
        rts

fd_choose_iec:
        lda b_record+1
        bpl fd_unclosed
        lda b_record
        beq fd_unsupported
        cmp #4
        bcs fd_unsupported
        sec
        sbc #1
        sta fd_chosen_type
        jsr b_filename
        lda N_FNAMELEN
        beq fd_unsupported
        sta fd_candidate_length
        ldx #0
fd_iec_name:
        lda N_FNAME,x
        sta fd_candidate,x
        inx
        cpx fd_candidate_length
        bne fd_iec_name
        jmp fd_chosen
fd_unclosed:
        lda #$22
        bne fd_selection_error
fd_unsupported:
        lda #$21
fd_selection_error:
        sta b_error
        jmp b_redraw
fd_choose_ultimate:
        lda #0
        sta fd_chosen_type
        lda bu_full_length
        sta fd_candidate_length
        ldx #0
fd_ultimate_name:
        lda N_UPATH,x
        sta fd_candidate,x
        inx
        cpx fd_candidate_length
        bne fd_ultimate_name
        jmp fd_chosen

; Save As can choose an empty folder/device. Preserve the proposed basename;
; the caller's field remains editable before its exclusive, verified save.
fd_choose_folder:
        lda fd_mode
        cmp #2
        bne b_loop
        lda #0
        sta fd_leaf_at
        sta fd_candidate_length
        lda fd_format
        cmp #3
        bne fd_folder_destination
        ldx #0
fd_find_leaf:
        cpx fd_length
        beq fd_folder_destination
        lda fd_name,x
        inx
        cmp #$2f
        bne fd_find_leaf
        stx fd_leaf_at
        jmp fd_find_leaf
fd_folder_destination:
        lda N_BROWSERFMT
        cmp #3
        bne fd_append_leaf
        lda N_BROWSERLEN
        sta fd_candidate_length
        ldx #0
fd_folder_copy:
        lda N_BROWSERPATH,x
        sta fd_candidate,x
        inx
        cpx fd_candidate_length
        bne fd_folder_copy
        lda fd_candidate-1,x
        cmp #$2f
        beq fd_append_leaf
        cpx #255
        beq fd_too_long
        lda #$2f
        sta fd_candidate,x
        inc fd_candidate_length
fd_append_leaf:
        lda fd_length
        sec
        sbc fd_leaf_at
        clc
        adc fd_candidate_length
        bcs fd_too_long
        ldy N_BROWSERFMT
        cpy #3
        beq +
        cmp #17
        bcs fd_too_long
+       ldx fd_candidate_length
        sta fd_candidate_length
        ldy fd_leaf_at
fd_leaf_copy:
        cpy fd_length
        beq fd_chosen
        lda fd_name,y
        sta fd_candidate,x
        inx
        iny
        bne fd_leaf_copy
fd_too_long:
        lda #$23
        bne fd_selection_error
fd_chosen:
        lda fd_mode
        cmp #2
        bne +
        lda #0
        sta fd_chosen_type
+
        lda #1
        sta fd_result
        lda N_BROWSERDEV
        sta fd_chosen_device
        lda N_BROWSERFMT
        sta fd_chosen_format
        jmp fd_finish
fd_cancel:
        lda #0
fd_failure:
        sta fd_error
        lda #0
        sta fd_result
fd_finish:
        ldx fd_sp
        txs
        lda #0
        sta N_READY
        jsr fd_close_cursors
        bcc +
        sta fd_error
+       lda #0
        sta fd_cache_at
fd_free_cache:
        ldx fd_cache_at
        lda b_cache,x
        beq fd_next_cache
        jsr fd_cache_handle
        lda b_owner
        sta N_OWNER
        jsr N_FREE
        bcc fd_cache_freed
        sta fd_error
        jmp fd_next_cache
fd_cache_freed:
        ldx fd_cache_at
        lda #0
        sta b_cache,x
fd_next_cache:
        clc
        lda fd_cache_at
        adc #4
        sta fd_cache_at
        cmp #40
        bne fd_free_cache
        lda N_BROWSERLEN
        sta fd_last_length
        ldx #0
fd_restore_paths:
        lda N_BROWSERPATH,x
        sta fd_last_path,x
        lda fd_desktop_path,x
        sta N_BROWSERPATH,x
        lda fd_desktop_name,x
        sta N_BROWSERNAME,x
        inx
        bne fd_restore_paths
        ldx #11
fd_restore_preferences:
        lda fd_preferences,x
        sta N_BROWSERDEV,x
        dex
        bpl fd_restore_preferences
        lda #0
        sta fd_active
        lda fd_error
        bne fd_return_error
        lda fd_result
        beq fd_return_error
        lda fd_candidate_length
        sta fd_length
        ldx #0
fd_return_name:
        cpx fd_length
        beq fd_terminate_name
        lda fd_candidate,x
        sta fd_name,x
        inx
        bne fd_return_name
fd_terminate_name:
        lda #0
        sta fd_name,x
        lda fd_chosen_device
        sta fd_device
        lda fd_chosen_format
        sta fd_format
        lda fd_chosen_type
        sta fd_type
        plp
        lda #0
        clc
        rts
fd_return_error:
        lda fd_error
        plp
        sec
        rts

fd_close_cursors:
        jsr bu_close_cursor
        bcs fd_cursors_done
        lda fd_iec_handle
        beq fd_cursors_done
        lda b_owner
        sta N_FOWNER
        ldx #3
fd_iec_close_handle:
        lda fd_iec_handle,x
        sta N_FHANDLE,x
        dex
        bpl fd_iec_close_handle
        jsr N_FCLOSE
        bcs fd_cursors_done
        lda #0
        sta fd_iec_handle
fd_cursors_done:
        rts

.include "file-browser.inc"
fd_scratch: .word FD_SCRATCH0,FD_SCRATCH1,FD_SCRATCH2,FD_SCRATCH3
fd_direct: .byte 0
fd_pointer: .word 0
fd_left: .word 0
fd_lengths: .fill 16,0
fd_record_at: .byte 0
fd_active: .byte 0
fd_sp: .byte 0
fd_error: .byte 0
fd_result: .byte 0
fd_mode: .byte 0
fd_device: .byte 8
fd_format: .byte 0
fd_type: .byte 0
fd_length: .byte 0
fd_name = FD_NAME_BUFFER
fd_candidate_length: .byte 0
fd_candidate = b_usb_path
fd_chosen_device: .byte 0
fd_chosen_format: .byte 0
fd_chosen_type: .byte 0
fd_leaf_at: .byte 0
fd_cache_at: .byte 0
fd_iec_handle: .fill 4,0
fd_last_length: .byte 0
fd_last_path: .fill 256,0
fd_preferences: .fill 12,0
fd_desktop_path: .fill 256,0
fd_desktop_name: .fill 256,0
