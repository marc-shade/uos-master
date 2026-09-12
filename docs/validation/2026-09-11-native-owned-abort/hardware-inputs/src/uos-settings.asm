;==========================================================================
; UltOS settings app v2 (FR-S3)
; Scott Hutter (upstream base); keyboard-first rewrite (fork).
;     D = cycle display mode (0=40, 1=80, 2=both) and kernal-SAVE "UOS-SET"
;     B / ESC = back to the desktop
;   #CreateWindow is deliberately NOT used here: its SaveRect/ClrRect REU
;   fills destabilise any app opened over the desktop (the CPU lands in
;   data RAM; see the fmgr note). Same outline pattern as the fmgr.
;==========================================================================

.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "kernal.inc"
.include "vic-ii.inc"
.include "io.inc"

oldshown        = $40    ; index of the mode text currently on screen
vtmpa           = $41
vtmpb           = $42

* = APP_START

    #RegisterApp

    #DrawRect 70,60,220,110,1
    ; title
    #Text 130, 66, title
    ; hint line
    #Text 80, 148, hint

    ; Loading this app overwrites the record at $7350 with its own compiled
    ; defaults (the app image is gap-padded up to $7350), so re-read UOS-SET
    ; from disk to show the values the user actually SAVED. Unshifted name so
    ; it matches the SAVE; an absent file just leaves the compiled defaults.
    lda #<savename
    sta r0L
    lda #>savename
    sta r0H
    jsr FILLFILE
    jsr APP_LOADER

    ; 80-column companion: header + hint; rows 4/5 mirror the two values
    jsr vd_clear_area
    lda #<title
    sta r9L
    lda #>title
    sta r9H
    lda #$02
    ldx #$00
    jsr VDTEXT
    lda #<hint
    sta r9L
    lda #>hint
    sta r9H
    lda #23
    ldx #$00
    jsr VDTEXT
    lda #<bglabel
    sta r9L
    lda #>bglabel
    sta r9H
    lda #$05
    ldx #$02
    jsr VDTEXT

    lda #$ff
    sta oldshown
    sta oldshowncol
    sta oldshowntz
    jsr draw_mode
    #Text 80, 100, bglabel
    jsr draw_color
    #Text 80, 112, tzlabel
    lda #<tzlabel
    sta r9L
    lda #>tzlabel
    sta r9H
    lda #$06
    ldx #$02
    jsr VDTEXT
    jsr draw_tz

    ; own the keyboard directly (like the fmgr and shell). The old design
    ; registered APP_KEY on the once-per-second tick and returned to the
    ; core main_loop; but main_loop ALSO polls KEYIN (for ESC), and being
    ; the faster of the two consumers it stole most keypresses before the
    ; tick could dispatch APP_KEY — the "app-lifecycle handoff" race that
    ; left D/B/ESC unreliable and the shell hop unreachable. A private
    ; input loop has a single KEYIN consumer, so every key is seen.
APP_KEY:
        jsr KEYIN
        cmp #$00
        beq APP_KEY
        cmp #$44                        ; 'D' — explicit unshifted PETSCII:
        bne _akc                        ; 64tass's #'D' assembles to $c4
        jsr ON_DISPLAY                  ; (shifted), which no keypress
        jmp APP_KEY                     ; ever produces
_akc:   cmp #$43                        ; 'C' = cycle background colour
        bne _akp
        jsr ON_COLOR
        jmp APP_KEY
_akp:   cmp #$2b                        ; '+' = zone one hour east
        bne _akm
        lda #$04
        jsr ON_TZ
        jmp APP_KEY
_akm:   cmp #$2d                        ; '-' = zone one hour west
        bne _akb
        lda #$fc
        jsr ON_TZ
        jmp APP_KEY
_akb:   cmp #$42                        ; 'B'
        beq _akbk
        cmp #$1b                        ; ESC also backs out
        beq _akbk
        jmp APP_KEY
_akbk:  jmp settings_back

title:  .text "Settings", $00
hint:   .text "D=display C=color +/-=zone ESC=back", $00
tzlabel: .text "time zone:", $00
bglabel: .text "background:", $00
mode0s: .text "display: 40 only", 0
mode1s: .text "display: 80 only", 0
mode2s: .text "display: both (40+80)", 0

modebuf: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
oldmode: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0

settings_back:
    #UnregisterApp
    jsr LOAD_IMM
    .text "uos-desktop",$00
    jsr APP_LOADER
    jmp DESK_START

; ---------- display-mode cycle + persistence ----------
; ON_DISPLAY cycles the mode byte in the settings record (0=40,
; 1=80, 2=both) and SAVEs "UOS-SET" to the drive through the KERNAL.
; The record lives here in the app region; the saved PRG header carries
; this address, so the boot-time LOAD restores it to the same place.
ON_DISPLAY:
    lda SETREC_DISP
    clc
    adc #$01
    cmp #3
    bcc on_d_ok
    lda #0
on_d_ok:
    sta SETREC_DISP
    jsr save_record
    jsr draw_mode
    rts

; ---------- mode text draw (XOR-safe erase + redraw) ----------
draw_mode:
    lda oldshown
    cmp #$ff
    beq dm_build
    ; erase the previously shown string (redraw = XOR out)
    lda #80
    sta X1
    lda #$00
    sta X1+1
    lda #84
    sta Y1
    lda #<oldmode
    sta r9L
    lda #>oldmode
    sta r9H
    jsr GPUTS
dm_build:
    lda SETREC_DISP
    jsr mode_str                   ; r2 = text for the current mode
    ldy #$00
dm_cp:  lda (r2),y
    beq dm_done
    cpy #23
    bcs dm_done
    sta modebuf,y
    iny
    jmp dm_cp
dm_done:
    lda #$00
    sta modebuf,y                  ; keep the buffer $00-terminated
    ; publish as the shown string
    ldy #$00
dm_old: lda modebuf,y
    sta oldmode,y
    beq dm_show
    iny
    cpy #24
    bne dm_old                     ; loop (was `bne dm_show`: copied one
                                   ; byte, so the XOR erase only ever
                                   ; cleared the first glyph)
dm_show:
    lda SETREC_DISP
    sta oldshown
    lda #80
    sta X1
    lda #$00
    sta X1+1
    lda #84
    sta Y1
    lda #<oldmode
    sta r9L
    lda #>oldmode
    sta r9H
    jsr GPUTS
    ; mirror on the 80-column display (row 4, after the label)
    lda #$04
    jsr VDCLR
    lda #<oldmode
    sta r9L
    lda #>oldmode
    sta r9H
    lda #$04
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
vd_pad: .text "                    ", $00

; A = display mode (0..2) -> r2 = $00-terminated text
mode_str:
    tay
    lda strtab_lo,y
    sta r2L
    lda strtab_hi,y
    sta r2H
    rts
strtab_lo: .byte <mode0s, <mode1s, <mode2s
strtab_hi: .byte >mode0s, >mode1s, >mode2s

; ---------- background-colour cycle + persistence ----------
; ON_COLOR advances SETREC_BG through the 16 VIC colours (wrap) and SAVEs.
; The desktop reads SETREC_BG when it clears the screen, so the new colour
; takes effect the moment you leave settings, and the boot re-applies it.
ON_COLOR:
    lda SETREC_BG
    clc
    adc #$01
    and #$0f                       ; wrap 0..15
    sta SETREC_BG
    jsr save_record
    jsr draw_color
    rts

oldshowncol: .byte $ff
colbuf:   .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
oldcolor: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0

; draw the current background-colour name at x=170,y=100 (XOR-safe: erase
; the previously shown name, then draw the new one)
draw_color:
    lda oldshowncol
    cmp #$ff
    beq dc_build
    lda #170
    sta X1
    lda #$00
    sta X1+1
    lda #100
    sta Y1
    lda #<oldcolor
    sta r9L
    lda #>oldcolor
    sta r9H
    jsr GPUTS
dc_build:
    lda SETREC_BG
    jsr col_str                    ; r2 = name for the current colour
    ldy #$00
dc_cp:  lda (r2),y
    beq dc_done
    cpy #19
    bcs dc_done
    sta colbuf,y
    iny
    jmp dc_cp
dc_done:
    lda #$00
    sta colbuf,y
    ldy #$00
dc_old: lda colbuf,y
    sta oldcolor,y
    beq dc_show
    iny
    cpy #20
    bne dc_old
dc_show:
    lda SETREC_BG
    sta oldshowncol
    lda #170
    sta X1
    lda #$00
    sta X1+1
    lda #100
    sta Y1
    lda #<oldcolor
    sta r9L
    lda #>oldcolor
    sta r9H
    jsr GPUTS
    ; mirror on the 80-column display (row 5, after the label)
    lda #<vd_pad
    sta r9L
    lda #>vd_pad
    sta r9H
    lda #$05
    ldx #14
    jsr VDTEXT
    lda #<oldcolor
    sta r9L
    lda #>oldcolor
    sta r9H
    lda #$05
    ldx #14
    jsr VDTEXT
    rts

; A = colour (0..15) -> r2 = $00-terminated name
col_str:
    tay
    lda coltab_lo,y
    sta r2L
    lda coltab_hi,y
    sta r2H
    rts
coltab_lo: .byte <col0,<col1,<col2,<col3,<col4,<col5,<col6,<col7
           .byte <col8,<col9,<cola,<colb,<colc,<cold,<cole,<colf
coltab_hi: .byte >col0,>col1,>col2,>col3,>col4,>col5,>col6,>col7
           .byte >col8,>col9,>cola,>colb,>colc,>cold,>cole,>colf
col0: .text "black",0
col1: .text "white",0
col2: .text "red",0
col3: .text "cyan",0
col4: .text "purple",0
col5: .text "green",0
col6: .text "blue",0
col7: .text "yellow",0
col8: .text "orange",0
col9: .text "brown",0
cola: .text "lt red",0
colb: .text "dk grey",0
colc: .text "md grey",0
cold: .text "lt green",0
cole: .text "lt blue",0
colf: .text "lt grey",0

; ---------- time zone (+/- one hour) ----------
; ON_TZ: A = signed quarter-hours delta. Clamps to -48..+56 (UTC-12..+14),
; SAVEs the record, redraws, and shifts the running clock at once through
; the driver (no network round trip needed for a zone change).
ON_TZ:
    sta tzdelta
    lda SETREC_TZ
    clc
    adc tzdelta
    sta tztmp
    ; clamp: signed compare against -48 / +56
    lda tztmp
    bmi _tz_neg
    cmp #57
    bcc _tz_ok
    rts                            ; already at +14 h
_tz_neg:
    cmp #$d0                       ; -48
    bcs _tz_ok
    rts                            ; already at -12 h
_tz_ok:
    sta SETREC_TZ
    lda #$02
    sta SETREC_VER
    lda #$a5
    sta SETREC_TZMAG
    jsr save_record
    jsr draw_tz
    lda tzdelta
    jsr NET_TZSHIFT
    rts

; the zone text "utc-04:00" / "utc+05:30" at x=170,y=112 (XOR-safe) + row 6
draw_tz:
    lda oldshowntz
    cmp #$ff
    beq dt_build
    lda #170
    sta X1
    lda #$00
    sta X1+1
    lda #112
    sta Y1
    lda #<oldtz
    sta r9L
    lda #>oldtz
    sta r9H
    jsr GPUTS
dt_build:
    jsr tz_str                     ; tzbuf = text for SETREC_TZ
    ldy #$00
dt_old: lda tzbuf,y
    sta oldtz,y
    beq dt_show
    iny
    cpy #12
    bne dt_old
dt_show:
    lda SETREC_TZ
    sta oldshowntz
    lda #170
    sta X1
    lda #$00
    sta X1+1
    lda #112
    sta Y1
    lda #<oldtz
    sta r9L
    lda #>oldtz
    sta r9H
    jsr GPUTS
    lda #<vd_pad
    sta r9L
    lda #>vd_pad
    sta r9H
    lda #$06
    ldx #14
    jsr VDTEXT
    lda #<oldtz
    sta r9L
    lda #>oldtz
    sta r9H
    lda #$06
    ldx #14
    jsr VDTEXT
    rts

; tzbuf = "utc" sign hh ":" mm from SETREC_TZ (quarter-hours)
tz_str:
    lda #<tzpfx
    sta r2L
    lda #>tzpfx
    sta r2H
    ldy #$00
ts_p:   lda (r2),y
    beq ts_s
    sta tzbuf,y
    iny
    bne ts_p
ts_s:   lda SETREC_TZ
    bmi ts_neg
    ldx #$2b                       ; '+'
    bne ts_sg
ts_neg: eor #$ff
    clc
    adc #$01
    ldx #$2d                       ; '-'
ts_sg:  sta vtmpa                   ; |quarters|
    txa
    sta tzbuf,y
    iny
    lda vtmpa
    lsr
    lsr                            ; hours
    jsr ts_2dig
    lda #$3a                       ; ':'
    sta tzbuf,y
    iny
    lda vtmpa
    and #$03
    tax
    lda tzminL,x
    sta tzbuf,y
    iny
    lda tzminH,x
    sta tzbuf,y
    iny
    lda #$00
    sta tzbuf,y
    rts
ts_2dig:                           ; A (0-14) -> two digits at tzbuf,y
    ldx #$30
ts_2l:  cmp #10
    bcc ts_2d
    sbc #10
    inx
    bne ts_2l
ts_2d:  pha
    txa
    sta tzbuf,y
    iny
    pla
    ora #$30
    sta tzbuf,y
    iny
    rts
tzpfx:  .text "utc", $00
tzminL: .byte $30, $31, $33, $34   ; "00" "15" "30" "45"
tzminH: .byte $30, $35, $30, $35
tzdelta: .byte 0
tztmp:   .byte 0
oldshowntz: .byte $ff
tzbuf:   .fill 12, 0
oldtz:   .fill 12, 0

; ---------- settings record persistence ----------
; kernal SAVE convention: A = zero-page pointer to a two-byte cell holding
; the START address; X/Y = end address (exclusive). The FILE NAME comes
; from SETNAM, so it must be set again after the scratch.
save_record:
    ; scratch any previous copy first (kernal SAVE errors on an existing
    ; file); a missing file just reports FILE NOT FOUND, harmless here
    jsr scr_record
    lda #7
    ldx #<savename
    ldy #>savename
    jsr SETNAM
    lda #<savehdr
    sta sptr
    lda #>savehdr
    sta sptr+1
    lda #$56                       ; ZP pointer cell (apps own $56-$57)
    ldx #<SAVEEND                  ; exclusive end = one past the last byte
    ldy #>SAVEEND
    jsr SAVE
    cli                             ; the serial paths can exit with IRQs
    rts                             ; masked (same kernel quirk as LOAD);
                                    ; the keyboard IRQ must live for the
                                    ; APP_TICK key service

savename: .byte $55,$4f,$53,$2d,$53,$45,$54,$00  ; "UOS-SET" unshifted

sptr    = $56
scrname: .byte $53,$30,$3a,$55,$4f,$53,$2d,$53,$45,$54,$00 ; "S0:UOS-SET" unshifted
scr_record:
    lda #$0f
    ldx $ba                        ; last used device (8)
    ldy #$0f
    jsr SETLFS
    lda #10
    ldx #<scrname
    ldy #>scrname
    jsr SETNAM
    jsr OPEN
    ldx #$0f
    jsr CHKOUT
    ldy #$00
_sr_cp: lda scrname,y
    beq _sr_cr
    jsr CHROUT
    iny
    jmp _sr_cp
_sr_cr: lda #$0d
    jsr CHROUT
    jsr CLRCHN
    lda #$0f
    jsr CLOSE
    rts

; the record: loading the saved PRG back with ,8,1 restores these bytes
; at SETREC ($7350), matching the boot-time read of SETREC_DISP
SAVEEND = SETREC + 7            ; load-address word + 5 record bytes

* = SETREC                      ; the record's fixed address
savehdr:                        ; the 2-byte load address header
    .word SETREC
    ; record format 2: version, time zone (signed quarter-hours from UTC,
    ; -16 = UTC-4), marker $a5 (routines.inc SETREC_VER/TZ/TZMAG); these
    ; three bytes were reserved zeros in format 0 records
    .byte $02, $f0, $a5
SETRECDATA:
    .byte $02                    ; display mode at SETREC+5: 0=40 1=80 2=both
    .byte VIC_COLOR_CYAN         ; background colour at SETREC+6 (SETREC_BG)
    .byte $00,$00                ; reserved (SETREC+7,+8)

save_end: