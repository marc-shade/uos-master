;==========================================================================
; UltOS command shell (FR-S4) v1 — keyboard-first
; Reuses the hardware-verified file-manager pieces (dirscan record spec,
; XOR text drawing, FILLFILE+APP_LOADER launch path) and adds a command
; line: DIR, RUN name, DEL name, VER, EXIT.
; Drawing note: GPUTC/GPUTS are XOR engines — every redraw first redraws
; the previously shown string so the glyphs cancel, then draws the new one.
;==========================================================================

.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "kernal.inc"
.include "vic-ii.inc"
.include "io.inc"

DLOADAPP        = $0826

LIST_MAX        := 10
COL_X           := 24
TOP_Y           := 40    ; directory rows
ROW_PX          := 12
CMD_Y           := 160   ; the command line
STAT_Y          := 172   ; the response line

shcnt           = $41
rowi            = $42
tmpb            = $4b
cmdlen          = $46
tmpa            = $48

* = APP_START

        #RegisterApp

        #DrawRect 16,8,304,180,1
        #Text 24, 14, sh_title
        #Text 200, 14, shver
        #Text 24, 26, sh_hint

        jsr refresh

        lda #$00
        sta cmdlen
        sta cmdbuf
        sta respbuf
        sta respold

        ; ================= command line loop =================
shloop: jsr KEYIN
        cmp #$00
        beq shloop
        cmp #$0d                        ; RETURN = execute
        beq j_exec
        cmp #$1b                        ; ESC = desktop
        beq j_desk
        cmp #$14                        ; DEL = backspace
        beq j_back
        cmp #$20                        ; printable from here on
        bcc shloop
        jsr sh_add
        jmp shloop

j_back: jsr sh_back
        jmp shloop
j_desk: jmp sh_desk
j_exec: jsr sh_parse
        ; the command was consumed (RUN/EXIT never return here): clear
        ; the line so the next command does not append to this one, and
        ; XOR-erase the echoed text
        lda #$00
        sta cmdlen
        sta cmdbuf
        jsr cmd_line
        jmp shloop

sh_add:
        ; A holds the character from KEYIN on entry — do NOT clobber it.
        ldy cmdlen
        cpy #30                         ; cap the command line
        bcs _sa_r
        sta cmdbuf,y                    ; store the character, not cmdlen
        iny
        sty cmdlen
        lda #$00
        sta cmdbuf,y                    ; keep the buffer $00-terminated
        jsr cmd_line                    ; whole-line redraw (XOR-safe)
_sa_r:  rts

sh_back:
        lda cmdlen
        beq _sb_r
        sec
        sbc #$01
        sta cmdlen
        jsr cmd_line
_sb_r:  rts

; ---------------- parse + dispatch the command line ----------------
sh_parse:
        lda cmdbuf
        cmp #$44                        ; 'D'
        beq _sp_d
        cmp #$52                        ; 'R'
        beq _sp_r
        cmp #$56                        ; 'V'
        beq _sp_v
        cmp #$45                        ; 'E'
        beq _sp_e
        jmp sp_unk
_sp_d:  lda cmdbuf+1
        cmp #$49                        ; 'I' -> DIR
        bne _sp_de
        jsr cmd_dir
        jmp sp_fin
_sp_de: cmp #$45                        ; 'E' -> DEL
        bne sp_unk
        jsr cmd_del
        rts
_sp_r:  lda cmdbuf+1
        cmp #$55                        ; 'U' -> RUN
        bne sp_unk
        jsr cmd_run
        jmp sp_fin
_sp_v:  lda cmdbuf+1
        cmp #$45                        ; 'E'
        bne sp_unk
        lda cmdbuf+2
        cmp #$52                        ; 'R' -> VER
        bne sp_unk
        jsr cmd_ver
        jmp sp_fin
_sp_e:  lda cmdbuf+1
        cmp #$58                        ; 'X' -> EXIT
        bne sp_unk
        jmp sh_desk
sp_unk:
        lda #<msg_unk
        sta r0L
        lda #>msg_unk
        sta r0H
        jsr setline
        jmp sp_fin
sp_fin:
        rts

; arg = cmdbuf+4 (after the 3-char verb and one space)
sh_argbuf:
        lda cmdbuf+3
        cmp #' '
        bne _sa_none
        ldy #$00
        ldx #$04
_ag_l:  lda cmdbuf,x
        beq _ag_z
        sta tokbuf,y
        inx
        iny
        cpy #16
        bne _ag_l
_ag_z:  lda #$00
        sta tokbuf,y
        rts
_sa_none:
        lda #$00
        sta tokbuf
        rts

; ---------------- command implementations ----------------
cmd_dir:
        lda #<msg_dird
        sta r0L
        lda #>msg_dird
        sta r0H
        jsr setline
        jsr refresh
_sp_dir_r:
        rts

cmd_ver:
        lda #<shver
        sta r0L
        lda #>shver
        sta r0H
        jsr setline
        rts

cmd_run:
        jsr sh_argbuf
        lda #<tokbuf
        sta r0L
        lda #>tokbuf
        sta r0H
        jsr FILLFILE
        jmp LAUNCH_APP                  ; core-resident: the load overwrites
                                        ; this shell, so never return here

cmd_del:
        jsr sh_argbuf
        lda tokbuf
        beq _sp_none                    ; no argument: nothing to scratch
        lda #$00
        sta fci
        lda #<p_del2
        sta r0L
        lda #>p_del2
        sta r0H
        jsr apstr                       ; "S0:"
        lda #<tokbuf
        sta r0L
        lda #>tokbuf
        sta r0H
        jsr apstr                       ; <arg>
        jsr apnull
        jsr sendcmd
        lda #<msg_deld
        sta r0L
        lda #>msg_deld
        sta r0H
        jsr setline
        jsr refresh
        rts
_sp_none:
        rts

sh_desk:
        lda #<dskstr
        sta r0L
        lda #>dskstr
        sta r0H
        jsr FILLFILE
        jsr DLOADAPP
        jmp DESK_START

; ---------------- building blocks ----------------
; append the (r0) $00-terminated string to fncmd at fci
apstr:
        ldx fci
        ldy #$00
ap_l:   lda (r0),y
        beq ap_d
        sta fncmd,x
        inx
        iny
        jmp ap_l
ap_d:   stx fci
        rts

apnull:
        ldx fci
        lda #$00
        sta fncmd,x
        rts

; send fncmd as a command on channel 15
sendcmd:
        lda #$0f
        ldx #$08
        ldy #$0f
        jsr SETLFS
        lda #$00
        ldx #$00
        ldy #$00
        jsr SETNAM
        jsr OPEN
        ldx #$0f
        jsr CHKOUT
        ldy #$00
sc_cp:  lda fncmd,y
        beq sc_cr
        jsr CHROUT
        iny
        jmp sc_cp
sc_cr:  lda #$0d
        jsr CHROUT
        jsr CLRCHN
        lda #$0f
        jsr CLOSE
        cli                             ; serial IRQ-mask quirk (see fmgr)
        rts

strlen:                                 ; r0 -> namlen (max 24)
        lda #$00
        sta namlen
        ldy #$00
stl_l:  lda (r0),y
        beq stl_d
        cpy #24
        bcs stl_d
        inc namlen
        iny
        jmp stl_l
stl_d:  rts

setline:                                ; r0 = $00-terminated response
        ; Copy the new text FIRST. The gfx engine's X1/Y1 ARE r0/r1
        ; ($02-$05), so the X1 write for the erase below destroys the
        ; pointer we were handed - copying afterwards read (X1) instead
        ; of the message and the response line stayed empty.
        ldy #$00
sl_cp:  lda (r0),y
        beq sl_d
        cpy #38
        bcs sl_d
        sta respbuf,y
        iny
        bne sl_cp
sl_d:   lda #$00
        sta respbuf,y
        ; erase what is currently shown (XOR of the old string)
        lda #COL_X
        sta X1
        lda #$00
        sta X1+1
        lda #STAT_Y
        sta Y1
        lda #<respold
        sta r9L
        lda #>respold
        sta r9H
        jsr GPUTS
        ; publish the new text as the shown string, then draw it
        ldy #$00
sl_old: lda respbuf,y
        sta respold,y
        beq sl_d2
        iny
        cpy #39
        bne sl_old
sl_d2:  jsr resp_show
        rts

show_hint:
        lda #<sh_hint
        sta r0L
        lda #>sh_hint
        sta r0H
        jsr setline
        rts

resp_show:
        lda #$01
        jsr GFX_SETCOLOR
        lda #COL_X
        sta X1
        lda #$00
        sta X1+1
        lda #STAT_Y
        sta Y1
        lda #<respold
        sta r9L
        lda #>respold
        sta r9H
        lda #$00
        sta X1+1
        lda #STAT_Y
        sta Y1
        jsr GPUTS
        rts

cmd_line:
        ; XOR redraw: cancel the previously shown string, publish the new
        ; one as both the visible line and the old-copy for the next cancel
        lda #COL_X
        sta X1
        lda #$00
        sta X1+1
        lda #CMD_Y
        sta Y1
        lda #<oldbuf
        sta r9L
        lda #>oldbuf
        sta r9H
        jsr GPUTS                       ; cancel the shown glyphs
        ldy #$00
cl_cp:  lda cmdbuf,y
        sta oldbuf,y
        iny
        cpy #31
        bne cl_cp
        lda #$00
        sta oldbuf,y
        lda #CMD_Y
        sta Y1
        lda #<oldbuf
        sta r9L
        lda #>oldbuf
        sta r9H
        jsr GPUTS                       ; draw the new line
        rts

refresh:
        lda #$01
        jsr GFX_SETCOLOR
        ; GPUTS is an XOR engine: rows already on screen must be drawn
        ; again (same names, before dirscan replaces them) to cancel out,
        ; or a second DIR would erase the listing instead of redrawing it
        lda painted
        beq _rf_scan
        jsr paintrows
_rf_scan:
        jsr dirscan
        lda #$ff
        sta prev_row
        jsr paintrows
        lda #$01
        sta painted
        lda #<sh_hint
        sta r0L
        lda #>sh_hint
        sta r0H
        jsr setline
        rts

repaint:
        jsr paintrows
        jmp shloop

; ---------- paint all rows from shnames -----------------------------
paintrows:
        lda shcnt
        beq pr_done                    ; empty directory: the row loop
        lda #$00                        ; below compares AFTER painting,
        sta rowi                        ; so 0 entries would paint 256 rows
pr_l:   lda rowi
        tax
        lda shnamesL,x
        sta r9L
        lda shnamesH,x
        sta r9H
        lda #COL_X
        sta X1
        lda #$00
        sta X1+1
        lda #TOP_Y
        sta Y1
        lda rowi
        jsr addrowy
        jsr GPUTS
        inc rowi
        lda rowi
        cmp shcnt
        bne pr_l
pr_done:
        rts

; Y1 += A*ROW_PX (ROW_PX = 12: row*8 + row*4)
addrowy:
        sta tmpa
        lda tmpa
        asl
        asl
        asl                             ; row*8
        sta tmpb
        lda rowi
        asl
        asl                             ; row*4
        clc
        adc tmpb
        clc
        adc Y1
        sta Y1
        rts

; ---------- directory scan (the fmgr's 32-byte-record parser) -------
shnamesL: .byte <sn1, <sn2, <sn3, <sn4, <sn5, <sn6
          .byte <sn7, <sn8, <sn9, <sna, <snb, <snc
shnamesH: .byte >sn1, >sn2, >sn3, >sn4, >sn5, >sn6
          .byte >sn7, >sn8, >sn9, >sna, >snb, >snc
sn1:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
sn2:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
sn3:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
sn4:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
sn5:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
sn6:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
sn7:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
sn8:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
sn9:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
sna:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
snb:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
snc:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0

dirscan:
        lda #$00
        sta shcnt
        lda #$05
        ldx #$08
        ldy #$00
        jsr SETLFS
        lda #$01
        ldx #<dname
        ldy #>dname
        jsr SETNAM
        jsr OPEN
        ldx #$05
        jsr CHKIN
        lda #$01
        sta dsfirst
ds_ent:
        lda #$00
        sta dseof
        ldy #$00
ds_rd:  jsr CHRIN
        sta dline,y
        iny
        jsr READST
        and #$40
        beq ds_more
        inc dseof
        jmp ds_parse
ds_more:
        cpy #32
        bne ds_rd
ds_parse:
        lda dsfirst
        beq ds_cnt
        lda #$00
        sta dsfirst
        jmp ds_next
ds_cnt: lda dline+2
        ora dline+3
        bne ds_xinit                    ; count > 0: look for the name
        jmp ds_next                     ; count 0 = disk title
ds_xinit:
        ldx #$00
ds_q1:  lda dline,x
        cmp #$22
        beq ds_qgot
        inx
        cpx #32
        bne ds_q1
        jmp ds_next
ds_qgot:
        inx                             ; step past the opening quote
        ldy #$00
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
        sta fnbuf,y                     ; terminator
        ldx shcnt
        cpx #LIST_MAX
        bcs ds_next
        lda shnamesL,x
        sta r0L
        lda shnamesH,x
        sta r0H
        ldy #$00
ds_cp:  lda fnbuf,y
        sta (r0),y
        iny
        cpy #$11
        bne ds_cp
        inc shcnt
ds_next:
        lda #$00
        sta dsfirst
        lda dseof
        bne ds_end
        jmp ds_ent
ds_end:
        jsr CLRCHN
        lda #$05
        jsr CLOSE
        cli
        rts

; ---------- strings / buffers ----------------------------------------
dskstr: .text "uos-desktop", 0
sh_title: .text "Command shell", 0
shver:  .text "UltOS 0.3", 0
sh_hint: .text "DIR RUN name DEL name VER EXIT", 0
p_del2: .byte $53,$30,$3a,$00           ; "S0:" unshifted (64tass .text
                                        ; would emit shifted PETSCII junk)
msg_dird: .text "dir", 0
msg_deld: .text "deleted", 0
msg_unk: .text "?", 0
dname:  .text "$"

cmdbuf: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
tokbuf: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
respbuf:.byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
oldbuf: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
respold:.byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
oldmode:.byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
namlen: .byte 0
prev_row: .byte 0
painted: .byte 0                        ; rows are on screen (XOR bookkeeping)
fci:    .byte 0
fncmd:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0
dseof:  .byte 0
dsfirst: .byte 0
fnbuf:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
dline:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0