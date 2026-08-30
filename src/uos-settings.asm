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

* = APP_START

    #RegisterApp

    #CreateWindow 1,72,64,143,96,true,title

    #CreateButton 1,1,<ON_TIME, >ON_TIME,88,95,88+24,88+44,false
    #DrawImage 88, 95, 24, 44, img_time
    #Text 92,120, btn_time

    #DrawImage 120, 95, 24, 44, img_colors
    #Text 119,120, btn_display

    #DrawImage 152, 95, 24, 44, img_drives
    #Text 152,120, btn_drives

    #CreateButton 1,2,<ON_BACK, >ON_BACK,184,95,184+24,88+44,false
    #Text 188,120, btn_back

    jmp MAINLOOP

title:  .text "Settings", $00
x:      .text "x", $00

btn_time:
        .text "time",$00
btn_display:
        .text "display", $00
btn_drives:
        .text "drives", $00
btn_back:
        .text "back", $00

.include "icons_settings.inc"

ON_CLOSE:
    #UnregisterApp
    jmp fmb_exittodsk

fmb_exittodsk:                  ; reload the desktop app and re-enter it
    #UnregisterApp
    jsr LOAD_IMM
    .text "uos-desktop",$00
    jsr APP_LOADER
    jmp DESK_START

; Back button on the settings window = same exit path
ON_BACK:
    #UnregisterApp
    jmp fmb_exittodsk

ON_TIME:  
    #RemoveButton 1,0
    #RemoveButton 1,1

    #CreateWindow 1,96,72,119,72,false, 0    
    #Text 112, 80, dlg_time

    #CreateButton 1,1,<ON_OK, >ON_OK,180,120,210,130,true
    #Text 189, 122, ok

    jmp MAINLOOP

ON_OK = *

    #CloseWindow 0, 96,72,119,72   
    #RemoveButton 0,1
    jmp MAINLOOP

dlg_time:       .text "Time", $00
ok:     .text "Ok", $00

; ---------- display-mode cycle + persistence (FR-S3 part 2) ----------
; ON_DISPLAY cycles the mode byte in the settings record (0=40,
; 1=80, 2=both) and SAVEs "0:UOS-SET" to device 8 through the KERNAL.
; The record lives here in the app region; the saved PRG header carries
; this address, so the boot-time LOAD restores it to the same place.
SETREC         = $7350
SETREC_DISP    = $7355
ON_DISPLAY:
    lda SETREC_DISP
    clc
    adc #$01
    cmp #3
    bcc on_d_ok
    lda #0
on_d_ok:
    sta SETREC_DISP
    ; SAVE "0:UOS-SET",8: record with a load-address header prepended
    lda #<savehdr
    sta $c1
    lda #>savehdr
    sta $c2
    ;;
    lda #<$7354                  ; end address = SETREC+4
    ldx #>$7354
    ;;
    ; kernal SAVE: A = pointer to the 2-byte start-address pointer,
    ; X/Y = end address (lo/hi)
    lda #$00                     ; placeholder replaced by exact values below
    ;;
save_start_addr = $c1
    lda #save_start_addr
    ldx #<$7354
    ldy #>$7354
    jsr $ffd8                    ; SAVE via pointer, end
    rts

sptr:   .word $0000              ; filled with SETREC at save time
savehdr:                        ; the 2-byte load address header
    .word SETREC
SETRECDATA:
    .byte $02                    ; display mode: 0=40 1=80 2=both (default 2)
    .byte $00,$00,$00            ; reserved

fsavd:  .byte 0

save_end:
