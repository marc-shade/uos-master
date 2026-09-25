.import _sh_calculate, __ENGINE_SIZE__
.segment "CALCLOAD"
        .word $b100
.segment "CALCHEADER"
        .byte "NMOD",1,1,13,0
        .word 16+__ENGINE_SIZE__
        .word 0
        .word _sh_calculate-$b100
        .word 0
