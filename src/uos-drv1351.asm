;==========================================================================
;	1351 proportional mouse driver for the c64
;
;	commodore business machines, inc.   27oct86
;		by hedley davis and fred bowen
;==========================================================================

iirq	= $0314
vic	= $d000
sid     = $d400
cia     = $dc00
cia_ddr	= $dc02
potx	= sid+$19
poty	= sid+$1a

xpos	= vic+$00	;x position (lsb)
ypos	= vic+$01	;y position
xposmsb	= vic+$10	;x position (msb)

* = $9e00

        jmp install1    ;install mouse in port 1      $9e00
	jmp install2    ;install mouse in port 2      $9e03
	jmp remove      ;remove mouse wedge           $9e06
        jmp KEYIN_EXT   ;OS keyboard read (see below) $9e09
extseen: .byte $00      ;sticky: 1 once the C128 ESC line read low ($9e0c)

install1:
    	ldx #0          ;port 1 mouse
	.byte $2c

install2:
    	ldx #2          ;port 2 mouse

        lda iirq+1      ;install irq wedge
        cmp #>mirq1
        beq _90         ;...branch if already installed!
        php
        sei

        lda iirq        ;save current irq indirect for our exit
        sta iirq2
        lda iirq+1
        sta iirq2+1

        lda _port,x     ;point irq indirect to mouse driver
        sta iirq
        lda _port+1,x
        sta iirq+1
        plp
_90:	rts

_port:	.word mirq1
	.word mirq2


remove:
        lda iirq+1      ;remove irq wedge
	cmp #>mirq1
	bne _190        ;...branch if already removed!
	php
        sei
        lda iirq2       ;restore saved indirect
        sta iirq
        lda iirq2+1
        sta iirq+1
        plp
_190: 	rts

iirq2:		.byte $00, $00
opotx:		.byte $00
opoty:		.byte $00
newvalue:	.byte $00
oldvalue:	.byte $00
ciasave:	.byte $00

mirq2:
        lda #$80        ;port2 mouse scan
        .byte $2c

mirq1:
        lda #$40        ;port1 mouse scan

        jsr setpot      ;configure cia per .a

        lda potx        ;get delta values for x
        ldy opotx
        jsr movchk
        sty opotx

        clc             ;modify low order x position
        adc xpos
        sta xpos
        txa
        adc #$00
        and #%00000001
        eor xposmsb
        sta xposmsb

        lda poty        ;get delta value for y
        ldy opoty
        jsr movchk
        sty opoty

        sec             ;modify y position (decrease y for increase in pot)
        eor #$ff
        adc ypos
        sta ypos

        ; clamp the sprite to the visible area so a single noisy pot delta
        ; can never strand the arrow off-screen (the bug behind "mouse arrow
        ; disappears": a bad read flipped the X msb, +256, no way back).
        lda xposmsb
        and #$01
        beq _cxlo
        lda xpos                ; msb set: X = 256+xpos, cap X at 340
        cmp #$55
        bcc _cxok
        lda #$54
        sta xpos
        jmp _cxok
_cxlo:  lda xpos                ; msb clear: floor X at 24
        cmp #$18
        bcs _cxok
        lda #$18
        sta xpos
_cxok:  lda ypos
        cmp #$32                ; floor Y at 50
        bcs _cyhi
        lda #$32
        sta ypos
        jmp _cyok
_cyhi:  cmp #$fa                ; cap Y at 249 = screen row 199 (the bottom
        bcc _cyok               ; bar / "ultos" button lives at screen y 189-199,
        lda #$f9               ; i.e. sprite Y 239-249 — the old 229 cap blocked it)
        sta ypos
_cyok:

        ; C128 extended-key scan (ESC + cursor keys on the VIC-IIe matrix,
        ; $d02f) is done HERE, inside the mouse IRQ, on purpose: $dc00 bits
        ; 6-7 are the SID pot-MUX select shared with the keyboard columns.
        ; The old KEYIN_EXT poked $dc00 from the main loop thousands of times
        ; a second, corrupting the 1351 pot reads (jittery/runaway pointer,
        ; worst in an app's tight key-poll loop). The IRQ already owns $dc00
        ; and restores it below; the pot was read above with a settled MUX,
        ; and next frame's setpot re-settles it, so the scan is harmless.
        lda #$ff
        sta cia                 ; deselect all standard keyboard columns
        lda #$fd                ; K1 low
        sta $d02f
        lda $dc01
        sta extk1
        lda #$fb                ; K2 low
        sta $d02f
        lda $dc01
        sta extk2
        lda #$ff
        sta $d02f
        lda extk1
        and #$01                ; K1 bit0 = ESC
        sta extmask
        lda extk2
        and #$78                ; K2 bits3-6 = up/down/left/right
        ora extmask
        eor #$79                ; 1 = pressed (on a plain C64 $d02f reads
        sta extmask             ; $ff -> extmask 0, so no false keys)
        lda extmask
        and #$01
        beq _mkedge
        lda #$01
        sta extseen             ; sticky: the ESC matrix line was seen (tests)
_mkedge:
        lda extlatch
        eor #$ff
        and extmask             ; newly pressed since the last IRQ
        sta extnew
        lda extmask
        sta extlatch
        lda extnew
        beq _mkdone
        ldx #$00
_mkl:   lda extnew
        and extbits,x
        bne _mkhit
        inx
        cpx #$05
        bne _mkl
        jmp _mkdone
_mkhit: lda extcodes,x
        sta extkey              ; latch one key event for KEYIN_EXT
_mkdone:
        ldx ciasave     ;restore keyboard
        stx cia

_90 	jmp (iirq2)     ;continue w/ irq operation



; movchk
;	entry	y = old value of pot register
;		a = currrent value of pot register
;	exit	y = value to use for old value
;		x,a = delta value for position
;

movchk:
        sty oldvalue    ;save old & new values
	sta newvalue
        ldx #0          ;preload x w/ 0

        sec             ;a = mod64(new-old)
        sbc oldvalue
        and #%01111111	
        cmp #%01000000	;if a > 0
        bcs _50
        lsr a           ;   then a = a/2
        beq _80         ;      if a <> 0
        ldy newvalue	;         then y = newvalue
        rts             ;              return

_50 	ora #%11000000	;   else or-in high order bits
        cmp #$ff        ;      if a <> -1
        beq _80
        sec             ;         then a = a/2
        ror a
        ldx #$ff        ;              x = -1
        ldy newvalue	;              y = newvalue
        rts             ;              return

_80 	lda #0          ;a = 0
	rts             ;return w/ y = old value



setpot:
        ldx cia         ;save keyboard GFX_LINEs
	stx ciasave

	sta cia         ;connect appropriate port to sid

        ldx #4
        ldy #$c7	;delay 4ms to let GFX_LINEs settle & get sync-ed
_10	dey 
        bne _10
        dex
        bne _10
        rts

;==========================================================================
; KEYIN_EXT — the OS keyboard read (core KEYIN jumps here)
;
; The C128's ESC key and its dedicated cursor keys are not on the C64
; keyboard matrix: they sit on three extra columns the VIC-IIe selects
; through $d02f (K0/K1/K2), which the C64-mode KERNAL never scans. So on a
; real C128 in C64 mode no key ever produced $1b and "escape did not work
; in menus" (reported 2026-09-06). This reads the KERNAL buffer first, then
; scans those columns directly, returning one event per key press.
; RUN/STOP ($03) is returned as ESC for C64 keyboards. On a C64 $d02f is
; not a register: the reads give $ff (nothing pressed) and nothing changes.
;
;   K1 ($d02f = $fd): bit 0 = ESC
;   K2 ($d02f = $fb): bit 3 = UP, bit 4 = DOWN, bit 5 = LEFT, bit 6 = RIGHT
;
; Returns A = $1b ESC, $91 up, $11 down, $9d left, $1d right, else the
; KERNAL character or 0.
;==========================================================================
; KEYIN_EXT is now a pure reader: KERNAL GETIN first (normal keys, and
; RUN/STOP -> ESC for C64 keyboards), else return the extended key the
; mouse IRQ latched (ESC / cursor keys). It touches NO CIA/VIC keyboard
; register, so it can be called as tightly as an app likes without
; disturbing the 1351 pot MUX. Returns A = PETSCII (0 = no key).
KEYIN_EXT:
        jsr $ffe4               ; KERNAL GETIN
        beq ke_ext
        cmp #$03                ; RUN/STOP -> ESC alias
        bne ke_r
        lda #$1b
ke_r:   rts
ke_ext: lda extkey             ; IRQ-latched extended key (0 = none)
        beq ke_z
        pha
        lda #$00
        sta extkey             ; consume it
        pla
ke_z:   rts
extbits:  .byte $01,$08,$10,$20,$40
extcodes: .byte $1b,$91,$11,$9d,$1d
extk1:    .byte $ff
extk2:    .byte $ff
extmask:  .byte $00
extlatch: .byte $00
extnew:   .byte $00
extkey:   .byte $00
