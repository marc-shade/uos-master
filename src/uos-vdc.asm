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

; ---- JUMP TABLE: fixed exports for the core (routines.inc) ----
; The routines below may grow or shrink freely; these slots never move.
; Before this table the exports were "natural order" addresses copied by
; hand into routines.inc, and they had drifted stale (VDC_CLS was listed
; as $cc88 while the real routine sat at $cc90, VDC_FONTUP $cce4 vs $ccb7,
; ...). The core was jumping into the middle of other routines — the real
; cause of every 80-column boot hang, and why the 80-col display never
; came up under uOS while a self-contained probe worked.
        jmp VDC_GETREG          ; $cc00
        jmp VDC_SETREG          ; $cc03
        jmp VDC_SEEK            ; $cc06
        jmp VDC_PUTS            ; $cc09
        jmp VDC_PUTCHR          ; $cc0c
        jmp VDC_CLS             ; $cc0f
        jmp VDC_FONTUP          ; $cc12
        jmp VDC_INIT            ; $cc15
        jmp VDC_PRESENT         ; $cc18
        jmp VDC_TEXT            ; $cc1b  A=row X=col r9->PETSCII (no-op until VDC_LIVE)
        jmp VDC_CLR             ; $cc1e  A=row -> 80 spaces (no-op until VDC_LIVE)
        jmp VDC_BANNER          ; $cc21  header rows 0-1
VDC_LIVE: .byte $00             ; $cc24  set to 1 by the core's VDSETUP once the 8563 is up

; VDC access is WAIT-FREE. The `bit $d600 / bpl` ready-guard stalls the boot
; on the real C128; register access needs no handshake, and back-to-back RAM
; writes via r31 auto-increment are spaced by the loop overhead at 1 MHz
; (proven on hardware, probes/vdc-fullinit.asm).

; read register X -> A
VDC_GETREG:
        stx VDC_ADDR
        lda VDC_DATA
        rts

; select register X, write A; X preserved
VDC_SETREG:
        sta vdcval
        stx VDC_ADDR
        lda vdcval
        sta VDC_DATA
        rts

; ready-wait: spin until status bit7 (ready). Preserves A and X.
; RAM access via r31 MUST wait: a write issued before the 8563 is ready is
; DROPPED and the auto-increment does not advance. This wait is UNBOUNDED,
; like the C128 kernal's own $CDCC/$CDD8 routines: on the real chip a
; 256-iteration bound still dropped runs of ~25 cells (hardware readback
; 2026-09-06 showed "Ul" + blanks in the header). Unbounded is safe
; because every caller runs after VDC_INIT (the display is up and the
; status bit toggles); the only place a wait ever hung was BEFORE init,
; and VDC_INIT does not wait at all.
vwait:  pha
vw_l:   bit VDC_ADDR
        bpl vw_l
        pla
        rts

; store A into the currently selected register's data port (r31), ready-waited
vdcpush:
        jsr vwait
        sta VDC_DATA
        rts

; select r31 (data port)
VDC_ST0:
        lda #VDC_R_DATA
        sta VDC_ADDR
        rts

; ---------- seek update address: A = lo, X = hi ----------
; r18 takes the HIGH byte, r19 the LOW byte; leaves r31 selected.
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
        jsr vwait                       ; settle before the first data store
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
        lda vdcdpL
        ldx vdcdpH
        jsr VDC_SEEK                    ; clobbers vdcval (SETREG scratch), so
                                        ; the char must NOT be parked there —
                                        ; the old code did, and wrote the
                                        ; seek's address byte instead
        lda (vdcbpL),y                  ; re-read; Y survives VDC_SEEK
        jsr p2s                         ; PETSCII -> screen code: the VDC
                                        ; font is indexed by SCREEN code, and
                                        ; writing PETSCII raw shows wrong glyphs
        jsr vdcpush                     ; char into screen cell (org+offset)
        lda vdcdpH
        clc
        adc #$08                        ; attribute plane is +$0800 — the old
        tax                             ; code re-sought the SAME cell and
        lda vdcdpL                      ; overwrote the glyph with $81
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
        pha                             ; keep the char: VDC_SEEK clobbers vdcval
        lda vdcdpL
        ldx vdcdpH
        jsr VDC_SEEK
        pla
        jsr vdcpush
        rts

; clear all 2000 screen cells to space, then all 2000 attributes to $81
; (2000 = 7 full pages + 208). The old loop ran cpx #$08 = only 8 cells —
; never caught because the core never reached this routine (stale export).
VDC_CLS:
        lda #$00                        ; screen plane at $0000
        ldx #$00
        jsr VDC_SEEK                    ; leaves r31 selected; writes auto-inc
        lda #$20
        ldx #$07
        jsr cls_fill
        lda #$00                        ; attribute plane at $0800
        ldx #$08
        jsr VDC_SEEK
        lda #$81
        ldx #$07
        jsr cls_fill
        rts
; fill A into (X full pages + 208) cells at the current auto-inc address.
; X holds the page count across the inner loop (which uses only Y).
cls_fill:
        sta vdcval
cls_pg: ldy #$00
cls_pb: lda vdcval
        jsr vdcpush
        iny
        bne cls_pb
        dex
        bne cls_pg
        ldy #$00                        ; + 208 tail
cls_tl: lda vdcval
        jsr vdcpush
        iny
        cpy #208
        bne cls_tl
        rts

; ---------- font upload: per-glyph bank-flip ----------
; Copies the C64 character ROM's lowercase/uppercase set ($d800, 2 KB) into
; the VDC lowercase bank at (R28 & $e0)<<8 + $1000, 16 B/glyph (8 rows + 8
; zero rows). The char ROM at $d000-$dfff is only visible with CHAREN clear,
; and that same banking HIDES the VDC at $d600 — so each glyph is read into
; a buffer with the ROM banked in, then written to the VDC with I/O banked
; back. IRQs are off for the whole copy (I/O hidden = no CIA for the IRQ).
; The old routine cleared the WRONG bit (HIRAM, not CHAREN), tried to read
; ROM and write the VDC in one banking state, and ran with IRQs live.
VDC_FONTUP:
        php
        sei
        lda $01
        pha                             ; restore banking on exit
        ldx #VDC_R_CHARBASE
        jsr VDC_GETREG                  ; A = R28 (I/O in)
        and #$e0
        clc
        adc #$10                        ; + $1000 -> lowercase bank
        sta vdcbaseHi
        lda #$00
        sta glyphn
fll:    ; --- VDC update address = bank + glyph*16 (I/O in) ---
        lda glyphn
        asl
        asl
        asl
        asl
        sta vdcdpL                      ; (glyph<<4) low byte
        lda glyphn
        lsr
        lsr
        lsr
        lsr
        clc
        adc vdcbaseHi
        sta vdcdpH
        lda vdcdpL
        ldx vdcdpH
        jsr VDC_SEEK                    ; r31 selected, auto-inc
        ; --- source = $d800 + glyph*8 ---
        lda glyphn
        asl
        asl
        asl
        sta srcL                        ; (glyph<<3) low byte
        lda glyphn
        lsr
        lsr
        lsr
        lsr
        lsr                             ; glyph>>5
        clc
        adc #$d8
        sta srcH
        ; --- read 8 rows: char ROM in, I/O (and the VDC) hidden ---
        lda $01
        and #%11111011                  ; CHAREN=0 -> char ROM at $d000
        sta $01
        ldy #$00
frd:    lda (srcL),y
        sta fbuf,y
        iny
        cpy #8
        bne frd
        lda $01
        ora #%00000100                  ; CHAREN=1 -> I/O back, VDC visible
        sta $01
        ; --- write 8 rows + 8 zero rows to the VDC ---
        ldy #$00
fwr:    lda fbuf,y
        jsr vdcpush
        iny
        cpy #8
        bne fwr
        lda #$00
fz0:    jsr vdcpush
        iny
        cpy #16
        bne fz0
        inc glyphn
        bne fll
        pla
        sta $01
        plp
        rts
fbuf:   .byte 0,0,0,0,0,0,0,0

; ---------- PETSCII -> screen code (standard C64 mapping) ----------
; A = PETSCII -> A = screen code. Control codes become a space.
p2s:    cmp #$20
        bcc p2s_sp
        cmp #$40
        bcc p2s_ok                      ; $20-$3f unchanged
        cmp #$60
        bcc p2s_m40                     ; $40-$5f -> -$40
        cmp #$80
        bcc p2s_m20                     ; $60-$7f -> -$20
        cmp #$a0
        bcc p2s_sp                      ; $80-$9f control
        cmp #$c0
        bcc p2s_m40                     ; $a0-$bf -> -$40
        cmp #$ff
        bcc p2s_m80                     ; $c0-$fe -> -$80
        lda #$5e                        ; $ff -> pi
        rts
p2s_m40: sec
        sbc #$40
        rts
p2s_m20: sec
        sbc #$20
        rts
p2s_m80: sec
        sbc #$80
        rts
p2s_sp: lda #$20
p2s_ok: rts

; ---------- apply the hardware-proven register table ----------
; (GEOS InitVDC semantics: $ff = leave unchanged)
; sets 80x25 character mode with display origin $0000
; COMPLETE init, r0..r36, written directly. The old table SKIPPED the
; vertical-timing registers (r4/r6/r7/r9...) with $ff, assuming the C128
; kernal had set them; after a C64-mode boot they are NOT set, so the VDC
; produced no lockable display. Every register now carries a real value
; (the set probes/vdc-fullinit.asm proved on the real C128).
VDC_INIT:
        ldx #$00
vinit_l:
        stx VDC_ADDR
        lda VDC_INIT_TABLE,x
        sta VDC_DATA
        inx
        cpx #37
        bne vinit_l
        rts

; r1=$50 (80 cols) r6=$19 (25 rows) r9=$07 (8 scanlines/char)
; r20/21=$0800 attribute base   r25=$47 attributes ENABLED (driver writes
; per-cell $81 attrs) r26=$00 background black (fg comes from the attribute)
; r28=$20 char base $2000 (VDC_FONTUP uploads to the lowercase bank $3000)
VDC_INIT_TABLE:
        .byte $7e,$50,$66,$49,$26,$00,$19,$20,$00,$07,$20,$07,$00,$00,$00,$00
        .byte $00,$00,$00,$00,$08,$00,$78,$e8,$20,$47,$00,$00,$20,$e7,$00,$00
        .byte $00,$00,$7d,$64,$00

; ---------- presence probe: A = 1 if an 8563 answers, else 0 ----------
; Register round-trip, run AFTER VDC_INIT: read back two registers the init
; just wrote (r1 = 80 columns, r6 = 25 rows). A real or emulated 8563
; returns them; a VDC-less C64 has the SID mirror at $d600/$d601, whose
; write-only registers never read back $50 then $19, so this fails closed.
; The previous probe watched status bit 7 for BOTH levels; that bit is the
; READY flag, which VICE holds constantly set, so under x128 it reported the
; VDC absent and the clear/font/banner were skipped (striped 80-col screen
; in the emulator while the real machine — where the bit happens to
; toggle — showed text). A deterministic read-back has no such dependency.
VDC_PRESENT:
        ldx #1
        jsr VDC_GETREG          ; r1: horizontal displayed
        cmp #$50                ; 80 columns, as VDC_INIT wrote
        bne vpr_no
        ldx #6
        jsr VDC_GETREG          ; r6: vertical displayed
        cmp #$19                ; 25 rows
        bne vpr_no
        lda #$01
        rts
vpr_no: lda #$00
        rts

vdcpr:  .byte 0
vprb0:  .byte 0
vprb1:  .byte 0

; ==========================================================
; 80-column companion text API. Lives in the driver (not the core): the
; core must stay below $1000 where the desktop loads, and these routines
; are only meaningful with the 8563 present anyway.
; VDC_TEXT: A = row (0-24), X = column (0-79), r9 ($14/$15) -> $00-
;           terminated PETSCII. VDC_CLR: A = row -> 80 spaces. Both are
;           no-ops until VDC_LIVE = 1, so apps call them unconditionally.
; The select/data pair is a two-step transaction: IRQs are held off around
; the write (php/sei ... plp keeps the caller's interrupt state).
; ==========================================================
r9L             = $14
r9H             = $15

VDC_TEXT:
        pha
        lda VDC_LIVE
        bne vt_go
        pla
        rts
vt_go:  pla
        jsr vd_cell             ; vdcdp = row*80 + col
        lda r9L
        sta vdcbpL
        lda r9H
        sta vdcbpH
        php
        sei
        jsr VDC_PUTS
        plp
        rts

VDC_CLR:
        ldx #$00
        pha
        lda #<vdblank
        sta r9L
        lda #>vdblank
        sta r9H
        pla
        jmp VDC_TEXT

; vdcdp (16-bit) = A*80 + X, by repeated addition (row <= 24)
vd_cell:
        stx vdtmp2
        sta vdtmp
        lda #$00
        sta vdcdpL
        sta vdcdpH
vc_l:   lda vdtmp
        beq vc_d
        lda vdcdpL
        clc
        adc #80
        sta vdcdpL
        bcc vc_n
        inc vdcdpH
vc_n:   dec vdtmp
        jmp vc_l
vc_d:   lda vdcdpL
        clc
        adc vdtmp2
        sta vdcdpL
        bcc vc_r
        inc vdcdpH
vc_r:   rts

; header rows 0-1 (called by the core after clear + font upload)
VDC_BANNER:
        lda #<vdcline1
        sta r9L
        lda #>vdcline1
        sta r9H
        lda #$00
        ldx #$00
        jsr VDC_TEXT
        lda #<vdcline2
        sta r9L
        lda #>vdcline2
        sta r9H
        lda #$01
        ldx #$00
        jmp VDC_TEXT

vdtmp:  .byte $00
vdtmp2: .byte $00
vdblank: .fill 80, $20
        .byte $00
vdcline1: .text "UltOS  80-column companion display", $00
vdcline2: .text "ultos menu (40-col, bottom left): apps  file manager  settings  shell  quit", 0
