.export _sh_api
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
