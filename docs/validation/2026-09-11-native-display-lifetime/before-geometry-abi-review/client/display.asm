; Isolated native display lifetime client, GPL v3.
; N_EXIT/RTS deliberately omit display cleanup; N_FREE also uses the resident hook.
.include "api.inc"
* = N_APPBASE
app_image:
        .text "napp"
        .byte 1,1,8,0
        .word app_end-app_image
        .byte 4,0
        .word app_entry-app_image
        .word 0
        .text "vic placement",0
        .fill N_APPBASE+32-*,0
app_entry:
        cld
        lda #0
        sta phase
        sta error
        sta handle
        sta active
        lda N_CURRENT
        sta N_OWNER
        lda #0
        sta N_BANK
        lda #$c0
        sta N_PAGE
        lda #36
        sta N_PAGES
        jsr N_RESERVE
        bcs failed
        ldx #3
save_handle:
        lda N_HANDLE,x
        sta handle,x
        dex
        bpl save_handle
        lda #0
        sta N_OFFSET
        sta N_OFFSET+1
        sta N_COUNT
        lda #2
        sta N_COUNT+1
fill_next:
        lda #$aa
        ldx N_OFFSET+1
        cpx #$20
        bcc fill_value
        lda #$e6
fill_value:
        sta N_VALUE
        jsr N_FILL
        bcs failed
        inc N_OFFSET+1
        inc N_OFFSET+1
        lda N_OFFSET+1
        cmp #$24
        bne fill_next
        jsr N_VSHOW
        bcs failed
        lda #1
        sta active
        lda #2
        sta phase
        bne input_loop
failed:
        sta error
        lda #1
        sta phase
input_loop:
        lda #1
        sta N_READY
        jsr N_KEYIN
        beq input_loop
        ldx #0
        stx N_READY
        cmp #13
        beq normal_return
        cmp #$46
        beq free_visible
        cmp #$49
        beq read_fixture
        cmp #$4d
        beq replace_missing
        cmp #$58
        beq replace_text
        cmp #$1b
        bne input_loop
        lda error
        jmp N_EXIT
normal_return:
        lda error
        rts

free_visible:
        lda N_CURRENT
        sta N_OWNER
        ldx #3
select_surface:
        lda handle,x
        sta N_HANDLE,x
        dex
        bpl select_surface
        jsr N_FREE
        sta error
        bcs input_loop
        lda #0
        sta active
        lda #3
        sta phase
        jmp input_loop

replace_missing:
        ldx #0
        beq replace_copy
replace_text:
        ldx #7
replace_copy:
        ldy #0
replace_next:
        lda replacements,x
        sta N_APPNAME,y
        inx
        iny
        cpy #7
        bne replace_next
        lda #7
        sta N_NAMELEN
        lda N_BOOTDEVICE
        sta N_DEVICE
        lda #0
        sta N_APPFORMAT
        jmp N_REPLACE          ; no local display teardown

read_fixture:
        lda N_CURRENT
        sta N_FOWNER
        lda N_BOOTDEVICE
        sta N_FDEVICE
        lda #0
        sta N_FMODE
        sta N_FTYPE
        sta N_FFORMAT
        lda #8
        sta N_FNAMELEN
        ldx #7
copy_fixture_name:
        lda fixture_name,x
        sta N_FNAME,x
        dex
        bpl copy_fixture_name
        jsr N_FOPEN
        bcs fixture_failed
        lda #0
        sta N_FCOUNT
        lda #2
        sta N_FCOUNT+1
        jsr N_FREAD
        bcs fixture_failed
        lda N_FACTUAL
        bne fixture_bad
        lda N_FACTUAL+1
        cmp #2
        bne fixture_bad
        ldx #0
check_fixture_block:
        lda N_BUFFER,x
        cmp #$a5
        bne fixture_bad
        lda N_BUFFER+256,x
        cmp #$a5
        bne fixture_bad
        inx
        bne check_fixture_block
        jsr N_FREAD
        bcs fixture_failed
        lda N_FACTUAL
        cmp #1
        bne fixture_bad
        lda N_FACTUAL+1
        bne fixture_bad
        lda N_FEOF
        cmp #1
        bne fixture_bad
        lda N_BUFFER
        cmp #$a5
        bne fixture_bad
        jsr N_FCLOSE
        bcs fixture_failed
        lda #5
        sta phase
        jmp input_loop
fixture_bad:
        lda #N_CORRUPT
fixture_failed:
        sta error
        lda #4
        sta phase
        jmp input_loop

phase:          .byte 0
error:          .byte 0
active:         .byte 0
handle:         .fill 4,0
replacements:   .text "missingtextapp"
fixture_name:   .text "graphchk"
app_end:
.cerror app_end > N_APPBASE+$0400, "display experiment exceeds four pages"
