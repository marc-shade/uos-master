; UltOS VDC live-screen test — C64-mode PRG (U2+ run_prg).
;
; The earlier full re-init hung (bad timing halts the VDC). This version does
; NOT touch the timing registers or upload a font: it relies on the config the
; C128 kernal left in the 8563 at power-on (proven live: r0=$7f, r1=$50=80
; cols) and just writes to the screen. If the second monitor then shows a
; solid background + banner, the VDC+monitor chain works; if it stays blank
; the fault is the cable/monitor/8563 output, not software.
;
; No ready-waits (a single-select + auto-increment write is what the working
; ml-probe used). Live register read-back goes to VIC RAM $0400 (DMA-visible).

SEL   = $d600
SDAT  = $d601
SCR   = $0400
baseH = $02
baseL = $03
dpL   = $04
dpH   = $05

* = $0801
        .byte $0c,$08,$0a,$00,$9e
        .text " 2062"
        .byte $00,$00,$00

start:
        sei

        ; ---- attributes OFF so r26 sets the whole-screen colour ----
        lda #25
        sta SEL
        lda SDAT
        and #%10111111          ; clear bit6 (attribute enable)
        pha
        lda #25
        sta SEL
        pla
        sta SDAT
        ; ---- r26 = fg white / bg blue (VDC palette) ----
        lda #26
        sta SEL
        lda #$f6
        sta SDAT

        ; ---- read the live screen base (r12 hi, r13 lo) ----
        lda #12
        sta SEL
        lda SDAT
        sta baseH
        lda #13
        sta SEL
        lda SDAT
        sta baseL

        ; ---- set VDC update address = screen base ----
        lda #18
        sta SEL
        lda baseH
        sta SDAT
        lda #19
        sta SEL
        lda baseL
        sta SDAT

        ; ---- fill 2000 cells with spaces (select r31 once, auto-inc) ----
        lda #31
        sta SEL
        ldx #$00                ; 7 full pages
fp:     ldy #$00
fb:     lda #$20
        sta SDAT
        iny
        bne fb
        inx
        cpx #$07
        bne fp
        ldy #$00                ; + 208
ft:     lda #$20
        sta SDAT
        iny
        cpy #208
        bne ft

        ; ---- rewind update address to base, write the banner ----
        lda #18
        sta SEL
        lda baseH
        sta SDAT
        lda #19
        sta SEL
        lda baseL
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

        ; ---- dump live regs r0,r1,r12,r13,r24,r25,r26,r28 to VIC $0400 ----
        ; write as screen codes so the VIC 40-col side is readable too
        lda #<SCR
        sta dpL
        lda #>SCR
        sta dpH
        ldy #$00
        ldx #$00
rl:     lda regs,x
        sta SEL
        lda SDAT
        pha
        lsr
        lsr
        lsr
        lsr
        jsr hexsc               ; hi nibble as screen code
        sta (dpL),y
        iny
        pla
        and #$0f
        jsr hexsc
        sta (dpL),y
        iny
        lda #$00                ; space (screen code)
        sta (dpL),y
        iny
        inx
        cpx #$08
        bne rl

        lda #$2a
        sta $02c0               ; DMA status: done
hang:   jmp hang

; hex nibble -> VIC SCREEN CODE ('0'-'9'=$30-$39, 'A'-'F'=$01-$06)
hexsc:  cmp #$0a
        bcc hs0
        sec
        sbc #$09                ; A->1 .. F->6
        rts
hs0:    clc
        adc #$30
        rts

regs:   .byte 0,1,12,13,24,25,26,28
; banner is written to VDC screen RAM as SCREEN CODES via the kernal font;
; the 8563 with the kernal font maps codes like the VIC (upper case = 1..26)
vban:   .byte 21,15,19,32,22,4,3,32,12,9,22,5,33   ; "UOS VDC LIVE!"
        .byte 0
