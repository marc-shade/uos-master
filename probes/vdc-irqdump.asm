; Read a stable VDC screen from a private-loop app without touching its code.
; IRQ vector $0314 -> $7c00; old vector at $7cf0, completion at $7cf2:
; 1 = complete, 2 = ready timeout, 3 = address failed three attempts.
; $7cf3/4 counts address resynchronizations. Output: $7400..$7bcf.
; The KERNAL IRQ has already stacked A/X/Y; preserve the borrowed font ZP.
; Seek each cell and verify the documented post-read address increment.
; A sequential-only capture occasionally skipped a byte on the reference
; C128, shifting all later cells. Never accept a silently shifted stream.
        * = $7c00
        jmp start
failed:
        lda #2
        jmp finish
start:
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
        ldy #0
cell:
        lda #3
        sta attempts
read_cell:
        lda #18
        sta $d600
        jsr ready
        bcs failed
        lda $fc
        sec
        sbc #$74
        sta $d601
        lda #19
        sta $d600
        jsr ready
        bcs failed
        lda $fb
        sta $d601
        lda #31
        sta $d600
        jsr ready
        bcs failed
        lda $d601
        sta ($fb),y
        inc $fb
        bne verify
        inc $fc
verify:
        lda #18
        sta $d600
        jsr ready
        bcs failed
        lda $fc
        sec
        sbc #$74
        cmp $d601
        bne resync
        lda #19
        sta $d600
        jsr ready
        bcs failed
        lda $d601
        cmp $fb
        bne resync
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
resync:
        lda $fb
        bne undo_low
        dec $fc
undo_low:
        dec $fb
        inc $7cf3
        bne retry
        inc $7cf4
retry:
        dec attempts
        beq exhausted
        jmp read_cell
exhausted:
        lda #3
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
attempts: .byte 0
        .cerror * > $7cf0, "VDC dump overlaps its control bytes"
