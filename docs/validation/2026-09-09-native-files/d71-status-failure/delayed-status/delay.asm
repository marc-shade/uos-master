*=$1800
pha
txa
pha
tya
pha
ldx #0
outer: ldy #0
inner: dey
bne inner
dex
bne outer
pla
tay
pla
tax
pla
jmp $3113
