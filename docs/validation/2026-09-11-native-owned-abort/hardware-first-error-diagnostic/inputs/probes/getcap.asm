; One-shot desktop tick: call the public GETCAP entry with every 8-bit id.
; Host supplies old tick at $5f00; completion byte at $5f02 must start at 0.
; Low bytes at $6000, high bytes at $6100. GETCAP promises to preserve Y.
.include "../src/routines.inc"

* = $5000
        lda $5f00
        sta $033c
        lda $5f01
        sta $033d
        ldy #$00
next:   tya
        tax
        lda #$a5
        jsr GETCAP
        sta $6000,y
        txa
        sta $6100,y
        iny
        bne next
        lda #$01
        sta $5f02
        rts
        .cerror * > $5100, "GETCAP probe exceeds its reserved page"
