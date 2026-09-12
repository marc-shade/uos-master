; VDC screen dump -> main RAM $6000 (2000 bytes), DMA-readable.
; Poked at $7f00, reached via uOS's tick vector; chains back to the desktop
; tick (vector low/high patched into VEC0/VEC1 by the injector).
        * = $7f00
        sei
        ldx #$12            ; r18 = update addr high = 0
        stx $d600
        lda #$00
        sta $d601
        ldx #$13            ; r19 = update addr low = 0
        stx $d600
        sta $d601
        ldx #$1f            ; select r31 (auto-inc data port)
        stx $d600
        lda #$00
        sta $fb             ; dest = $6000
        lda #$60
        sta $fc
        lda #<2000
        sta cnt
        lda #>2000
        sta cnt+1
        ldy #$00
cell:   bit $d600           ; wait VDC ready
        bpl cell
        lda $d601
        sta ($fb),y
        inc $fb
        bne nolo
        inc $fc
nolo:   lda cnt             ; 16-bit dec cnt
        bne dechi
        dec cnt+1
dechi:  dec cnt
        lda cnt
        ora cnt+1
        bne cell
        lda #$00
VEC0 = *-1
        sta $033c
        lda #$00
VEC1 = *-1
        sta $033d
        cli
        jmp ($033c)
cnt:    .byte 0,0
