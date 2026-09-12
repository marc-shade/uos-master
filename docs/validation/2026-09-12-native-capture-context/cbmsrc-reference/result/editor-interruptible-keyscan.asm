*=$c214
vicreg=$d000
graphm=$d8
scnkey=$c55d
blink=$c6e7
irqrts: bcs local_10
	lda vicreg+48
	and #$01
	beq local_10
	lda graphm
	and #$40
	beq local_10
	lda vicreg+17
	bpl local_10
	sec
local_10: cli
	bcc local_20
	jsr scnkey
	jsr blink
	sec
local_20: rts
