; probe: how does the serial bus report an ABSENT device?
; $0700 = 1 + OPEN carry   $0701 = ST after OPEN
; $0702 = kernal IEC timeout flag ($0291)
; $0703 = ST after TALK(dev9)/TKSA(15) + ACPTR on an absent device
        * = $0801
        .word $080b, 2026
        .byte $9e
        .text "2061", $00
        .byte $00, $00
        lda #$03
        ldx #$09
        ldy #$0f
        jsr $ffba               ; SETLFS
        lda #$00
        ldx #$00
        ldy #$00
        jsr $ffbd               ; SETNAM (no name)
        clc
        jsr $ffc0               ; OPEN
        php
        jsr $ffb7               ; READST
        and #$7f
        sta $0701
        lda #$03
        jsr $ffc3               ; CLOSE
        plp
        lda #$01
        adc #$00
        sta $0700
        ; --- raw serial path ---
        lda $0291
        sta $0702
        lda #$00
        sta $0291               ; timeout ON
        lda #$49                ; TALK device 9
        jsr $ffb4
        lda #$6f                ; TKSA 15
        jsr $ff96
        jsr $ffb7               ; READST
        sta $0703
        lda #$00
        jsr $ffab               ; UNTALK? (UNTLK = $ffab with A=0)
        ; --- same TALK on the PRESENT device 8 for comparison ---
        lda #$48                ; TALK device 8
        jsr $ffb4
        lda #$6f                ; TKSA 15
        jsr $ff96
        jsr $ffb7               ; READST
        sta $0704
        lda #$00
        jsr $ffab               ; UNTALK
        rts