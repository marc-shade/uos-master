; UltOS VDC full no-wait init test — C64-mode PRG (U2+ run_prg).
;
; Hypothesis: the 80-col monitor is blank under uOS (C64 mode) because uOS's
; VDC init SKIPS the vertical-timing registers (r4/r6/r7/r9...) assuming the
; C128 kernal already set them; after a C64-mode boot they aren't, so the VDC
; produces no lockable display. And a re-init that uses ready-waits hangs,
; because the wait never terminates until the VDC is already displaying.
;
; This writes the COMPLETE standard C128 80x25 text register set (r0-r36)
; with NO ready-waits, attributes off + r26 blue, then fills the screen and
; writes a banner. If the 80-col monitor now shows blue + banner, a complete
; no-wait init is the fix to port into uos-vdc.asm.

SEL   = $d600
SDAT  = $d601
SCR   = $0400
baseL = $02
baseH = $03

* = $0801
        .byte $0c,$08,$0a,$00,$9e
        .text " 2062"
        .byte $00,$00,$00

start:
        sei
        lda #$00
        sta $d020
        sta $d021

        ; ---- full register init, r0..r36, NO waits ----
        ldx #$00
ri:     stx SEL
        lda vtab,x
        sta SDAT
        inx
        cpx #37
        bne ri

        ; ---- screen base = $0000 (r12/r13 already 0); update addr -> $0000
        lda #18
        sta SEL
        lda #$00
        sta SDAT                ; r18 high = 0
        lda #19
        sta SEL
        lda #$00
        sta SDAT                ; r19 low = 0

        ; ---- fill 2000 cells with space (select r31 once, auto-inc) ----
        lda #31
        sta SEL
        ldx #$00
fp:     ldy #$00
fb:     lda #$20
        sta SDAT
        iny
        bne fb
        inx
        cpx #$07
        bne fp
        ldy #$00
ft:     lda #$20
        sta SDAT
        iny
        cpy #208
        bne ft

        ; ---- banner at $0000 ----
        lda #18
        sta SEL
        lda #$00
        sta SDAT
        lda #19
        sta SEL
        lda #$00
        sta SDAT
        lda #31
        sta SEL
        ldy #$00
bn:     lda vban,y
        beq bne
        sta SDAT
        iny
        bne bn
bne:

        ; ---- read back r0,r1,r6,r7,r9 to VIC $0400 (screen codes) ----
        lda #<SCR
        sta baseL
        lda #>SCR
        sta baseH
        ldy #$00
        ldx #$00
rl:     lda rr,x
        sta SEL
        lda SDAT
        pha
        lsr
        lsr
        lsr
        lsr
        jsr hexsc
        sta (baseL),y
        iny
        pla
        and #$0f
        jsr hexsc
        sta (baseL),y
        iny
        lda #$00
        sta (baseL),y
        iny
        inx
        cpx #$05
        bne rl

        lda #$2a
        sta $02c0
hang:   jmp hang

hexsc:  cmp #$0a
        bcc h0
        sec
        sbc #$09
        rts
h0:     clc
        adc #$30
        rts

rr:     .byte 0,1,6,7,9
; complete C128 80x25 text register set, r0..r36 (attr OFF via r25 bit6=0,
; r26 = fg white / bg blue so spaces paint blue)
vtab:   .byte $7e,$50,$66,$49,$26,$00,$19,$20,$00,$07,$20,$07,$00,$00,$00,$00
        .byte $00,$00,$00,$00,$08,$00,$78,$e8,$20,$07,$f6,$00,$27,$e7,$00,$00
        .byte $00,$00,$7d,$64,$00
vban:   .byte 21,15,19,32,22,4,3,32,80,73,89,88,69,76,83,33  ; "UOS VDC PIXELS!"
        .byte 0
