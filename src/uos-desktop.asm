;==========================================================================
; UltOS
; Scott Hutter
;
;   This file is part of UltOS.
;
;    UltOS is free software: you can redistribute it and/or modify
;    it under the terms of the GNU General Public License as published by
;    the Free Software Foundation, either version 3 of the License, or
;    (at your option) any later version.
;
;    UltOS is distributed in the hope that it will be useful,
;    but WITHOUT ANY WARRANTY; without even the implied warranty of
;    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
;    GNU General Public License for more details.
;
;    You should have received a copy of the GNU General Public License
;    along with UltOS.  If not, see <https://www.gnu.org/licenses/>.
;==========================================================================

.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "kernal.inc"
.include "vic-ii.inc"
.include "io.inc"


* = DESK_START

        ; One-way entry: callers `jmp` here from any stack depth (core
        ; esc_to_desk, app EXITs, click handlers), so the caller's frames
        ; are dead on arrival. Reset the stack and re-enter the core loop
        ; at the end instead of RTS - an RTS here pops an empty stack and
        ; kills the TICK dispatch (proven in tests/dbg_esc.py).
        ldx #$ff
        txs

        ; Clear the screen before redrawing. Every app exit (fmgr ESC, shell
        ; EXIT, settings back, core esc_to_desk) lands here, and the
        ; outline-pattern apps paint straight onto the desktop bitmap with
        ; XOR text and never restore it — on the real C128 the file
        ; manager's rows/title/hint stayed on screen after exit and piled
        ; up on every open ("opens too big, seems broke"). GFX_ON does the
        ; colour-RAM fill + CLEARBITMAP.
        ; Background colour is user-selectable (settings 'C'): the colour
        ; byte GFX_ON wants is (fg<<4)|bg; fg stays black (high nibble 0),
        ; so A = the low-nibble background colour from the settings record.
        lda SETREC_BG
        and #$0f
        bne _bgok
        lda #$10                ; black background: GFX_ON treats colour byte
                                ; $00 as "skip the clear", and black-on-black
                                ; icons are invisible — use a white foreground
                                ; (byte $10) so the clear runs and icons show
_bgok:  jsr GFX_ON

        ; #HiresOn's colour fill spans $8400-$87ff, and the VIC sprite
        ; pointers live in its last 8 bytes ($87f8+) — the fill leaves the
        ; pointer sprite aimed at garbage (a "block of lines"). Restore
        ; sprite 0 to the arrow shape at $8000 (data itself is untouched).
        lda #$00
        sta $87f8

        #RegisterApp

        lda #$ff
        sta minute              ; force the clock redraw on the first tick
        lda #<APP_TICK
        sta $033c
        lda #>APP_TICK
        sta $033d

        jsr clr_ctls            ; fresh control table on every entry

        #PenWrite
        #DrawLine 0,189,319,189
        
        #CreateButton 0, 0, <MNU_ULTOS, >MNU_ULTOS, 0,189,30,199,true
        #Text 5, 191, mnu_main
        
        #Text 282, 191, time

        #CreateButton 0, 1, <ON_CLICK_COMPUTER, >ON_CLICK_COMPUTER, 10,5,10+24,5+44, false
        #DrawImage 10, 5, 24, 44, img_computer
        #Text 5, 25, computer

        #DrawImage 280, 150, 24, 44, img_trash
        #Text 283,174, trash
        
        #SaveScreen

        ; 80-column companion: the desktop owns rows 2-23; blank them (an
        ; app may have left its listing there) and announce the desktop.
        jsr vd_reset
        jmp MAINLOOP

vd_desk: .text "desktop", $00
computer:
        .text "computer", $00
trash:
        .text "trash", $00



APP_TICK = *
        lda minute      ; check if minute has changed
        cmp TODMIN
        bne _updateclock
        jmp _done
_updateclock:           ; if so, update the clock
        lda TODMIN
        sta minute

        #ClrRect 280, 191, 39, 8
        #DrawLine 280,189,319,189

        ldy #$00
        lda TODHRS      ; hour (tens)
        and #$7f        ; ignore AM/PM for now
        ror
        clc 
        ror
        clc 
        ror
        clc 
        ror
        clc
        and #$0f
        adc #$30        ; convert to petscii
        sta time,y
        iny
        lda TODHRS      ; hour (ones)
        and #$0f
        adc #$30        ; convert to petscii
        sta time,y
        iny
        lda #':'
        sta time,y
        iny
        lda TODMIN      ;mins (tens)
        ror
        clc 
        ror
        clc 
        ror
        clc 
        ror
        clc
        and #$0f
        adc #$30        ; convert to petscii
        sta time,y
        iny
        lda TODMIN      ; mins (ones)
        and #$0f
        adc #$30        ; convert to petscii
        sta time,y
        iny
        iny
        lda TODHRS      ; check if AM/PM
        and #$80
        cmp #$80
        beq _pm 
        lda #'A'
        sta time,y
        jmp _startclk
_pm:    lda #'P'
        sta time,y 
.comment
        iny
        lda #':'
        sta time,y
        iny
        lda $dc09       ; secs (tens)
        ror
        clc 
        ror
        clc 
        ror
        clc 
        ror
        clc
        and #$0f
        adc #$30        ; convert to petscii
        sta time,y
        iny
        lda $dc09       ; secs (ones)
        and #$0f
        adc #$30        ; convert to petscii
        sta time,y
.endc
_startclk:
        lda $dc08       ; tod has stopped since we read the hour value
        sta $dc08       ; writing to the 10th/sec value restarts tod

        jsr vd_clock    ; 80-column mirror: time + how it was set (row 0)
        jsr vd_status   ; row 24: date + ip + clock source
        #Text 282, 191, time
_done:
        rts

; vdtime = time + "  " + clock tag, written at row 0 col 58 (fits col 79)
vd_clock:
        ldx #$00
_vc_t:  lda time,x
        beq _vc_sp
        sta vdtime,x
        inx
        bne _vc_t
_vc_sp: lda #' '
        sta vdtime,x
        inx
        sta vdtime,x
        inx
        jsr clk_tag             ; r0 -> tag text for NET_STATE
        ldy #$00
_vc_c:  lda (r0),y
        beq _vc_p
        sta vdtime,x
        inx
        iny
        bne _vc_c
_vc_p:  lda #' '                ; pad to 22 columns (58..79): a shorter tag
        sta vdtime,x            ; must blank the tail of the previous one
        inx
        cpx #22
        bne _vc_p
        lda #$00
        sta vdtime,x
_vc_w:  lda #<vdtime
        sta r9L
        lda #>vdtime
        sta r9H
        lda #$00
        ldx #58
        jsr VDTEXT
        rts

; r0 -> the short text for NET_STATE (0-4, anything else = "unsynced").
; Uses Y only: the callers keep their output index in X (the first cut
; loaded X here and the tag landed at offset NET_STATE: "12:no ultimate")
clk_tag:
        ldy NET_STATE
        cpy #$05
        bcc _ck_ok
        ldy #$05
_ck_ok: lda clktagL,y
        sta r0L
        lda clktagH,y
        sta r0H
        rts
clktagL: .byte <ctag0, <ctag1, <ctag2, <ctag3, <ctag4, <ctag5
clktagH: .byte >ctag0, >ctag1, >ctag2, >ctag3, >ctag4, >ctag5
ctag0:  .text "ntp", $00
ctag1:  .text "no reply", $00
ctag2:  .text "no network", $00
ctag3:  .text "no ultimate", $00
ctag4:  .text "no ntp host", $00
ctag5:  .text "unsynced", $00
vdtime: .fill 24, 0

WIN_OK = *
        jmp ON_CLOSE

;==========================================================================
; Applications launcher
;
; Reads the drive directory live, lists every "uos-*" app found on the
; system disk (up to APPS_MAX rows), each row clickable.  Rows launch via
; the core FILLFILE + APP_LOADER path, so any app dropped on the disk
; shows up without touching this code.
;
; Coordinates are 320x200 bitmap; rows are unrolled (6 fixed trampolines)
; because callbacks carry no context.
;==========================================================================
APPS_MAX        := 6
APPS_X          := 70
APPS_Y          := 60
APPS_W          := 180
APPS_ROW_H      := 14

apps_title:     .text "Applications", $00
noapps:         .text "no apps found on disk", $00

MENU_APPS = *
        jsr closemenu

        ; CreateWindow takes x, y, WIDTH, HEIGHT (it used to be handed the
        ; far corner: height 152 pushed the rect rows to band 26 = $c0c0 and
        ; the REU stash/fetch overwrote the graphics engine on real hardware)
        #CreateWindow 1,APPS_X,APPS_Y,APPS_W,110,true,apps_title

        ; 80-column companion: title on row 2, the app rows follow (4..)
        lda #<apps_title
        sta r9L
        lda #>apps_title
        sta r9H
        lda #$02
        ldx #$00
        jsr VDTEXT

        jsr dir_scan_apps

        lda apps_count
        bne _populate

        #Text APPS_X+6, APPS_Y+22, noapps
        jmp _apps_ok

_populate:
        ; draw rows at runtime via GPUTS: r9 = string, X1 = x word, Y1 = y
        jsr draw_rows

        ldx apps_count
        cpx #$01
        bcc _r1skip
        jmp _apps_ok
_r1skip:
        #CreateButton 1,20,<APPS_LAUNCH_1, >APPS_LAUNCH_1, APPS_X+2, APPS_Y+18, APPS_X+APPS_W-4, APPS_Y+18+APPS_ROW_H, false
        cpx #$02
        bcs _r2
        jmp _apps_ok
_r2:
        #CreateButton 1,21,<APPS_LAUNCH_2, >APPS_LAUNCH_2, APPS_X+2, APPS_Y+18+APPS_ROW_H, APPS_X+APPS_W-4, APPS_Y+18+(APPS_ROW_H*2), false
        cpx #$03
        bcs _r3
        jmp _apps_ok
_r3:
        #CreateButton 1,22,<APPS_LAUNCH_3, >APPS_LAUNCH_3, APPS_X+2, APPS_Y+18+(APPS_ROW_H*2), APPS_X+APPS_W-4, APPS_Y+18+(APPS_ROW_H*3), false
        cpx #$04
        bcs _r4
        jmp _apps_ok
_r4:
        #CreateButton 1,23,<APPS_LAUNCH_4, >APPS_LAUNCH_4, APPS_X+2, APPS_Y+18+(APPS_ROW_H*3), APPS_X+APPS_W-4, APPS_Y+18+(APPS_ROW_H*4), false
        cpx #$05
        bcs _r5
        jmp _apps_ok
_r5:
        #CreateButton 1,24,<APPS_LAUNCH_5, >APPS_LAUNCH_5, APPS_X+2, APPS_Y+18+(APPS_ROW_H*4), APPS_X+APPS_W-4, APPS_Y+18+(APPS_ROW_H*5), false
        cpx #$06
        bcs _r6
        jmp _apps_ok
_r6:
        #CreateButton 1,25,<APPS_LAUNCH_6, >APPS_LAUNCH_6, APPS_X+2, APPS_Y+18+(APPS_ROW_H*5), APPS_X+APPS_W-4, APPS_Y+18+(APPS_ROW_H*6), false

_apps_ok:
        #CreateButton 1,29,<APPS_CANCEL, >APPS_CANCEL, APPS_X+APPS_W-38, APPS_Y+96, APPS_X+APPS_W-8, APPS_Y+104, true
        #Text APPS_X+APPS_W-34, APPS_Y+97, cancel
        jmp MAINLOOP

; draws up to apps_count rows with GPUTS
draw_rows:
        lda apps_count
        beq _drdone
        cmp #APPS_MAX
        bcc _drlim
        lda #APPS_MAX
_drlim:
        sta rows_drawn
        ldx #$00
_drl:   jsr _drrow              ; (was: jsr for row 0, then a plain branch
        inx                     ; into _drrow whose rts left draw_rows early,
        cpx rows_drawn          ; and GPUTS had clobbered X anyway)
        bcc _drl
_drdone:
        rts
_drrow:
        ; r0 = row buffer address (rowadd tables), r9 = same (GPUTS ptr)
        lda rowadd_lo,x
        sta r0L
        sta r9L
        lda rowadd_hi,x
        sta r0H
        sta r9H
        ; X1 = APPS_X+6 word; Y1 = APPS_Y+10 + row*APPS_ROW_H
        lda #<APPS_X+6
        sta X1
        lda #>APPS_X+6
        sta X1+1
        lda #APPS_Y+22          ; below the 14 px title bar (rows used to
        sta Y1                  ; start at +10 and overprint the title)
        txa                     ; row index -> y offset row*14
        asl
        sta vartmp1             ; 2*row
        asl
        sta vartmp2             ; 4*row
        asl
        sta vartmp3             ; 8*row
        lda vartmp1
        clc
        adc vartmp2             ; 6*row
        adc vartmp3             ; 14*row
        clc
        adc Y1
        sta Y1
        stx vartmp1             ; GPUTS clobbers X: keep the row index
        jsr GPUTS
        ldx vartmp1
        ; mirror the row on the 80-column display (row 4+X, col 4)
        lda rowadd_lo,x
        sta r9L
        lda rowadd_hi,x
        sta r9H
        txa
        clc
        adc #$04
        ldx #$04
        jsr VDTEXT
        ldx vartmp1
        rts
rows_drawn:
        .byte $00
vartmp1: .byte $00
vartmp2: .byte $00
vartmp3: .byte $00
APPS_LAUNCH_1:
        lda #<row1
        jmp apps_launch
APPS_LAUNCH_2:
        lda #<row2
        jmp apps_launch
APPS_LAUNCH_3:
        lda #<row3
        jmp apps_launch
APPS_LAUNCH_4:
        lda #<row4
        jmp apps_launch
APPS_LAUNCH_5:
        lda #<row5
        jmp apps_launch
APPS_LAUNCH_6:
        lda #<row6
        jmp apps_launch

apps_launch:
        sta r0L
        lda #>row1
        sta r0H
        jsr FILLFILE
        jmp LAUNCH_APP          ; clears the screen; DESK_START drops the
                                ; window's controls when the app returns

APPS_CANCEL:
        jmp ON_CLOSE            ; same as the title-bar close box

;--------------------------------------------------------------------------
; dir_scan_apps: OPEN 5,8,0,"$"; walk the 1541 directory stream; any prg
; whose name starts with "uos-" is copied into the next free row buffer.
; Uses kernal serial file ops; leaves apps_count/apps rows filled.
;--------------------------------------------------------------------------
dirname:        .text "$"
dirnamesz       := 1
uospref:        .text "uos-"

; components that must never appear in the launcher (loading them over
; the running system would crash it)
SYSCOMPS_N      := 9
syscomps:
        .text "uos", $00
        .text "uos-net", $00
        .text "uos-gfx", $00
        .text "uos-vdc", $00
        .text "uos-drv1351", $00
        .text "uos-sprites", $00
        .text "uos-reu", $00
        .text "uos-desktop", $00
        .text "uos-set", $00

; 17-byte name slots (16 + terminator): dir_scan_apps zeroes and apps_add
; copies 17 bytes per row; they were 1-byte placeholders, so every name
; overwrote the following rows (the launcher never listed correctly)
row1:   .fill 17, 0
row2:   .fill 17, 0
row3:   .fill 17, 0
row4:   .fill 17, 0
row5:   .fill 17, 0
row6:   .fill 17, 0

ftmpname:       .fill 17, 0     ; 16-char name + terminator (was 8 bytes: the scan overflowed it)
dsline: .fill 32, 0
dsfirst: .byte 0
dseof:  .byte 0
                .byte $00,$00,$00,$00,$00,$00,$00,$00

dir_scan_apps:
        ; clear rows and counters
        ldx #$00
        lda #$00
_dzero:
        sta row1,x
        sta row2,x
        sta row3,x
        sta row4,x
        sta row5,x
        sta row6,x
        inx
        cpx #$11
        bne _dzero
        lda #$00
        sta apps_count

        lda #$05
        ldx #$08
        ldy #$00                ; secondary address 0 = read directory as file
        jsr $FFBA               ; SETLFS 5,8,0
        lda #dirnamesz
        ldx #<dirname
        ldy #>dirname
        jsr $FFBD               ; SETNAM "$"
        jsr $FFC0               ; OPEN
        bcc _dopenok
        rts                     ; device not present -> leave list empty

_dopenok:
        ldx #$05
        jsr $FFC6               ; CHKIN 5
        lda #$01
        sta dsfirst
        ; The "$" file is the BASIC-formatted listing (load address, then
        ; 32-byte lines: link, block count, quoted name, type), NOT raw
        ; directory sectors. Same parser as the file manager's dirscan.
_dentry:
        lda #$00
        sta dseof
        ldy #$00
_drd:   jsr $FFCF               ; CHRIN: one 32-byte record
        sta dsline,y
        iny
        jsr $FFB7               ; READST
        and #$40
        beq _dmore
        inc dseof               ; EOF: parse this record, then finish
        jmp _dparse
_dmore: cpy #32
        bne _drd
_dparse:
        lda dsfirst
        beq _dcnt
        lda #$00
        sta dsfirst
        jmp _dnextrec           ; first record carries the load address
_dcnt:  lda dsline+2
        ora dsline+3
        bne _dxinit
        jmp _dnextrec           ; block count 0 = disk title line
_dxinit:
        ldx #$00
_dq1:   lda dsline,x
        cmp #$22
        beq _dqgot
        inx
        cpx #32
        bne _dq1
        jmp _dnextrec           ; no quote: "blocks free" trailer
_dqgot: inx                     ; past the opening quote
        ldy #$00
_dnc:   lda dsline,x
        cmp #$22
        beq _dncend
        sta ftmpname,y
        inx
        iny
        cpy #$10
        bne _dnc
_dncend:
        lda #$00
        sta ftmpname,y          ; terminate (Y = length)
_dpad:  cpy #$10
        beq _dchk
        iny
        sta ftmpname,y          ; zero-fill to 16 so compares are clean
        jmp _dpad
_dchk:  jsr is_uos_app
        bcc _dnextrec
        jsr apps_add            ; copy ftmpname into the next free row
_dnextrec:
        lda dseof
        bne _dend
        jmp _dentry

_dend:
        lda #$0f
        jsr $FFCC               ; CLRCHN
        lda #$05
        jsr $FFC3               ; CLOSE 5
        rts

; does ftmpname start with "uos-" AND is it not a system component?
is_uos_app:
        ldy #$00
_iul:
        lda ftmpname,y
        cmp uospref,y
        bne _iuno
        iny
        cpy #$04
        bne _iul

        ; prefix matches; reject the boot + driver components
        lda #<syscomps
        sta r0L
        lda #>syscomps
        sta r0H
        ldx #$00
_iucmp:
        jsr cmp_sys_entry
        bcs _iuhide             ; it IS a system component -> hide
        ; step r0 past this entry's terminator to the next table entry
        ; (the old loop reset r0 to the table start every time, so only
        ; "uos" was ever compared and every module showed up as an app)
        ldy #$00
_iuadv: lda (r0),y
        beq _iuend
        iny
        bne _iuadv
_iuend: tya
        sec                     ; +Y+1
        adc r0L
        sta r0L
        bcc _iunext2
        inc r0H
_iunext2:
        inx
        cpx #SYSCOMPS_N
        bne _iucmp
        sec
        rts
_iuhide:
        clc
        rts
_iuno:
        clc
        rts

; compare ftmpname with the r0-pointed syscomp name ($00-terminated)
cmp_sys_entry:
        ldy #$00
_csl:
        lda ftmpname,y
        beq _csmatch            ; ftmpname ended exactly -> equal
        cmp (r0),y
        bne _csno
        iny
        cpy #$11
        bne _csl
        clc
        rts
_csmatch:
        lda (r0),y
        beq _csyes              ; both terminated -> equal
_csno:
        clc
        rts
_csyes:
        sec
        rts

; copy ftmpname into the next free row buffer
apps_add:
        ldx apps_count
        cpx #APPS_MAX
        bcs _aafull
        lda rowadd_lo,x
        sta r0L
        lda rowadd_hi,x
        sta r0H
        ldy #$00
_aacp:
        lda ftmpname,y
        beq _aazer
        sta (r0),y
        iny
        cpy #$11
        bne _aacp
_aazer:
        lda #$00
        sta (r0),y
        inc apps_count
_aafull:
        rts

rowadd_lo:      .byte <row1, <row2, <row3, <row4, <row5, <row6
rowadd_hi:      .byte >row1, >row2, >row3, >row4, >row5, >row6

apps_count:     .byte $00

;--------------------------------------------------------------------------
; Applications launcher
; Reads the drive directory live and lists every "uos-*" app found on
; the disk (up to APPS_MAX), each clickable.  Clicking one loads it the
; same way MENU_SETTINGS does, so any app the author drops on the disk
; shows up without touching this code.
;--------------------------------------------------------------------------
; The menu entries launch through the core's LAUNCH_APP (FILLFILE + the
; launcher path): it clears the desktop bitmap first. The old LOAD_IMM +
; APP_LOADER path left the icons and the ultos bar under the app, so the
; file manager's title collided with the "computer" label and the settings
; shadow sat on the trash can (visible in tests/screens.py captures).
MENU_FILEMGR = *
        jsr closemenu
        lda #<s_fmgr
        sta r0L
        lda #>s_fmgr
        sta r0H
        jsr FILLFILE
        jmp LAUNCH_APP

MENU_SETTINGS = *
        jsr closemenu
        lda #<s_settings
        sta r0L
        lda #>s_settings
        sta r0H
        jsr FILLFILE
        jmp LAUNCH_APP

; "command line" opens the shell (it used to show a placeholder dialog)
MENU_CMDLN = *
        jsr closemenu
        lda #<s_shell
        sta r0L
        lda #>s_shell
        sta r0H
        jsr FILLFILE
        jmp LAUNCH_APP

MENU_CALC = *
        jsr closemenu
        lda #<s_calc
        sta r0L
        lda #>s_calc
        sta r0H
        jsr FILLFILE
        jmp LAUNCH_APP

s_fmgr:     .text "uos-fmgr", $00
s_settings: .text "uos-settings", $00
s_shell:    .text "uos-shell", $00
s_calc:     .text "uos-calc", $00

MENU_QUIT = *
        jsr closemenu
        #DrawRect 100,70,119,70,1      
        #Text 112, 80, dlg_quit

        top := 120
        left := 180
        width := 30
        height := 10
        #CreateButton 1,1,<QUIT_YES, >QUIT_YES, left, top, left + width, top + height,true
        #Text 189, 122, yes

        top := 120
        left := 140
        width := 30
        height := 10
        #CreateButton 1,2,<QUIT_NO, >QUIT_NO, left, top, left + width, top + height,true
        #Text 148, 122, no 

        jmp MAINLOOP

QUIT_YES:
        jmp $fce2

QUIT_NO:
        jmp ON_CLOSE


MNU_ULTOS = *
        lda menuopen
        beq _openmenu

_farclosemenu:
        jsr closemenu
        jmp MAINLOOP

_openmenu:
        #SaveScreen
        lda #$01
        sta menuopen
        
        height := 12
        left := 0
        width := 75
        top := 105

        #CreateButton 2, 1, <MENU_APPS,  >MENU_APPS, left, top + (height * 1), width, (top + height) + (height*1),true
        #Text left + 5, top + 4 + (height * 1), mnu_apps
        #CreateButton 2, 2, <MENU_FILEMGR,  >MENU_FILEMGR, left, top + (height * 2), width, (top + height) + (height*2),true
        #Text left + 5, top + 4 + (height * 2), mnu_fileman
        #CreateButton 2, 3, <MENU_SETTINGS, >MENU_SETTINGS,left, top + (height * 3), width, (top + height) + (height*3),true
        #Text left + 5, top + 4 + (height * 3), mnu_settings
        #CreateButton 2, 4, <MENU_CMDLN,    >MENU_CMDLN   ,left, top + (height * 4), width, (top + height) + (height*4),true
        #Text left + 5, top + 4 + (height * 4), mnu_cmdline
        #CreateButton 2, 5, <MENU_CALC,     >MENU_CALC    ,left, top + (height * 5), width, (top + height) + (height*5),true
        #Text left + 5, top + 4 + (height * 5), mnu_calc
        #CreateButton 2, 6, <MENU_QUIT,     >MENU_QUIT    ,left, top + (height * 6), width, (top + height) + (height*6),true
        #Text left + 5, top + 4 + (height * 6), mnu_quit

        jmp MAINLOOP

closemenu:
        #FetchScreen
        lda #$02                ; free every popup-menu control (layer 2).
        jsr rm_app_ctls         ; The old RemoveButton 0,1..4 removed the
                                ; FIRST (0,1) = the computer icon (id clash)
                                ; and never removed quit (0,5).
        lda #$00
        sta menuopen
        rts

ON_CLICK_COMPUTER:

        #CreateWindow 1,80,48,159,84,true,win_computer_title
        ; "about this computer": version, second display state, REU size,
        ; network address, clock source
        #Text 86, 66, ci_ver
        lda VDC_LIVE
        beq _ci_off
        #Text 86, 76, ci_vdc_on
        jmp _ci_reu
_ci_off:
        #Text 86, 76, ci_vdc_off
_ci_reu:
        jsr REU_SIZE            ; A = number of 64K banks (1 = no REU;
        sta ci_banks            ;  0 = wrapped: 256+ banks = 16 MB U2+)
        jsr ci_fmt_banks
        #Text 86, 86, ci_reubuf
        jsr ci_fmt_ip           ; "ip: 192.168.1.42" / "ip: none" / "ip: no ultimate"
        #Text 86, 96, ci_ipbuf
        jsr ci_fmt_clk          ; "clock: ntp" / "clock: no network" ...
        #Text 86, 106, ci_clkbuf
        ; 80-column mirror (rows 2-7)
        lda #<win_computer_title
        sta r9L
        lda #>win_computer_title
        sta r9H
        lda #$02
        ldx #$00
        jsr VDTEXT
        lda #<ci_ver
        sta r9L
        lda #>ci_ver
        sta r9H
        lda #$04
        ldx #$02
        jsr VDTEXT
        lda #<ci_reubuf
        sta r9L
        lda #>ci_reubuf
        sta r9H
        lda #$05
        ldx #$02
        jsr VDTEXT
        lda #<ci_ipbuf
        sta r9L
        lda #>ci_ipbuf
        sta r9H
        lda #$06
        ldx #$02
        jsr VDTEXT
        lda #<ci_clkbuf
        sta r9L
        lda #>ci_clkbuf
        sta r9H
        lda #$07
        ldx #$02
        jsr VDTEXT
        jmp MAINLOOP

; ci_ipbuf = "ip: " + NET_IPSTR, or "ip: none" / "ip: no ultimate"
ci_fmt_ip:
        ldx #$00
_cip_p: lda ci_ip_pfx,x
        beq _cip_v
        sta ci_ipbuf,x
        inx
        bne _cip_p
_cip_v: lda NET_STATE
        cmp #$03
        bne _cip_n
        lda #<ctag3             ; "no ultimate"
        sta r0L
        lda #>ctag3
        sta r0H
        jmp _cip_c
_cip_n: lda NET_IPSTR
        beq _cip_none
        lda #<NET_IPSTR
        sta r0L
        lda #>NET_IPSTR
        sta r0H
        jmp _cip_c
_cip_none:
        lda #<ci_none
        sta r0L
        lda #>ci_none
        sta r0H
_cip_c: ldy #$00
_cip_l: lda (r0),y
        sta ci_ipbuf,x
        beq _cip_d
        inx
        iny
        bne _cip_l
_cip_d: rts

; ci_clkbuf = "clock: " + tag
ci_fmt_clk:
        ldx #$00
_ccl_p: lda ci_clk_pfx,x
        beq _ccl_v
        sta ci_clkbuf,x
        inx
        bne _ccl_p
_ccl_v: jsr clk_tag
        ldy #$00
_ccl_l: lda (r0),y
        sta ci_clkbuf,x
        beq _ccl_d
        inx
        iny
        bne _ccl_l
_ccl_d: rts
ci_ip_pfx:  .text "ip: ", $00
ci_clk_pfx: .text "clock: ", $00
ci_none:    .text "none", $00
ci_ipbuf:   .fill 24, 0
ci_clkbuf:  .fill 24, 0

; ci_reubuf = "reu: NNN x 64k" from ci_banks (0 -> "reu: 16 mb")
ci_fmt_banks:
        lda ci_banks
        bne _cf_dec
        ldx #$00
_cf_16: lda ci_16mb,x
        sta ci_reubuf,x
        beq _cf_done
        inx
        bne _cf_16
_cf_dec:
        ldx #$00
_cf_cp: lda ci_reu_pfx,x
        beq _cf_num
        sta ci_reubuf,x
        inx
        bne _cf_cp
_cf_num:
        ; 3-digit decimal of ci_banks
        lda ci_banks
        ldy #$30
_cf_h:  cmp #100
        bcc _cf_h1
        sbc #100
        iny
        bne _cf_h
_cf_h1: pha
        tya
        sta ci_reubuf,x         ; (no STY abs,X on the 6502)
        pla
        inx
        ldy #$30
_cf_t:  cmp #10
        bcc _cf_t1
        sbc #10
        iny
        bne _cf_t
_cf_t1: pha
        tya
        sta ci_reubuf,x
        pla
        inx
        clc
        adc #$30
        sta ci_reubuf,x
        inx
        ldy #$00
_cf_sf: lda ci_reu_sfx,y
        sta ci_reubuf,x
        beq _cf_done
        inx
        iny
        bne _cf_sf
_cf_done:
        rts
ci_ver:     .text "UltOS 0.3 C128/8502", $00
ci_vdc_on:  .text "80-col display: on", $00
ci_vdc_off: .text "80-col display: off", $00
ci_reu_pfx: .text "reu: ", $00
ci_reu_sfx: .text " x 64k", $00
ci_16mb:    .text "reu: 16 mb", $00
ci_banks:   .byte $00
ci_reubuf:  .fill 20, 0

; ON_CLOSE — the one close path for every window/dialog (title-bar X,
; Cancel, No, OK). It used to #CloseWindow the Computer window's hardcoded
; rect, so the X on the Applications window restored the wrong pixels; and
; nothing ever freed the close box itself. Windows are modal over a static
; desktop whose full screen was stashed in DESK_START, so restoring that
; stash erases any window; freeing layer 1 drops the window's controls.
ON_CLOSE:
        #FetchScreen
        lda #$01
        jsr rm_app_ctls
        jsr vd_reset            ; 80-col rows back to "desktop"
        lda #$ff
        sta minute              ; the restored stash carries a stale clock:
        jmp MAINLOOP            ; redraw it on the next tick

; free every control slot belonging to layer A (0 desktop, 1 window/dialog,
; 2 popup menu). Slots are 10 bytes; 25 of them ($9001-$90fa).
rm_app_ctls:
        sta rmid
        ldx #$00
        ldy #25
_ra_l:  lda APP_CTL_BUF,x
        cmp rmid
        bne _ra_n
        lda #$ff
        sta APP_CTL_BUF,x
        sta APP_CTL_BUF+1,x
        dec APP_CTL_CTR
_ra_n:  txa
        clc
        adc #$0a
        tax
        dey
        bne _ra_l
        rts
rmid:   .byte 0

; empty the control table: every desktop (re-)entry starts clean, so a
; window or app that was open when the desktop was left cannot leave ghost
; click targets behind
clr_ctls:
        lda #$00
        sta APP_CTL_CTR
        lda #$ff
        ldx #$00
_cc_l:  sta APP_CTL_BUF,x
        inx
        cpx #250
        bne _cc_l
        rts

; 80-column companion: the desktop owns rows 2-23; blank them and announce
vd_reset:
        lda #$02
_vdclr: pha
        jsr VDCLR
        pla
        clc
        adc #$01
        cmp #24
        bne _vdclr
        lda #<vd_desk
        sta r9L
        lda #>vd_desk
        sta r9H
        lda #$02
        ldx #$00
        jsr VDTEXT
        ; fall through to the row-24 status line

; vd_status — persistent status on VDC row 24: "YYYY-MM-DD  ip A.B.C.D  src"
; built from uos-net's NET_YEAR/MON/DAY, NET_IPSTR and NET_STATE. Row 24 is
; below the app area (rows 2-23), so windows/apps never touch it.
vd_status:
        ldx #$00
        lda NET_YEAR
        sta vsw
        lda NET_YEAR+1
        sta vsw+1
        jsr vs_put4                     ; YYYY
        lda #'-'
        sta statbuf,x
        inx
        lda NET_MON
        jsr vs_put2
        lda #'-'
        sta statbuf,x
        inx
        lda NET_DAY
        jsr vs_put2
        lda #' '                        ; "  " separator
        sta statbuf,x
        inx
        sta statbuf,x
        inx
        lda NET_IPSTR
        beq _vs_noip
        ldy #$00                        ; "ip " + dotted address
_vs_pp: lda vs_ippfx,y
        beq _vs_ic
        sta statbuf,x
        inx
        iny
        bne _vs_pp
_vs_ic: ldy #$00
_vs_il: lda NET_IPSTR,y
        beq _vs_src
        sta statbuf,x
        inx
        iny
        cpy #16
        bne _vs_il
        jmp _vs_src
_vs_noip:
        ldy #$00
_vs_nn: lda vs_none,y
        beq _vs_src
        sta statbuf,x
        inx
        iny
        bne _vs_nn
_vs_src:
        lda #' '
        sta statbuf,x
        inx
        sta statbuf,x
        inx
        jsr clk_tag                     ; r0 -> source text
        ldy #$00
_vs_sc: lda (r0),y
        beq _vs_end
        sta statbuf,x
        inx
        iny
        cpx #78
        bne _vs_sc
_vs_end:
        lda #' '
_vs_pad:
        cpx #78
        bcs _vs_term
        sta statbuf,x
        inx
        bne _vs_pad
_vs_term:
        lda #$00
        sta statbuf,x
        lda #<statbuf
        sta r9L
        lda #>statbuf
        sta r9H
        lda #24
        ldx #$00
        jmp VDTEXT

; A (byte, 0-99) -> two decimal digits at statbuf,x
vs_put2:
        ldy #$2f                        ; first iny -> $30 = '0'
_v2t:   iny
        sec
        sbc #10
        bcs _v2t
        adc #10                         ; A = ones digit (0-9)
        pha
        tya                             ; Y already holds the tens as '0'..'9'
        sta statbuf,x
        inx
        pla
        clc
        adc #$30
        sta statbuf,x
        inx
        rts

; vsw (16-bit) -> four decimal digits at statbuf,x (leading zeros kept)
vs_put4:
        lda #<1000
        sta vsdiv
        lda #>1000
        sta vsdiv+1
        jsr vs_digit                    ; thousands
        lda #<100
        sta vsdiv
        lda #$00
        sta vsdiv+1
        jsr vs_digit                    ; hundreds
        lda #10
        sta vsdiv
        lda #$00
        sta vsdiv+1
        jsr vs_digit                    ; tens
        lda vsw
        clc
        adc #$30
        sta statbuf,x                   ; ones
        inx
        rts
vs_digit:
        lda #$00
        sta vsdig
_vd_l:  lda vsw+1                       ; vsw >= vsdiv ?
        cmp vsdiv+1
        bcc _vd_done
        bne _vd_sub
        lda vsw
        cmp vsdiv
        bcc _vd_done
_vd_sub:
        sec
        lda vsw
        sbc vsdiv
        sta vsw
        lda vsw+1
        sbc vsdiv+1
        sta vsw+1
        inc vsdig
        jmp _vd_l
_vd_done:
        lda vsdig
        clc
        adc #$30
        sta statbuf,x
        inx
        rts
vs_ippfx: .text "ip ", $00
vs_none:  .text "no ip", $00
statbuf:  .fill 80, 0
vsw:      .word 0
vsdiv:    .word 0
vsdig:    .byte 0

win_computer_title:
        .text "Computer", $00
x:
        .text "x", $00

;WAIT     JSR GETIN
;         BEQ WAIT
;         RTS

dlg_apps:       .text "Apps submenu", $00
dlg_fileman:    .text "File manager", $00
dlg_settings:   .text "Settings", $00
dlg_cmd:        .text "Cmd Line", $00
dlg_quit:       .text "Quit: Are you sure?", $00

mnu_apps:       .text "applications", $00
mnu_fileman:    .text "file manager", $00
mnu_quit:       .text "quit", $00
mnu_settings:   .text "settings", $00
mnu_cmdline:    .text "command line", $00
mnu_calc:       .text "calculator", $00
mnu_main:       .text "ultos", $00

time:           .text "12:00 PM", $00

yes:    .text "Yes", $00
no:     .text "No", $00
ok:     .text "Ok", $00
cancel: .text "Cancel", $00

menuopen:
        .byte $00

minute:
        .byte $00

.include "icons_desktop.inc"
