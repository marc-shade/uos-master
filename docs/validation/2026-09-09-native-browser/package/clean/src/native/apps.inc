; Native foreground application lifecycle, GPL v3.
; Read-only IEC loader: fixed bank-0 slot, checked manifest and CRC16.
; No KERNAL LOAD to an untrusted PRG address. Only owned channels are closed.
APP_LFN = 120
APP_CMD = 121
APP_SA = 7

app_launch:
        php
        lda N_APPSTATE
        ora N_CURRENT
        ora N_BUSY
        ora N_FBUSY
        beq app_available
app_nested:
        lda #N_REENTRANT
        plp
        sec
        rts
app_available:
        tsx
        lda $0101,x
        and #4
        beq app_interrupts
        lda #N_PLATFORM
        jmp app_before
app_interrupts:
        cld
        jsr heap_stats
        bcc *+5
        jmp app_before
        lda NFILES
        cmp #N_APPOWNER
        beq app_nested
        lda NFILES+16
        cmp #N_APPOWNER
        beq app_nested
        ldx #0
app_owner_scan:
        lda NHANDLES,x
        cmp #N_APPOWNER
        beq app_nested
        txa
        clc
        adc #8
        tax
        bne app_owner_scan
        lda N_DEVICE
        cmp #8
        bcc app_argument
        cmp #31
        bcs app_argument
        lda N_APPFORMAT
        cmp #3
        bcs app_argument
        lda N_NAMELEN
        beq app_argument
        cmp #17
        bcs app_argument
        ldx #0
app_name_loop:
        lda N_APPNAME,x
        cmp #$20
        bcc app_argument
        cmp #$7f
        bcs app_argument
        cmp #$2a               ; *, ?, comma, colon, slash and backslash
        beq app_argument
        cmp #$3f
        beq app_argument
        cmp #$2c
        beq app_argument
        cmp #$3a
        beq app_argument
        cmp #$2f
        beq app_argument
        cmp #$5c
        beq app_argument
        sta l_filename,x
        inx
        cpx N_NAMELEN
        bne app_name_loop
        ldy #0
app_name_suffix:
        lda l_suffix,y
        sta l_filename,x
        inx
        iny
        cpy #4
        bne app_name_suffix
        stx l_namelen
        jmp app_channels
app_argument:
        lda #N_BADARG
app_before:
        sta N_APPERROR
        plp
        cmp #1
        rts
app_channels:
        lda $99
        bne app_channel_busy
        lda $9a
        cmp #3
        bne app_channel_busy
        ldx $98
        cpx #9                  ; leave room for our two logical files
        bcs app_channel_busy
        dex
        bmi app_begin
app_channel_scan:
        lda $0362,x
        cmp #APP_LFN
        beq app_channel_busy
        cmp #APP_CMD
        beq app_channel_busy
        lda $036c,x
        cmp N_DEVICE
        bne app_channel_next
        ; Closing command channel 15 can close every file on that drive.
        ; The private loader therefore requires exclusive use of its device.
        beq app_channel_busy
app_channel_next:
        dex
        bpl app_channel_scan
        bmi app_begin
app_channel_busy:
        lda #N_CHANNELS
        jmp app_before
app_begin:
        lda #1
        sta N_APPSTATE
        lda #N_APPOWNER
        sta N_CURRENT
        lda #0
        sta N_READY
        sta N_EXITCODE
        sta N_DOSCODE
        sta N_IOSTATUS
        sta N_APPERROR
        sta N_ACTION
        sta l_result
        sta l_open
        sta l_command
        sta l_eof
        ldx #5
app_save_parameters:
        lda $b7,x
        sta l_parameters,x
        dex
        bpl app_save_parameters
        lda $c6
        sta l_parameters+6
        lda $c7
        sta l_parameters+7
        lda $9d
        sta l_parameters+8
        lda #0
        sta $9d
        tax
        jsr $ff68              ; native SETBNK: data and filename in RAM0
        lda #APP_CMD
        ldx N_DEVICE
        ldy #15
        jsr $ffba
        lda #0
        ldx #<l_filename
        ldy #>l_filename
        jsr $ffbd
        inc l_command          ; CLOSE is safe even if OPEN fails partway
        jsr $ffc0
        bcc *+5
        jmp app_io_failure
        lda #APP_LFN
        ldx N_DEVICE
        ldy #APP_SA
        jsr $ffba
        lda l_namelen
        ldx #<l_filename
        ldy #>l_filename
        jsr $ffbd
        inc l_open
        jsr $ffc0
        bcc *+5
        jmp app_io_failure
        jsr app_drive_status
        bcc *+5
        jmp app_io_failure
        jsr $ffcc
        ldx #APP_LFN
        jsr $ffc6
        bcc *+5
        jmp app_io_failure
        jsr app_byte
        bcc *+5
        jmp app_failure
        cmp #<N_APPBASE
        beq *+5
        jmp app_bad_image
        jsr app_byte
        bcc *+5
        jmp app_failure
        cmp #>N_APPBASE
        beq *+5
        jmp app_bad_image
        lda #0
        sta l_index
app_read_header:
        jsr app_byte
        bcc *+5
        jmp app_failure
        ldx l_index
        sta N_APPHEADER,x
        inc l_index
        lda l_index
        cmp #32
        bne app_read_header
        jsr app_validate
        bcc *+5
        jmp app_failure
        lda #N_APPOWNER
        sta N_OWNER
        lda N_APPHEADER+10
        sta N_PAGES
        lda #0
        sta N_BANK
        lda #>N_APPBASE
        sta N_PAGE
        jsr heap_reserve
        bcc *+5
        jmp app_failure
        ; Initialize the full declared allocation, including uninitialized
        ; data beyond the file. The validated range is below system ROM.
        lda N_APPHEADER+10
        sta l_zero_pages
        lda #>N_APPBASE
        sta app_zero+2
        lda #0
        ldx #0
app_zero:
        sta N_APPBASE,x
        inx
        bne app_zero
        inc app_zero+2
        dec l_zero_pages
        bne app_zero
        lda #$ff
        sta l_crc
        sta l_crc+1
        lda #0
        sta l_index
app_header_copy:
        ldx l_index
        lda N_APPHEADER,x
        sta N_APPBASE,x
        cpx #14
        beq app_crc_zero
        cpx #15
        bne app_header_crc
app_crc_zero:
        lda #0
app_header_crc:
        jsr app_crc_byte
        inc l_index
        lda l_index
        cmp #32
        bne app_header_copy
        lda #<(N_APPBASE+32)
        sta app_image_store+1
        lda #>(N_APPBASE+32)
        sta app_image_store+2
        sec
        lda N_APPHEADER+8
        sbc #32
        sta l_left
        lda N_APPHEADER+9
        sbc #0
        sta l_left+1
app_image_loop:
        jsr app_byte
        bcc *+5
        jmp app_failure
app_image_store:
        sta N_APPBASE+32
        jsr app_crc_byte
        inc app_image_store+1
        bne app_image_next
        inc app_image_store+2
app_image_next:
        lda l_left
        bne app_image_low
        dec l_left+1
app_image_low:
        dec l_left
        lda l_left
        ora l_left+1
        bne app_image_loop
        lda l_eof
        bne app_image_eof
        lda #N_LONGIMAGE
        bne app_failure
app_image_eof:
        lda l_crc
        cmp N_APPHEADER+14
        bne app_bad_crc
        lda l_crc+1
        cmp N_APPHEADER+15
        bne app_bad_crc
        jsr app_close
        lda l_result
        bne app_cleanup
        lda #2
        sta N_APPSTATE
        lda #N_APPOWNER
        sta N_OWNER
        tsx
        stx l_app_sp
        lda #0
        jsr app_jump
app_return:
        sta N_EXITCODE
        cld
        lda #$0e
        sta $ff00
        cli
        lda #0
        sta N_READY
        jmp app_cleanup
app_jump:
        jmp (l_entry)
app_exit:
        ldx N_APPSTATE
        cpx #2
        beq app_exit_active
app_exit_invalid:
        lda #N_BADARG
        sec
        rts
app_replace:
        lda #1
        bne app_request
app_workspace:
        lda #2
app_request:
        ldx N_APPSTATE
        cpx #2
        bne app_exit_invalid
        sta N_ACTION
        lda #0
app_exit_active:
        ldx l_app_sp
        txs
        jmp app_return
app_bad_crc:
        lda #N_CHECKSUM
        bne app_failure
app_bad_image:
        lda #N_BADIMAGE
        bne app_failure
app_io_failure:
        jsr $ffb7
        sta N_IOSTATUS
        lda #N_IOERROR
app_failure:
        sta l_result
        jsr app_close
app_cleanup:
        lda #3
        sta N_APPSTATE
        lda NFILES
        cmp #N_APPOWNER
        beq app_close_files
        lda NFILES+16
        cmp #N_APPOWNER
        bne app_release_memory
app_close_files:
        lda #N_APPOWNER
        sta N_FOWNER
        jsr fs_release
        bcs app_retain_resources
app_release_memory:
        lda #N_APPOWNER
        sta N_OWNER
        jsr heap_release
        bcc app_released
app_retain_resources:
        sta l_result
        lda #4                 ; corrupt ownership stays reserved, not reused
        sta N_APPSTATE
        bne app_finish
app_released:
        lda #0
        sta N_CURRENT
        sta N_APPSTATE
app_finish:
        lda l_result
        sta N_APPERROR
        plp
        cmp #1
        rts

app_validate:
        ldx #3
app_magic_loop:
        lda N_APPHEADER,x
        cmp l_magic,x
        beq *+5
        jmp app_invalid
        dex
        bpl app_magic_loop
        lda N_APPHEADER+4
        cmp #1
        bne app_invalid
        lda N_APPHEADER+5
        cmp #1
        bne app_invalid
        lda N_APPHEADER+6
        cmp #N_ABI_MINOR+1
        bcs app_invalid
        lda N_APPHEADER+7
        ora N_APPHEADER+11
        bne app_invalid
        lda N_APPHEADER+10
        beq app_invalid
        cmp #((N_APPLIMIT-N_APPBASE)/256)+1
        bcs app_invalid
        lda N_APPHEADER+9
        cmp N_APPHEADER+10
        bcc app_size_fits
        bne app_invalid
        lda N_APPHEADER+8
        bne app_invalid
app_size_fits:
        lda N_APPHEADER+9
        bne app_image_large
        lda N_APPHEADER+8
        cmp #33
        bcc app_invalid
app_image_large:
        lda N_APPHEADER+13
        bne app_entry_large
        lda N_APPHEADER+12
        cmp #32
        bcc app_invalid
app_entry_large:
        lda N_APPHEADER+13
        cmp N_APPHEADER+9
        bcc app_entry_fits
        bne app_invalid
        lda N_APPHEADER+12
        cmp N_APPHEADER+8
        bcs app_invalid
app_entry_fits:
        lda N_APPHEADER+12
        sta l_entry
        clc
        lda N_APPHEADER+13
        adc #>N_APPBASE
        sta l_entry+1
        ldx #16
app_title_loop:
        lda N_APPHEADER,x
        beq app_title_next
        cmp #$20
        bcc app_invalid
        cmp #$7f
        bcs app_invalid
app_title_next:
        inx
        cpx #32
        bne app_title_loop
        clc
        rts
app_invalid:
        lda #N_BADIMAGE
        sec
        rts

; Carry clear returns one byte, even when that byte carries EOI. A further
; request after EOI is an explicit short-image error, never a fabricated zero.
app_byte:
        lda l_eof
        beq app_byte_read
        lda #N_SHORTIMAGE
        sec
        rts
app_byte_read:
        jsr $ffcf
        sta l_byte
        jsr $ffb7
        sta N_IOSTATUS
        and #$bf
        beq app_byte_ok
        lda #N_IOERROR
        sec
        rts
app_byte_ok:
        lda N_IOSTATUS
        and #$40
        sta l_eof
        lda l_byte
        clc
        rts

; CRC16-CCITT, initial $ffff, polynomial $1021; header bytes 14/15 are zero.
app_crc_byte:
        eor l_crc+1
        sta l_crc+1
        ldx #8
app_crc_bit:
        asl l_crc
        rol l_crc+1
        bcc app_crc_next
        lda l_crc
        eor #$21
        sta l_crc
        lda l_crc+1
        eor #$10
        sta l_crc+1
app_crc_next:
        dex
        bne app_crc_bit
        rts

app_drive_status:
        jsr $ffcc
        ldx #APP_CMD
        jsr $ffc6
        bcs app_status_error
        lda #0
        sta l_index
app_status_read:
        jsr $ffcf
        sta l_byte
        jsr $ffb7
        sta N_IOSTATUS
        and #$bf
        bne app_status_error
        ldx l_index
        lda l_byte
        sta l_status,x
        inc l_index
        cmp #13
        beq app_status_complete
        lda N_IOSTATUS
        and #$40
        bne app_status_error
        lda l_index
        cmp #40
        bne app_status_read
app_status_error:
        jsr $ffcc
        sec
        rts
app_status_complete:
        jsr $ffcc
        lda l_index
        cmp #4
        bcc app_status_error
        lda l_status+2
        cmp #$2c
        bne app_status_error
        ldx #1
app_status_digits:
        lda l_status,x
        cmp #$30
        bcc app_status_error
        cmp #$3a
        bcs app_status_error
        and #15
        sta l_status,x
        dex
        bpl app_status_digits
        lda l_status
        asl
        sta l_byte
        asl
        asl
        clc
        adc l_byte
        adc l_status+1
        sta N_DOSCODE
        cmp #1                 ; accept only DOS 00, not a startup/error reply
        rts

app_close:
        jsr $ffcc
        lda l_open
        beq app_close_command
        lda #APP_LFN
        jsr $ffc3
        lda #0
        sta l_open
        jsr app_close_status
app_close_command:
        lda l_command
        beq app_restore_parameters
        ; Preserve the first error's DOS code while checking final close.
        lda N_DOSCODE
        pha
        jsr app_drive_status
        bcc app_closed_drive
        lda l_result
        bne app_closed_drive
        lda #N_IOERROR
        sta l_result
app_closed_drive:
        pla
        beq app_keep_close_code
        sta N_DOSCODE
app_keep_close_code:
        lda #APP_CMD
        jsr $ffc3
        lda #0
        sta l_command
        jsr app_close_status
app_restore_parameters:
        jsr $ffcc
        ldx #5
app_restore_loop:
        lda l_parameters,x
        sta $b7,x
        dex
        bpl app_restore_loop
        lda l_parameters+6
        sta $c6
        lda l_parameters+7
        sta $c7
        lda l_parameters+8
        sta $9d
        rts
app_close_status:
        jsr $ffb7
        and #$bf
        beq app_close_status_done
        sta N_IOSTATUS
        lda l_result
        bne app_close_status_done
        lda #N_IOERROR
        sta l_result
app_close_status_done:
        rts

l_magic: .text "napp"
l_suffix: .text ",p,r"
l_filename: .fill 20,0
l_namelen: .byte 0
l_parameters: .fill 9,0
l_status: .fill 40,0
l_open: .byte 0
l_command: .byte 0
l_result: .byte 0
l_index: .byte 0
l_byte: .byte 0
l_eof: .byte 0
l_zero_pages: .byte 0
l_app_sp: .byte 0
l_crc: .word 0
l_left: .word 0
        .align 2
l_entry: .word 0
