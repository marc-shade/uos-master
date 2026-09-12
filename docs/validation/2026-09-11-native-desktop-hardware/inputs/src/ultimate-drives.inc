; Browser drive panel. Inventory records remain separate from filename slots.
; Only explicit, powered emulated-drive IEC IDs can reach DOS mount/eject.
; System-drive locks accumulate for this app session, including across refresh.
drives:
        lda #1
        sta driveview
        lda #0
        sta drive_selected
        sta pending
        sta viewpath
        sta nameoff
        sta nameoff+1
        jsr drive_probe
        jmp frame

drive_key:
        cmp #$44
        bne drive_not_back
        jmp drive_back
drive_not_back:
        cmp #$1b
        beq drive_cancel
        cmp #$0d
        bne drive_not_confirm
        jmp drive_confirm
drive_not_confirm:
        cmp #$9d
        bne drive_not_left
        jmp left
drive_not_left:
        cmp #$1d
        bne drive_not_right
        jmp right
drive_not_right:
        cmp #$50
        bne drive_not_path
        jmp toggle_path
drive_not_path:
        pha
        lda pending
        beq drive_idle_key
        pla                     ; only confirm/cancel or inspection while pending
        rts
drive_idle_key:
        pla
        cmp #$52
        bne drive_not_refresh
        jmp drive_probe
drive_not_refresh:
        cmp #$4d
        bne drive_not_mount
        jsr image_selected
        bcs drive_return
        lda #$23
        bne drive_prepare
drive_not_mount:
        cmp #$45
        bne drive_not_eject
        lda #$24
drive_prepare:
        pha
        jsr drive_guard
        pla
        bcs drive_return
        sta pending
        jsr drive_prompt
        jmp dirty_status
drive_not_eject:
        cmp #$91
        beq drive_up
        cmp #$11
        bne drive_return
        lda drive_selected
        clc
        adc #1
        cmp drive_count
        bcs drive_return
        sta drive_selected
        jmp drive_hint
drive_up:
        lda drive_selected
        beq drive_return
        dec drive_selected
        jmp drive_hint
drive_cancel:
        lda pending
        beq drive_back
        lda #0
        sta pending
        jmp drive_hint
drive_back:
        lda #0
        sta driveview
        sta pending
        jsr listed
        jsr frame
        lda #DIR_ALL
        sta dirty
drive_return:
        rts

; Clear old capabilities before every probe. A failure never leaves a stale
; writable record. The only reconciled short form is count=4, two physical
; records, plus matching independent A/B power queries.
drive_probe:
        lda #0
        sta drive_valid
        sta drive_count
        ldx #11
drive_clear:
        sta drive_records,x
        dex
        bpl drive_clear
        lda #$29
        sta REQUEST+1
        lda #1
        sta REQUEST+2
        lda #3
        jsr control_command
        bcc drive_probe_status
        jmp command_error
drive_probe_status:
        cmp #0
        beq drive_probe_data
        jmp firmware_error
drive_probe_data:
        lda NET_TRUNC
        ora NET_LEN+1
        bne drive_probe_bad
        lda NET_LEN
        bne drive_probe_length
drive_probe_bad:
        jmp drive_invalid
drive_probe_length:
        lda NET_DATA
        cmp #5
        bcs drive_invalid
        sta drive_declared
        asl
        clc
        adc drive_declared
        adc #1
        cmp NET_LEN
        beq drive_complete
        lda drive_declared
        cmp #4
        bne drive_invalid
        lda NET_LEN
        cmp #7
        bne drive_invalid
        lda NET_DATA+1
        cmp #4
        bcs drive_invalid
        lda NET_DATA+4
        cmp #4
        bcs drive_invalid
        lda #2
        sta drive_count
        sta drive_valid
        bne drive_copy
drive_complete:
        lda drive_declared
        sta drive_count
        lda #1
        sta drive_valid
drive_copy:
        ldx #0
        ldy #0
drive_record:
        cpx drive_count
        beq drive_copied
        lda NET_DATA+1,y
        sta drive_records,y
        lda NET_DATA+2,y
        cmp #31
        bcs drive_invalid
        sta drive_records+1,y
        cmp sysdev
        bne drive_not_system
        lda #1
        sta drive_locks,x
drive_not_system:
        lda NET_DATA+3,y
        cmp #2
        bcs drive_invalid
        sta drive_records+2,y
        iny
        iny
        iny
        inx
        bne drive_record
drive_invalid:
        lda #0
        sta drive_valid
        sta drive_count
        lda #<drive_bad
        ldx #>drive_bad
        jmp set_status
drive_copied:
        lda drive_valid
        cmp #2
        beq drive_reconcile
        jmp drive_reconciled
drive_reconcile:
        lda drive_records+1
        cmp #8
        bcc drive_invalid
        cmp drive_records+4
        beq drive_invalid
        lda drive_records+4
        cmp #8
        bcc drive_invalid
        ; Check each physical unit's power, independent of the short payload.
        lda #0
        sta drive_index
drive_power:
        lda drive_index
        clc
        adc #$34
        sta REQUEST+1
        lda #2
        jsr control_command
        bcs drive_invalid
        cmp #0
        bne drive_invalid
        lda NET_TRUNC
        ora NET_LEN+1
        bne drive_invalid
        lda NET_LEN
        cmp #2
        bcc drive_invalid
        cmp #4
        bcs drive_invalid
        lda NET_DATA
        cmp #$6f
        bne drive_invalid
        lda NET_DATA+1
        cmp #$6e
        beq drive_on
        cmp #$66
        bne drive_invalid
        lda NET_LEN
        cmp #3
        bne drive_invalid
        lda NET_DATA+2
        cmp #$66
        bne drive_invalid
        lda #0
        beq drive_power_match
drive_on:
        lda NET_LEN
        cmp #2
        beq drive_is_on
        lda NET_DATA+2
        cmp #$20
        beq drive_is_on
        jmp drive_invalid
drive_is_on:
        lda #1
drive_power_match:
        ldx drive_index
        ldy drive_offsets,x
        cmp drive_records+2,y
        beq drive_power_next
        jmp drive_invalid
drive_power_next:
        inc drive_index
        lda drive_index
        cmp #2
        bne drive_power
drive_reconciled:
        lda drive_selected
        cmp drive_count
        bcc drive_hint
        lda #0
        sta drive_selected
drive_hint:
        lda #<drive_full
        ldx #>drive_full
        ldy drive_valid
        cpy #1
        beq drive_message
        lda #<drive_partial
        ldx #>drive_partial
        cpy #2
        beq drive_message
        lda #<drive_bad
        ldx #>drive_bad
drive_message:
        jmp set_status

control_command:
        pha
        lda #4
        sta REQUEST
        lda #0
        sta NET_DIRMODE
        lda #<REQUEST
        sta r0L
        lda #>REQUEST
        sta r0H
        pla
        jmp NET_CMD

; Carry clear only for a uniquely addressed powered emulated drive. The
; current IEC system ID and previously observed system slot are both locked.
drive_guard:
        lda drive_valid
        beq drive_guard_bad
        ldx drive_selected
        cpx drive_count
        bcs drive_guard_bad
        ldy drive_offsets,x
        lda drive_records,y
        cmp #4
        bcs drive_guard_bad
        lda drive_records+1,y
        cmp #8
        bcc drive_guard_bad
        sta drive_id
        cmp sysdev
        beq drive_system
        lda drive_locks,x
        bne drive_system
        lda drive_records+2,y
        beq drive_off
        ldx #0
drive_unique:
        cpx drive_count
        beq drive_allowed
        cpx drive_selected
        beq drive_unique_next
        ldy drive_offsets,x
        lda drive_records+2,y
        beq drive_unique_next
        lda drive_records+1,y
        cmp drive_id
        beq drive_guard_bad
drive_unique_next:
        inx
        bne drive_unique
drive_allowed:
        clc
        rts
drive_system:
        lda #<drive_protected
        ldx #>drive_protected
        bne drive_denied
drive_off:
        lda #<drive_off_text
        ldx #>drive_off_text
        bne drive_denied
drive_guard_bad:
        lda #<drive_unavailable
        ldx #>drive_unavailable
drive_denied:
        jsr set_status
        sec
        rts

image_selected:
        lda count
        beq image_bad
        ldx selected
        lda attrs,x
        and #$10
        bne image_bad
        jsr selected_source
        lda remain+1
        bne image_long
        lda remain
        cmp #5
        bcc image_bad
image_long:
        clc
        lda sptr
        adc remain
        sta sptr
        lda sptr+1
        adc remain+1
        sta sptr+1
        sec
        lda sptr
        sbc #4
        sta sptr
        bcs image_suffix
        dec sptr+1
image_suffix:
        ldy #0
        lda (sptr),y
        cmp #$2e
        bne image_bad
        iny
        lda (sptr),y
        and #$df
        cmp #$44
        beq image_disk
        cmp #$47
        bne image_bad
image_disk:
        sta image_kind
        iny
        lda (sptr),y
        cmp #$36
        beq image_64
        cmp #$37
        beq image_71
        cmp #$38
        bne image_bad
        lda image_kind
        cmp #$44
        bne image_bad
image_71:
        lda #$31
        bne image_last
image_64:
        lda #$34
image_last:
        iny
        cmp (sptr),y
        bne image_bad
        clc
        rts
image_bad:
        lda #<image_required
        ldx #>image_required
        jmp drive_denied

drive_prompt:
        lda #<confirm_text
        ldx #>confirm_text
        jsr set_status
        ldx #4
drive_verb:
        lda mount_text,x
        ldy pending
        cpy #$23
        beq drive_verb_copy
        lda eject_text,x
drive_verb_copy:
        sta status,x
        dex
        bpl drive_verb
        lda drive_id
        jsr drive_decimal
        stx status+6
        sta status+7
        rts

drive_confirm:
        lda pending
        bne drive_confirm_begin
        rts
drive_confirm_begin:
        lda drive_count
        sta saved_count
        ldx #11
drive_snapshot:
        lda drive_records,x
        sta saved_records,x
        dex
        bpl drive_snapshot
        jsr drive_probe
        lda drive_valid
        bne drive_compare_count
        jmp drive_confirm_end
drive_compare_count:
        lda drive_count
        cmp saved_count
        beq drive_compare_begin
drive_compare_changed:
        jmp drive_changed
drive_compare_begin:
        ldx #11
drive_compare:
        lda drive_records,x
        cmp saved_records,x
        bne drive_compare_changed
        dex
        bpl drive_compare
        jsr drive_guard
        bcs drive_confirm_end
        lda pending
        sta REQUEST+1
        lda drive_id
        sta REQUEST+2
        lda #3
        sta commandlen
        lda #0
        sta commandlen+1
        lda pending
        cmp #$24
        beq drive_send
        jsr selected_source
        clc
        lda remain
        adc #3
        sta commandlen
        lda remain+1
        adc #0
        sta commandlen+1
        lda #<REQUEST+3
        sta dptr
        lda #>REQUEST+3
        sta dptr+1
        jsr copy_bytes
drive_send:
        lda commandlen
        sta r1L
        lda commandlen+1
        sta r1H
        jsr command_stream
        bcs drive_command_error
        cmp #0
        beq drive_command_ok
        jsr firmware_error
        jmp drive_confirm_end
drive_command_ok:
        lda NET_TRUNC
        bne drive_unknown_result
        lda #<drive_accepted
        ldx #>drive_accepted
        jsr set_status
        jmp drive_confirm_end
drive_unknown_result:
        lda #<drive_unknown_text
        ldx #>drive_unknown_text
        jsr set_status
        jmp drive_confirm_end
drive_command_error:
        jsr command_error
        jmp drive_confirm_end
drive_changed:
        lda #<drive_changed_text
        ldx #>drive_changed_text
        jsr set_status
drive_confirm_end:
        lda #0
        sta pending
drive_confirm_return:
        rts

; Two decimal digits for the validated IEC range 0..30. X=tens, A=units.
drive_decimal:
        ldx #$30
drive_tens:
        cmp #10
        bcc drive_units
        sec
        sbc #10
        inx
        bne drive_tens
drive_units:
        ora #$30
        rts

drive_paint:
        ; Reuse the browser's full-name/path inspector and status renderer.
        lda #0
        sta row
drive_paint_row:
        ldx row
        lda row_y,x
        sta draw_y
        jsr clear_field
        ldx #32
        lda #$20
drive_line_clear:
        sta line,x
        dex
        bpl drive_line_clear
        lda #0
        sta line+33
        ldx row
        cpx drive_count
        bcs drive_line_ready
        cpx drive_selected
        bne drive_line_id
        lda #$3e
        sta line
drive_line_id:
        ldy drive_offsets,x
        sty drive_record_index
        lda drive_records+1,y
        jsr drive_decimal
        stx line+2
        sta line+3
        ldy drive_record_index
        lda drive_records,y
        tax
        cmp #4
        bcc drive_type
        ldx #4
        cmp #$0f
        beq drive_type
        inx
        cmp #$50
        beq drive_type
        inx
drive_type:
        lda typesL,x
        sta sptr
        lda typesH,x
        sta sptr+1
        ldy #0
drive_type_copy:
        lda (sptr),y
        beq drive_line_power
        sta line+5,y
        iny
        bne drive_type_copy
drive_line_power:
        ldy drive_record_index
        lda #$4f
        sta line+14
        lda drive_records+2,y
        beq drive_line_off
        lda #$4e
        sta line+15
        bne drive_line_lock
drive_line_off:
        lda #$46
        sta line+15
        sta line+16
drive_line_lock:
        ldx row
        lda drive_locks,x
        beq drive_line_ready
        ldx #5
drive_lock_copy:
        lda system_text,x
        sta line+19,x
        dex
        bpl drive_lock_copy
drive_line_ready:
        lda draw_y
        jsr vic_line
        lda row
        clc
        adc #4
        ldx #0
        jsr vdc_line
        inc row
        lda row
        cmp #4
        beq drive_paint_path
        jmp drive_paint_row
drive_paint_path:
        jsr path_source
        ldx #76
        jsr text_chunk
        lda #3
        ldx #0
        jsr vdc_line
        lda #0
        sta line+34
        lda #26
        jsr clear_field
        lda #26
        jsr vic_line
        lda #0
        sta Y1+1
        #Text 24,94,drive_usage
        lda #0
        sta Y1+1
        #Text 24,106,drive_safety
        lda #0
        sta Y1+1
        #Text 24,118,drive_confirm_help
        jsr paint_details
        lda #DIR_STATUS
        sta dirty
        jmp paint_status_test

titlesL: .byte <title,<drive_title
titlesH: .byte >title,>drive_title
helpsL: .byte <help,<drive_help
helpsH: .byte >help,>drive_help
switchesL: .byte <drive_switch,<file_switch
switchesH: .byte >drive_switch,>file_switch
drive_title: .text "Ultimate drives",0
drive_switch: .text "drives",0
file_switch: .text "files",0
drive_help: .text "up/dn select M mount E eject R refresh enter confirm ESC cancel/back D files",0
        .cerror *-drive_help > 81, "drive help exceeds a VDC row"
drive_usage: .text "Select a drive. M=mount E=eject",0
drive_safety: .text "System drive stays mounted.",0
drive_confirm_help: .text "Enter confirms. Esc cancels.",0
drive_bad: .text "drive info unavailable; R=retry",0
drive_full: .text "drive inventory complete",0
drive_partial: .text "2 drives; other devices unknown",0
drive_protected: .text "system drive protected",0
drive_unavailable: .text "drive unsupported or ambiguous",0
drive_off_text: .text "drive is off",0
image_required: .text "select a D64/G64/D71/G71/D81 file",0
confirm_text: .text "mount 00? enter=yes esc=no",0
mount_text: .text "mount"
eject_text: .text "eject"
drive_changed_text: .text "drives changed; review and retry",0
drive_accepted: .text "drive command accepted",0
drive_unknown_text: .text "result unknown; check drive media",0
system_text: .text "system"
type1541: .text "1541",0
type1571: .text "1571",0
type1581: .text "1581",0
typeauto: .text "auto",0
typesoft: .text "soft IEC",0
typeprint: .text "printer",0
typeunknown: .text "unknown",0
typesL: .byte <type1541,<type1571,<type1581,<typeauto,<typesoft,<typeprint,<typeunknown
typesH: .byte >type1541,>type1571,>type1581,>typeauto,>typesoft,>typeprint,>typeunknown
btn_down: .text "down",0
btn_mount: .text "mnt",0
btn_eject: .text "ejct",0
btn_retry: .text "rtry",0
btn_yes: .text "yes",0
btn_no: .text "no",0
btn_back: .text "back",0
drive_offsets: .byte 0,3,6,9
driveview: .byte 0
drive_count: .byte 0
drive_declared: .byte 0
drive_valid: .byte 0
drive_selected: .byte 0
drive_index: .byte 0
drive_record_index: .byte 0
drive_id: .byte 0
pending: .byte 0
image_kind: .byte 0
drive_locks: .fill 4,0
drive_records: .fill 12,0
saved_records: .fill 12,0
saved_count: .byte 0
