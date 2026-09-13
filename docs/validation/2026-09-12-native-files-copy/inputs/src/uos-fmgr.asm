;==========================================================================
; UltOS file manager (FR-S2) v2 — directory + file actions
; Composed from hardware-verified launcher pieces:
;   dirscan = launcher's directory parser (32-byte record spec, probed)
;   rows    = launcher's GPUTS text row drawer
;   launch  = FILLFILE + APP_LOADER path
; v2 adds (PRD FR-S2 / FR-F1): SCRATCH / RENAME / COPY through the kernal
; serial abstraction (same-device copy via the drive's own DOS COPY
; command), an info line, and an in-window line editor. Keyboard-first.
; per-row block/type capture landed (fmblockL/fmtype, fed by show_info).
; Drawing note: GPUTC/GPUTS are NOT XOR engines. Each set glyph bit is
; plotted with EOR-BITMASK/AND/EOR — pen 1 (GFX_SETCOLOR 1) ORs the bit
; in, pen 0 clears it. Drawing text over text with pen 1 therefore
; unions the glyphs (overprint garbage), and "erasing" by redrawing the
; same string is a no-op. Every redraw in this app first ClrRects the
; region it is about to draw (the old XOR belief is what left the '>'-
; marker ghosts and the overprinted rows visible after rename/scratch).
;==========================================================================

.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "kernal.inc"
.include "vic-ii.inc"
.include "io.inc"

LIST_MAX        := 10
CACHE_MAX       := 64    ; bounded RAM cache; cursor refills it on demand
CACHE_STEP      := CACHE_MAX - LIST_MAX + 1
LISTN           := 13   ; list-state key table entries
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
mode            = $45    ; editor purpose: 1 = rename, 2 = copy, 3 = copy to other device
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
cdst            = $56    ; cross-device copy: the other device (8<->9)

* = APP_START

        #RegisterApp

        lda $ba                 ; device that loaded this application
        bne fm_bootdev
        lda #8
fm_bootdev:
        sta sysdev
        lda #$00
        sta fmrow
        sta state
        sta scroll
        sta cachebase
        sta cachebase+1
        sta fmready
        #ClrRect 16,8,288,180

        ; NOTE: #CreateWindow (SaveRect/ClrRect REU fills) destabilises the
        ; app when opened on top of the desktop — the CPU lands in data RAM.
        ; Kept as the outline + banner until upstream's window system is
        ; understood; the close box is the OS-level ESC path meanwhile.
        #DrawRect 16,8,288,180,1
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

        ; 80-column companion: header + hint; rows 4-13 get the listing
        jsr vd_clear_area
        lda #<fm_title
        sta r9L
        lda #>fm_title
        sta r9H
        lda #$02
        ldx #$00
        jsr VDTEXT
        lda #<vd_dev8
        sta r9L
        lda #>vd_dev8
        sta r9H
        lda #$02
        ldx #$16
        jsr VDTEXT
        lda #<p_hint
        sta r9L
        lda #>p_hint
        sta r9H
        lda #23
        ldx #$00
        jsr VDTEXT

        lda #$08
        sta fmdev
        lda #$00
        sta linebuf     ; empty status line: nothing to erase later
        lda #$01
        jsr GFX_SETCOLOR ; pen = write (a desktop ClrRect may have left erase)

        jsr refresh

        ; ================= input loop =================
fmloop: lda #$01
        sta fmready             ; published only after scan + both paints
        jsr KEYIN
        sta keytmp      ; the key, kept for the editor path
        cmp #$00
        beq fmloop
        lda #$00
        sta fmready
        lda keytmp
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
        .byte $38, <fmdev8, >fmdev8
        .byte $39, <fmdev9, >fmdev9
        .byte $30, <fmdev10, >fmdev10
        .byte $31, <fmdev11, >fmdev11
        .byte $42, <ask_copyx, >ask_copyx
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
        jsr clr_inline
        jsr show_hint
        jmp inp_ret2
gl_accept:
        lda gllen
        beq gl_cancel
        lda #$00
        sta state
        lda mode
        cmp #$01
        bne gla_cp2
        jsr do_rename
        jmp gla_ret
gla_cp2:
        cmp #$03                        ; 3 = copy to the other device
        beq gla_cpx
        jsr do_copy
        jmp gla_ret
gla_cpx:
        jsr do_copyx
gla_ret:
        jsr clr_inline
        jmp j_fmloop

; ---------------- cursor movement ----------------
fmdn:   lda fmcnt
        beq cur_ret       ; no files, back to the loop
        ldx fmrow
        inx
        cpx fmcnt
        bcc cur_ok
        lda morefiles
        beq cur_ret
        ; Keep the last nine entries when refilling, so down-scroll
        ; moves the visible list by exactly one row across cache edges.
        clc
        lda cachebase
        adc #CACHE_STEP
        sta cachebase
        bcc cur_next
        inc cachebase+1
cur_next:
        lda #LIST_MAX-1
        sta fmrow
        lda #$00
        sta scroll
        jsr refresh
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
        bne cur_up
        lda cachebase
        ora cachebase+1
        beq cur_ret
        sec
        lda cachebase
        sbc #CACHE_STEP
        sta cachebase
        lda cachebase+1
        sbc #$00
        sta cachebase+1
        lda #CACHE_STEP-1
        sta fmrow
        lda #CACHE_STEP-LIST_MAX
        sta scroll
        jsr refresh
        jmp cur_ret
cur_up:
        dex
        stx fmrow
        jmp repaint

; ---------------- open path (row -> app) ----------------
fmopen:
        lda fmcnt
        beq cur_ret
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
        ; The desktop is resident. Reloading it uses the last IEC device,
        ; which may now be an empty data disk on drive 9.
        lda sysdev              ; subsequent desktop app loads use system disk
        sta $ba
        jmp DESK_START

; ---------------- actions ----------------
ask_scratch:
        lda fmcnt
        bne as_have
        jmp fmloop
as_have:
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
        lda fmcnt
        bne ar_have
        jmp fmloop
ar_have:
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
        lda fmcnt
        bne ac_have
        jmp fmloop
ac_have:
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

; 'B': same editor flow, but the accept path byte-stream copies the file
; to the other device (mode 3)
ask_copyx:
        lda fmcnt
        bne ax_have
        jmp fmloop
ax_have:
        lda #<p_cpyx
        sta r0L
        lda #>p_cpyx
        sta r0H
        jsr setline
        lda #$00
        sta gllen
        sta fnbuf2
        lda #$03
        sta mode
        lda #$02
        sta state
        jsr gl_show
        jmp fmloop

show_info:
        lda fmcnt
        bne si_have
        jmp fmloop
si_have:
        ; 16-bit block count; CMD/1581 files can exceed 255 blocks.
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
        sta bnum
        lda fmblockH,x
        sta bnum+1
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
        bcc scratch_ok
        jmp dc_err
scratch_ok:
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
        bcs dc_err
        jsr refresh
        lda #<msg_ren
        sta r0L
        lda #>msg_ren
        sta r0H
        jsr setline
        rts

do_copy:
        ; same-device copy via the drive's own DOS command channel:
        ; "C0:<new>=<old>". (Cross-device copy is the explicit 'B' key —
        ; see do_copyx. Auto-detecting the other device from the serial
        ; status proved unreliable under VICE, and silently guessing a
        ; destination is worse than an explicit key.)
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
        bcs dc_err
        jsr refresh
        lda #<msg_cpy
        sta r0L
        lda #>msg_cpy
        sta r0H
        jsr setline
        rts
dc_err:                                 ; reached by error paths only
        jsr refresh
        lda #<msg_err
        sta r0L
        lda #>msg_err
        sta r0H
        jsr setline
        rts

; 'B': stream the selected file to the paired device (8/9 or 10/11).
; Success requires EOF and clean drive/serial status, including CLOSE.
; Tests separately reopen both disk images and compare every data byte.
do_copyx:
        lda fmdev
        eor #$01
        sta cdst
        jsr dc_seqcopy
        bcs dc_err
        jsr refresh
        lda cdst
        sec
        sbc #8
        tax
        lda copymsgL,x
        sta r0L
        lda copymsgH,x
        sta r0H
        jsr setline
        rts

; Stream PRG/SEQ/USR files without changing their type or load-address
; bytes. Every bus-direction change uses CLRCHN, then selects its channel
; again. Counters live in RAM: CHKIN/CHKOUT overwrite X. The source's
; directory block count bounds broken streams; files are not capped at 16K.
dc_seqcopy:
        lda #$00
        sta cperror
        sta cpcreated
        lda fmrow
        asl
        clc
        adc fmrow
        tay
        lda fmtype,y
        jsr normkey
        cmp #$50               ; PRG
        beq dcs_typeok
        cmp #$53               ; SEQ
        beq dcs_typeok
        cmp #$55               ; USR
        beq dcs_typeok
        sec                    ; REL requires record-aware copying
        rts
dcs_typeok:
        sta w_sufx+1
        ldx fmrow
        clc
        lda fmblockL,x
        adc #$01
        sta cpbudget
        lda fmblockH,x
        adc #$00
        sta cpbudget+1
        ldy #$00
dcs_n:
        lda fnbuf2,y
        beq dcs_s
        sta csrcbuf,y
        iny
        cpy #16
        bne dcs_n
dcs_s:
        ldx #$00
dcs_s2:
        lda w_sufx,x
        sta csrcbuf,y
        beq dcs_source
        iny
        inx
        bne dcs_s2
dcs_source:
        jsr CLRCHN
        ldx fmrow
        lda fmnamesL,x
        sta r0L
        lda fmnamesH,x
        sta r0H
        lda #$02
        ldy #$02
        jsr openseq
        bcc dcs_source_status
        jmp dcs_error
dcs_source_status:
        lda fmdev
        jsr drive_status
        bcc dcs_dest
        jmp dcs_error
dcs_dest:
        lda #<csrcbuf
        sta r0L
        lda #>csrcbuf
        sta r0H
        jsr strlen
        lda #$03
        ldx cdst
        ldy #$03
        jsr SETLFS
        lda namlen
        ldx #<csrcbuf
        ldy #>csrcbuf
        jsr SETNAM
        jsr OPEN
        bcc dcs_dest_status
        jmp dcs_error
dcs_dest_status:
        lda cdst
        jsr drive_status
        bcc dcs_dstok
        jmp dcs_error
dcs_dstok:
        inc cpcreated
dcs_pg:
        jsr CLRCHN
        ldx #$02
        jsr CHKIN
        bcc dcs_inputok
        jmp dcs_error
dcs_inputok:
        ldy #$00
dcs_rd:
        jsr CHRIN
        sta cpbuf,y
        jsr READST
        sta cpst
        and #$bf
        bne dcs_error
        iny
        lda cpst
        and #$40
        bne dcs_weof
        cpy #$00
        bne dcs_rd
dcs_weof:
        sty dnum               ; zero means a full 256-byte page
        jsr dcs_write
        bcs dcs_error
        lda cpst
        and #$40
        bne dcs_fin
        ; A working stream terminates on EOF; the size bound is an error,
        ; never a successful truncated copy.
        lda cpbudget
        bne dcs_dec
        dec cpbudget+1
dcs_dec:
        dec cpbudget
        lda cpbudget
        ora cpbudget+1
        beq dcs_error
        jsr KEYIN
        cmp #$1b
        beq dcs_error
        jmp dcs_pg
dcs_error:
        lda #$01
        sta cperror
dcs_fin:
        jsr CLRCHN
        lda #$02
        jsr CLOSE
        lda #$03
        jsr CLOSE
        lda cpcreated
        beq dcs_result
        lda cdst
        jsr drive_status       ; includes flush/disk-full failure at CLOSE
        bcc dcs_result
        inc cperror
dcs_result:
        cli
        lda cperror
        beq dcs_ok
        sec
        rts
dcs_ok:
        clc
        rts

dcs_write:
        jsr CLRCHN             ; UNTALK source before LISTEN destination
        ldx #$03
        jsr CHKOUT
        bcs dcw_fail
        ldy #$00
dcw_l:
        lda cpbuf,y
        jsr CHROUT
        jsr READST
        bne dcw_fail
        iny
        cpy dnum
        bne dcw_l
        jsr CLRCHN             ; flush the last byte and UNLISTEN
        clc
        rts
dcw_fail:
        sec
        rts

; A = IEC device -> read command-channel status WITHOUT closing channel
; 15 (CLOSE 15 also closes data files on some drives). No logical-file
; table entry is needed for TALK/secondary 15. Bounded, including timeout.
drive_status:
        pha
        jsr CLRCHN
        lda #$00
        sta $90                ; fresh KERNAL serial status
        sta statlen
        pla
        jsr TALK
        lda #$6f
        jsr TKSA
status_read:
        jsr ACPTR
        ldx statlen
        sta statusbuf,x
        inc statlen
        cmp #$0d
        beq status_end
        jsr READST
        bne status_end
        lda statlen
        cmp #38
        bcc status_read
status_end:
        jsr UNTLK
        ldx statlen
        lda #$00
        sta statusbuf,x
        lda statusbuf
        cmp #$30
        bne status_bad
        lda statusbuf+1
        cmp #$30
        beq status_ok
        cmp #$31
        bne status_bad
status_ok:
        clc
        rts
status_bad:
        sec
        rts
cpbudget: .word 0
cperror: .byte 0
cpcreated: .byte 0
statlen: .byte 0
statusbuf: .fill 40, 0

; ---------------- device switch keys ----------------
fmdev8:
        lda #$08
        sta fmdev
        jsr firstpage
        jsr refresh
        jmp j_fmloop
fmdev9:
        lda #$09
        bne fmdevice
fmdev10:
        lda #10
        bne fmdevice
fmdev11:
        lda #11
fmdevice:
        sta fmdev
        jsr firstpage
        jsr refresh
        jmp j_fmloop

firstpage:
        lda #$00
        sta fmrow
        sta scroll
        sta cachebase
        sta cachebase+1
        rts

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
        lda fmdev
        jmp drive_status

; shifted letters ($c1-$da) -> unshifted ($41-$5a)
normkey:
        cmp #$c1
        bcc nk_ret
        cmp #$db
        bcs nk_ret
        sec
        sbc #$80
nk_ret: rts

; bnum word -> five decimal digits (leading spaces) in fncmd.
bin2dec:
        ldy #$00
        sty decseen
bd_digit:
        lda #$30
        sta decdigit
bd_sub:
        sec
        lda bnum
        sbc decpowersL,y
        tax
        lda bnum+1
        sbc decpowersH,y
        bcc bd_emit
        sta bnum+1
        stx bnum
        inc decdigit
        bne bd_sub
bd_emit:
        lda decdigit
        cmp #$30
        bne bd_seen
        cpy #$04
        beq bd_seen
        ldx decseen
        bne bd_seen
        lda #$20
        bne bd_put
bd_seen:
        inc decseen
bd_put:
        jsr apchr
        iny
        cpy #$05
        bne bd_digit
        rts
decpowersL: .byte <10000,<1000,<100,<10,<1
decpowersH: .byte >10000,>1000,>100,>10,>1
decdigit: .byte 0
decseen: .byte 0

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
        #ClrRect 24, (ACT_Y - 2), 280, 12
        lda #24
        sta X1
        lda #$00
        sta X1+1
        sta Y1+1
        lda #ACT_Y
        sta Y1
        lda #<linebuf
        sta r9L
        lda #>linebuf
        sta r9H
        jsr GPUTS
        lda #21
        jsr VDCLR
        lda #<linebuf
        sta r9L
        lda #>linebuf
        sta r9H
        lda #21
        ldx #0
        jmp VDTEXT

show_hint:
        lda #<p_hint
        sta r0L
        lda #>p_hint
        sta r0H
        jsr setline
        rts

; redraw the editor line: clear the strip, then draw the new text
gl_show:
        #ClrRect 24, (IN_Y - 2), 240, 12
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
        lda #20
        jsr VDCLR
        lda #<glnold
        sta r9L
        lda #>glnold
        sta r9H
        lda #20
        ldx #0
        jmp VDTEXT

; blank the editor strip (leaving the rename/copy editor state)
clr_inline:
        #ClrRect 24, (IN_Y - 2), 240, 12
        lda #20
        jmp VDCLR

; ---------------- refresh after a mutation ----------------
refresh:
        lda #$00
        sta fmready
ref_scan:
        jsr dirscan
        lda direrror
        bne ref_draw
        lda fmcnt
        bne ref_draw
        lda cachebase
        ora cachebase+1
        beq ref_draw
        ; Deleting the last entry of a cached page must reveal its
        ; predecessors rather than strand the user on an empty page.
        sec
        lda cachebase
        sbc #CACHE_STEP
        sta cachebase
        lda cachebase+1
        sbc #$00
        sta cachebase+1
        lda #$00
        sta fmrow
        sta scroll
        jmp ref_scan
ref_draw:
        jsr show_device
        lda #$01
        jsr GFX_SETCOLOR
        lda fmrow
        cmp fmcnt
        bcc ref_ok
        lda fmcnt
        beq ref_zero
        sec
        sbc #$01
        sta fmrow
        jmp ref_ok
ref_zero:
        lda #$00
        sta fmrow
ref_ok: jsr keepvisible
        jsr paintrows
        lda direrror
        beq ref_hint
        lda #<msg_direrr
        sta r0L
        lda #>msg_direrr
        sta r0H
        jmp setline
ref_hint:
        jsr show_hint
        rts

repaint:
        lda #$00
        sta fmready
        lda #$01
        jsr GFX_SETCOLOR
        jsr keepvisible
        jsr paintrows
        jmp fmloop

; fmrow is a cache index; scroll is the first visible cache entry.
keepvisible:
        lda fmrow
        cmp scroll
        bcs kv_down
        sta scroll
kv_down:
        sec
        sbc scroll
        cmp #LIST_MAX
        bcc kv_done
        lda fmrow
        sec
        sbc #LIST_MAX-1
        sta scroll
kv_done:
        rts

; title-bar close box binds here (the CreateWindow macro expects ON_CLOSE)
ON_CLOSE:
        jmp fmescape

; ---------- paint all rows from fmnames -----------------------------
; The list region is cleared whole, then every row and exactly one
; marker are drawn with pen = write. (The previous erase-the-previous-
; marker-by-redrawing scheme relied on a false XOR model and left one
; '>' behind per move.)
paintrows:
        ; ClrRect rounds to 8-pixel cell bands. End below y=160 so list
        ; redraws cannot erase the first scanlines of the status at y=164.
        #ClrRect (CUR_X - 2), (TOP_Y - 2), 288, (LIST_MAX * ROW_PX)
        lda #$00
        sta rowi
pr_l:
        lda rowi
        clc
        adc #$04
        jsr VDCLR
        lda rowi
        clc
        adc scroll
        cmp fmcnt
        bcs pr_nomark
        sta rowindex
        tax
        lda fmnamesL,x
        sta r9L
        lda fmnamesH,x
        sta r9H
        lda #COL_X
        sta X1
        lda #$00
        sta X1+1
        sta Y1+1
        lda #TOP_Y
        sta Y1
        lda rowi
        jsr addrowy
        jsr GPUTS
        ; Rendering routines clobber registers; keep the cache index in RAM.
        ldx rowindex
        lda fmnamesL,x
        sta r9L
        lda fmnamesH,x
        sta r9H
        lda rowi
        clc
        adc #$04
        ldx #$04
        jsr VDTEXT
        lda rowindex
        cmp fmrow
        bne pr_nomark
        lda rowi
        jsr marky
        lda #$3e
        jsr GPUTC
        lda #<vd_mark
        sta r9L
        lda #>vd_mark
        sta r9H
        lda rowi
        clc
        adc #$04
        ldx #$02
        jsr VDTEXT
pr_nomark:
        inc rowi
        lda rowi
        cmp #LIST_MAX
        bne pr_l
pr_done:
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
vd_mark: .text ">", $00
vd_dev8: .text "device 08", $00
devhint: .text "disk 08  8/9/0/1=device  up/dn=scroll", 0
vd_keys: .text "B: copy to paired drive. PRG/SEQ/USR supported; REL needs record copying", 0

show_device:
        lda #$30
        sta devhint+5
        sta vd_dev8+7
        lda fmdev
        cmp #10
        bcc sd_one
        sec
        sbc #10
        inc devhint+5
        inc vd_dev8+7
sd_one:
        clc
        adc #$30
        sta devhint+6
        sta vd_dev8+8
        #ClrRect 24,24,264,8
        #Text 24,24,devhint
        lda #<vd_dev8
        sta r9L
        lda #>vd_dev8
        sta r9H
        lda #2
        ldx #22
        jsr VDTEXT
        lda #<devhint
        sta r9L
        lda #>devhint
        sta r9H
        lda #3
        ldx #0
        jsr VDTEXT
        lda #<vd_keys
        sta r9L
        lda #>vd_keys
        sta r9H
        lda #22
        ldx #0
        jmp VDTEXT

; set X1 = CUR_X word, Y1 = TOP_Y + A*ROW_PX (GPUTC call setup)
marky:
        sta vtmp2
        lda #CUR_X
        sta X1
        lda #$00
        sta X1+1
        sta Y1+1
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
fmnamesL:
        .for n := 0, n < CACHE_MAX, n += 1
        .byte <(fmnames + n * 17)
        .next
fmnamesH:
        .for n := 0, n < CACHE_MAX, n += 1
        .byte >(fmnames + n * 17)
        .next
fmblockL: .fill CACHE_MAX, 0
fmblockH: .fill CACHE_MAX, 0
fmtype:   .fill CACHE_MAX * 3, 0
fmnames:  .fill CACHE_MAX * 17, 0
scroll:   .byte 0
rowindex: .byte 0
cachebase: .word 0          ; absolute directory ordinal of cache entry zero
morefiles: .byte 0
fmready:  .byte 0
sysdev:   .byte 8
scanindex: .word 0
direrror: .byte 0
dslink:   .byte 0
dsblocks: .word 0
dslen:    .byte 0

; Read the directory as a BASIC program: load word, then linked lines
; (link word, block-count word, zero-terminated text), ending in a zero
; link. No fixed 32-byte record assumption: headers and device-specific
; listings have different line lengths. No painting while IEC is active.
dirscan:
        lda #$00
        sta fmcnt
        sta morefiles
        sta direrror
        sta dseof
        sta scanindex
        sta scanindex+1
        jsr CLRCHN
        lda #$05
        ldx fmdev
        ldy #$00
        jsr SETLFS
        lda #$01
        ldx #<dname
        ldy #>dname
        jsr SETNAM
        jsr OPEN
        bcc ds_open
        jmp ds_fail
ds_open:
        ldx #$05
        jsr CHKIN
        bcc ds_input
        jmp ds_fail
ds_input:
        jsr ds_get               ; load-address low/high
        jsr ds_get
        lda #$01
        sta dsfirst
ds_ent:
        jsr ds_get
        sta dslink
        jsr ds_get
        ora dslink
        bne ds_line
        jmp ds_end               ; null BASIC link = directory end
ds_line:
        lda direrror
        beq ds_readline
        jmp ds_end
ds_readline:
        jsr ds_get
        sta dsblocks
        jsr ds_get
        sta dsblocks+1
        lda #$00
        sta dslen
ds_text:
        jsr ds_get
        beq ds_parse
        ldx dslen
        cpx #63
        bcc ds_savechar
        jmp ds_fail
ds_savechar:
        sta dline,x
        inc dslen
        bne ds_text
ds_parse:
        ldx dslen
        lda #$00
        sta dline,x
        sta dline+1,x
        sta dline+2,x
        lda dsfirst
        beq ds_name
        dec dsfirst
        jmp ds_ent
ds_name:
        ldx #$00
ds_q1:
        cpx dslen
        bcc ds_quotechar
        jmp ds_ent
ds_quotechar:
        lda dline,x
        inx
        cmp #$22
        bne ds_q1
        ldy #$00
ds_nc:
        cpx dslen
        bcc ds_namechar
        jmp ds_fail
ds_namechar:
        lda dline,x
        inx
        cmp #$22
        beq ds_ncend
        cpy #16
        bcc ds_savename
        jmp ds_fail
ds_savename:
        sta fnbuf,y
        iny
        bne ds_nc
ds_ncend:
        lda #$00
        sta fnbuf,y
        stx fmclose
        ; Ignore earlier cache pages; zero-block files still count.
        lda scanindex+1
        cmp cachebase+1
        bcc ds_skip
        bne ds_store
        lda scanindex
        cmp cachebase
        bcc ds_skip
ds_store:
        ldx fmcnt
        cpx #CACHE_MAX
        bcc ds_slot
        lda #$01
        sta morefiles
        jmp ds_end
ds_slot:
        lda fmnamesL,x
        sta r0L
        lda fmnamesH,x
        sta r0H
        lda dsblocks
        sta fmblockL,x
        lda dsblocks+1
        sta fmblockH,x
        ldy #$00
ds_cp:
        lda fnbuf,y
        sta (r0),y
        iny
        cpy #17
        bne ds_cp
        ; Type after closing quote: skip padding and unclosed marker.
        ldx fmclose
ds_typestart:
        lda dline,x
        cmp #$20
        beq ds_typepad
        cmp #$2a
        bne ds_typegot
ds_typepad:
        inx
        cpx dslen
        bcc ds_typestart
ds_typegot:
        lda fmcnt
        asl
        clc
        adc fmcnt
        tay
        lda dline,x
        sta fmtype,y
        lda dline+1,x
        sta fmtype+1,y
        lda dline+2,x
        sta fmtype+2,y
        inc fmcnt
ds_skip:
        inc scanindex
        bne ds_continue
        inc scanindex+1
        beq ds_fail
ds_continue:
        jmp ds_ent
ds_fail:
        lda #$01
        sta direrror
ds_end:
        jsr CLRCHN
        lda #$05
        jsr CLOSE
        cli
        rts

; CHRIN status is fresh only AFTER the read. Bit 6 accompanies a valid
; final byte; other bits are errors. Remember EOF to bound malformed input.
ds_get:
        lda direrror
        ora dseof
        bne ds_bad
        jsr CHRIN
        sta cpbyte
        jsr READST
        sta dseof
        and #$bf
        beq ds_good
        sta direrror
ds_bad:
        lda #$00
        rts
ds_good:
        lda cpbyte
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
p_cpyx: .text "COPY TO OTHER DEV AS:", 0
p_d0:   .byte $24,$30,$3a,$00   ; "$0:" unshifted (see p_s0 note)
p_bsep: .text " B=", 0
w_sufx: .byte $2c,$53,$2c,$57,$00     ; ",S,W" unshifted (see p_s0 note)
msg_scr: .text "scratched", 0
msg_ren: .text "renamed", 0
msg_cpy: .text "copied", 0
msg_to8: .text "copied to device 8", 0
msg_to9: .text "copied to device 9", 0
msg_to10: .text "copied to device 10", 0
msg_to11: .text "copied to device 11", 0
copymsgL: .byte <msg_to8,<msg_to9,<msg_to10,<msg_to11
copymsgH: .byte >msg_to8,>msg_to9,>msg_to10,>msg_to11
msg_err: .text "copy failed", 0
msg_direrr: .text "directory read failed", 0
csrcbuf: .fill 24, 0                      ; copy: dest name (name + ",S,W")
cpbuf:   .fill 256, 0                     ; copy: one page in flight

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
bnum:   .word 0
cpbyte: .byte 0
cpst:   .byte 0
errtag: .byte 0
dc_cnt: .byte 0
linebuf:.byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
        .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
dseof:  .byte 0
dsfirst: .byte 0
dline:  .fill 66, 0

        .cerror * > SETREC, "file manager overlaps persistent settings"
