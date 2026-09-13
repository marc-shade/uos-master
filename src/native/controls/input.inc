; Keyboard, mouse, picker and explicit confirmation are foreground app work.
ug_key:
        sta ug_key_value
        lda ug_mode
        beq ug_main_key
        lda ug_key_value
        cmp #27
        beq ug_cancel_dialog
        cmp #9
        beq ug_toggle_confirm
        cmp #$9d
        beq ug_toggle_confirm
        cmp #$1d
        beq ug_toggle_confirm
        cmp #13
        bne ug_handled
        ldx ui_selected
        jmp ug_activate
ug_toggle_confirm:
        lda ui_selected
        eor #1
        tax
        jsr ug_focus
        jmp ug_handled
ug_cancel_dialog:
        jsr ud_cancel
        lda #2
        sta ug_notice
        jmp ug_leave_dialog
ug_main_key:
        lda ug_key_value
        cmp #9
        beq ug_tab
        cmp #13
        bne +
        ldx ui_selected
        jmp ug_activate
+       lda uc_page
        cmp #1
        bne ug_unhandled
        lda ug_key_value
        cmp #$91
        beq ug_previous_drive
        cmp #$9d
        beq ug_previous_drive
        cmp #$11
        beq ug_next_drive
        cmp #$1d
        beq ug_next_drive
        and #$df
        cmp #$4d
        beq ug_mount
        cmp #$45
        beq ug_eject
ug_unhandled:
        lda ug_key_value
        clc
        rts
ug_tab:
        ldx ui_selected
-       inx
        cpx #16
        bcc +
        ldx #0
+       jsr ug_enabled
        bcs -
        jsr ug_focus
ug_handled:
        lda #0
        sec
        rts
ug_activate:
        jsr ug_enabled
        bcs ug_handled
        cpx #10
        beq ug_confirm_dialog
        cpx #11
        beq ug_cancel_dialog
        cpx #12
        bcs ug_choose_row
        cpx #8
        beq ug_mount
        cpx #9
        beq ug_eject
        lda uc_page
        cmp #1
        bne +
        cpx #5
        beq ug_previous_drive
        cpx #6
        beq ug_next_drive
+
        lda ug_keys,x
        sta ug_key_value
        clc
        rts
ug_choose_row:
        txa
        sec
        sbc #12
        sta ud_selected
        jmp ug_drive_changed
ug_previous_drive:
        lda ud_count
        beq ug_handled
        lda ud_selected
        bne +
        lda ud_count
+       sec
        sbc #1
        sta ud_selected
        jmp ug_drive_changed
ug_next_drive:
        lda ud_count
        beq ug_handled
        lda ud_selected
        clc
        adc #1
        cmp ud_count
        bcc +
        lda #0
+       sta ud_selected
ug_drive_changed:
        lda ud_selected
        clc
        adc #12
        sta ui_selected
        jsr ug_update
        jsr uc_draw_both
        jmp ug_handled

ug_mount:
        jsr ug_cleanup
        bcs ug_cleanup_failed
        jsr ud_guard
        bcs ug_result
        jsr ug_view_close
        lda #1
        sta drive_picker.fd_mode
        lda ud_context
        sta drive_picker.fd_device
        lda #3
        sta drive_picker.fd_format
        lda ud_name_length
        sta drive_picker.fd_length
        jsr drive_picker.fd_run
        sta ug_picker_error
        lda #0
        rol
        sta ug_picker_failed
        jsr ug_cleanup
        bcs ug_picker_cleanup_failed
        lda ug_picker_failed
        bne ug_picker_cancelled
        lda drive_picker.fd_format
        cmp #3
        bne ug_picker_wrong_source
        lda drive_picker.fd_device
        sta ud_context
        lda drive_picker.fd_length
        sta ud_name_length
        lda #$23
        jsr ud_prepare
        bcs ug_picker_result
        jsr ug_enter_dialog
        jmp ug_picker_reopen
ug_picker_cancelled:
        lda ug_picker_error
        bne ug_picker_result
        lda #2
        sta ug_notice
        bne ug_picker_reopen
ug_picker_wrong_source:
        lda #UD_ERR_CONTEXT
ug_picker_result:
        jsr ug_notice_for_error
ug_picker_reopen:
        jsr ug_collect_body
        jsr ug_view_open
        jsr uc_draw_both
        jmp ug_handled
ug_picker_cleanup_failed:
        lda #10
        sta ug_notice
        bne ug_picker_reopen
ug_eject:
        jsr ug_cleanup
        bcs ug_cleanup_failed
        lda #$24
        jsr ud_prepare
        bcs ug_result
        jsr ug_enter_dialog
        jsr ug_update
        jsr uc_draw_both
        jmp ug_handled
ug_enter_dialog:
        lda ui_selected
        sta ug_saved_focus
        lda #11
        sta ui_selected
        lda #1
        sta ug_mode
        lda #0
        sta ug_notice
        lda #$ff
        sta pm_arm
        rts
ug_confirm_dialog:
        jsr ud_confirm
        bcs ug_dialog_error
        lda #1                 ; accepted is not a verified mounted-media claim
        sta ug_notice
        bne ug_leave_dialog
ug_dialog_error:
        jsr ug_notice_for_error
ug_leave_dialog:
        lda #0
        sta ug_mode
        lda ug_saved_focus
        sta ui_selected
        lda #$ff
        sta pm_arm
        jsr ug_update
        jsr uc_draw_both
        jmp ug_handled
ug_result:
        jsr ug_notice_for_error
        jsr ug_update
        jsr uc_draw_both
        jmp ug_handled
ug_cleanup_failed:
        lda #10
        sta ug_notice
        jsr ug_update
        jsr uc_draw_both
        jmp ug_handled
ug_notice_for_error:
        cmp #UD_ERR_SYSTEM
        bne +
        lda #3
        bne ug_notice_set
+       cmp #UD_ERR_OFF
        bne +
        lda #4
        bne ug_notice_set
+       cmp #UD_ERR_INVALID
        bne +
        lda #5
        bne ug_notice_set
+       cmp #UD_ERR_CHANGED
        bne +
        lda #6
        bne ug_notice_set
+       cmp #UD_ERR_IMAGE
        beq ug_image_notice
        cmp #UD_ERR_CONTEXT
        bne +
ug_image_notice:
        lda #7
        bne ug_notice_set
+       cmp #UD_ERR_BUSY
        bne +
        lda #8
        bne ug_notice_set
+       lda #9
ug_notice_set:
        sta ug_notice
        rts

ug_focus:
        lda ug_bitmap
        beq +
        jsr ui_focus
        bcs ug_focus_failed
        jmp uc_draw_both
+       stx ui_selected
        jmp uc_draw_both
ug_focus_failed:
        jsr ug_failed
        jmp uc_draw_both
ug_mouse:
        lda ug_bitmap
        beq ug_no_mouse
        jsr pm_poll
        lda pm_event
        beq ug_no_mouse
        lda #0
        sta N_READY
        ldx pm_hit
        jsr ug_focus
        lda pm_event
        cmp #2
        bne ug_no_mouse
        ldx pm_hit
        jsr ug_activate
        bcs ug_no_mouse
        rts
ug_no_mouse:
        lda #0
        rts
pm_control_count=ui_button_count
pm_select_surface=ug_select_view
pm_find_hit:
        lda ug_mode
        beq +
        lda #10
        sta ui_first
        lda #12
        bne ug_hit_limit
+       sta ui_first
        lda #16
ug_hit_limit:
        sta ui_limit
        lda pm_x
        sta ui_x
        lda pm_x+1
        sta ui_x+1
        lda pm_y
        sta ui_y
        jsr ui_hit
        jsr ug_enabled
        bcc +
        ldx #$ff
+       rts

ug_cleanup:
        jsr drive_picker.fd_close_cursors
        bcs ug_cleanup_done
        lda #0
        sta ug_cache_at
-       ldx ug_cache_at
        lda drive_picker.b_cache,x
        beq +
        jsr drive_picker.fd_cache_handle
        lda N_CURRENT
        sta N_OWNER
        jsr N_FREE
        bcs ug_cleanup_done
        ldx ug_cache_at
        lda #0
        sta drive_picker.b_cache,x
+       lda ug_cache_at
        clc
        adc #4
        sta ug_cache_at
        cmp #40
        bne -
        lda #0
        clc
ug_cleanup_done:
        rts
ug_exit:
        jsr ug_cleanup
        bcs ug_cleanup_failed
        jsr ug_view_close
        jsr nk_close
        lda #0
        jmp N_EXIT
ug_safe_character:
        cmp #32
        bcc +
        cmp #127
        bcc ug_cleanup_done
+       lda #46
        rts

ug_keys: .byte $49,$44,$4e,$54,27,$9d,$1d,$52
ug_key_value: .byte 0
ug_saved_focus: .byte 0
ug_picker_error: .byte 0
ug_picker_failed: .byte 0
ug_cache_at: .byte 0
