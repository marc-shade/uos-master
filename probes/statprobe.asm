; probe: OPEN 15 (cmd), OPEN 2 "NOTES.T,S,R", read the command channel into
; $6000 (status string), then close. $60ff=$a5 when done. Run at $c000 via
; the desktop tick trampoline.
.include "kernal.inc"
        * = $c000
        lda #$0f
        ldx $ba
        ldy #$0f
        jsr SETLFS
        lda #$00
        jsr SETNAM
        jsr OPEN
        lda #$02
        ldx $ba
        ldy #$02
        jsr SETLFS
        lda #11
        ldx #<nm
        ldy #>nm
        jsr SETNAM
        jsr OPEN
        lda $90
        sta $60fe              ; ST after OPEN 2
        ldx #$0f
        jsr CHKIN
        ldy #$00
rd:     jsr READST
        and #$40
        bne done
        jsr CHRIN
        sta $6000,y
        iny
        cpy #$28
        bne rd
done:   jsr CLRCHN
        lda #$02
        jsr CLOSE
        lda #$0f
        jsr CLOSE
        lda #$a5
        sta $60ff
        rts
nm:     .byte $4e,$4f,$54,$45,$53,$2e,$54,$2c,$53,$2c,$52   ; "NOTES.T,S,R"
