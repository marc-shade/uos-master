; Sample 32 interrupted foreground register sets through the KERNAL IRQ.
; Only for an idle app below $7400. Host backs up/restores $7c00..$7dff.
; $7cf0 old IRQ vector, $7cf2 count, $7cf3 done. Records at $7d00:
; PC lo/hi, A, X, Y, P, original SP, reserved. No ZP or I/O is borrowed.
* = $7c00
        php
        pha
        txa
        pha
        tya
        pha
        tsx
        lda $7cf2
        asl
        asl
        asl
        tay
        ; KERNAL stacked A/X/Y after the CPU stacked PC/P; this wrapper
        ; added four bytes above those six bytes.
        lda $0109,x
        sta $7d00,y
        lda $010a,x
        sta $7d01,y
        lda $0107,x
        sta $7d02,y
        lda $0106,x
        sta $7d03,y
        lda $0105,x
        sta $7d04,y
        lda $0108,x
        sta $7d05,y
        txa
        clc
        adc #10
        sta $7d06,y
        inc $7cf2
        lda $7cf2
        cmp #32
        bne return_irq
        lda $7cf0
        sta $0314
        lda $7cf1
        sta $0315
        lda #1
        sta $7cf3
return_irq:
        pla
        tay
        pla
        tax
        pla
        plp
        jmp ($7cf0)
        .cerror * > $7cf0, "IRQ sampler overlaps its parameters"
