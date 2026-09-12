; nettrace: run the SNTP steps through uos-net and log every status to
; $6000 for DMA readback. Poked at $7f00, reached via the tick vector;
; VEC0/VEC1 patched by the injector (same layout rule as vdcdump).
.include "equates.inc"
.include "routines.inc"
        * = $7f00
        lda #$00
VEC0 = *-1
        sta $033c
        lda #$00
VEC1 = *-1
        sta $033d
        ; log layout ($6000): +0 open A, +1 open C, +2..+33 NET_STAT after open
        ;   +$40 write A, +$41.. NET_STAT after write
        ;   +$80 read tries used, +$81 final read A, +$82.. NET_STAT after the last read
        ;   +$c0/+$c1 NET_LEN, +$c2.. 48 payload bytes, +$f8 close A
        lda #<host
        sta r0L
        lda #>host
        sta r0H
        lda portL
        sta r1L
        lda portH
        sta r1H
        lda proto
        jsr NET_OPEN
        sta $6000
        lda #$00
        rol
        sta $6001
        ldx #$02
        jsr logstat
        lda $6001
        bne done
        lda #<req
        sta r0L
        lda #>req
        sta r0H
        ldx reqlen
        lda NET_SOCK
        jsr NET_WRITE
        sta $6040
        ldx #$41
        jsr logstat
        lda #$00
        sta tries
rd:     inc tries
        lda #200
        sta r1L
        lda #$00
        sta r1H
        lda NET_SOCK
        jsr NET_READ
        sta $6081
        cmp #$01
        bne rdone
        lda tries
        cmp #200
        bne rd
rdone:  lda tries
        sta $6080
        ldx #$82
        jsr logstat
        lda NET_LEN
        sta $60c0
        lda NET_LEN+1
        sta $60c1
        ldy #$00
cp:     lda NET_DATA+2,y
        sta $60c2,y
        iny
        cpy #48
        bne cp
        lda NET_SOCK
        jsr NET_CLOSE
        sta $60f8
done:   lda #$a5
        sta $60ff
        jmp ($033c)
logstat:
        ldy #$00
ls:     lda NET_STAT,y
        sta $6000,x
        beq lsd
        inx
        iny
        cpy #31
        bne ls
lsd:    rts
tries:  .byte 0
; patched by hw_nettrace.py (addresses from the listing)
proto:  .byte $08               ; 7 tcp / 8 udp
portL:  .byte 123
portH:  .byte 0
reqlen: .byte 48
host:   .text "pool.ntp.org", $00
        .fill 12, 0
req:    .byte $23
        .fill 31, 0             ; keep the probe under $8000 (sprite data)
