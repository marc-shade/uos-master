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
CUR_X           := 22
TOP_Y           := 40   ; below the title text (drawn at y=14)
ROW_PX          := 12

fmrow           = $40
fmcnt           = $41
rowi            = $42

* = APP_START

        #RegisterApp

        ; NOTE: #CreateWindow (SaveRect/ClrRect REU fills) destabilises the
        ; app when opened on top of the desktop — the CPU lands in data RAM.
        ; Kept as the outline + banner until upstream's window system is
        ; understood; the close box is the OS-level ESC path meanwhile.
        #DrawRect 16,8,304,180,1
        ; title text
        lda #24
        sta X1
        lda #$00                        ; x word high byte (COL_X < 256)
        sta X1+1
        lda #14
        sta Y1
        lda #<fm_title
        sta r9L
        lda #>fm_title
        sta r9H
        jsr GPUTS

        jsr dirscan

        lda #$ff                        ; no previous marker yet
        sta prev_row
        jsr paintrows

        lda #(TOP_Y+12*ROW_PX)          ; below the list rows
        sta Y1
        lda #COL_X
        sta X1
        lda #$00
        sta X1+1
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
x:      .text "x", $00                  ; CreateWindow's close-box label

; title-bar close box binds here (the CreateWindow macro expects ON_CLOSE)
ON_CLOSE:
        jmp fmescape

; ---------- paint all rows from fmnames (launcher draw_rows pattern) ------
; Marker: GPUTC is an XOR engine, so a marker is ERASED by drawing '>' over
; its old position again (text erase can't work — a space glyph XORs 0).
paintrows:
        ; erase previous marker
        lda prev_row
        cmp #$ff
        beq pr_noprev
        cmp fmrow
        beq pr_noprev
        lda prev_row
        jsr marky
        lda #$3e
        jsr GPUTC
pr_noprev:
        ; draw marker at the current row (capture the row BEFORE marky
        ; clobbers the scratch regs)
        lda fmrow
        sta prev_row
        jsr marky
        lda #$3e                        ; '>'
        jsr GPUTC
        ; draw every name row
        lda #$00
        sta rowi
pr_l:
        lda rowi
        tax
        lda fmnamesL,x
        sta r9L
        lda fmnamesH,x
        sta r9H
        lda #COL_X
        sta X1
        lda #$00                        ; x word high byte (COL_X < 256)
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

; set X1 = CUR_X word, Y1 = TOP_Y + A*ROW_PX (GPUTC call setup)
marky:
        sta vtmp2
        lda #CUR_X
        sta X1
        lda #$00
        sta X1+1
        lda #TOP_Y
        sta Y1
        lda vtmp2
        jsr addrowy
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
        ; the $ stream = 32-byte records from byte 0; the first record's
        ; first pair IS the load address (01 04), later records carry 01 01.
        ; Record 0 is skipped: it is the disk-title line.
        lda #$01
        sta dsfirst
ds_ent:
        lda #$00
        sta dseof
        ldy #$00
ds_rd:  jsr $ffcf                       ; read one full 32-byte record.
                                        ; Store BEFORE the status check:
                                        ; the status latch still holds EOF
                                        ; from the app's own LOAD here.
        sta dline,y
        iny
        jsr $ffb7
        and #$40
        beq ds_more
        inc dseof                       ; EOF: parse this, then finish
        jmp ds_parse
ds_more:
        cpy #32
        bne ds_rd
ds_parse:
        ; a record is a file entry iff it carries a count > 0 AND a quoted
        ; name. Record 0 is special: it hosts the stream load address, so
        ; its count fields sit at [4..5] — skip it unconditionally (it is
        ; the disk title). The BLOCKS FREE trailer drops out at the quote
        ; gate.
        lda dsfirst
        beq ds_cnt
        lda #$00
        sta dsfirst
        jmp ds_next
ds_cnt: lda dline+2
        ora dline+3
        beq ds_next                     ; count 0 = disk title
        ldx #$00
ds_q1:  lda dline,x
        cmp #$22
        beq ds_qgot
        inx
        cpx #32
        bne ds_q1
        jmp ds_next                     ; no quotes -> header/trailer line
ds_qgot:
        inx                             ; step past the opening quote
        ldy #$00                        ; copy the name between the quotes
ds_nc:  lda dline,x
        cmp #$22
        beq ds_ncend
        sta fnbuf,y
        inx
        iny
        cpy #$10                        ; cap at 16 chars
        bne ds_nc
ds_ncend:
        lda #$00
        sta fnbuf,y                     ; terminator (Y = copied length)
        ldx fmcnt
        cpx #LIST_MAX
        bcs ds_next
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
ds_next:
        lda #$00
        sta dsfirst                     ; every later record uses [2..3]
        lda dseof
        bne ds_end
        jmp ds_ent
ds_end:
        lda #$0f
        jsr $ffcc
        lda #$05
        jsr $ffc3
        cli                             ; the serial OPEN/GETIN paths can
        rts                             ; exit with IRQs masked (kernal
                                        ; serial timeout under load) — the
                                        ; keyboard IRQ must live for KEYIN

fnbuf:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
dname:  .text "$"
vtmp:   .byte 0
vtmp2:  .byte 0
prev_row: .byte 0
fntyp:  .byte 0
dseof:  .byte 0
dsfirst: .byte 0
dline:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
msgopen: .text "RETURN=open  ESC=desk", 0
