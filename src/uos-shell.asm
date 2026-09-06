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

        ; 80-column companion: header, version, hint; row 5 = command,
        ; row 7 = response (both mirrored as they change)
        jsr vd_clear_area
        lda #<sh_title
        sta r9L
        lda #>sh_title
        sta r9H
        lda #$02
        ldx #$00
        jsr VDTEXT
        lda #<shver
        sta r9L
        lda #>shver
        sta r9H
        lda #$02
        ldx #$14
        jsr VDTEXT
        lda #<sh_hint
        sta r9L
        lda #>sh_hint
        sta r9H
        lda #23
        ldx #$00
        jsr VDTEXT
        lda #<vd_prompt
        sta r9L
        lda #>vd_prompt
        sta r9H
        lda #$05
        ldx #$00
        jsr VDTEXT

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
        cmp #$43                        ; 'C'
        beq _sp_c
        cmp #$48                        ; 'H' -> HELP
        beq _sp_h
        jmp sp_unk                      ; (T/I/G/P verbs are checked there)
_sp_h:  lda cmdbuf+1
        cmp #$45                        ; 'E'
        bne sp_unk
        jsr cmd_help
        jmp sp_fin
_sp_c:  lda cmdbuf+1
        cmp #$4f                        ; 'O' -> COPY old new
        bne _sp_ca
        jsr cmd_copy
        rts
_sp_ca: cmp #$41                        ; 'A' -> CAT file
        bne sp_unk
        jsr cmd_cat
        jmp sp_fin
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
        beq _sp_run
        cmp #$45                        ; 'E' -> REN old new
        bne sp_unk
        jsr cmd_ren
        rts
_sp_run:
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
; the newer verbs are matched here (after the original dispatch, whose
; branch targets would otherwise drift out of range)
sp_unk:
        lda cmdbuf
        cmp #$54                        ; 'T' -> TIME [SYNC]
        beq sp_t
        cmp #$49                        ; 'I' -> IP
        beq sp_i
        cmp #$47                        ; 'G' -> GET host path
        beq sp_g
        cmp #$50                        ; 'P' -> PEEK / POKE
        beq sp_p
sp_unk_msg:
        lda #<msg_unk
        sta r0L
        lda #>msg_unk
        sta r0H
        jsr setline
sp_fin:
        rts
sp_t:   lda cmdbuf+1
        cmp #$49                        ; 'I'
        bne sp_unk_msg
        jsr cmd_time
        jmp sp_fin
sp_i:   lda cmdbuf+1
        cmp #$50                        ; 'P'
        bne sp_unk_msg
        jsr cmd_ip
        jmp sp_fin
sp_g:   lda cmdbuf+1
        cmp #$45                        ; 'E'
        bne sp_unk_msg
        jsr cmd_get
        jmp sp_fin
sp_p:   lda cmdbuf+1
        cmp #$45                        ; 'E' -> PEEK
        bne _sp_po
        jsr cmd_peek
        jmp sp_fin
_sp_po: cmp #$4f                        ; 'O' -> POKE
        bne sp_unk_msg
        jsr cmd_poke
        jmp sp_fin

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

; two args: X = offset of the first in cmdbuf -> tokbuf (old), tok2buf (new)
; (space-separated, each capped at 16 chars); tok2buf empty if missing
sh_args2:
        ldy #$00
_a2_l:  lda cmdbuf,x
        beq _a2_e1
        cmp #' '
        beq _a2_sp
        sta tokbuf,y
        inx
        iny
        cpy #16
        bne _a2_l
_a2_e1: lda #$00
        sta tokbuf,y
        sta tok2buf
        rts
_a2_sp: lda #$00
        sta tokbuf,y
        inx                             ; skip the space
        ldy #$00
_a2_m:  lda cmdbuf,x
        beq _a2_e2
        cmp #' '
        beq _a2_e2
        sta tok2buf,y
        inx
        iny
        cpy #16
        bne _a2_m
_a2_e2: lda #$00
        sta tok2buf,y
        rts

; COPY old new  ->  DOS "C0:new=0:old"
cmd_copy:
        ldx #$05                        ; after "COPY "
        jsr sh_args2
        lda tokbuf
        beq cp_none
        lda tok2buf
        beq cp_none
        lda #$00
        sta fci
        lda #<p_copy
        sta r0L
        lda #>p_copy
        sta r0H
        jsr apstr                       ; "C0:"
        lda #<tok2buf
        sta r0L
        lda #>tok2buf
        sta r0H
        jsr apstr                       ; new
        lda #<p_eq0
        sta r0L
        lda #>p_eq0
        sta r0H
        jsr apstr                       ; "=0:"
        lda #<tokbuf
        sta r0L
        lda #>tokbuf
        sta r0H
        jsr apstr                       ; old
        jsr apnull
        jsr sendcmd
        jsr refresh
        lda #<msg_copd
        sta r0L
        lda #>msg_copd
        sta r0H
        jsr show_status
        rts
cp_none:
        lda #<msg_args
        sta r0L
        lda #>msg_args
        sta r0H
        jsr setline
        rts

; REN old new  ->  DOS "R0:new=old"
cmd_ren:
        ldx #$04                        ; after "REN "
        jsr sh_args2
        lda tokbuf
        beq cp_none
        lda tok2buf
        beq cp_none
        lda #$00
        sta fci
        lda #<p_ren
        sta r0L
        lda #>p_ren
        sta r0H
        jsr apstr                       ; "R0:"
        lda #<tok2buf
        sta r0L
        lda #>tok2buf
        sta r0H
        jsr apstr                       ; new
        lda #<p_eq
        sta r0L
        lda #>p_eq
        sta r0H
        jsr apstr                       ; "="
        lda #<tokbuf
        sta r0L
        lda #>tokbuf
        sta r0H
        jsr apstr                       ; old
        jsr apnull
        jsr sendcmd
        jsr refresh
        lda #<msg_rend
        sta r0L
        lda #>msg_rend
        sta r0H
        jsr show_status
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
        jsr refresh
        lda #<msg_deld
        sta r0L
        lda #>msg_deld
        sta r0H
        jsr show_status
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
        ; read the drive's status line ("00, OK,00,00" or the error) into
        ; stbuf so the caller can show it - a rejected command is otherwise
        ; silent
        ldx #$0f
        jsr CHKIN
        ldy #$00
st_l:   jsr CHRIN
        cmp #$0d
        beq st_d
        cpy #30
        bcs st_l                        ; drain, but keep only 30 chars
        sta stbuf,y
        iny
        jmp st_l
st_d:   lda #$00
        sta stbuf,y
        jsr CLRCHN
        lda #$0f
        jsr CLOSE
        cli                             ; serial IRQ-mask quirk (see fmgr)
        rts

; show (r0) on the response line if the drive said "00"; else the status
show_status:
        lda stbuf
        cmp #'0'
        bne ss_err
        lda stbuf+1
        cmp #'0'                        ; "00, OK"
        beq ss_ok
        cmp #'1'                        ; "01, FILES SCRATCHED" (1541 scratch)
        bne ss_err
ss_ok:  jsr setline
        rts
ss_err: lda #<stbuf
        sta r0L
        lda #>stbuf
        sta r0H
        jsr setline
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
        cpy #46
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
        cpy #47
        bne sl_old
sl_d2:  jsr resp_show
        ; mirror the response on the 80-column display (row 7)
        lda #$07
        jsr VDCLR
        lda #<respbuf
        sta r9L
        lda #>respbuf
        sta r9H
        lda #$07
        ldx #$02
        jsr VDTEXT
        rts

; blank companion rows 2-23 (app area) on the 80-column display
vd_clear_area:
        lda #$02
vca_l:  pha
        jsr VDCLR
        pla
        clc
        adc #$01
        cmp #24
        bne vca_l
        rts
vd_prompt: .text "> ", $00

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
        ; mirror the command line on the 80-column display (row 5, after "> ")
        lda #$05
        jsr VDCLR
        lda #<vd_prompt
        sta r9L
        lda #>vd_prompt
        sta r9H
        lda #$05
        ldx #$00
        jsr VDTEXT
        lda #<cmdbuf
        sta r9L
        lda #>cmdbuf
        sta r9H
        lda #$05
        ldx #$02
        jsr VDTEXT
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
        ; GPUTS advances X1 as it draws: reset it, or the new line starts
        ; where the erase pass ended and every keystroke smears the echo
        ; ("ddir" on the command line, tests/screens.py 06-shell)
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
        jsr GPUTS                       ; draw the new line
        rts

refresh:
        lda #$01
        jsr GFX_SETCOLOR
        ; a GET response is on the rows region: wipe it (its text was not
        ; painted through the XOR bookkeeping) and forget the painted rows
        lda dirty
        beq _rf_clean
        jsr rows_wipe
_rf_clean:
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

; ---------------- network / clock commands (uos-net) ----------------
; TIME [SYNC]: the running clock, the date, and how the clock was set
cmd_time:
        lda cmdbuf+4
        cmp #$20
        bne _ct_show
        lda cmdbuf+5
        cmp #$53                        ; 'S' -> TIME SYNC
        bne _ct_show
        jsr NET_SYNC
_ct_show:
        jsr fmt_time
        lda #<linebuf
        sta r0L
        lda #>linebuf
        sta r0H
        jsr setline
        rts

; linebuf = "01:45:07 PM 2026/09/06 ntp" or "clock unsynced: <reason>"
fmt_time:
        lda NET_STATE
        beq _ft_ok
        ldx #$00
_ft_u:  lda msg_unsync,x
        beq _ft_u2
        sta linebuf,x
        inx
        bne _ft_u
_ft_u2: ldy NET_STATE
        cpy #$05
        bcc _ft_u3
        ldy #$05
_ft_u3: lda tagL,y
        sta r0L
        lda tagH,y
        sta r0H
        ldy #$00
_ft_u4: lda (r0),y
        sta linebuf,x
        beq _ft_r
        inx
        iny
        bne _ft_u4
_ft_r:  rts
_ft_ok: ldx #$00
        lda TODHRS                      ; latches the TOD registers
        pha
        and #$1f
        jsr put_bcd
        lda #':'
        sta linebuf,x
        inx
        lda TODMIN
        jsr put_bcd
        lda #':'
        sta linebuf,x
        inx
        lda TODSEC
        jsr put_bcd
        lda TODTEN                      ; releases them
        lda #' '
        sta linebuf,x
        inx
        pla
        and #$80
        beq _ft_am
        lda #'P'
        bne _ft_ap
_ft_am: lda #'A'
_ft_ap: sta linebuf,x
        inx
        lda #'M'
        sta linebuf,x
        inx
        lda #' '
        sta linebuf,x
        inx
        sec
        lda NET_YEAR
        sbc #<2000
        pha
        lda NET_YEAR+1
        sbc #>2000
        bcc _ft_19
        lda #'2'
        sta linebuf,x
        inx
        lda #'0'
        sta linebuf,x
        inx
        pla
        jmp _ft_y2
_ft_19: pla
        clc
        adc #100                        ; (y-2000)+100 = y-1900
        pha
        lda #'1'
        sta linebuf,x
        inx
        lda #'9'
        sta linebuf,x
        inx
        pla
_ft_y2: jsr put_dec2
        lda #'/'
        sta linebuf,x
        inx
        lda NET_MON
        jsr put_dec2
        lda #'/'
        sta linebuf,x
        inx
        lda NET_DAY
        jsr put_dec2
        lda #' '
        sta linebuf,x
        inx
        ldy #$00
_ft_t:  lda tag0,y
        sta linebuf,x
        beq _ft_r2
        inx
        iny
        bne _ft_t
_ft_r2: rts

put_bcd:                                ; A = BCD -> two digits at linebuf,x
        pha
        lsr
        lsr
        lsr
        lsr
        ora #$30
        sta linebuf,x
        inx
        pla
        and #$0f
        ora #$30
        sta linebuf,x
        inx
        rts
put_dec2:                               ; A (0-99) -> two digits at linebuf,x
        ldy #$30
_pd_l:  cmp #10
        bcc _pd_d
        sbc #10
        iny
        bne _pd_l
_pd_d:  pha
        tya
        sta linebuf,x
        inx
        pla
        ora #$30
        sta linebuf,x
        inx
        rts

; IP: the Ultimate's address (re-queried, not the boot-time copy)
cmd_ip:
        jsr NET_PRESENT
        bne _ci_p
        lda #<msg_noult
        sta r0L
        lda #>msg_noult
        sta r0H
        jsr setline
        rts
_ci_p:  jsr NET_GETIP
        bne _ci_ok
        lda #<msg_nonet
        sta r0L
        lda #>msg_nonet
        sta r0H
        jsr setline
        rts
_ci_ok: ldx #$00
_ci_c1: lda p_ip,x
        beq _ci_c2
        sta linebuf,x
        inx
        bne _ci_c1
_ci_c2: ldy #$00
_ci_c3: lda NET_IPSTR,y
        sta linebuf,x
        beq _ci_d
        inx
        iny
        bne _ci_c3
_ci_d:  lda #<linebuf
        sta r0L
        lda #>linebuf
        sta r0H
        jsr setline
        rts

; GET host path: HTTP/1.0 GET over the Ultimate's TCP socket. The status
; line goes on the response line, the next lines of the reply (headers,
; then body) fill the rows region; the 80-column display mirrors up to
; eight 78-character lines on rows 9-16.
cmd_get:
        jsr NET_PRESENT
        bne _cg_p
        lda #<msg_noult
        sta r0L
        lda #>msg_noult
        sta r0H
        jsr setline
        rts
_cg_p:  ldx #$04
        jsr sh_args2                    ; tokbuf = host, tok2buf = path
        lda tokbuf
        bne _cg_h
        lda #<msg_getargs
        sta r0L
        lda #>msg_getargs
        sta r0H
        jsr setline
        rts
_cg_h:  lda tok2buf
        bne _cg_ok
        lda #$2f                        ; missing path -> "/"
        sta tok2buf
        lda #$00
        sta tok2buf+1
_cg_ok: ldx #$00
_cg_a1: lda tokbuf,x                    ; typed PETSCII -> ASCII
        beq _cg_a2
        jsr p2a
        sta tokbuf,x
        inx
        bne _cg_a1
_cg_a2: ldx #$00
_cg_a3: lda tok2buf,x
        beq _cg_a4
        jsr p2a
        sta tok2buf,x
        inx
        bne _cg_a3
_cg_a4: lda #<msg_conn
        sta r0L
        lda #>msg_conn
        sta r0H
        jsr setline                     ; "connecting..." while the Ultimate resolves
        lda #<tokbuf
        sta r0L
        lda #>tokbuf
        sta r0H
        lda #80
        sta r1L
        lda #$00
        sta r1H
        lda #$07                        ; tcp
        jsr NET_OPEN
        bcc _cg_open
        ; "open failed: " + the Ultimate's status line
        ldx #$00
_cg_f1: lda msg_openf,x
        beq _cg_f2
        sta linebuf,x
        inx
        bne _cg_f1
_cg_f2: ldy #$00
_cg_f3: lda NET_STAT,y
        beq _cg_f4
        jsr a2p
        sta linebuf,x
        inx
        iny
        cpx #44
        bne _cg_f3
_cg_f4: lda #$00
        sta linebuf,x
        lda #<linebuf
        sta r0L
        lda #>linebuf
        sta r0H
        jsr setline
        rts
_cg_open:
        ; request: "GET " path " HTTP/1.0" CRLF "Host: " host CRLF CRLF
        lda #$00
        sta rqi
        lda #<p_get
        sta r0L
        lda #>p_get
        sta r0H
        jsr rq_app
        lda #<tok2buf
        sta r0L
        lda #>tok2buf
        sta r0H
        jsr rq_app
        lda #<p_http
        sta r0L
        lda #>p_http
        sta r0H
        jsr rq_app
        lda #<tokbuf
        sta r0L
        lda #>tokbuf
        sta r0H
        jsr rq_app
        lda #<p_crlf2
        sta r0L
        lda #>p_crlf2
        sta r0H
        jsr rq_app
        lda #<reqbuf
        sta r0L
        lda #>reqbuf
        sta r0H
        ldx rqi
        lda NET_SOCK
        jsr NET_WRITE
        lda #50                         ; up to 2 s for the first bytes
        sta tries
_cg_rd: lda #<500
        sta r1L
        lda #>500
        sta r1H
        lda NET_SOCK
        jsr NET_READ
        cmp #$00
        beq _cg_got
        cmp #$01
        bne _cg_none
        dec tries
        bne _cg_rd
_cg_none:
        lda NET_SOCK
        jsr NET_CLOSE
        lda #<msg_nodata
        sta r0L
        lda #>msg_nodata
        sta r0H
        jsr setline
        rts
_cg_got:
        ; (the socket is closed at _cg_done: NET_CLOSE goes through NET_CMD,
        ; which resets NET_LEN and reuses NET_DATA - the reply we are about
        ; to show)
        lda NET_LEN                     ; terminate the payload
        sta r0L
        lda NET_LEN+1
        sta r0H
        clc
        lda r0L
        adc #<(NET_DATA+2)
        sta r0L
        lda r0H
        adc #>(NET_DATA+2)
        sta r0H
        ldy #$00
        lda #$00
        sta (r0),y
        ; line 1 = status line -> response line
        lda #<(NET_DATA+2)
        sta gp
        lda #>(NET_DATA+2)
        sta gp+1
        jsr next_line                   ; -> linebuf (40) + vdline (78)
        lda #<linebuf
        sta r0L
        lda #>linebuf
        sta r0H
        jsr setline
        ; lines 2..9 -> rows region (cleared first) + VDC rows 9..16
        jsr rows_wipe
        lda #$01
        sta dirty
        lda #$00
        sta rowi
        jsr show_body
        lda NET_SOCK
        jsr NET_CLOSE                   ; one chunk is what we show
        rts

; show up to 8 lines from (gp) in the rows region + VDC rows 9-16.
; rowi = the first row to draw on (usually 0). Shared by GET and CAT.
show_body:
_sb_ln: jsr next_line
        bcs _sb_done                    ; end of data
        lda #COL_X
        sta X1
        lda #$00
        sta X1+1
        lda #TOP_Y
        sta Y1
        lda rowi
        jsr addrowy
        lda #<linebuf
        sta r9L
        lda #>linebuf
        sta r9H
        jsr GPUTS
        lda #<vdline
        sta r9L
        lda #>vdline
        sta r9H
        lda rowi
        clc
        adc #$09
        ldx #$02
        jsr VDTEXT
        inc rowi
        lda rowi
        cmp #$08
        bne _sb_ln
_sb_done:
        rts

; CAT filename — read up to 512 bytes of a disk file and show it as text
; (a PRG's 2-byte load header shows as two leading chars; fine for a viewer)
cmd_cat:
        jsr sh_argbuf
        lda tokbuf
        bne _cat_go
        jmp sp_unk_msg                  ; no filename
_cat_go:
        ldy #$00
_cat_len:
        lda tokbuf,y
        beq _cat_l2
        iny
        cpy #16
        bne _cat_len
_cat_l2:
        tya
        ldx #<tokbuf
        ldy #>tokbuf
        jsr SETNAM
        lda #$05
        ldx $ba                         ; last-used device (8)
        ldy #$00
        jsr SETLFS
        jsr OPEN
        ldx #$05
        jsr CHKIN
        lda #<catbuf
        sta gp
        lda #>catbuf
        sta gp+1
        lda #$00
        sta catn
        sta catn+1
_cat_rd:
        jsr READST                      ; check BEFORE the read (dirscan order)
        and #$40
        bne _cat_eof
        jsr CHRIN
        ldy #$00
        sta (gp),y
        inc gp
        bne _cat_i1
        inc gp+1
_cat_i1:
        inc catn
        bne _cat_i2
        inc catn+1
_cat_i2:
        lda catn+1
        cmp #$02                        ; cap at 512 bytes
        bne _cat_rd
_cat_eof:
        ldy #$00
        lda #$00
        sta (gp),y                      ; terminate for next_line
        jsr CLRCHN
        lda #$05
        jsr CLOSE
        lda #<tokbuf                    ; filename on the response line
        sta r0L
        lda #>tokbuf
        sta r0H
        jsr setline
        jsr rows_wipe
        lda #$01
        sta dirty
        lda #$00
        sta rowi
        lda #<catbuf
        sta gp
        lda #>catbuf
        sta gp+1
        jsr show_body
        rts

; blank the rows region (ClrRect expands to ~290 bytes: keep it out of
; the branch ranges of its callers)
rows_wipe:
        #ClrRect 24, 40, 272, 120
        lda #$00
        sta dirty
        sta painted
        rts

; append the (r0) 0-terminated bytes to reqbuf at rqi
rq_app: ldx rqi
        ldy #$00
_rq_l:  lda (r0),y
        beq _rq_d
        sta reqbuf,x
        inx
        iny
        cpx #120
        bne _rq_l
_rq_d:  stx rqi
        rts

; the next text line at (gp) -> linebuf (<=40 chars) and vdline (<=78),
; both 0-terminated, ASCII converted to PETSCII; C=1 when no data is left
next_line:
        ldy #$00
        lda (gp),y
        bne _nl_go
        sec
        rts
_nl_go: ldx #$00
_nl_l:  lda (gp),y
        beq _nl_e
        cmp #$0a
        beq _nl_e
        cmp #$0d
        beq _nl_s
        cmp #$09
        bne _nl_c
        lda #$20
_nl_c:  jsr a2p
        cpx #78
        bcs _nl_s
        sta vdline,x
        cpx #40
        bcs _nl_x
        sta linebuf,x
_nl_x:  inx
_nl_s:  iny
        bne _nl_l
_nl_e:  lda #$00
        sta vdline,x
        cpx #40
        bcc _nl_t
        ldx #40
_nl_t:  sta linebuf,x
        ; advance gp past the line (and its LF)
        lda (gp),y
        beq _nl_adv
        iny
_nl_adv:
        tya
        clc
        adc gp
        sta gp
        bcc _nl_r
        inc gp+1
_nl_r:  clc
        rts

; typed PETSCII -> ASCII: unshifted letters become lower case, shifted
; letters upper case (URLs are case-sensitive); everything else as is
p2a:    cmp #$41
        bcc _p2a_r
        cmp #$5b
        bcs _p2a_u
        ora #$20
        rts
_p2a_u: cmp #$c1
        bcc _p2a_r
        cmp #$db
        bcs _p2a_r
        and #$7f
_p2a_r: rts

; ASCII -> the font's PETSCII: a-z -> $41-$5a, A-Z -> $c1-$da, other
; control or 8-bit bytes -> '.'
a2p:    cmp #$20
        bcc _a2p_dot
        cmp #$7f
        bcs _a2p_dot
        cmp #$61
        bcc _a2p_up
        cmp #$7b
        bcs _a2p_r
        and #$df
        rts
_a2p_up:
        cmp #$41
        bcc _a2p_r
        cmp #$5b
        bcs _a2p_r
        ora #$80
_a2p_r: rts
_a2p_dot:
        lda #$2e
        rts

tagL:   .byte <tag0, <tag1, <tag2, <tag3, <tag4, <tag5
tagH:   .byte >tag0, >tag1, >tag2, >tag3, >tag4, >tag5
tag0:   .text "ntp", 0
tag1:   .text "no reply", 0
tag2:   .text "no network", 0
tag3:   .text "no ultimate", 0
tag4:   .text "no ntp host", 0
tag5:   .text "unsynced", 0
msg_unsync: .text "clock unsynced: ", 0
msg_noult:  .text "no ultimate command interface", 0
msg_nonet:  .text "no network", 0
msg_getargs: .text "need: host path", 0
msg_conn:   .text "connecting...", 0
msg_openf:  .text "open failed: ", 0
msg_nodata: .text "no data from host", 0
p_ip:       .text "ip: ", 0
; ASCII request fragments (64tass -a would turn .text into PETSCII)
p_get:   .byte $47,$45,$54,$20,$00                              ; "GET "
p_http:  .byte $20,$48,$54,$54,$50,$2f,$31,$2e,$30,$0d,$0a       ; " HTTP/1.0\r\n"
         .byte $48,$6f,$73,$74,$3a,$20,$00                       ; "Host: "
p_crlf2: .byte $0d,$0a,$0d,$0a,$00
rqi:     .byte 0
tries:   .byte 0
dirty:   .byte 0
gp       = $4c                          ; line pointer (apps own $40-$4f)
linebuf: .fill 48, 0
vdline:  .fill 80, 0
reqbuf:  .fill 128, 0
catbuf:  .fill 513, 0
catn:    .word 0
pkaddr:  .word 0
pkval:   .byte 0
pkaL:    .byte 0
pkaH:    .byte 0

; ---------------- memory monitor: PEEK / POKE / HELP ----------------
; PEEK addr        -> "$ADDR: $VV" on the response line
cmd_peek:
        ldx #$05                        ; after "PEEK " (4-char verb + space)
        jsr sh_args2                    ; tokbuf = hex address
        lda tokbuf
        bne _pk_go
        jmp sp_unk_msg
_pk_go: lda #<tokbuf
        sta r0L
        lda #>tokbuf
        sta r0H
        jsr parse_hex                   ; -> pkaddr (16-bit)
        lda pkaddr
        sta r0L
        lda pkaddr+1
        sta r0H
        ldy #$00
        lda (r0),y
        sta pkval
        jsr fmt_peek                    ; linebuf = "$AAAA: $VV"
        lda #<linebuf
        sta r0L
        lda #>linebuf
        sta r0H
        jsr setline
        rts

; POKE addr val    -> writes val to addr, "$ADDR = $VV"
cmd_poke:
        ldx #$05                        ; after "POKE "
        jsr sh_args2                    ; tokbuf = addr, tok2buf = val
        lda tokbuf
        bne _po_go
        jmp sp_unk_msg
_po_go: lda tok2buf
        bne _po_v
        jmp sp_unk_msg
_po_v:  lda #<tokbuf
        sta r0L
        lda #>tokbuf
        sta r0H
        jsr parse_hex
        lda pkaddr
        sta pkaL
        lda pkaddr+1
        sta pkaH
        lda #<tok2buf
        sta r0L
        lda #>tok2buf
        sta r0H
        jsr parse_hex
        lda pkaddr
        sta pkval                       ; low byte of the value
        lda pkaL
        sta r0L
        lda pkaH
        sta r0H
        lda pkval
        ldy #$00
        sta (r0),y
        ; report as "$AAAA: $VV" (address = the poked one)
        lda pkaL
        sta pkaddr
        lda pkaH
        sta pkaddr+1
        jsr fmt_peek
        lda #<linebuf
        sta r0L
        lda #>linebuf
        sta r0H
        jsr setline
        rts

; linebuf = "$" AAAA ": $" VV, from pkaddr / pkval
fmt_peek:
        ldx #$00
        lda #'$'
        sta linebuf,x
        inx
        lda pkaddr+1
        jsr put_hex2
        lda pkaddr
        jsr put_hex2
        lda #':'
        sta linebuf,x
        inx
        lda #' '
        sta linebuf,x
        inx
        lda #'$'
        sta linebuf,x
        inx
        lda pkval
        jsr put_hex2
        lda #$00
        sta linebuf,x
        rts

; A -> two hex digits at linebuf,x (x advanced); PETSCII digits/letters
put_hex2:
        pha
        lsr
        lsr
        lsr
        lsr
        jsr _ph_nib
        pla
        and #$0f
_ph_nib:
        cmp #10
        bcc _ph_dig
        clc
        adc #$c1-10                     ; A-F -> $c1-$c6 (shifted uppercase)
        jmp _ph_put
_ph_dig:
        clc
        adc #$30                        ; 0-9 -> $30-$39
_ph_put:
        sta linebuf,x
        inx
        rts

; (r0) hex string -> pkaddr (16-bit); stops at the first non-hex/terminator
parse_hex:
        lda #$00
        sta pkaddr
        sta pkaddr+1
        ldy #$00
_hx_l:  lda (r0),y
        jsr hex_nib                     ; A -> 0-15, C=1 if not a hex digit
        bcs _hx_d
        ; pkaddr = pkaddr*16 + nibble
        ldx #$04
_hx_s:  asl pkaddr
        rol pkaddr+1
        dex
        bne _hx_s
        ora pkaddr
        sta pkaddr
        iny
        cpy #$04                        ; 4 hex digits max
        bne _hx_l
_hx_d:  rts

; A = PETSCII char -> A = 0-15, C=0 ok / C=1 not a hex digit
; A = ASCII char from the keyboard -> A = 0-15, C=0 ok / C=1 not hex.
; Uses explicit ASCII codes: 64tass char literals ('A') would compile to
; this project's shifted-PETSCII encoding ($c1), but GETIN returns ASCII.
hex_nib:
        cmp #$30                        ; '0'
        bcc _hn_bad
        cmp #$3a                        ; '9'+1
        bcs _hn_af
        sec
        sbc #$30
        clc
        rts
_hn_af: and #$df                        ; force upper-case ($61-$66 -> $41-$46)
        cmp #$41                        ; 'A'
        bcc _hn_bad
        cmp #$47                        ; 'F'+1
        bcs _hn_bad
        sec
        sbc #$37                        ; 'A'($41) - 10
        clc
        rts
_hn_bad:
        sec
        rts

; HELP: common set on the response line (unchanged), full list in the rows
cmd_help:
        lda #<sh_hint
        sta r0L
        lda #>sh_hint
        sta r0H
        jsr setline
        lda #<help_text
        sta gp
        lda #>help_text
        sta gp+1
        jsr rows_wipe
        lda #$01
        sta dirty
        lda #$00
        sta rowi
        jsr show_body
        rts

; ---------- strings / buffers ----------------------------------------
dskstr: .text "uos-desktop", 0
sh_title: .text "Command shell", 0
shver:  .text "UltOS 0.3", 0
sh_hint: .text "DIR CAT RUN DEL COPY REN VER IP TIME GET EXIT", 0
help_text: .byte 68,73,82,32,67,65,84,32,82,85,78,32,68,69,76,32,67,79,80,89,32,82,69,78,32,86,69,82,13,73,80,32,84,73,77,69,32,71,69,84,32,80,69,69,75,32,80,79,75,69,32,69,88,73,84,13,67,65,84,32,70,32,32,86,73,69,87,32,70,73,76,69,13,80,69,69,75,32,65,65,65,65,32,32,82,69,65,68,32,65,32,66,89,84,69,13,80,79,75,69,32,65,65,65,65,32,86,86,32,32,87,82,73,84,69,32,65,32,66,89,84,69,13,71,69,84,32,72,79,83,84,32,80,65,84,72,32,32,72,84,84,80,32,70,69,84,67,72,13,0
p_del2: .byte $53,$30,$3a,$00           ; "S0:" unshifted (64tass .text
                                        ; would emit shifted PETSCII junk)
msg_dird: .text "dir", 0
msg_deld: .text "deleted", 0
msg_copd: .text "copied", 0
msg_rend: .text "renamed", 0
msg_args: .text "need: old new", 0
msg_unk: .text "?", 0
p_copy: .byte $43,$30,$3a,$00           ; "C0:" unshifted
p_ren:  .byte $52,$30,$3a,$00           ; "R0:" unshifted
p_eq0:  .byte $3d,$30,$3a,$00           ; "=0:"
p_eq:   .byte $3d,$00                   ; "="
tok2buf: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
stbuf:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
dname:  .text "$"

cmdbuf: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
tokbuf: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
respbuf: .fill 48, 0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
oldbuf: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
respold: .fill 48, 0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
oldmode:.byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
namlen: .byte 0
prev_row: .byte 0
painted: .byte 0                        ; rows are on screen (XOR bookkeeping)
fci:    .byte 0
fncmd:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0     ; "C0:"+16+"=0:"+16+NUL = 39
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0
dseof:  .byte 0
dsfirst: .byte 0
fnbuf:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
dline:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0