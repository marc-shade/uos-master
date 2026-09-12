; Reserved tail of native-read's scratch: current probe ends before $3fc0.
; Host patches the KERNAL key-check vector only after installing both bodies.
* = $3fc0
        php
        sei
        pha
        txa
        pha
        tya
        pha
        lda $ff00
        pha
        lda #$0e
        sta $ff00
        jsr $5003
        pla
        sta $ff00
        pla
        tay
        pla
        tax
        pla
        plp
        jmp KEYCHECK_TARGET
        .cerror * > $3ff0, "input gate overlaps IRQ capture command"
