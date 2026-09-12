; One-shot input-dispatch probe, loaded at $7f00. Parameters at $7fe0:
; old tick word, TESTCLICK routine word, VIC x-low/x-high/y bytes, done, hit.
; Restore the pointer and IRQ state before entering the registered callback.
.include "../src/equates.inc"
* = $7f00
        lda $7fe0
        sta $033c
        lda $7fe1
        sta $033d
        php
        sei
        lda $d000
        pha
        lda $d001
        pha
        lda $d010
        pha
        and #$fe
        ora $7fe5
        sta $d010
        lda $7fe4
        sta $d000
        lda $7fe6
        sta $d001
        jsr hit_test
        sta $7fe8
        pla
        sta $d010
        pla
        sta $d001
        pla
        sta $d000
        plp
        lda #1
        sta $7fe7
        lda $7fe8
        beq no_hit
        jmp (r4L)
no_hit: rts
hit_test:
        jmp ($7fe2)
        .cerror * > $7fe0, "control probe overlaps parameters"
