; OPEN 2 "NOPE.T,S,R" (missing), report ST after OPEN and after 1 CHRIN.
.include "kernal.inc"
        * = $c000
        lda #$02
        ldx $ba
        ldy #$02
        jsr SETLFS
        lda #8
        ldx #<nm
        ldy #>nm
        jsr SETNAM
        jsr OPEN
        lda $90
        sta $60f0              ; ST after OPEN (missing file)
        ldx #$02
        jsr CHKIN
        lda $90
        sta $60f1              ; ST after CHKIN
        jsr CHRIN
        sta $60f2              ; first byte
        lda $90
        sta $60f3              ; ST after 1st CHRIN
        jsr CLRCHN
        lda #$02
        jsr CLOSE
        lda #$a5
        sta $60ff
        rts
nm:     .byte $4e,$4f,$50,$45,$2c,$53,$2c,$52   ; "NOPE,S,R"
