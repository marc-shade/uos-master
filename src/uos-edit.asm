;==========================================================================
; UltOS text editor (uos-edit) — create/edit/save a text file.
;
;   This file is part of UltOS (GPL v3, see uos.asm).
;
; A minimal but complete note editor: type text, RETURN for a new line,
; DEL to backspace, F1 to save, ESC to exit to the desktop. On entry it
; loads NOTES.T if present. Append-style editing (DEL removes the last
; character); the whole buffer is re-rendered on every change (it is small,
; correctness over speed). Both displays are drawn: the 40-column VIC via
; the proportional GPUTS engine and the 80-column VDC monospace mirror.
;
; Save/load use a SEQ file "NOTES.T" over the KERNAL. The editor owns the
; keyboard (its own KEYIN loop) like the file manager and shell.
;==========================================================================

.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "kernal.inc"
.include "vic-ii.inc"
.include "io.inc"

EDPAGES         = 3             ; read bound = 3*256 bytes (bulletproof)
EDMAX           = 768            ; buffer cap (EDPAGES*256)
LW              = 38             ; wrap width
MAXLINES        = 18             ; visible text lines
EDX             = 16            ; VIC text-area origin x
EDY             = 24            ; VIC text-area origin y
EDLH            = 9             ; VIC line height (px)

edptr           = $40           ; render/scan pointer (apps own $40-$4f)
ecnt            = $42           ; chars consumed (word)
eline           = $44           ; current output line
etmp            = $45
elx             = $46
edcnt           = $47

* = APP_START

        #RegisterApp

        #DrawRect 8, 6, 304, 188, 1
        #Text 16, 12, ed_title
        #Text 16, 182, ed_hint

        ; 80-column companion: title row 2, hint row 23
        jsr ed_vdclear
        lda #<ed_title
        sta r9L
        lda #>ed_title
        sta r9H
        lda #$02
        ldx #$00
        jsr VDTEXT
        lda #<ed_hint
        sta r9L
        lda #>ed_hint
        sta r9H
        lda #$17                        ; row 23
        ldx #$00
        jsr VDTEXT

        jsr ed_load                     ; NOTES.T -> edbuf (empty if absent)
        jsr ed_render

edloop:
        jsr KEYIN
        cmp #$00
        beq edloop
        cmp #$1b                        ; ESC -> desktop
        beq ed_exit
        cmp #$85                        ; F1 -> save
        beq _ek_save
        cmp #$14                        ; DEL -> backspace
        beq _ek_bs
        cmp #$0d                        ; RETURN -> newline
        beq _ek_add
        cmp #$20                        ; ignore other control codes
        bcc edloop
        cmp #$7b
        bcs edloop
_ek_add:
        jsr ed_addchar
        jmp edloop
_ek_bs:
        jsr ed_backspace
        jmp edloop
_ek_save:
        jsr ed_save
        jmp edloop

ed_exit:
        #UnregisterApp
        jsr LOAD_IMM
        .text "uos-desktop",$00
        jsr APP_LOADER
        jmp DESK_START

; ---------- edit primitives ----------
; A = char to append (printable or $0d)
ed_addchar:
        pha
        lda edlen+1                     ; edlen >= EDMAX ?
        cmp #>EDMAX
        bcc _ea_ok
        lda edlen
        cmp #<EDMAX
        bcc _ea_ok
        pla                             ; full: drop the key
        rts
_ea_ok:
        clc
        lda #<edbuf
        adc edlen
        sta edptr
        lda #>edbuf
        adc edlen+1
        sta edptr+1
        pla
        ldy #$00
        sta (edptr),y
        inc edlen
        bne _ea_r
        inc edlen+1
_ea_r:  jsr ed_render
        rts

ed_backspace:
        lda edlen
        ora edlen+1
        bne _eb_go
        rts                             ; empty
_eb_go: lda edlen
        bne _eb_l
        dec edlen+1
_eb_l:  dec edlen
        jsr ed_render
        rts

; ---------- render the whole buffer ----------
ed_render:
        #ClrRect EDX, EDY, 296, (MAXLINES*EDLH)
        lda #$03                        ; clear VDC text rows 3..20
        jsr ed_vdrows
        lda #<edbuf
        sta edptr
        lda #>edbuf
        sta edptr+1
        lda #$00
        sta ecnt
        sta ecnt+1
        sta eline
_er_line:
        ldx #$00                        ; elbuf index
_er_ch:
        lda ecnt+1                      ; ecnt >= edlen ?  (end of buffer)
        cmp edlen+1
        bcc _er_more
        bne _er_last
        lda ecnt
        cmp edlen
        bcs _er_last
_er_more:
        ldy #$00
        lda (edptr),y
        inc edptr
        bne _er_i1
        inc edptr+1
_er_i1: inc ecnt
        bne _er_i2
        inc ecnt+1
_er_i2: cmp #$0d                        ; newline ends the line
        beq _er_draw
        sta elbuf,x
        inx
        cpx #LW
        bcc _er_ch
_er_draw:
        lda #$00
        sta elbuf,x
        jsr ed_drawline
        inc eline
        lda eline
        cmp #MAXLINES
        bcs _er_done
        jmp _er_line
_er_last:
        lda #$00
        sta elbuf,x
        cpx #$00
        beq _er_done                    ; nothing left on the last line
        jsr ed_drawline
_er_done:
        ; draw the cursor block at the end of the last line
        rts

; draw elbuf at line `eline`: VIC proportional + VDC monospace
ed_drawline:
        stx elx                         ; GPUTS clobbers X
        lda #EDX
        sta X1
        lda #$00
        sta X1+1
        lda eline                       ; Y1 = EDY + eline*EDLH (9 = 8+1)
        asl
        asl
        asl
        sta etmp                        ; eline*8
        lda eline
        clc
        adc etmp                        ; +eline -> *9
        clc
        adc #EDY
        sta Y1
        lda #<elbuf
        sta r9L
        lda #>elbuf
        sta r9H
        jsr GPUTS
        lda #<elbuf
        sta r9L
        lda #>elbuf
        sta r9H
        clc
        lda eline
        adc #$03                        ; VDC text rows start at 3
        ldx #$02
        jsr VDTEXT
        ldx elx
        rts

; ---------- 80-column helpers ----------
ed_vdclear:
        lda #$02
_evc_l: pha
        jsr VDCLR
        pla
        clc
        adc #$01
        cmp #24
        bne _evc_l
        rts

; clear VDC rows A..20
ed_vdrows:
_evr_l: pha
        jsr VDCLR
        pla
        clc
        adc #$01
        cmp #21
        bne _evr_l
        rts

; ---------- save / load (SEQ file NOTES.T) ----------
ed_save:
        jsr ed_scratch                  ; remove any existing NOTES.T first
        lda #$02
        ldx $ba                         ; last-used device
        ldy #$02
        jsr SETLFS
        lda #savenamL
        ldx #<savename
        ldy #>savename
        jsr SETNAM
        jsr OPEN
        ldx #$02
        jsr CHKOUT
        lda #<edbuf
        sta edptr
        lda #>edbuf
        sta edptr+1
        lda #$00
        sta ecnt
        sta ecnt+1
_sv_l:  lda ecnt+1
        cmp edlen+1
        bcc _sv_w
        bne _sv_d
        lda ecnt
        cmp edlen
        bcs _sv_d
_sv_w:  ldy #$00
        lda (edptr),y
        jsr CHROUT
        inc edptr
        bne _sv_i1
        inc edptr+1
_sv_i1: inc ecnt
        bne _sv_l
        inc ecnt+1
        jmp _sv_l
_sv_d:  jsr CLRCHN
        lda #$02
        jsr CLOSE
        lda #<ed_saved                  ; status on the VDC hint row
        sta r9L
        lda #>ed_saved
        sta r9H
        lda #$17
        ldx #$00
        jsr VDTEXT
        rts

; scratch S0:NOTES.T via the command channel (ignore "file not found")
ed_scratch:
        lda #$0f
        ldx $ba
        ldy #$0f
        jsr SETLFS
        lda #scrnamL
        ldx #<scrname
        ldy #>scrname
        jsr SETNAM
        jsr OPEN
        lda #$0f
        jsr CLOSE
        rts

; NOTES.T exists?  C=1 yes. Pattern-list "$0:NOTES.T" and count quote
; characters: the disk-title header has one quoted name (2 quotes), and a
; matching file adds another (4 total). Neither ST nor the command channel
; distinguishes missing from present after a bare OPEN on the real 1541
; (a missing file reads $00 forever, ST=$00; the command channel reads
; empty), but the directory read is reliable on both the emulator and hw.
ed_exists:
        lda #$03                         ; own logical file (not 2) so the
        ldx $ba                          ; file channel ed_load reopens is
        ldy #$00                         ; untouched
        jsr SETLFS
        lda #dirpatL
        ldx #<dirpat
        ldy #>dirpat
        jsr SETNAM
        jsr OPEN
        ldx #$03
        jsr CHKIN
        lda #$00
        sta etmp                        ; quote count
_ex_l:  jsr READST
        and #$40
        bne _ex_e
        jsr CHRIN
        cmp #$22                        ; '"'
        bne _ex_l
        inc etmp
        jmp _ex_l
_ex_e:  jsr CLRCHN
        lda #$03
        jsr CLOSE
        lda etmp
        cmp #$03                        ; >=3 quotes -> >=2 quoted entries
        rts

ed_load:
        lda #$00
        sta edlen
        sta edlen+1
        jsr ed_exists
        bcs _ld_open
        rts                             ; no NOTES.T: leave the buffer empty
_ld_open:
        lda #$02
        ldx $ba
        ldy #$02
        jsr SETLFS
        lda #loadnamL
        ldx #<loadname
        ldy #>loadname
        jsr SETNAM
        jsr OPEN
        ldx #$02
        jsr CHKIN
        lda #<edbuf
        sta edptr
        lda #>edbuf
        sta edptr+1
        lda #$00
        sta edcnt
        ; Read with a bulletproof page/byte bound: EDPAGES pages of 256 via
        ; nested X/Y byte counters (no 16-bit compare that can slip). ST EOF
        ; ends it early on the emulator; the real 1541 (Ultimate) returns $00
        ; forever with ST=$00 past a SEQ file's end, so the page bound is
        ; what actually stops it there.
        ldx #EDPAGES
_ld_pg: ldy #$00
_ld_l:  jsr CHRIN
        ldy #$00
        sta (edptr),y
        inc edptr
        bne _ld_i1
        inc edptr+1
_ld_i1: inc edlen
        bne _ld_i2
        inc edlen+1
_ld_i2: jsr READST
        and #$40                        ; EOF -> stop (emulator path)
        bne _ld_close
        inc edcnt
        bne _ld_l
        dex
        bne _ld_pg
_ld_close:
        jsr CLRCHN
        lda #$02
        jsr CLOSE
        rts

; ---------- strings / buffers ----------
ed_title: .text "Text editor", $00
ed_hint:  .text "type  DEL=back  RETURN=newline  F1=save  ESC=exit", $00
ed_saved: .text "saved NOTES.T                                      ", $00
; unshifted ASCII bytes: SEQ write/read + the scratch command
savename: .byte $4e,$4f,$54,$45,$53,$2e,$54,$2c,$53,$2c,$57   ; "NOTES.T,S,W"
savenamL = 11
loadname: .byte $4e,$4f,$54,$45,$53,$2e,$54,$2c,$53,$2c,$52   ; "NOTES.T,S,R"
loadnamL = 11
scrname:  .byte $53,$30,$3a,$4e,$4f,$54,$45,$53,$2e,$54       ; "S0:NOTES.T"
scrnamL = 10
dirpat:   .byte $24,$30,$3a,$4e,$4f,$54,$45,$53,$2e,$54       ; "$0:NOTES.T"
dirpatL = 10
elbuf:    .fill LW+2, 0
edlen:    .word 0
edbuf:    .fill EDMAX+1, 0
edit_end:
