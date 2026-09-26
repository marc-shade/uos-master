; One-shot native C128 IRQ observer that holds the foreground (GPL v3).
; For apps whose idle loop keeps using N_BUFFER ($3a00), such as AES clients:
; the IRQ stays in this handler while the host saves $3a00, lets the copy run,
; reads the result and puts $3a00 back, so the foreground never sees the
; borrow. RAM only (no VDC); no heap or KERNAL calls except INDFET ($ff74).
; $3ff0 old IRQ, +2 done (1 ok, 2 host timeout, 4 bad command),
; +4 bank (0/1), +5 source word, +7 count word (1..512), output at $3a00.
; +11/+12 MMU mode/common registers; +13 interrupted foreground MMU config.
; +14 handshake: probe 1 held; host 2 copy; probe (after the copy) waits for
; host 3 release. Each wait gives up after about 20 seconds.
* = $3e00
        php
        pha
        txa
        pha
        tya
        pha
        tsx
        lda $0105,x            ; native IRQ additionally stacked the MMU
        sta $3ffd
        lda $d505
        sta $3ffb
        lda $d506
        sta $3ffc
        cld
        lda $fb
        pha
        lda $fc
        pha
        lda $fd
        pha
        lda $fe
        pha
        lda #1                  ; held: the host may save $3a00 now
        sta $3ffe
        lda #2
        jsr handshake
        bcs timed_out
        lda $3ff5
        sta $fb
        lda $3ff6
        sta $fc
        lda #0
        sta $fd
        lda #$3a
        sta $fe
        lda $3ff7
        sta left
        lda $3ff8
        sta left+1
        cmp #>512
        bcc count_low
        bne invalid
        lda left
        cmp #<513
        bcs invalid
count_low:
        lda left
        ora left+1
        beq invalid
        lda $3ff4
        cmp #2
        bcs invalid
copy:
        lda #$fb
        ldx $3ff4
        ldy #0
        jsr $ff74
        sta ($fd),y
        inc $fb
        bne +
        inc $fc
+       inc $fd
        bne +
        inc $fe
+       lda left
        bne +
        dec left+1
+       dec left
        lda left
        ora left+1
        bne copy
        lda #1
        bne copied
invalid:
        lda #4
copied:
        sta $3ff2               ; the host reads $3a00, restores it, releases
        lda #3
        jsr handshake
        jmp finish
timed_out:
        lda #2
        sta $3ff2
finish:
        lda $3ff0
        sta $0314
        lda $3ff1
        sta $0315
        pla
        sta $fe
        pla
        sta $fd
        pla
        sta $fc
        pla
        sta $fb
        pla
        tay
        pla
        tax
        pla
        plp
        jmp ($3ff0)
; Wait until $3ffe = A; carry set after about 20 seconds without it.
handshake:
        sta want
        lda #0
        sta wait
        sta wait+1
        lda #22
        sta wait+2
-       lda $3ffe
        cmp want
        beq +
        dec wait
        bne -
        dec wait+1
        bne -
        dec wait+2
        bne -
        sec
        rts
+       clc
        rts
left: .word 0
want: .byte 0
wait: .fill 3,0
        .cerror * > $3ff0, "held capture exceeds private scratch region"
