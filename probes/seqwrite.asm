; minimal SEQ write probe: OPEN 2,dev,2,"SWTEST,S,W" / write "AB" / close.
; run at $c000 via the desktop tick trampoline; sets $6000=$a5 when done.
.include "kernal.inc"
        * = $c000
        lda #$02
        ldx $ba
        ldy #$02
        jsr SETLFS
        lda #10
        ldx #<nm
        ldy #>nm
        jsr SETNAM
        jsr OPEN
        ldx #$02
        jsr CHKOUT
        lda $90
        sta $6001              ; ST after CHKOUT
        lda #$41
        jsr CHROUT
        lda #$42
        jsr CHROUT
        jsr CLRCHN
        lda #$02
        jsr CLOSE
        lda #$a5
        sta $6000
        rts
nm:     .byte $53,$57,$54,$45,$53,$54,$2c,$53,$2c,$57   ; "SWTEST,S,W"
