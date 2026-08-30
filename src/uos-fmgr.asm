;==========================================================================
; UltOS file manager (FR-S2) v1 — keyboard-first increment
; Composed from hardware-verified launcher pieces:
;   dirscan = Applications launcher's directory parser
;   rows    = launcher's GPUTS text row drawer
;   launch  = launcher's FILLFILE + APP_LOADER path
; v1: directory listing + cursor up/down + RETURN open + ESC reload desk.
;==========================================================================

.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "kernal.inc"
.include "vic-ii.inc"
.include "io.inc"

DLOADAPP        = $0826
SCR             = $0400
LIST_MAX        := 12
COL_X           := 30
TOP_Y           := 26
ROW_PX          := 12

fmrow           = $40
fmcnt           = $41
rowi            = $42

* = APP_START

        #RegisterApp

        #DrawRect 16,8,304,180,1
        ; title text
        lda #24
        sta X1
        lda #$01
        sta X1+1
        lda #14
        sta Y1
        lda #<fm_title
        sta r9L
        lda #>fm_title
        sta r9H
        jsr GPUTS

        jsr dirscan

        lda #2                          ; paint from list row 2
        sta Y1
        jsr paintrows

        lda #(TOP_Y+12*ROW_PX)          ; below the list rows
        sta Y1
        lda #<msgopen
        sta r9L
        lda #>msgopen
        sta r9H
        jsr GPUTS

        ; ================= input loop =================
fmloop: jsr KEYIN
        cmp #$00
        beq fmloop
        cmp #$11                        ; cursor down
        beq fmdn
        cmp #$91                        ; cursor up
        beq fmup_
        cmp #$0d                        ; RETURN
        beq fmopen
        cmp #$1b                        ; ESC
        beq fmescape
        jmp fmloop
fmdn:   lda fmcnt
        beq fmloop
        ldx fmrow
        cpx fmcnt
        beq fmloop
        inx
        stx fmrow
        jsr paintrows
        jmp fminput
fmup_:
        ldx fmrow
        beq fmloop
        dex
        stx fmrow
        jsr paintrows
        jmp fminput
fmopen:
        lda fmrow
        asl
        tax
        lda fmnamesL,x
        sta r0L
        lda fmnamesH,x
        sta r0H
        jsr FILLFILE
        jsr DLOADAPP
        jmp APP_START
fmescape:
        lda #<dskstr
        sta r0L
        lda #>dskstr
        sta r0H
        jsr FILLFILE
        jsr DLOADAPP
        jmp DESK_START
fminput:
        jmp fmloop
dskstr: .text "uos-desktop", 0
fm_title: .text "File manager", 0

; title-bar close box binds here (the CreateWindow macro expects ON_CLOSE)
ON_CLOSE:
        jmp fmescape

; ---------- paint all rows from fmnames (launcher draw_rows pattern) ------
paintrows:
        lda #$00
        sta rowi
pr_l:
        lda rowi
        asl
        tax
        lda fmnamesL,x
        sta r9L
        lda fmnamesH,x
        sta r9H
        lda #COL_X
        sta X1
        lda #$01
        sta X1+1
        lda #TOP_Y
        sta Y1
        lda rowi
        jsr addrowy                     ; Y1 += row*ROW_PX
        jsr GPUTS
        inc rowi
        lda rowi
        cmp fmcnt
        bne pr_l
        rts

; Y1 += A*ROW_PX (ROW_PX = 12: row*8 + row*4)
addrowy:
        sta vtmp
        lda vtmp
        asl
        asl
        asl                             ; row*8
        sta vtmp2
        lda vtmp
        asl
        asl                             ; row*4
        clc
        adc vtmp2
        clc
        adc Y1
        sta Y1
        rts
; ---------- directory scan: names into fm buffers (launcher parser) ------
dirname:  .text "$"
fmnamesL: .byte <fm1, <fm2, <fm3, <fm4, <fm5, <fm6
          .byte <fm7, <fm8, <fm9, <fma, <fmb, <fmc
fmnamesH: .byte >fm1, >fm2, >fm3, >fm4, >fm5, >fm6
          .byte >fm7, >fm8, >fm9, >fma, >fmb, >fmc
fm1:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fm2:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fm3:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fm4:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fm5:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fm6:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fm7:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fm8:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fm9:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fma:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fmb:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fmc:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0

dirscan:
        lda #$00
        sta fmcnt
        ; OPEN 5,8,0,"$"
        lda #$05
        ldx #$08
        ldy #$00
        jsr $ffba
        lda #$01
        ldx #<dname
        ldy #>dname
        jsr $ffbd
        jsr $ffc0
        ldx #$05
        jsr $ffc6
        jsr $ffcf
        jsr $ffcf
ds_ent:
        jsr $ffcf
        jsr $ffb7
        and #$40
        bne ds_end
        jsr $ffcf
        jsr $ffcf
        ldy #$00
ds_nm:  jsr $ffcf
        sta fnbuf,y
        iny
        cpy #$10
        bne ds_nm
        jsr $ffcf
        jsr $ffcf
        ldy #$00
ds_t:   lda fnbuf,y
        cmp #$a0
        bne ds_nz
        lda #$00
        sta fnbuf,y
ds_nz:  iny
        cpy #$10
        bne ds_t
        ldx fmcnt
        cpx #LIST_MAX
        bcs ds_ent
        lda fmnamesL,x
        sta r0L
        lda fmnamesH,x
        sta r0H
        ldy #$00
ds_cp:  lda fnbuf,y
        sta (r0),y
        iny
        cpy #$11
        bne ds_cp
        inc fmcnt
        jmp ds_ent
ds_end:
        lda #$0f
        jsr $ffcc
        lda #$05
        jsr $ffc3
        rts

fnbuf:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
dname:  .text "$"
vtmp:   .byte 0
vtmp2:  .byte 0
msgopen: .text "RETURN=open  ESC=desk", 0
