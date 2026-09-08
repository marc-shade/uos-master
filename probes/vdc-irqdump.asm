; Read a stable VDC screen from a private-loop app without touching its code.
; IRQ vector $0314 -> $7c00; old vector at $7cf0, completion at $7cf2.
; 2000 screen bytes -> $7400..$7bcf. Caller must first wait for fmready.
; The KERNAL IRQ has already stacked A/X/Y; preserve the borrowed font ZP.
        * = $7c00
        lda $fb
        pha
        lda $fc
        pha
        lda #$00
        sta $fb
        lda #$74
        sta $fc
        lda #<2000
        sta count
        lda #>2000
        sta count+1
        lda #18
        sta $d600
        jsr ready
        bcs failed
        lda #0
        sta $d601
        lda #19
        sta $d600
        jsr ready
        bcs failed
        lda #0
        sta $d601
        lda #31
        sta $d600
        ldy #0
cell:
        jsr ready
        bcs failed
        lda $d601
        sta ($fb),y
        inc $fb
        bne samepage
        inc $fc
samepage:
        lda count
        bne lowbyte
        dec count+1
lowbyte:
        dec count
        lda count
        ora count+1
        bne cell
        lda #1
        bne finish
failed:
        lda #2
finish:
        sta $7cf2
        pla
        sta $fc
        pla
        sta $fb
        lda $7cf0
        sta $0314
        lda $7cf1
        sta $0315
        jmp ($7cf0)
ready:
        ldx #0
poll:
        bit $d600
        bmi available
        dex
        bne poll
        sec
        rts
available:
        clc
        rts
count: .word 0
        .cerror * > $7cf0, "VDC dump overlaps its control bytes"
