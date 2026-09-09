; Export oldest-first history to a new SEQ file, then reopen and compare bytes.
save_begin:
        lda history_count
        bne save_prompt
        lda #4
        sta save_status
        jmp save_redraw
save_prompt:
        lda #0
        sta save_length
        sta save_name
        sta save_status
        lda #1
        sta save_mode
save_redraw:
        jsr c_show
        jmp cloop
save_key:
        cmp #27
        beq save_cancel
        cmp #13
        bne *+5
        jmp save_enter
        cmp #$14
        beq save_delete
        cmp #$20
        bcc save_key_done
        cmp #$7f
        bcs save_key_done
        cmp #$2a
        beq save_key_done
        cmp #$3f
        beq save_key_done
        cmp #$2c
        beq save_key_done
        cmp #$3a
        beq save_key_done
        cmp #$2f
        beq save_key_done
        cmp #$5c
        beq save_key_done
        cmp #$40
        beq save_key_done
        cmp #$23
        beq save_key_done
        cmp #$24
        beq save_key_done
        ldx save_length
        cpx #16
        beq save_key_done
        sta save_name,x
        inx
        stx save_length
        lda #0
        sta save_name,x
        jmp save_redraw
save_delete:
        ldx save_length
        beq save_key_done
        dex
        stx save_length
        lda #0
        sta save_name,x
        jmp save_redraw
save_cancel:
        lda #0
        sta save_mode
        jmp save_redraw
save_key_done:
        jmp cloop
save_enter:
        lda save_length
        beq save_key_done
        lda #0
        sta save_mode
        sta save_size
        sta save_row
        ; 32 records, at most five text bytes and CR per record (192 total).
save_collect:
        jsr history_select
        sec
        lda history_head
        sbc history_count
        clc
        adc save_row
        and #31
        jsr history_offset
        jsr N_READ
        bcc *+5
        jmp history_failure
        ldx #0
        ldy save_size
save_collect_text:
        lda N_BUFFER,x
        cmp #$20
        beq save_collect_line
        sta save_data,y
        iny
        inx
        cpx #5
        bne save_collect_text
save_collect_line:
        lda #13
        sta save_data,y
        iny
        sty save_size
        inc save_row
        lda save_row
        cmp history_count
        bne save_collect
        lda owner
        sta N_FOWNER
        lda N_DEVICE
        sta N_FDEVICE
        lda save_length
        sta N_FNAMELEN
        ldx #15
save_filename:
        lda save_name,x
        sta N_FNAME,x
        dex
        bpl save_filename
        lda #0
        sta N_FTYPE
        sta N_FHANDLE
        sta save_open
        lda N_APPFORMAT
        sta N_FFORMAT
        lda #1
        sta N_FMODE
        jsr N_FOPEN
        bcc save_created
        lda N_FDOS
        cmp #63
        beq *+5
        jmp save_failed
        lda #3
        sta save_status
        jmp save_redraw
save_created:
        inc save_open
        ldx #0
save_copy:
        lda save_data,x
        sta N_BUFFER,x
        inx
        cpx save_size
        bne save_copy
        lda save_size
        sta N_FCOUNT
        lda #0
        sta N_FCOUNT+1
        jsr N_FWRITE
        bcs save_failed
        jsr N_FCLOSE
        bcs save_failed
        dec save_open
        lda #0
        sta N_FMODE
        jsr N_FOPEN
        bcs save_failed
        inc save_open
        lda #0
        sta N_FCOUNT
        lda #2
        sta N_FCOUNT+1
        jsr N_FREAD
        bcs save_failed
        lda N_FACTUAL+1
        bne save_failed
        lda N_FACTUAL
        cmp save_size
        bne save_failed
        lda N_FEOF
        cmp #1
        bne save_failed
        ldx #0
save_compare:
        lda save_data,x
        cmp N_BUFFER,x
        bne save_failed
        inx
        cpx save_size
        bne save_compare
        jsr N_FCLOSE
        bcs save_failed
        lda #0
        sta save_open
        lda #1
        sta save_status
        jmp save_redraw
save_failed:
        lda save_open
        beq save_failed_closed
        jsr N_FCLOSE             ; never retry file data or remove a partial file
        lda #0
        sta save_open
save_failed_closed:
        lda #2
        sta save_status
        jmp save_redraw

save_show:
        lda save_mode
        beq save_show_status
        lda #<save_prompt_text
        ldx #>save_prompt_text
        jsr puts
        lda #<save_name
        ldx #>save_name
        jsr puts
        lda #<save_controls
        ldx #>save_controls
        jmp puts
save_show_status:
        ldx save_status
        beq save_show_done
        dex
        lda save_messages_lo,x
        pha
        lda save_messages_hi,x
        tax
        pla
        jmp puts
save_show_done:
        rts
save_prompt_text: .text 13,"save as (seq file on iec disk)",13,"name: ",0
save_controls: .text 13,"enter save   esc cancel",0
save_ok: .text 13,"history saved and verified",0
save_error_text: .text 13,"disk error; file may be partial",0
save_exists: .text 13,"file exists - choose another name",0
save_empty: .text 13,"no results to save",0
save_messages_lo: .byte <save_ok,<save_error_text,<save_exists,<save_empty
save_messages_hi: .byte >save_ok,>save_error_text,>save_exists,>save_empty
save_mode: .byte 0
save_status: .byte 0
save_length: .byte 0
save_size: .byte 0
save_row: .byte 0
save_open: .byte 0
save_name: .fill 17,0
save_data: .fill 192,0
