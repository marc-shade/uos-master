; One-shot desktop tick client for the PUBLIC shared file API. MODE 0 creates
; a 66053-byte deterministic binary file; MODE 1 copies it via two contexts.
; The host chooses fresh, private absolute names and independently reads both
; files afterward. Never use this probe on an active app or foreign handles.
.include "../src/equates.inc"
.include "../src/routines.inc"
.include "../src/ultimate-files.inc"
OLDTICK = $5f00
MODE = $5f02
DONE = $5f03
RESULT = $5f04
CLEANUP = $5f05
TOTAL = $5f06
NAME = $5500
DEST = $5700
BUFFER = $6000

* = $5000
        lda OLDTICK
        sta $033c
        lda OLDTICK+1
        sta $033d
        lda #0
        sta DONE
        sta RESULT
        sta CLEANUP
        sta gen_page
        ldx #3
zero_total:
        sta TOTAL,x
        dex
        bpl zero_total
        lda #11
        sta gen_seed
        lda #<NAME
        sta r0L
        lda #>NAME
        sta r0H
        lda MODE
        bne copy_begin
        lda #7
        ldx #2
        jsr UFS_OPEN
        bcc generate_opened
        jmp failed
generate_opened:
        jmp generate
copy_begin:
        lda #1
        ldx #1
        jsr UFS_OPEN
        bcc copy_source_opened
        jmp failed
copy_source_opened:
        lda #<DEST
        sta r0L
        lda #>DEST
        sta r0H
        lda #7
        ldx #2
        jsr UFS_OPEN
        bcc copy_next
        jmp failed
copy_next:
        jsr buffer_args
        ldx #1
        jsr UFS_READ
        bcs failed
        lda UFS_COUNT
        sta amount
        lda UFS_COUNT+1
        sta amount+1
        ora amount
        beq finished
        jmp write_next
generate:
        jsr fill_buffer
        lda #0
        sta amount
        lda #2
        sta amount+1
        lda TOTAL+2
        beq write_next
        lda TOTAL+1
        cmp #2
        bne write_next
        lda #5
        sta amount
        lda #0
        sta amount+1
write_next:
        jsr buffer_args
        lda amount
        sta r1L
        lda amount+1
        sta r1H
        ldx #2
        jsr UFS_WRITE
        bcs failed
        clc
        lda TOTAL
        adc amount
        sta TOTAL
        lda TOTAL+1
        adc amount+1
        sta TOTAL+1
        lda TOTAL+2
        adc #0
        sta TOTAL+2
        lda TOTAL+3
        adc #0
        sta TOTAL+3
        jsr OS_TICK             ; clock serviced only BETWEEN transactions
        lda MODE
        bne copy_next
        lda TOTAL
        cmp #5
        bne generate
        beq finished
failed:
        sta RESULT
finished:
        jsr UFS_CLOSEALL
        sta CLEANUP
        lda #1
        sta DONE
        rts
buffer_args:
        lda #<BUFFER
        sta r0L
        lda #>BUFFER
        sta r0H
        lda #0
        sta r1L
        lda #2
        sta r1H
        rts
fill_buffer:
        lda #<BUFFER
        sta r0L
        lda #>BUFFER
        sta r0H
        ldx #2
fill_page:
        ldy #0
        lda gen_seed
fill_byte:
        sta (r0),y
        clc
        adc #73
        iny
        bne fill_byte
        clc
        adc #17
        inc gen_page
        bne fill_seed
        clc
        adc #29                ; bytes after 64 KiB differ from the first bank
fill_seed:
        sta gen_seed
        inc r0H
        dex
        bne fill_page
        rts
amount:   .word 0
gen_seed: .byte 0
gen_page: .byte 0
        .cerror * > NAME, "file workflow probe overlaps host filenames"
