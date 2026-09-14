; Port-1 fire pulls keyboard row bit 4 low. A transition during the ROM's
; multi-column scan can decode as F1, M or another otherwise valid key.
; The client owns all 256 function-key bytes. Keep the first 20 bytes for
; the ten one-byte definitions, and install this small KEYCHK filter in the
; unused tail, visible in bank 0 during the ROM IRQ. No IRQ vector or MMU is
; changed. Chain the saved callback for unambiguous input and restore both
; the callback and the complete table before giving up ownership.
.weak
NK_LOCAL_HELP=0
NK_LOCAL_SECONDARY=0
.endweak
nk_filter_image:
.logical $1014
pk_entry:
        php
        sei
        pha
        txa
        pha
        tya
        pha
        cpy #88
        bcs pk_pass            ; keep the resident's invalid-index guard
        tya
        and #7
 .if NK_LOCAL_SECONDARY
        beq pk_right_row
 .endif
        cmp #4
        bne pk_pass
 .if NK_LOCAL_SECONDARY
        lda #$10
        bne pk_mask_ready
pk_right_row:
        lda #1
pk_mask_ready:
        sta pk_mask
 .endif
        lda $dc02
        cmp #$ff
        bne pk_pass
        lda $dc03
        bne pk_pass            ; do not take over a foreign CIA configuration
        lda $dc00
        sta pk_columns
        lda $d02f
        sta pk_extended
        lda #$ff
        sta $dc00
        sta $d02f
        lda $dc01
 .if NK_LOCAL_SECONDARY
        and pk_mask
 .else
        and #$10
 .endif
        beq pk_reject          ; fire held: this row is electrically ambiguous
        ; Fire may have been released halfway through the earlier scan. A
        ; real key on this row must still pull its own selected column low.
        tya
        lsr
        lsr
        lsr
        tax
        lda pk_masks,x
        cpx #8
        bcc +
        sta $d02f
        jmp pk_read_key
+       sta $dc00
pk_read_key:
        lda $dc01
 .if NK_LOCAL_SECONDARY
        and pk_mask
 .else
        and #$10
 .endif
        beq pk_accept
pk_reject:
        lda #1
        bne pk_restore_columns
pk_accept:
        lda #0
pk_restore_columns:
        sta pk_rejected
        lda pk_extended
        sta $d02f
        lda pk_columns
        sta $dc00
        lda pk_rejected
        beq pk_pass
        inc pk_rejects
        bne +
        inc pk_rejects+1
+       pla
        tay
        pla
        tax
        pla
        plp
        lda #$7f              ; the ROM's SCNRTS column-restoration contract
        sta $dc00
        rts
pk_pass:
        pla
        tay
        pla
        tax
        pla
 .if NK_LOCAL_HELP
        cmp #$84
        bne pk_chained
        pha
        txa
        and #4                ; KEYCHK receives the scan's modifiers in X
        beq pk_plain_help
        pla
        lda #255              ; no ROM key table emits $ff as an input key
        bne pk_chained
pk_plain_help:
        pla
pk_chained:
 .endif
        plp
        jmp (pk_next)
pk_next: .word 0
pk_rejects: .word 0
pk_columns: .byte 0
pk_extended: .byte 0
pk_rejected: .byte 0
 .if NK_LOCAL_SECONDARY
pk_mask: .byte $10
 .endif
pk_masks: .byte $fe,$fd,$fb,$f7,$ef,$df,$bf,$7f,$fe,$fd,$fb
pk_end:
.cerror pk_end>$1100, "Pointer keyboard filter exceeds its owned function-key tail"
.here
