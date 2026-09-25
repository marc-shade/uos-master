*=$b0fe
        .word $b100
        .byte $4e,$4d,$4f,$44
        .byte 1,1,13,0
        .word end-$b100,0,16,0
        rts
        .binary "../graphics/font8.bin"
end:
