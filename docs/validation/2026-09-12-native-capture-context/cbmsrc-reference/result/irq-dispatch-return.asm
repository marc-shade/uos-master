*=$ff17
mmucr=$ff00
sysbnk=0
ibrk=$0316
iirq=$0314
irq:
	pha
	txa
	pha
	tya
	pha
	lda mmucr
	pha
	lda #sysbnk
	sta mmucr
	tsx
	lda $105,x
	and #$10
	beq local_1
	jmp (ibrk)
local_1: jmp (iirq)
prend:
	pla
	sta mmucr
	pla
	tay
	pla
	tax
	pla
	rti
