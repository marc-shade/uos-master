; Native directory browser, app discovery and bounded binary viewer. GPL v3.
.include "api.inc"
* = N_APPBASE
b_image:
        .text "napp"
        .byte 1,1,2,0
        .word b_end-b_image
        .byte 16,0
        .word b_entry-b_image
        .word 0
        .text "files and apps",0
        .fill N_APPBASE+32-*,0
b_entry:
        cld
        lda N_CURRENT
        sta b_owner
        sta N_OWNER
        lda #37                 ; 296 normalized entries, the root D81 maximum
        sta N_PAGES
        lda #1
        sta N_BANK
        jsr N_ALLOC
        bcs b_exit_error
        ldx #3
b_keep_cache:
        lda N_HANDLE,x
        sta b_cache,x
        dex
        bpl b_keep_cache
        lda N_BROWSERDEV
        cmp #8
        bcc b_default_device
        cmp #31
        bcc b_device_valid
b_default_device:
        lda N_DEVICE
        sta N_BROWSERDEV
b_device_valid:
        lda N_BROWSERFMT
        cmp #3
        bcc b_format_valid
        lda #0
        sta N_BROWSERFMT
b_format_valid:
        lda N_BROWSERERROR
        sta b_launch_error
        lda #0
        sta N_BROWSERERROR
        sta b_selected
        sta b_selected+1
        jsr b_refresh
b_redraw:
        jsr b_draw
cloop:
        lda #1
        sta N_READY
        jsr N_KEYIN
        beq cloop
        ldx #0
        stx N_READY
        ldx b_prompt
        bne b_prompt_key
        ldx b_preview
        bne b_preview_key
        cmp #27
        beq b_workspace
        cmp #$11                ; native cursor down
        beq b_down
        cmp #$91
        beq b_up
        cmp #13
        beq b_enter
        and #$df
        cmp #$52
        beq b_rescan
        cmp #$46
        beq b_change_format
        cmp #$44
        beq b_device_prompt
        cmp #$4e
        beq b_next_page
        cmp #$42
        beq b_previous_page
        cmp #$41
        beq b_next_app
        cmp #$49
        beq b_inspect
        jmp cloop
b_workspace:
        jmp N_WORKSPACE
b_exit_error:
        jmp N_EXIT
b_rescan:
        lda #0
        sta b_launch_error
        jsr b_refresh
        jmp b_redraw
b_change_format:
        inc N_BROWSERFMT
        lda N_BROWSERFMT
        cmp #3
        bne b_change_ready
        lda #0
        sta N_BROWSERFMT
b_change_ready:
        lda #0
        sta b_selected
        sta b_selected+1
        jmp b_rescan
b_device_prompt:
        lda #1
        sta b_prompt
        lda #0
        sta b_device_length
        jmp b_redraw
b_prompt_key:
        cmp #27
        beq b_prompt_cancel
        cmp #13
        beq b_prompt_enter
        cmp #20
        beq b_prompt_delete
        cmp #$30
        bcc cloop
        cmp #$3a
        bcs cloop
        ldx b_device_length
        cpx #2
        beq cloop
        sta b_device_text,x
        inc b_device_length
        jmp b_redraw
b_prompt_delete:
        lda b_device_length
        beq cloop
        dec b_device_length
        jmp b_redraw
b_prompt_enter:
        ldx b_device_length
        beq cloop
        lda b_device_text
        and #15
        cpx #1
        beq b_device_number
        asl
        sta b_digit
        asl
        asl
        clc
        adc b_digit
        sta b_digit
        lda b_device_text+1
        and #15
        clc
        adc b_digit
b_device_number:
        cmp #8
        bcc cloop
        cmp #31
        bcs cloop
        sta N_BROWSERDEV
        lda #0
        sta b_prompt
        sta b_selected
        sta b_selected+1
        jmp b_rescan
b_prompt_cancel:
        lda #0
        sta b_prompt
        jmp b_redraw
b_down:
        inc b_selected
        bne b_selected_changed
        inc b_selected+1
b_selected_changed:
        jsr b_clamp
        jmp b_redraw
b_up:
        lda b_selected
        ora b_selected+1
        beq cloop
        lda b_selected
        bne b_up_low
        dec b_selected+1
b_up_low:
        dec b_selected
        jmp b_redraw
b_next_page:
        clc
        lda b_selected
        adc #8
        sta b_selected
        bcc b_selected_changed
        inc b_selected+1
        jmp b_selected_changed
b_previous_page:
        sec
        lda b_selected
        sbc #8
        sta b_selected
        lda b_selected+1
        sbc #0
        sta b_selected+1
        bcs b_redraw
        lda #0
        sta b_selected
        sta b_selected+1
        jmp b_redraw
b_clamp:
        lda b_total
        ora b_total+1
        beq b_clamp_zero
        lda b_selected
        cmp b_total
        lda b_selected+1
        sbc b_total+1
        bcc b_clamped
        sec
        lda b_total
        sbc #1
        sta b_selected
        lda b_total+1
        sbc #0
        sta b_selected+1
b_clamped:
        rts
b_clamp_zero:
        sta b_selected
        sta b_selected+1
        rts
b_next_app:
        lda b_total
        ora b_total+1
        beq b_no_apps
        lda b_selected
        sta b_saved_selection
        lda b_selected+1
        sta b_saved_selection+1
b_find_app:
        inc b_selected
        bne b_find_app_bound
        inc b_selected+1
b_find_app_bound:
        lda b_selected
        cmp b_total
        lda b_selected+1
        sbc b_total+1
        bcc b_find_app_read
        lda #0
        sta b_selected
        sta b_selected+1
b_find_app_read:
        jsr b_selected_record
        lda b_record+20
        bne b_redraw
        lda b_selected
        cmp b_saved_selection
        bne b_find_app
        lda b_selected+1
        cmp b_saved_selection+1
        bne b_find_app
b_no_apps:
        lda #$20
        sta b_error
        jmp b_redraw
b_enter:
        lda b_total
        ora b_total+1
        beq cloop
        jsr b_selected_record
        lda b_record+20
        beq b_view_open
        jsr b_filename
        lda N_FNAMELEN
        sta N_NAMELEN
        ldx #15
b_launch_name:
        lda N_FNAME,x
        sta N_APPNAME,x
        dex
        bpl b_launch_name
        lda N_BROWSERDEV
        sta N_DEVICE
        lda N_BROWSERFMT
        sta N_APPFORMAT
        jmp N_REPLACE
b_inspect:
        lda b_total
        ora b_total+1
        beq cloop
        jsr b_selected_record
        jmp b_view_open

; Refresh takes a bounded directory snapshot. File bytes are never written.
b_refresh:
        lda #0
        sta b_total
        sta b_total+1
        sta b_error
        sta b_page
        lda #1
        sta b_busy
        jsr b_draw
b_scan_page:
        lda b_owner
        sta N_FOWNER
        lda N_BROWSERDEV
        sta N_FDEVICE
        lda N_BROWSERFMT
        sta N_FFORMAT
        lda b_page
        sta N_DPAGE
        jsr N_DIRPAGE
        bcs b_scan_failed
        lda N_DNEXT
        sta b_next
        lda N_DCOUNT
        beq b_scan_done
        ldx #0
b_page_copy:
        lda N_BUFFER,x
        sta b_page_data,x
        inx
        bne b_page_copy
        stx b_scan_offset
b_scan_record:
        ldx b_scan_offset
        lda b_page_data,x
        beq b_scan_next
        ldy #0
b_record_copy:
        lda b_page_data,x
        sta b_record,y
        inx
        iny
        cpy #32
        bne b_record_copy
        lda #0
        sta b_record+20
        sta b_record+21
        jsr b_probe_app
        lda b_total
        sta b_index
        lda b_total+1
        sta b_index+1
        jsr b_cache_select
        ldx #31
b_record_store:
        lda b_record,x
        sta N_BUFFER,x
        dex
        bpl b_record_store
        jsr N_WRITE
        bcs b_exit_error
        inc b_total
        bne b_scan_next
        inc b_total+1
b_scan_next:
        clc
        lda b_scan_offset
        adc #32
        sta b_scan_offset
        bne b_scan_record
        lda b_next
        cmp #$ff
        beq b_scan_done
        sta b_page
        jmp b_scan_page
b_scan_failed:
        sta b_error
        lda N_FHANDLE
        beq b_scan_done
        lda b_error
        jmp b_exit_error         ; uncertain metadata cleanup remains owned
b_scan_done:
        lda #0
        sta b_busy
        jmp b_clamp

b_cache_select:
        lda b_owner
        sta N_OWNER
        ldx #3
b_cache_handle:
        lda b_cache,x
        sta N_HANDLE,x
        dex
        bpl b_cache_handle
        lda b_index
        sta N_OFFSET
        lda b_index+1
        sta N_OFFSET+1
        ldx #5
b_cache_offset:
        asl N_OFFSET
        rol N_OFFSET+1
        dex
        bne b_cache_offset
        lda #32
        sta N_COUNT
        lda #0
        sta N_COUNT+1
        rts
b_selected_record:
        lda b_selected
        sta b_index
        lda b_selected+1
        sta b_index+1
b_read_record:
        jsr b_cache_select
        jsr N_READ
        bcs b_exit_error
        ldx #31
b_record_loaded:
        lda N_BUFFER,x
        sta b_record,x
        dex
        bpl b_record_loaded
        rts
b_filename:
        ldx #0
b_filename_byte:
        lda b_record+2,x
        sta N_FNAME,x
        cmp #$a0
        beq b_filename_done
        inx
        cpx #16
        bne b_filename_byte
b_filename_done:
        stx N_FNAMELEN
        rts
b_open_record:
        lda #0
        sta b_open
        sta N_FHANDLE
        sta N_FHANDLE+1
        sta N_FHANDLE+2
        sta N_FHANDLE+3
        sta N_FMODE
        lda b_record+1
        and #$80
        beq b_unclosed
        lda b_record
        cmp #1
        bcc b_unsupported
        cmp #4
        bcs b_unsupported
        sec
        sbc #1
        sta N_FTYPE
        jsr b_filename
        lda b_owner
        sta N_FOWNER
        lda N_BROWSERDEV
        sta N_FDEVICE
        lda N_BROWSERFMT
        sta N_FFORMAT
        jsr N_FOPEN
        bcs b_open_failed
        inc b_open
        rts
b_open_failed:
        ldx N_FHANDLE
        bne b_exit_error
        sec
        rts
b_unclosed:
        lda #$22
        sec
        rts
b_unsupported:
        lda #$21
        sec
        rts
b_close_file:
        lda b_open
        beq b_file_closed
        jsr N_FCLOSE
        bcs b_exit_error
        lda #0
        sta b_open
b_file_closed:
        rts
b_probe_app:
        lda b_record
        cmp #2
        bne b_probe_done
        lda b_record+1
        and #$80
        beq b_probe_done
        jsr b_open_record
        bcs b_probe_error
        lda #34
        sta N_FCOUNT
        lda #0
        sta N_FCOUNT+1
        jsr N_FREAD
        bcs b_probe_read_error
        lda N_FACTUAL
        cmp #34
        bne b_probe_close
        ldx #5
b_probe_magic:
        lda N_BUFFER,x
        cmp b_app_magic,x
        bne b_probe_close
        dex
        bpl b_probe_magic
        inc b_record+20         ; discovery only: the loader validates full image/CRC
b_probe_close:
        jmp b_close_file
b_probe_read_error:
        sta b_record+21
        jmp b_probe_close
b_probe_error:
        sta b_record+21
b_probe_done:
        rts

.include "browser-ui.inc"
.include "browser-view.inc"

b_app_magic: .byte 0,$60,$4e,$41,$50,$50
b_cache: .fill 4,0
b_owner: .byte 0
b_total: .word 0
b_selected: .word 0
b_saved_selection: .word 0
b_index: .word 0
b_page: .byte 0
b_next: .byte 0
b_scan_offset: .byte 0
b_busy: .byte 0
b_error: .byte 0
b_launch_error: .byte 0
b_open: .byte 0
b_prompt: .byte 0
b_device_length: .byte 0
b_device_text: .fill 2,0
b_record: .fill 32,0
b_page_data: .fill 256,0
b_end:
        .cerror * > N_APPBASE+$1000, "browser exceeds its declared allocation"
