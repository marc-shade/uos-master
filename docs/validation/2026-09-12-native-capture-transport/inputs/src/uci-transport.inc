; Ultimate register transport. Included by uos-net at $8a00; the public
; jump table stays at $9100. NET_DATA is exactly $8800-$89ff.
; Protocol: 896-byte command/data queues, 256-byte status queue. See
; https://1541u-documentation.readthedocs.io/en/latest/uci/core_uci_architecture.html

NET_PRESENT:
        lda UCI_ID
        cmp #$c9
        bne np_no
        lda UCI_ID
        cmp #$c9
        bne np_no
        lda #$01
        rts
np_no:  lda #$00
        rts

tmo_init:
        lda #$00
        sta tmo0
        sta tmo1
        lda #TMO_OUTER
        sta tmo2
        rts
tmo_tick:
        dec tmo0
        bne tt_ok
        dec tmo1
        bne tt_ok
        dec tmo2
        bne tt_ok
        sec
        rts
tt_ok:  clc
        rts

wait_idle:
        jsr tmo_init
wi_l:   lda UCI_STAT
        and #$30
        beq wi_ok
        jsr tmo_tick
        bcc wi_l
        rts
wi_ok:  clc
        rts

wait_done:
        jsr tmo_init
wd_l:   lda UCI_STAT
        and #$30
        cmp #$10
        bne wd_ok
        jsr tmo_tick
        bcc wd_l
        rts
wd_ok:  clc
        rts

; Legacy aggregate call: r0=command, A=length (2..255).
; Keep at most 510 data bytes; DIRMODE keeps only complete leading entries.
; NET_TRUNC reports discarded bytes. No callback from a preceding app survives.
NET_CMD:
        sta cmdlen
        lda #$00
        sta cmdlen+1
        sta streamhook
        sta streamhook+1
        jmp nc_init

; r0=command, r1=length (2..896), r3=callback (zero=aggregate).
; A nonzero callback receives each raw packet at NET_DATA, length NET_LEN,
; with NET_PACKET_TRUNC for this packet. It may clobber A/X/Y and r0..r15.
; Return C=1 to abort ($fd); never issue another UCI command inside it.
; Packet data is binary, and a full 512-byte packet has NO zero terminator.
NET_STREAM:
        lda r1L
        sta cmdlen
        lda r1H
        sta cmdlen+1
        lda r3L
        sta streamhook
        lda r3H
        sta streamhook+1
nc_init:
        lda #$00
        sta NET_LEN
        sta NET_LEN+1
        sta NET_STAT
        sta NET_DATA
        sta NET_DIRN
        sta NET_TRUNC
        sta NET_PACKET_TRUNC
        sta NET_PACKETS
        sta NET_PACKETS+1
        lda #<NET_DATA_MAX
        sta datacap
        lda #>NET_DATA_MAX
        sta datacap+1
        lda streamhook
        ora streamhook+1
        beq nc_length
        lda #$00
        sta datacap
        lda #$02
        sta datacap+1           ; stream: all 512 bytes of a file-read packet
nc_length:
        lda cmdlen+1
        cmp #$03
        bcc nc_lenlow
        bne nc_badlen
        lda cmdlen
        cmp #$81               ; max command = $0380 (hardware FIFO)
        bcs nc_badlen
        bcc nc_probe
nc_lenlow:
        ora cmdlen+1
        bne nc_probe
        lda cmdlen
        cmp #$02
        bcs nc_probe
nc_badlen:
        lda #$fc
        sec
        rts
nc_probe:
        jsr NET_PRESENT
        bne nc_go
        lda #$fe
        sec
        rts
nc_go:  jsr wait_idle
        bcc nc_push
        lda #$04
        sta UCI_CTRL
        lda #$08
        sta UCI_CTRL
        jsr wait_idle
        bcc nc_push
        jmp nc_tmo
nc_push:
        lda r0L
        sta r2L
        lda r0H
        sta r2H
        ldy #$00
nc_w:   lda (r2),y
        sta UCI_CMD
        inc r2L
        bne nc_count
        inc r2H
nc_count:
        lda cmdlen
        bne nc_declo
        dec cmdlen+1
nc_declo:
        dec cmdlen
        lda cmdlen
        ora cmdlen+1
        bne nc_w
        lda #$01
        sta UCI_CTRL
        lda UCI_STAT
        and #$08
        beq nc_wait
        lda #$08
        sta UCI_CTRL
        jmp nc_tmo
nc_wait:
        jsr wait_done
        bcc nc_more
        jmp nc_tmo
nc_more:
        lda streamhook
        ora streamhook+1
        beq nc_packet
        lda #$00
        sta NET_LEN
        sta NET_LEN+1
nc_packet:
        lda NET_LEN
        sta packet_start
        lda NET_LEN+1
        sta packet_start+1
        lda #$00
        sta NET_PACKET_TRUNC
        jsr tmo_init
        jsr read_data
        bcs nc_readerr
        jsr read_status
        bcs nc_readerr
        inc NET_PACKETS
        bne nc_deliver
        inc NET_PACKETS+1
        bne nc_deliver
nc_readerr:
        jmp nc_tmo             ; bound even an endless sequence of replies
nc_deliver:
        lda streamhook
        ora streamhook+1
        beq nc_directory
        jsr nc_callback
        bcc nc_ack
        lda #$fd               ; caller stopped a streaming transaction
        bne nc_abort
nc_directory:
        lda NET_DIRMODE
        beq nc_ack
        lda NET_PACKET_TRUNC
        bne nc_rollback
        lda NET_LEN
        cmp packet_start
        bne nc_entry
        lda NET_LEN+1
        cmp packet_start+1
        beq nc_ack             ; status-only/empty reply is not an entry
nc_entry:
        lda NET_DIRN
        cmp #$ff
        beq nc_rollback
        inc NET_DIRN
        inc NET_LEN            ; keep read_data's terminator as separator
        bne nc_ack
        inc NET_LEN+1
        bne nc_ack
nc_rollback:
        lda #$01
        sta NET_TRUNC
        lda packet_start
        sta NET_LEN
        sta r2L
        lda packet_start+1
        sta NET_LEN+1
        clc
        adc #>NET_DATA
        sta r2H
        lda #$00
        tay
        sta (r2),y             ; discard an incomplete directory entry
nc_ack:
        lda #$02
        sta UCI_CTRL
        jsr tmo_init
nc_acc: lda UCI_STAT
        and #$02
        beq nc_acc_ok
        jsr tmo_tick
        bcc nc_acc
        bcs nc_tmo
nc_acc_ok:
        jsr wait_done
        bcs nc_tmo
        lda UCI_STAT
        and #$30
        beq nc_fin
        jmp nc_more
nc_fin: jsr stat_code
        clc
        rts
nc_tmo: lda #$ff
nc_abort:
        pha
        lda #$04
        sta UCI_CTRL
        pla
        sec
        rts
nc_callback:
        jmp (streamhook)

read_data:
        lda NET_LEN
        sta r2L                ; NET_DATA is page-aligned
        clc
        lda #>NET_DATA
        adc NET_LEN+1
        sta r2H
rd_l:   lda UCI_STAT
        bpl rd_done
        lda UCI_RDAT
        jsr tmo_tick
        bcs rd_timeout
        ldx streamhook
        bne rd_capacity
        ldx streamhook+1
        bne rd_capacity
        ldx NET_DIRMODE
        beq rd_capacity
        ldx NET_TRUNC
        bne rd_drop            ; a directory result is a complete prefix
rd_capacity:
        ldx NET_LEN+1
        cpx datacap+1
        bcc rd_st
        bne rd_drop             ; high byte matters after the limit
        ldx NET_LEN
        cpx datacap
        bcs rd_drop
rd_st:  ldy #$00
        sta (r2),y
        inc r2L
        bne rd_i
        inc r2H
rd_i:   inc NET_LEN
        bne rd_l
        inc NET_LEN+1
        jmp rd_l
rd_drop:
        lda #$01
        sta NET_TRUNC
        sta NET_PACKET_TRUNC
        bne rd_l
rd_done:
        lda NET_LEN+1
        cmp #$02
        bcs rd_ok              ; never terminate at $8a00 over transport code
        lda #$00
        ldy #$00
        sta (r2),y
rd_ok:  clc
        rts
rd_timeout:
        sec
        rts

read_status:
        ldy #$00
rs_l:   lda UCI_STAT
        and #$40
        beq rs_done
        lda UCI_SDAT
        jsr tmo_tick
        bcs rd_timeout
        cpy #31
        bcs rs_l
        sta NET_STAT,y
        iny
        bne rs_l
rs_done:
        lda #$00
        sta NET_STAT,y
        clc
        rts

stat_code:
        lda NET_STAT
        sec
        sbc #'0'
        cmp #10
        bcs sc_bad
        sta tmpa
        asl
        asl
        adc tmpa
        asl
        sta tmpa
        lda NET_STAT+1
        sec
        sbc #'0'
        cmp #10
        bcs sc_bad
        clc
        adc tmpa
        rts
sc_bad: lda #$ff
        rts

uci_vars:
tmo0:         .byte 0
tmo1:         .byte 0
tmo2:         .byte 0
cmdlen:       .word 0
datacap:      .word 0
streamhook:   .word 0
packet_start: .word 0
uci_end:
        .cerror * > $9000, "UCI transport overlaps control table"
