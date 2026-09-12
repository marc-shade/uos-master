; Disposable native display placement/IRQ experiment, GPL v3.
; This client restores its own display; it is not a kernel display lease.
.include "api.inc"
* = N_APPBASE
app_image:
        .text "napp"
        .byte 1,1,7,0
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
        ; Restrict this experiment to the observed native text setup.
        lda $ff00
        cmp #$0e
        beq *+5
        jmp platform_error
        lda $d506
        and #$4f
        cmp #4
        beq *+5
        jmp platform_error
        lda $d8
        beq *+5
        jmp platform_error
        lda $00
        and #6
        cmp #6
        bne platform_error
        lda $d01a
        and #15
        cmp #1
        bne platform_error
        lda $d011
        and #$60
        bne platform_error
        lda $d016
        and #$10
        bne platform_error
        lda $dd02
        and #3
        cmp #3
        bne platform_error
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
        jsr enter_display
        lda #2
        sta phase
        bne input_loop
platform_error:
        lda #N_PLATFORM
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
        cmp #$1b
        bne input_loop
        jsr release_display
        lda error
        jmp N_EXIT
normal_return:
        jsr release_display
        lda error
        rts

enter_display:
        php
        sei
        lda $d8
        sta saved_d8
        lda $d011
        and #$7f
        sta saved_d011
        lda $d016
        sta saved_d016
        lda $d018
        sta saved_d018
        lda $dd00
        and #3
        sta saved_vic_bank
        lda $01
        and #6
        sta saved_port
        lda #$ff
        sta $d8                ; current KERNAL skips its split/mode writes
        sta $d012              ; retain the native text raster compare (255)
        lda $01
        and #$fd
        ora #4
        sta $01                ; same VIC ROM/color-bank selection as C128 bitmap IRQ
        lda #$80
        sta $d018              ; matrix $e000, bitmap $c000, VIC bank $c000
        lda saved_d016
        and #$ef
        sta $d016
        lda saved_d011
        ora #$20
        sta $d011              ; bit 7 is compare-high on write, not readback
        lda $dd00
        and #$fc
        sta $dd00
        lda #1
        sta active
        plp
        rts

release_display:
        lda active
        beq free_surface
        php
        sei
        lda $dd00
        and #$fc
        ora saved_vic_bank
        sta $dd00
        lda saved_d018
        sta $d018
        lda saved_d016
        sta $d016
        lda #$ff
        sta $d012
        lda saved_d011
        sta $d011
        lda $01
        and #$f9
        ora saved_port
        sta $01
        lda saved_d8
        sta $d8
        lda #0
        sta active
        plp
free_surface:
        lda handle
        beq released
        lda N_CURRENT
        sta N_OWNER
        ldx #3
restore_handle:
        lda handle,x
        sta N_HANDLE,x
        dex
        bpl restore_handle
        jsr N_FREE
        bcc released
        ldx error
        bne released
        sta error
released:
        lda #3
        sta phase
        rts

phase:          .byte 0
error:          .byte 0
active:         .byte 0
handle:         .fill 4,0
saved_d8:       .byte 0
saved_d011:     .byte 0
saved_d016:     .byte 0
saved_d018:     .byte 0
saved_vic_bank: .byte 0
saved_port:     .byte 0
app_end:
.cerror app_end > N_APPBASE+$0400, "display experiment exceeds four pages"
