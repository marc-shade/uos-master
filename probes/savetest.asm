; Standalone hardware test of the REAL save_record path.
; Loads UOS-SETTINGS (brings save_record to $56eb + the SETREC record to
; $7350), sets bg=purple, calls save_record, then corrupts $7356 and
; reloads UOS-SET,8,1 to prove the kernal SAVE physically landed on the
; mounted .d64.  Results: $c800 = bg after reload (want 4), $c810 = status
; (1 ok / $e0 settings-load err / $e1 reload err), $c801 = $aa done.
SETNAM = $ffbd
SETLFS = $ffba
LOAD   = $ffd5
save_record = $56eb

* = $0801
        .byte $0b,$08,$0a,$00,$9e,$32,$30,$36,$31,$00,$00,$00  ; 10 SYS 2061
* = $080d
start:
        lda #$08
        sta $ba                 ; device 8 for save_record's ldx $ba
        ; LOAD "UOS-SETTINGS",8,1  -> $5000..$7357
        lda #12
        ldx #<n_set
        ldy #>n_set
        jsr SETNAM
        lda #$01
        ldx #$08
        ldy #$01                ; secondary 1 = load to file's own address
        jsr SETLFS
        lda #$00
        jsr LOAD
        bcc l_ok
        lda #$e0
        sta $c810
        jmp fin
l_ok:
        lda #$04
        sta $7356               ; bg = purple
        jsr save_record         ; the real routine: scratch old + kernal SAVE
        lda #$00
        sta $7356               ; corrupt to prove the reload restores it
        ; LOAD "UOS-SET",8,1 -> $7350..$7357
        lda #7
        ldx #<n_uos
        ldy #>n_uos
        jsr SETNAM
        lda #$01
        ldx #$08
        ldy #$01
        jsr SETLFS
        lda #$00
        jsr LOAD
        bcc r_ok
        lda #$e1
        sta $c810
        lda #$00
        sta $c800
        jmp fin
r_ok:
        lda $7356
        sta $c800               ; bg read back from disk (want 4)
        lda #$01
        sta $c810
fin:
        lda #$aa
        sta $c801               ; done marker
fin_loop:
        jmp fin_loop
n_set:  .byte $55,$4f,$53,$2d,$53,$45,$54,$54,$49,$4e,$47,$53  ; UOS-SETTINGS
n_uos:  .byte $55,$4f,$53,$2d,$53,$45,$54                       ; UOS-SET
