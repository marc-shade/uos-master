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

    lda #$ff
    sta oldshown
    jsr draw_mode

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
        bne _akb                        ; 64tass's #'D' assembles to $c4
        jsr ON_DISPLAY                  ; (shifted), which no keypress
        jmp APP_KEY                     ; ever produces
_akb:   cmp #$42                        ; 'B'
        beq _akbk
        cmp #$1b                        ; ESC also backs out
        beq _akbk
        jmp APP_KEY
_akbk:  jmp settings_back

title:  .text "Settings", $00
hint:   .text "D=display B/ESC=back", $00
mode0s: .text "display: 40 only", 0
mode1s: .text "display: 80 only", 0
mode2s: .text "display: both (40+80)", 0

modebuf: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0
oldmode: .byte 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0

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
    cpy #19
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
    cpy #20
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
    rts

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
    .byte $00,$00,$00           ; reserved (SETREC+2..4)
SETRECDATA:
    .byte $02                    ; display mode at SETREC+5: 0=40 1=80 2=both
    .byte $00,$00,$00            ; reserved

save_end: