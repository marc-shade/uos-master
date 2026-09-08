; One-shot desktop-tick client for the public NET_STREAM API.
; Host parameters at $5f00, command at $5500, captured packets at $6000.
; Record format: length word, clipped byte, raw data. No disk writes.
.include "../src/equates.inc"
.include "../src/routines.inc"

OLDTICK = $5f00
CMDLEN = $5f02
DONE = $5f04
RESULT = $5f05
CARRY = $5f06
COUNT = $5f07
FULL = $5f09
ENDPTR = $5f0a
CLIPPED = $5f0c

* = $5000
        lda OLDTICK
        sta $033c
        lda OLDTICK+1
        sta $033d
        lda #$00
        sta COUNT
        sta COUNT+1
        sta FULL
        sta ENDPTR
        sta NET_DIRMODE
        lda #$60
        sta ENDPTR+1
        lda #$00
        sta r0L
        lda #$55
        sta r0H
        lda CMDLEN
        sta r1L
        lda CMDLEN+1
        sta r1H
        lda #<receive
        sta r3L
        lda #>receive
        sta r3H
        jsr NET_STREAM
        sta RESULT
        php
        pla
        and #$01
        sta CARRY
        lda NET_TRUNC
        sta CLIPPED
        lda #$01
        sta DONE
        rts

receive:
        inc COUNT
        bne rc_counted
        inc COUNT+1
rc_counted:
        lda FULL
        beq rc_reserve
        clc
        rts
rc_reserve:
        ; Reserve the complete record, or skip it and all following ones.
        clc
        lda ENDPTR
        adc #$03
        sta candidate
        lda ENDPTR+1
        adc #$00
        sta candidate+1
        clc
        lda candidate
        adc NET_LEN
        sta candidate
        lda candidate+1
        adc NET_LEN+1
        cmp #$7c
        bcc rc_space
        bne rc_full
        lda candidate
        beq rc_space
rc_full:
        inc FULL
        bne rc_done
rc_space:
        lda ENDPTR
        sta r0L
        lda ENDPTR+1
        sta r0H
        ldy #$00
        lda NET_LEN
        sta remaining
        jsr put
        lda NET_LEN+1
        sta remaining+1
        jsr put
        lda NET_PACKET_TRUNC
        jsr put
        lda #<NET_DATA
        sta r2L
        lda #>NET_DATA
        sta r2H
rc_copy:
        lda remaining
        ora remaining+1
        beq rc_saved
        lda (r2),y
        jsr put
        inc r2L
        bne rc_dec
        inc r2H
rc_dec:
        lda remaining
        bne rc_declo
        dec remaining+1
rc_declo:
        dec remaining
        jmp rc_copy
rc_saved:
        lda r0L
        sta ENDPTR
        lda r0H
        sta ENDPTR+1
rc_done:
        clc
        rts

put:    sta (r0),y
        inc r0L
        bne put_done
        inc r0H
put_done:
        rts
candidate: .word 0
remaining: .word 0
        .cerror * > $5500, "probe overlaps command buffer"
