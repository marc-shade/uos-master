; Resident loader and directory lease. The original path remains resident
; even if the caller reuses the modal workspace or a later app replaces it.
* = UFP_PICK
        jmp pick_file
        jmp pick_recover
        .byte 1
pick_result:    .byte 0
pick_pending:   .byte 0
pick_context:   .byte 0
pick_cwdlen:    .word 0
pick_pathlen:   .word 0
pick_active:    .byte 0
pick_mode:      .byte 0
pick_default:   .word 0
pick_request:   .byte 0
        .cerror pick_default != UFP_DEFAULT, "picker gateway ABI"

pick_file:
        pha
        lda busy
        ora pick_active
        beq pick_available
        pla
        lda #UFS_BUSY
        sec
        rts
pick_available:
        pla
        cpx #1
        bcc pick_argument
        cpx #3
        bcs pick_argument
        cmp #1
        beq pick_arguments
        cmp #7
        beq pick_arguments
pick_argument:
        lda #UFS_BADARG
        bne pick_return
pick_arguments:
        sta pick_mode
        stx pick_request
        lda r0L
        sta pick_default
        lda r0H
        sta pick_default+1
        jsr pick_recover
        bcs pick_return
        ldx pick_request
        lda modes-1,x
        beq pick_load
        lda #UFS_BUSY
        bne pick_return
pick_load:
        stx pick_context
        inc pick_active
        lda #0
        sta UFP_LIBRARY+3       ; a partial/missing library cannot be entered
        lda #<pick_module
        sta r0L
        lda #>pick_module
        sta r0H
        jsr FILLFILE
        jsr APP_LOADER
        bcs pick_load_failed
        lda UFP_LIBRARY+3
        cmp #1
        bne pick_load_failed
        jsr UFP_LIBRARY
        jmp pick_loaded
pick_load_failed:
        lda #UFP_LOAD
pick_loaded:
        ldx #0
        stx pick_active
pick_return:
        sta pick_result
        cmp #1
        rts

; Called from CLOSE while its own service lock is held. Never invokes UFS
; recursively. OPENs on a failed-restoration context are refused below.
pick_close_finish:
        lda pick_active
        bne pick_close_ok
        lda target
        cmp pick_context
        bne pick_close_ok
        jsr pick_recover
        bcc pick_close_ok
        pha
        ldx #31
pick_close_status:
        lda NET_STAT,x
        sta status,x
        dex
        bpl pick_close_status
        pla
        jmp finish
pick_close_ok:
        jmp ok

pick_recover:
        lda pick_pending
        beq pick_recovered
        ldx pick_context
        lda modes-1,x
        beq pick_restore
        cmp #$ff
        beq pick_uncertain
        lda #UFS_BUSY
        sec
        rts
pick_restore:
        lda #2
        sta pick_pending
        lda #<UFP_CWD
        sta r0L
        lda #>UFP_CWD
        sta r0H
        lda pick_cwdlen
        sta r1L
        lda pick_cwdlen+1
        sta r1H
        lda #0
        sta NET_DIRMODE
        sta r3L
        sta r3H
        jsr NET_STREAM
        bcs pick_uncertain
        cmp #0
        bne pick_uncertain
        lda NET_TRUNC
        bne pick_uncertain
        sta pick_pending
pick_recovered:
        lda #0
        clc
        rts
pick_uncertain:
        lda #UFS_UNCERTAIN
        sec
        rts
pick_module: .text "uos-picker", 0
pick_gateway_end:
        .cerror * > UFP_CWD, "picker gateway overlaps saved CWD"
* = UFP_CWD
        .fill 512, 0
