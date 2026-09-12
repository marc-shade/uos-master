; Temporary diagnostic, installed only while the desktop is quiescent.
; Calls the original N_KEYIN and retains first 20 scan/consumption records.
; HOLD=1 consumes keys without delivering them to the desktop. No heap calls.
; Host borrows free bank-0 $5000..$57ff and restores it before releasing input.
; KEYIN_TARGET is the verified original native keyboard entry.
COUNT = $5206
OVERFLOW = $5207
PHASE = $5209
HOLD = $520a
SCANS = $520b
KEYS = $520d
FG = $5280
IRQ = $52c0
* = $5000
        jmp foreground
        jmp scan
        .text "UOSKEY1"
foreground:
        php
        sei
        pha
        txa
        pha
        tya
        pha
        tsx
        lda $0104,x
        sta FG+3
        lda #2
        sta FG
        lda PHASE
        sta FG+2
        lda $ff00
        sta FG+5
        ldy #2
before_time:
        lda $a0,y
        sta FG+7,y
        dey
        bpl before_time
        ldy #9
before_state:
        lda $cc,y
        sta FG+13,y
        lda $034a,y
        sta FG+23,y
        dey
        bpl before_state
        ldy $d2
        lda $100a,y
        sta FG+53
        lda $3d13
        sta FG+55
        lda $3d14
        sta FG+56
        lda $3d15
        sta FG+59
        pla
        tay
        pla
        tax
        pla
        plp
        jsr KEYIN_TARGET
        php
        sei
        pha
        txa
        pha
        tya
        pha
        tsx
        lda $0103,x
        beq done
        sta FG+1
        lda $0104,x
        sta FG+4
        cld
        inc KEYS
        bne +
        inc KEYS+1
+       lda $ff00
        sta FG+6
        ldy #2
after_time:
        lda $a0,y
        sta FG+10,y
        dey
        bpl after_time
        ldy #9
after_state:
        lda $cc,y
        sta FG+33,y
        lda $034a,y
        sta FG+43,y
        dey
        bpl after_state
        ldy $d2
        lda $100a,y
        sta FG+54
        lda $3d13
        sta FG+57
        lda $3d14
        sta FG+58
        lda $3d15
        sta FG+60
        lda $dc00
        sta FG+61
        lda $dc01
        sta FG+62
        lda $d3
        sta FG+63
        ldx #<FG
        jsr append
done:
        lda HOLD
        beq deliver
        pla
        tay
        pla
        tax
        pla
        plp
        lda #0
        rts
deliver:
        pla
        tay
        pla
        tax
        pla
        plp
        rts

; Gate saved P,A,X,Y,MMU and JSR return: these are stack offsets 7..3.
; IRQs remain disabled until the low gate restores the entry state.
scan:
        cld
        tsx
        lda #1
        sta IRQ
        lda $0106,x
        sta IRQ+1
        lda PHASE
        sta IRQ+2
        lda $0107,x
        sta IRQ+3
        lda $0105,x
        sta IRQ+4
        lda $0103,x
        sta IRQ+5
        lda $0104,x
        sta IRQ+6
        ldy #2
scan_time:
        lda $a0,y
        sta IRQ+7,y
        dey
        bpl scan_time
        lda $d02f
        sta IRQ+10
        lda $dc02
        sta IRQ+11
        lda $dc03
        sta IRQ+12
        ldy #9
scan_state:
        lda $cc,y
        sta IRQ+13,y
        lda $034a,y
        sta IRQ+23,y
        dey
        bpl scan_state
        ldy $d2
        lda $100a,y
        sta IRQ+53
        lda $3d13
        sta IRQ+55
        lda $3d14
        sta IRQ+56
        lda $3d15
        sta IRQ+59
        lda $dc00
        sta IRQ+61
        lda $dc01
        sta IRQ+62
        lda $d3
        sta IRQ+63
        inc SCANS
        bne +
        inc SCANS+1
+       ldx #<IRQ
append:
        stx copy_record+1
        lda COUNT
        cmp #20
        bcc room
        lda OVERFLOW
        and OVERFLOW+1
        cmp #$ff
        beq full
        inc OVERFLOW
        bne full
        inc OVERFLOW+1
full:   rts
room:
        ldy #63
copy_record:
        lda FG,y
record_store:
        sta $5300,y
        dey
        bpl copy_record
        inc COUNT
        clc
        lda record_store+1
        adc #64
        sta record_store+1
        bcc +
        inc record_store+2
+       rts
        .cerror * > $5200, "input trace exceeds code area"
* = $5200
        .byte $55,$49,$54,$31
        .byte 1,20,0
        .word 0
        .byte 0,1
        .word 0,0
        .fill $5800-*,0
