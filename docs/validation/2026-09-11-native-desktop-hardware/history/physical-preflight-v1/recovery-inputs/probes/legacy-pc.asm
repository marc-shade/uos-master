; One-shot C64-mode IRQ observation. Preserve the handler's registers/status.
; KERNAL has stacked A/X/Y above the hardware P/PC frame before ($0314).
; Borrow $7e00..$7eff, above all app images and below the liveness trampoline.
.include "../src/equates.inc"
* = $7e00
        php
        pha
        txa
        pha
        tya
        pha
        tsx
        stx $7ef3
        lda $0109,x
        sta $7ef4
        lda $010a,x
        sta $7ef5
        lda $0108,x
        sta $7ef6
        lda $00
        sta $7ef7
        lda $01
        sta $7ef8
        lda r16
        sta $7ef9
        lda $dc09
        sta $7efa
        lda $dc00
        sta $7efb
        lda $dc01
        sta $7efc
        lda $df1c
        sta $7efd
        lda $7ef0
        sta $0314
        lda $7ef1
        sta $0315
        lda #1
        sta $7ef2
        pla
        tay
        pla
        tax
        pla
        plp
        jmp ($7ef0)
        .cerror * > $7ef0, "PC observer overlaps its record"
