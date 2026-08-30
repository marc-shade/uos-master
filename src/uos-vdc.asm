;==========================================================================
; UltOS uVDC — 8563/8568 VDC driver module  (fork increment: Gate G1 → M1)
;
; Character-mode 80x25 driver for the second display. Mirrors the uOS
; status/menu layer onto the VDC while the VIC-II keeps its 40-col desktop.
;
; Memory origin: $cc00 (uos-gfx ends below that).
; Entry points are published in routines.inc with the addresses this module
; actually assembles to (see the .lst after building).
; Access convention per kernal/GEOS: select $D600, transfer $D601.
; The chip needs no ready-wait on these paths (see probes/vdc-mlprobe).
;==========================================================================

SEL     = $d600
SDATA   = $d601
vdcbpL  = $fb                 ; caller-provided string pointer (zero page)
vdcbpH  = $fc
vdcdpL  = $fd                 ; caller-provided VDC cell pointer (zero page)
vdcdpH  = $fe

* = $cc00

; read register X -> A
VDC_GETREG:
        stx SEL
        lda SDATA
        rts

; write A to register X
VDC_SETREG:
        sta vdcval
        stx SEL
        lda vdcval
        sta SDATA
        rts

; seek VDC RAM word: A = lo, X = hi
VDC_SEEK:
        sta vdclo
        stx vdchi
        lda #$12                       ; r18: update pointer low
        sta SEL
        lda vdclo
        sta SDATA
        lda #$13                       ; r19: update pointer high
        sta SEL
        lda vdchi
        sta SDATA
        rts

; copy $00-terminated PETSCII at (bp) to screen cells at (dp);
; attributes in the plane at org+$0800 are set to $01 (white)
VDC_PUTS:
        lda vdcdpH
        cmp #$08                       ; screen plane is $0000-$07CF
        bcs vps_done
        ldy #$00
vps_l:  lda (vdcbpL),y
        beq vps_done
        sta vdcch
        jsr vseekdp
        lda vdcch
        sta SDATA                      ; screen byte

        lda vdcdpH                        ; attribute hi = vdcdpH + $08
        clc
        adc #$08
        sta vdchi
        lda vdcdpL
        sta vdclo
        lda #$12
        sta SEL
        lda vdclo
        sta SDATA
        lda #$13
        sta SEL
        lda vdchi
        sta SDATA
        lda #$01                       ; white attribute
        sta SDATA

        inc vdcdpL
        bne vps_y
        inc vdcdpH
vps_y:  iny
        bne vps_l
vps_done:
        rts

; write char in A at cell (dp)
VDC_PUTCHR:
        sta vdcch
        jsr vseekdp
        lda vdcch
        sta SDATA
        rts

; clear 2000 cells to $20, attributes to $01 (r31 = linear auto-increment)
VDC_CLS:
        lda #$00
        ldx #$00
        jsr VDC_SEEK
        lda #$1f
        sta SEL
        ldx #$08                       ; 8 x 250
        lda #$20
cls_chp:
        ldy #$00
cls_chr: sta SDATA
        iny
        cpy #$fa
        bne cls_chr
        inx
        bne cls_chp

        lda #$00
        ldx #$08                       ; attribute plane at $0800
        jsr VDC_SEEK
        lda #$1f
        sta SEL
        ldx #$08
        lda #$01
cls_atp:
        ldy #$00
cls_atr: sta SDATA
        iny
        cpy #$fa
        bne cls_atr
        inx
        bne cls_atp
        rts

; internal: point r18/r19 at cell (dp)
vseekdp:
        lda vdcdpL
        sta vdclo
        lda vdcdpH
        sta vdchi
        lda #$12
        sta SEL
        lda vdclo
        sta SDATA
        lda #$13
        sta SEL
        lda vdchi
        sta SDATA
        rts

vdcval: .byte $00
vdcch:  .byte $00
vdclo:  .byte $00
vdchi:  .byte $00