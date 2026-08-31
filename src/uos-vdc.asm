;==========================================================================
; UltOS uVDC — 8563/8568 VDC driver module (Gate G1 → M1)
; Reverse-engineered from the hardware-verified ~/code/claude-c128 client,
; the GEOS 128 reverse-engineered kernal, and the kernal ROM disassembly.
;
; Register facts encoded (all sourced, see probes/vdc-mlprobe):
;   r18 = update address HIGH, r19 = update address LOW (never swapped)
;   r31 = data port, auto-increment; guarded by bit $d600 / bpl before each
;         store, and a MANDATORY settle wait follows writing the address low
;   r28 bits 7-5 = char def base << 13; 512 defs of 16 B: 0-255 uppercase,
;         256-511 lowercase; attribute cell bit 7 selects the lowercase set
;
; Entry points at origin $cc00, natural order; mirrored in routines.inc:
;   VDC_GETREG  X = reg -> A          VDC_SETREG  X = reg, A = value
;   VDC_SEEK    A = lo, X = hi        VDC_PUTS    string (vdcbp) at cell (vdcdp)
;   VDC_PUTCHR  A = char              VDC_CLS     VDC_FONTUP
;==========================================================================

VDC_ADDR        = $d600
VDC_DATA        = $d601
VDC_R_HSTART    = 18
VDC_R_LSTART    = 19
VDC_R_DATA      = 31
VDC_R_CHARBASE  = 28

vdcbpL          = $23
vdcbpH          = $24
vdcdpL          = $25
vdcdpH          = $26
vdcbankHi       = $27
glyphn          = $28
srcL            = $29
srcH            = $2a
vdcbaseHi       = $2b
vdclo           = $2d
vdchi           = $2e
vdcval          = $2c

* = $cc00

; read register X -> A
VDC_GETREG:
        stx VDC_ADDR
gwt:    bit VDC_ADDR
        bpl gwt
        lda VDC_DATA
        rts

; select register X, write A (guarded); X preserved
VDC_SETREG:
        sta vdcval
        stx VDC_ADDR
swt:    bit VDC_ADDR
        bpl swt
        lda vdcval
        sta VDC_DATA
        rts

; guarded store of A into the currently selected register's data port
vdcpush:
        bit VDC_ADDR
        bpl vdcpush
        sta VDC_DATA
        rts

; select r31 guarded
VDC_ST0:
        lda #VDC_R_DATA
        sta VDC_ADDR
swf:    bit VDC_ADDR
        bpl swf
        rts

; ---------- seek update address: A = lo, X = hi ----------
; r18 takes the HIGH byte, r19 the LOW byte; settle after.
VDC_SEEK:
        sta vdclo
        stx vdchi
        lda vdchi
        sta vdcval
        ldx #VDC_R_HSTART
        jsr VDC_SETREG                  ; HIGH -> r18
        lda vdclo
        sta vdcval
        ldx #VDC_R_LSTART
        jsr VDC_SETREG                  ; LOW -> r19
        lda #VDC_R_DATA
        sta VDC_ADDR
sw4:    bit VDC_ADDR
        bpl sw4                         ; settle before any data store
        rts

; ---------- copy $00-terminated PETSCII at (vdcbp) to cells (vdcdp) ----------
; attributes = $81 (lowercase set, white) in the plane at org+$0800
VDC_PUTS:
        lda vdcdpH
        cmp #$08                        ; screen plane $0000-$07cf
        bcs vps_done
        ldy #$00
vps_l:  lda (vdcbpL),y
        beq vps_done
        sta vdcval
        lda vdcdpL
        ldx vdcdpH
        jsr VDC_SEEK
        lda vdcval
        jsr vdcpush                     ; char into screen cell
        lda vdcdpL
        ldx vdcdpH
        jsr VDC_SEEK
        lda #$81
        jsr vdcpush                     ; attribute into attr plane
        inc vdcdpL
        bne vps_c
        inc vdcdpH
vps_c:  iny
        bne vps_l
vps_done:
        rts

; write char A at cell (vdcdp)
VDC_PUTCHR:
        sta vdcval
        lda vdcdpL
        ldx vdcdpH
        jsr VDC_SEEK
        lda vdcval
        jsr vdcpush
        rts

; clear 2000 cells ($20) + 2000 attributes ($81)
VDC_CLS:
        lda #$00
        ldx #$00
        jsr VDC_SEEK
        ldx #$00
cls_chn:
        lda #$20
        jsr vdcpush
        inx
        cpx #$08
        bne cls_chn
        lda #$00
        ldx #$08
        jsr VDC_SEEK
        ldx #$00
cls_atn:
        lda #$81
        jsr vdcpush
        inx
        cpx #$08
        bne cls_atn
        rts

; ---------- font upload: 2 KB chargen -> lowercase defs ----------
; target = (R28 & $e0)<<8 + $1000 + glyph*16 (8 pattern rows + 8 zero rows);
; clears CHAREN (bit 2 of $01) for the whole copy.
VDC_FONTUP:
        lda $01
        pha
        and #%11111101
        sta $01
        ldx #VDC_R_CHARBASE
        jsr VDC_GETREG                  ; A = R28
        and #$e0                        ; def base high byte
        clc
        adc #$10                        ; + $1000 -> lowercase bank
        sta vdcbaseHi
        lda #$00
        sta glyphn
fll:    lda glyphn
        asl
        asl
        asl
        asl                             ; glyph<<4 (low byte)
        sta vdcdpL
        lda glyphn
        lsr
        lsr
        lsr
        lsr                             ; glyph>>4
        clc
        adc vdcbaseHi
        sta vdcdpH
        lda vdcdpL
        ldx vdcdpH
        jsr VDC_SEEK
        ; source pointer = $d000 + glyph*8
        lda #<$d000
        sta srcL
        lda #>$d000
        sta srcH
        lda glyphn
        asl
        asl
        asl
        clc
        adc srcL
        sta srcL
        bcc fno
        inc srcH
fno:
        jsr VDC_ST0                     ; select r31, guarded
        ldy #0
fpat:   lda (srcL),y
        jsr vdcpush
        iny
        cpy #8
        bne fpat
        lda #0                          ; 8 zero rows: defs are 16 cells
        ldy #8
fz0:    jsr vdcpush
        iny
        cpy #16
        bne fz0
        inc glyphn
        bne fll
        pla
        sta $01
        rts

; ---------- apply the hardware-proven register table ----------
; (GEOS InitVDC semantics: $ff = leave unchanged)
; sets 80x25 character mode with display origin $0000
VDC_INIT:
        ldx #36
vinit_l:
        lda VDC_INIT_TABLE,x
        cmp #$ff
        beq vinit_n
        ; keep X for VDC_SETREG: it preserves X (guarded by VDC_ADDR only)
        jsr VDC_SETREG
vinit_n:
        dex
        bpl vinit_l
        rts

VDC_INIT_TABLE:
        .byte $7e,$50,$66,$49,$ff,$e0,$ff,$20,$fc,$ff,$a0,$e7,$00,$00,$00,$00
        .byte $ff,$ff,$ff,$ff,$ff,$ff,$78,$e8,$ff,$ff,$ff,$00,$ff,$f8,$ff,$ff
        .byte $ff,$ff,$7d,$64,$ff

; ---------- presence probe: A = 1 if an 8563 answers, else 0 ----------
; The VDC status byte's vblank bit (7) toggles ~50/60 Hz in normal
; operation. Watch it for ~64K reads: BOTH levels must be seen. On a
; VDC-less machine $d600 is SID/sidcart space and the byte there is stable
; (read-what-you-wrote on a write-only register), so exactly one level is
; ever seen -> absent. This replaces the earlier r31 round-trip probe,
; which a SID register alias can pass. The result gates VDSETUP: the
; guarded waits in the rest of the driver never terminate without a VDC.
VDC_PRESENT:
        lda #$00
        sta vdcpr
        sta vprb0               ; saw bit7 clear
        sta vprb1               ; saw bit7 set
        ldx #$00                ; X counts 256 passes of 256 samples
vpr_l:  ldy #$00
vpr_s:  lda VDC_ADDR
        bpl vpr_zero
        inc vprb1
        jmp vpr_nx
vpr_zero:
        inc vprb0
vpr_nx: iny
        bne vpr_s
        inx
        bne vpr_l               ; 65536 samples total, then decide
        lda vprb0
        beq vpr_done
        lda vprb1
        beq vpr_done
        lda #$01
        sta vdcpr
vpr_done:
        lda vdcpr
        rts

vdcpr:  .byte 0
vprb0:  .byte 0
vprb1:  .byte 0