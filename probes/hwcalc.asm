; HW probe: load UOS-CALC from device 8 and enter it. Diagnostics latched
; for the host: $02a7 = A from the failed LOAD, $02a8 = tries left,
; $02a9 = READST after the last failure, $02aa = ST of a control LOAD of
; UOS-REU (same disk, known name), $02ab = ST after LOAD "$",8 (drive
; present?). The retry loop gives the 1541 ~2 s per attempt to come up
; after run_prg's reset.
        * = $0801
        .word $080c, 10
        .byte $9e
        .text " 2062", $00
        .byte $00, $00
        lda #$05                ; 5 attempts
        sta $02a8
hw_try: jsr hw_tryload
        bcc hw_go               ; LOAD OK -> enter the app
        sta $02a7               ; kernal A latch for the host
        jsr $ffb7               ; READST -> what did the bus say?
        sta $02a9
        jsr hw_settle           ; ~2 s, then retry
        dec $02a8
        bne hw_try
        ; --- diagnostics after all retries failed ---
        lda #$00                ; LOAD "$",8 -> is the DRIVE there at all?
        ldx #$08
        ldy #$01
        jsr $ffba
        lda #dnamlen
        ldx #<dnam
        ldy #>dnam
        jsr $ffbd
        lda #$00
        jsr $ffd5
        jsr $ffb7
        sta $02ab               ; ST after the directory LOAD
        ; control: LOAD UOS-REU (known module, same disk)
        lda #rnamlen
        ldx #<rnam
        ldy #>rnam
        jsr $ffbd
        lda #$01
        ldx #$08
        ldy #$01
        jsr $ffba
        lda #$00
        jsr $ffd5
        jsr $ffb7
        sta $02aa               ; ST of the control LOAD
        rts
hw_go:  jmp $5000               ; the calculator's entry

hw_tryload:
        lda #cnamlen
        ldx #<cnam
        ldy #>cnam
        jsr $ffbd               ; SETNAM
        lda #$01
        ldx #$08
        ldy #$01
        jsr $ffba               ; SETLFS
        lda #$00
        jsr $ffd5               ; LOAD
        rts

; ~2 s settle via the jiffy clock: wait for 120 jiffy ticks ($a2 change)
hw_settle:
        ldy #$78
ws_t:   lda $a2
ws_1:   cmp $a2
        beq ws_1
        dey
        bne ws_t
        rts

cnam:   .byte $55,$4f,$53,$2d,$43,$41,$4c,$43   ; "UOS-CALC" unshifted
cnamlen = 8
rnam:   .byte $55,$4f,$53,$2d,$52,$45,$55       ; "UOS-REU" unshifted
rnamlen = 7
dnam:   .byte $24                               ; "$"
dnamlen = 1