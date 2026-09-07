; HW probe: load UOS-CALC from device 8 and enter it. After the jump the
; calculator owns the CPU; the host verifies via DMA (dispbuf + $5000).
;
; The LOAD retries with a settle delay: run_prg resets the machine and the
; 1541 emulation needs a moment to come up — an immediate LOAD reports
; device-not-present ($20).
        * = $0801
        .word $080b, 2026
        .byte $9e
        .text "2061", $00
        .byte $00, $00
        lda #$05                ; 5 attempts
        sta $0701
hw_try: jsr hw_tryload
        bcc hw_go               ; LOAD OK -> enter the app
        sta $0700               ; kernal error latch for the host
        jsr hw_settle           ; ~2 s, then retry
        dec $0701
        bne hw_try
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