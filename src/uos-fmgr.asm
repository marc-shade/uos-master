;==========================================================================
; UltOS file manager (FR-S2) v2 — directory + file actions
; Composed from hardware-verified launcher pieces:
;   dirscan = launcher's directory parser (32-byte record spec, probed)
;   rows    = launcher's GPUTS text row drawer
;   launch  = FILLFILE + APP_LOADER path
; v2 adds (PRD FR-S2 / FR-F1): SCRATCH / RENAME / COPY through the kernal
; serial abstraction (same-device copy via the drive's own DOS COPY
; command), an info line, and an in-window line editor. Keyboard-first.
; deferred: system-component filter + per-row block/type capture — both
; corrupt the first paint (root cause pending, task FR-S2 polish).
; Drawing note: GPUTC/GPUTS are XOR engines — erasing text means
; redrawing the same glyphs; strings are erased+redrawn whole.
;==========================================================================

.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "kernal.inc"
.include "vic-ii.inc"
.include "io.inc"

DLOADAPP        = $0826
LIST_MAX        := 10
LISTN           := 8    ; list-state key table entries
INPN            := 5    ; input-state key table entries
COL_X           := 30
CUR_X           := 22
TOP_Y           := 40    ; below the title text (drawn at y=14)
ROW_PX          := 12
ACT_Y           := 164   ; status/hint line
IN_Y            := 176   ; input line (rename/copy text)

fmrow           = $40
fmcnt           = $41
rowi            = $42
fmdev           = $43    ; current device (default 8)
state           = $44    ; 0 = list, 1 = confirm, 2 = line editor
mode            = $45    ; editor purpose: 1 = rename, 2 = copy
gllen           = $46    ; editor buffer length
fci             = $47    ; fncmd write index
keytmp          = $48    ; A save for the editor path
fmclose         = $49    ; dirscan: closing-quote offset
opentmp         = $4a    ; openseq: LFN save
opensa          = $4b    ; openseq: secondary address save
namlen          = $55    ; openseq: filename length
tchr0           = $4c
tchr1           = $4d
tchr2           = $4e
kd_lo           = $4f    ; keyfind jump target
kd_hi           = $50
dnum            = $51
kcnt            = $52
ktblo           = $53    ; keyfind: table pointer (2 bytes)
ktbhi           = $54

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
        lda #$00
        sta X1+1
        lda #14
        sta Y1
        lda #<fm_title
        sta r9L
        lda #>fm_title
        sta r9H
        jsr GPUTS

        lda #$08
        sta fmdev
        lda #$00
        sta linebuf     ; empty status line: nothing to erase later
        lda #$01
        jsr GFX_SETCOLOR ; pen = write (a desktop ClrRect may have left erase)

        jsr refresh

        ; ================= input loop =================
fmloop: jsr KEYIN
        sta keytmp      ; the key, kept for the editor path
        cmp #$00
        beq fmloop
        jsr normkey
        sta keytmp
        lda state
        cmp #$00
        beq j_list
        cmp #$01
        beq j_confirm
        jmp j_input
j_list: jmp st_list
j_confirm:
        jmp st_confirm
j_input:
        jmp st_input
j_fmloop:
        jmp fmloop

; ---------------- list state: keys ----------------
st_list:
        lda #<listtbl
        sta ktblo
        lda #>listtbl
        sta ktbhi
        lda keytmp
        ldx #LISTN
        jsr keyfind
        beq s_list_no
        jmp (kd_lo)
s_list_no:
        jmp j_fmloop

; ---------------- confirm state: Y/N ----------------
st_confirm:
        lda keytmp
        cmp #$59                        ; Y
        beq cf_yes
        cmp #$4e                        ; N
        beq cf_no
        jmp j_fmloop
cf_yes:
        lda #$00
        sta state
        jsr do_scratch
        jmp j_fmloop
cf_no:
        lda #$00
        sta state
        jsr show_hint
        jmp j_fmloop

; ---------------- line editor state ----------------
st_input:
        lda #<inputtbl
        sta ktblo
        lda #>inputtbl
        sta ktbhi
        lda keytmp
        ldx #INPN
        jsr keyfind
        beq s_in_prt
        jmp (kd_lo)
s_in_prt:
        lda keytmp
        cmp #$20                        ; printable -> editor add path
        bcc s_in_none
        jmp gl_add
s_in_none:
        jmp j_fmloop

keyfind:                                ; A = key, X = entries,
                                        ; ktblo/hi = key/code/word table
        sta dnum
        ldy #$00
kf_l:   cmp (ktblo),y
        beq kf_hit
        iny
        iny
        iny
        dex
        bne kf_l
        lda #$00                        ; no match
        rts
kf_hit: iny
        lda (ktblo),y
        sta kd_lo
        iny
        lda (ktblo),y
        sta kd_hi
        lda #$01
        rts

listtbl:
        .byte $11, <fmdn, >fmdn
        .byte $91, <fmup_, >fmup_
        .byte $0d, <fmopen, >fmopen
        .byte $1b, <fmescape, >fmescape
        .byte $44, <ask_scratch, >ask_scratch
        .byte $52, <ask_rename, >ask_rename
        .byte $43, <ask_copy, >ask_copy
        .byte $49, <show_info, >show_info
; keys not in the input table (and >= $20) go to the editor add path

inputtbl:
        .byte $0d, <gl_accept, >gl_accept
        .byte $1b, <gl_cancel, >gl_cancel
        .byte $14, <gl_del, >gl_del
        .byte $11, <fmloop, >fmloop
        .byte $91, <fmloop, >fmloop
gl_del:
        lda gllen
        beq inp_ret2
        sec
        sbc #$01
        sta gllen
        ldy gllen
        lda #$00
        sta fnbuf2,y
        jsr gl_show
inp_ret2:
        jmp j_fmloop
gl_add:
        lda gllen
        cmp #16                         ; cap at 16 chars
        bcc gla_add
        jmp inp_ret2
gla_add:
        ldy gllen
        lda keytmp
        sta fnbuf2,y
        iny
        lda #$00
        sta fnbuf2,y
        sty gllen
        jsr gl_show
        jmp j_fmloop
gl_cancel:
        lda #$00
        sta state
        jsr show_hint
        jmp inp_ret2
gl_accept:
        lda #$00
        sta state
        lda mode
        cmp #$01
        bne gla_cp2
        jsr do_rename
        jmp gla_ret
gla_cp2:
        jsr do_copy
gla_ret:
        jmp j_fmloop

; ---------------- cursor movement ----------------
fmdn:   lda fmcnt
        beq cur_ret       ; no files, back to the loop
        ldx fmrow
        inx
        cpx fmcnt
        bcc cur_ok
        jmp cur_ret
cur_ret2:
        jmp fmloop
cur_ret:
        jmp inp_ret2
cur_ok:
        stx fmrow
        jmp repaint
fmup_:
        ldx fmrow
        beq cur_ret
        dex
        stx fmrow
        jmp repaint

; ---------------- open path (row -> app) ----------------
fmopen:
        lda fmrow
        tax
        lda fmnamesL,x
        sta r0L
        lda fmnamesH,x
        sta r0H
        jsr FILLFILE
        jmp LAUNCH_APP                  ; core-resident: the new app loads
                                        ; over THIS code, so the kernal LOAD
                                        ; must not return into the fmgr
fmescape:
        lda #<dskstr
        sta r0L
        lda #>dskstr
        sta r0H
        jsr FILLFILE
        jsr DLOADAPP
        jmp DESK_START

; ---------------- actions ----------------
ask_scratch:
        ; prompt line: "DEL <name> (Y/N)"
        lda #$00
        sta fci
        lda #<p_del
        sta r0L
        lda #>p_del
        sta r0H
        jsr apstr
        jsr apcur
        lda #<p_yn
        sta r0L
        lda #>p_yn
        sta r0H
        jsr apstr
        jsr apnull
        jsr showlinecmd
        lda #$01
        sta state
        jmp fmloop

ask_rename:
        lda #<p_ren
        sta r0L
        lda #>p_ren
        sta r0H
        jsr setline
        lda #$00
        sta gllen
        sta fnbuf2
        lda #$01
        sta mode
        lda #$02                        ; line editor state (1 = Y/N confirm)
        sta state
        jsr gl_show
        jmp fmloop

ask_copy:
        lda #<p_cpy
        sta r0L
        lda #>p_cpy
        sta r0H
        jsr setline
        lda #$00
        sta gllen
        sta fnbuf2
        lda #$02
        sta mode
        lda #$02
        sta state
        jsr gl_show
        jmp fmloop

show_info:
        ; status line = <name> B=nn <TYP> (blocks are 0 until the
        ; dirscan type capture is fixed)
        lda #$00
        sta fci
        jsr apcur
        lda #<p_bsep
        sta r0L
        lda #>p_bsep
        sta r0H
        jsr apstr
        ldx fmrow
        lda fmblockL,x
        jsr bin2dec
        ; type = 3 chars at fmtype + 3*row (zeroes = no type known)
        lda fmrow
        asl
        clc
        adc fmrow
        tay
        lda fmtype,y
        beq si_fin
        lda #' '
        jsr apchr
        jsr aptype
si_fin:
        jsr apnull
        jsr showlinecmd
        jmp fmloop

do_scratch:
        ; "S0:<name>" on command channel 15, then rescan
        lda #$00
        sta fci
        lda #<p_s0
        sta r0L
        lda #>p_s0
        sta r0H
        jsr apstr
        jsr apcur
        jsr apnull
        jsr sendcmd
        jsr refresh
        lda #<msg_scr
        sta r0L
        lda #>msg_scr
        sta r0H
        jsr setline
        rts

do_rename:
        ; "R0:<new>=<old>", then rescan
        lda #$00
        sta fci
        lda #<p_r0
        sta r0L
        lda #>p_r0
        sta r0H
        jsr apstr
        lda #<fnbuf2
        sta r0L
        lda #>fnbuf2
        sta r0H
        jsr apstr
        lda #$3d                        ; '='
        jsr apchr
        jsr apcur
        jsr apnull
        jsr sendcmd
        jsr refresh
        lda #<msg_ren
        sta r0L
        lda #>msg_ren
        sta r0H
        jsr setline
        rts

do_copy:
        ; same-device copy via the drive's own DOS command channel:
        ; "C0:<new>=<old>". The kernal's sequential file reads stall under
        ; this VICE build's warp (only $-directory reads complete), so the
        ; byte-stream copy is not viable yet; the drive-side COPY is.
        ; Cross-device copy (FR-F1 drive->drive) returns to the seq-read
        ; path once that is resolved on hardware.
        lda #$00
        sta fci
        lda #<p_c0
        sta r0L
        lda #>p_c0
        sta r0H
        jsr apstr                       ; "C0:"
        lda #<fnbuf2
        sta r0L
        lda #>fnbuf2
        sta r0H
        jsr apstr                       ; <new>
        lda #$3d                        ; '='
        jsr apchr
        jsr apcur                       ; <old>
        jsr apnull
        jsr sendcmd
        jsr refresh
        lda #<msg_cpy
        sta r0L
        lda #>msg_cpy
        sta r0H
        jsr setline
        jmp j_fmloop
dc_err:                                 ; reached by error paths only
        jsr refresh
        lda #<msg_err
        sta r0L
        lda #>msg_err
        sta r0H
        jsr setline
        jmp j_fmloop

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

apchr:                                  ; A = char
        ldx fci
        sta fncmd,x
        inc fci
        rts

apnull:
        ldx fci
        lda #$00
        sta fncmd,x
        rts

aptype:                                 ; append the 3 type chars of fmrow
        lda fmrow
        asl
        clc
        adc fmrow
        tay
        lda fmtype,y
        jsr apchr
        iny
        lda fmtype,y
        jsr apchr
        iny
        lda fmtype,y
        jsr apchr
        rts

; append the current row's file name
apcur:
        ldx fmrow
        lda fmnamesL,x
        sta r0L
        lda fmnamesH,x
        sta r0H
        jmp apstr

; open a sequential file: A = LFN, Y = secondary address, r0 = name ptr
; (the 1541 needs a distinct secondary per open channel)
openseq:
        sta opentmp
        sty opensa
        jsr strlen
        lda opentmp
        ldx fmdev
        ldy opensa
        jsr SETLFS
        lda namlen
        ldx r0L
        ldy r0H
        jsr SETNAM
        jsr OPEN
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

; send fncmd ("S0:...", "R0:...") as a command on channel 15
sendcmd:
        lda #$0f
        ldx fmdev
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
        rts

; shifted letters ($c1-$da) -> unshifted ($41-$5a)
normkey:
        cmp #$c1
        bcc nk_ret
        cmp #$db
        bcs nk_ret
        sec
        sbc #$80
nk_ret: rts

; binary in A -> 3 ASCII digits in fncmd[fci..fci+2]; fci += 3
bin2dec:
        sta bnum
        ldy #$30
bd_h:   cmp #100
        bcc bd_h1
        sbc #100
        iny
        jmp bd_h
bd_h1:  ldx fci
        tya
        sta fncmd,x             ; hundreds
        ldy #$30
bd_t:   cmp #10
        bcc bd_t1
        sbc #10
        iny
        jmp bd_t
bd_t1:  sta dnum                ; remainder < 10
        tya
        sta fncmd+1,x           ; tens
        lda dnum
        clc
        adc #$30
        sta fncmd+2,x           ; ones
        lda fncmd,x
        cmp #$30
        bne bd_end
        lda #' '                ; $20
        sta fncmd,x
        lda fncmd+1,x
        cmp #$30
        bne bd_end
        lda #' '
        sta fncmd+1,x
bd_end: lda fci
        clc
        adc #$03
        sta fci
        rts

; ---------------- status line plumbing ----------------
setline:                                ; r0 = $00-terminated string
        ldy #$00
sl_cp:  lda (r0),y
        beq sl_d
        cpy #38
        bcs sl_d
        sta linebuf,y
        iny
        bne sl_cp
sl_d:   lda #$00
        sta linebuf,y
        jsr drawlinea
        rts

showlinecmd:
        lda #<fncmd
        sta r0L
        lda #>fncmd
        sta r0H
        jmp setline

drawlinea:
        lda #24
        sta X1
        lda #$00
        sta X1+1
        lda #ACT_Y
        sta Y1
        lda #<linebuf
        sta r9L
        lda #>linebuf
        sta r9H
        jsr GPUTS
        rts

show_hint:
        lda #<p_hint
        sta r0L
        lda #>p_hint
        sta r0H
        jsr setline
        rts

; redraw the editor line: erase the old string (XOR), draw the new one
gl_show:
        lda #24
        sta X1
        lda #$00
        sta X1+1
        lda #IN_Y
        sta Y1
        lda #<glnold
        sta r9L
        lda #>glnold
        sta r9H
        jsr GPUTS                       ; erase what was shown
        ldy #$00
gs_cp:  lda fnbuf2,y
        sta glnold,y
        beq gs_d
        iny
        cpy #17
        bne gs_cp
gs_d:   lda #24
        sta X1
        lda #$00
        sta X1+1
        lda #IN_Y
        sta Y1
        lda #<glnold
        sta r9L
        lda #>glnold
        sta r9H
        jsr GPUTS
        rts

; ---------------- refresh after a mutation ----------------
refresh:
        jsr dirscan
        lda #$01
        jsr GFX_SETCOLOR
        lda fmrow
        sec
        sbc fmcnt               ; fmrow - fmcnt
        bmi ref_ok              ; fmrow < fmcnt: in range
        lda fmcnt
        beq ref_zero
        sec
        sbc #$01
        sta fmrow
        jmp ref_ok
ref_zero:
        lda #$00
        sta fmrow
ref_ok: lda #$ff
        sta prev_row
        jsr paintrows
        jsr show_hint
        rts

repaint:
        lda #$01
        jsr GFX_SETCOLOR
        jsr paintrows
        jmp fmloop

; title-bar close box binds here (the CreateWindow macro expects ON_CLOSE)
ON_CLOSE:
        jmp fmescape

; ---------- paint all rows from fmnames -----------------------------
paintrows:
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
        lda fmrow
        sta prev_row
        jsr marky
        lda #$3e
        jsr GPUTC
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
        lda #$00
        sta X1+1
        lda #TOP_Y
        sta Y1
        lda rowi
        jsr addrowy
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

; ---------- directory scan: names into fm buffers --------------------
fmnamesL: .byte <fm1, <fm2, <fm3, <fm4, <fm5, <fm6
          .byte <fm7, <fm8, <fm9, <fma, <fmb, <fmc
fmnamesH: .byte >fm1, >fm2, >fm3, >fm4, >fm5, >fm6
          .byte >fm7, >fm8, >fm9, >fma, >fmb, >fmc
fmblockL: .byte 0,0,0,0,0,0,0,0,0,0,0,0
fmtype:   .byte 0,0,0,0,0,0,0,0,0,0,0,0
          .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
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
        lda #$05
        ldx fmdev
        ldy #$00
        jsr SETLFS
        lda #$01
        ldx #<dname
        ldy #>dname
        jsr SETNAM
        jsr OPEN
        ldx #$05
        jsr CHKIN
        ; the $ stream = 32-byte records from byte 0; the first record's
        ; first pair IS the load address (01 04), later records carry 01 01.
        ; Record 0 is skipped: it is the disk-title line.
        lda #$01
        sta dsfirst
ds_ent:
        lda #$00
        sta dseof
        ldy #$00
ds_rd:  jsr CHRIN                       ; read one full 32-byte record.
                                        ; Store BEFORE the status check:
                                        ; the status latch still holds EOF
                                        ; from the app's own LOAD here.
        sta dline,y
        iny
        jsr READST
        and #$40
        beq ds_more
        inc dseof                       ; EOF: parse this, then finish
        jmp ds_parse
ds_more:
        cpy #32
        bne ds_rd
ds_parse:
        ; a record is a file entry iff it carries a count > 0 AND a quoted
        ; name. Record 0 is the disk title. The BLOCKS FREE trailer drops
        ; out at the quote gate.
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
        inc fmcnt                       ; v1-style single increment after copy
ds_next:
        lda #$00
        sta dsfirst                     ; every later record uses [2..3]
        lda dseof
        bne ds_end
        jmp ds_ent
ds_end:
        jsr CLRCHN
        lda #$05
        jsr CLOSE
        cli                             ; the serial OPEN/GETIN paths can
        rts                             ; exit with IRQs masked (kernal
                                        ; serial timeout under load) — the
                                        ; keyboard IRQ must live for KEYIN

; hide system components: compact the fm name list in place after the scan
; (the in-parse version broke the first paint — see task notes; this runs
; after the serial channel is closed)
sysfilter:
        lda #$00
        sta rowi                        ; read index
        sta fci                         ; write (keep) index
sf_l:   lda rowi
        cmp fmcnt
        bcs sf_done
        tax
        lda fmnamesL,x
        sta r0L
        lda fmnamesH,x
        sta r0H
        ldy #$00
sf_cp:  lda (r0),y
        sta fnbuf,y                     ; row name into the compare buffer
        beq sf_got
        iny
        cpy #17
        bne sf_cp
sf_got: jsr is_syscomp                  ; C=1 -> it IS a system component
        bcs sf_drop
        lda rowi
        cmp fci
        beq sf_step
        ; keep this row but compacted down to the write slot
        lda rowi                        ; r0 = read-row buffer
        tax
        lda fmnamesL,x
        sta r0L
        lda fmnamesH,x
        sta r0H
        lda fci                         ; r1 = write-slot buffer
        tax
        lda fmnamesL,x
        sta r1L
        lda fmnamesH,x
        sta r1H
        ldy #$00
sf_mv:  lda (r0),y
        sta (r1),y
        iny
        cpy #17
        bne sf_mv
sf_step:
        inc fci
sf_drop:
        inc rowi
        jmp sf_l
sf_done:
        lda fci
        sta fmcnt
        rts

is_syscomp:
        ; does fnbuf match any entry in syscomps? C=0 keep, C=1 hide
        lda #<syscomps
        sta r1L
        lda #>syscomps
        sta r1H
        lda #<syscomps
        sta r2L
        lda #>syscomps
        sta r2H
        ldx #$00
is_l:   jsr cmpname                     ; C=1 -> fnbuf == (r1)
        bcs is_yes
        jsr nextentry                   ; r1 = r2 = next entry
        inx
        cpx #6
        bne is_l
        clc
is_yes: rts

cmpname:                                ; r1 = $00-terminated entry name
        ldy #$00
cn_l:   lda fnbuf,y
        beq cn_end
        cmp (r1),y
        bne cn_no
        iny
        cpy #17
        bne cn_l
cn_no:  clc
        rts
cn_end: lda (r1),y
        beq cn_yes
        jmp cn_no
cn_yes: sec
        rts

nextentry:                              ; r2 skips to after entry's $00,
                                        ; then r1 = r2
        ldy #$00
ne_l:   lda (r2),y
        beq ne_d
        iny
        jmp ne_l
ne_d:   iny
        tya
        clc
        adc r2L
        sta r2L
        bcc ne_r
        inc r2H
ne_r:   lda r2L
        sta r1L
        lda r2H
        sta r1H
        rts

; ---------- strings / buffers ----------------------------------------
dskstr: .text "uos-desktop", 0
fm_title: .text "File manager", 0
x:      .text "x", $00

; components that must never be opened from the file manager (loading
; them over the running system clobbers the live load addresses)
SYSCOMPS_N      := 6
syscomps:
        .text "uos", $00
        .text "uos-gfx", $00
        .text "uos-vdc", $00
        .text "uos-drv1351", $00
        .text "uos-sprites", $00
        .text "uos-reu", $00

p_hint: .text "D=del R=ren C=cpy I=info ESC=desk", 0
p_s0:   .byte $53,$30,$3a,$00   ; "S0:" — unshifted: 64tass .text would
p_r0:   .byte $52,$30,$3a,$00   ; "R0:"   emit shifted uppercase, which the
                                        ; drive treats as junk in commands
p_del:  .text "DEL ", 0
p_yn:   .text " (Y/N)", 0
p_c0:   .byte $43,$30,$3a,$00   ; "C0:" unshifted (see p_s0 note)
p_ren:  .text "RENAME TO:", 0
p_cpy:  .text "COPY AS:", 0
p_bsep: .text " B=", 0
w_sufx: .byte $2c,$53,$2c,$57,$00     ; ",S,W" unshifted (see p_s0 note)
msg_scr: .text "scratched", 0
msg_ren: .text "renamed", 0
msg_cpy: .text "copied", 0
msg_err: .text "copy failed", 0

fnbuf:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fnbuf2: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
glnold: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
srcname: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
fncmd:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0
dname:  .text "$"
vtmp:   .byte 0
vtmp2:  .byte 0
prev_row: .byte 0
bnum:   .byte 0
cpbyte: .byte 0
cpst:   .byte 0
errtag: .byte 0
dc_cnt: .byte 0
linebuf:.byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
dseof:  .byte 0
dsfirst: .byte 0
dline:  .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0