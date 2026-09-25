.export _sh_api, _sh_recalculate, _sh_clipboard
.import sg_module
.import _sh_types, _sh_values, _sh_clip_text
.segment "CODE"
_sh_api:
        sta call+1
        asl
        clc
        adc call+1
        adc #$20
        sta call+1
call:   jsr $1c20
        ldx #0
        rts
_sh_recalculate:
        lda #2
        jsr sg_module
        bcc calculate
        pha
        ldx #0
invalid:
        lda #10
        sta _sh_types,x
        lda #0
        sta _sh_values,x
        sta _sh_values+256,x
        sta _sh_values+512,x
        sta _sh_values+768,x
        inx
        bne invalid
        pla
        bne done
calculate:
        jsr $1c62
done:   ldx #0
        rts
_sh_clipboard:
        sta clip_operation
        lda #3
        jsr sg_module
        bcs done
        ldx #31
copy_in:
        lda _sh_clip_text,x
        sta $3a00,x
        dex
        bpl copy_in
        lda clip_operation
        sta $3d0c
        jsr $1c62
        bcs done
        ldx #31
copy_out:
        lda $3a00,x
        sta _sh_clip_text,x
        dex
        bpl copy_out
        lda #0
        beq done
.segment "DATA"
clip_operation: .byte 0
