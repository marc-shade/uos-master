; UltOS VDC full-display test — C64-mode PRG (run via U2+ run_prg).
;
; Purpose: settle "is the 80-column VDC + monitor chain alive?" independent of
; uOS. Does a COMPLETE, known-good 80x25 text init, uploads the C64 character
; ROM into VDC RAM, then fills the whole VDC screen with a bright background
; and writes an unmistakable banner. If the second monitor shows a solid
; colour + "UOS VDC FULL TEST ..." the VDC and the display chain work; if it
; stays blank the problem is the cable/monitor/8563 output, not software.
;
; It also copies the VDC register read-back and a status byte into VIC screen
; RAM ($0400, DMA-readable) so the host can verify the init took even without
; eyes on the 80-col monitor.
;
; VDC RAM map (16K): screen $0000, attributes $0800, font $2000.

dpL   = $02
dpH   = $03
srcL  = $04
srcH  = $05
dstL  = $06
dstH  = $07
cnt   = $08
tmp   = $09

SEL   = $d600
SDAT  = $d601
SCR   = $0400

* = $0801
        .byte $0c,$08,$0a,$00,$9e
        .text " 2062"
        .byte $00,$00,$00

start:
        sei
        lda #$00
        sta $d020
        sta $d021

        ; ---- clear VIC screen (status area) ----
        ldx #$00
vclr:   lda #$20
        sta SCR,x
        sta SCR+$100,x
        sta SCR+$200,x
        sta SCR+$300,x
        lda #$0d
        sta $d800,x
        sta $d900,x
        sta $da00,x
        sta $db00,x
        inx
        bne vclr

        ; status headline on the VIC screen
        ldy #$00
h1:     lda msg1,y
        beq h1e
        sta SCR,y
        iny
        bne h1
h1e:

        ; ---- 1. full VDC register init (r0..r36 from table) ----
        ldx #$00
ri:     lda vtab,x
        ldy vtab_r,x            ; register number
        cpy #$ff
        beq rie                 ; $ff sentinel = end
        jsr vset
        inx
        bne ri
rie:

        ; ---- 2. upload the C64 char ROM to VDC RAM $2000 (16 B/char) ----
        ; bank the character ROM in at $d000 ($01: clear bit2)
        lda $01
        sta tmp
        and #$fb                ; bit2=0 -> char ROM visible $d000-$dfff
        sta $01
        ; VDC update address -> $2000
        lda #$20
        ldx #$00
        jsr vseek
        ; copy 256 chars: 8 ROM bytes then 8 zero bytes each
        lda #$d0
        sta srcH
        lda #$00
        sta srcL
        ldx #$00                ; char counter (256 wraps to 0)
fc_ch:  ldy #$00
fc_b:   lda (srcL),y            ; 8 glyph rows
        jsr vwr
        iny
        cpy #$08
        bne fc_b
        lda #$00                ; 8 pad rows
fc_p:   jsr vwr
        iny
        cpy #$10
        bne fc_p
        ; advance src by 8
        lda srcL
        clc
        adc #$08
        sta srcL
        bcc fc_nc
        inc srcH
fc_nc:  inx
        bne fc_ch               ; 256 chars
        lda tmp
        sta $01                 ; restore banking

        ; ---- 3. fill the screen ($0000, 2000 cells) with spaces ----
        lda #$00
        ldx #$00
        jsr vseek
        ldx #$00                ; 2000 = 7*256 + 208
fs_pg:  ldy #$00
fs_b:   lda #$20                ; space (shows the background colour)
        jsr vwr
        iny
        bne fs_b
        inx
        cpx #$07
        bne fs_pg
        ldy #$00
fs_t:   lda #$20
        jsr vwr
        iny
        cpy #208
        bne fs_t

        ; ---- 4. write the banner at row 0 ($0000) ----
        lda #$00
        ldx #$00
        jsr vseek
        ldy #$00
bn:     lda vban,y
        beq bne
        jsr vwr                 ; screen codes = ASCII-ish here; font is ROM
        iny
        bne bn
bne:

        ; ---- 5. dump r0-r7 read-back to the VIC screen row 2 ----
        lda #<SCR+80
        sta dpL
        lda #>SCR+80
        sta dpH
        ldx #$00
        ldy #$00
rd:     txa
        jsr vget                ; A = reg X value
        pha
        txa
        clc
        adc #'0'
        sta (dpL),y
        iny
        lda #'='
        sta (dpL),y
        iny
        pla
        pha
        lsr
        lsr
        lsr
        lsr
        jsr hexn
        sta (dpL),y
        iny
        pla
        and #$0f
        jsr hexn
        sta (dpL),y
        iny
        lda #$20
        sta (dpL),y
        iny
        inx
        cpx #$08
        bne rd

        ; status byte for DMA: $02c0 = $2a ('done')
        lda #$2a
        sta $02c0

hang:   jmp hang

; ---- helpers ----------------------------------------------------------
; vset: select register Y, write A  (guarded)
vset:   sty SEL
vsw:    bit SEL
        bpl vsw
        sta SDAT
        rts

; vget: select register X, read -> A (guarded)
vget:   stx SEL
vgw:    bit SEL
        bpl vgw
        lda SDAT
        rts

; vseek: set the VDC update address to A=hi, X=lo (r18=hi, r19=lo)
vseek:  pha
        ldy #18
        sty SEL
vk1:    bit SEL
        bpl vk1
        sta SDAT                ; r18 high
        txa
        ldy #19
        sty SEL
vk2:    bit SEL
        bpl vk2
        sta SDAT                ; r19 low
        pla
        rts

; vwr: write A to the VDC data port r31 (auto-increment), guarded
vwr:    pha
        ldy #31
        sty SEL
vww:    bit SEL
        bpl vww
        pla
        sta SDAT
        rts

hexn:   cmp #$0a
        bcc hn1
        clc
        adc #$07
hn1:    clc
        adc #$30
        rts

; ---- known-good 80x25 text register values (r, value) -----------------
; r0 htotal r1 hdisp=80 r2 hsync r3 syncw r4 vtotal r5 vadjust r6 vdisp=25
; r7 vsync r8 interlace r9 chartotal=7 r10 cursor r12/13 screen=$0000
; r14/15 cursor r20/21 attr=$0800 r22 charwidth r23 charheight r24 vscroll
; r25 mode(attr off) r26 fg/bg r27 addr-inc r28 charbase=$2000
vtab_r: .byte 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
        .byte 20,21,22,23,24,25,26,27,28,34,35,$ff
vtab:   .byte $7e,$50,$66,$49,$26,$00,$19,$1d,$fc,$07,$20,$e7,$00,$00,$00,$00
        .byte $08,$00,$78,$e8,$20,$07,$f6,$00,$20,$7d,$64

msg1:   .text "vdc full test running - look at 80-col monitor", 0
vban:   .text "UOS VDC FULL TEST - IF YOU SEE THIS THE 80-COL VDC WORKS", 0
