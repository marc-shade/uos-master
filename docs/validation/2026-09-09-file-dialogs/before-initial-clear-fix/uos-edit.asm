; Small text editor, GPL v3, see uos.asm. The document stays below the
; disk-loaded file selector. Save As creates a new cartridge file, verifies
; each write, then closes/reopens and compares every byte before success.
; NOTES.T is imported read-only from the system IEC disk; never scratched.
.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "kernal.inc"
.include "ultimate-files.inc"
.include "file-dialog.inc"
EDMAX = 768
STAGE = $6e00
LW = 38
MAXLINES = 15
EDX = 16
EDY = 34
EDLH = 9
edptr = $40
q = $42
ecnt = $44
eline = $46
etmp = $47

* = APP_START
        ldx #$ff
        txs
        #RegisterApp
        lda $ba
        bne ed_device
        lda #8
ed_device:
        sta sysdev
        lda #0
        sta edlen
        sta edlen+1
        sta dirty
        sta ready
        sta ed_result
        lda #<ed_new_text
        ldx #>ed_new_text
        jsr message
        jsr ed_load
ed_redraw:
        jsr ed_frame
edloop:
        lda #1
        sta ready
        jsr OS_TICK
        jsr KEYIN
        beq edloop
        ldx #0
        stx ready
        cmp #$85
        bne ed_not_save
        jsr ed_save
        jmp ed_redraw
ed_not_save:
        cmp #$86
        beq ed_open_action
        cmp #$87
        beq ed_new_action
        cmp #$1b
        beq ed_exit_action
        cmp #$14
        bne *+5
        jmp ed_backspace
        cmp #13
        bne ed_printable
        lda #10
        bne ed_addchar
ed_printable:
        jsr key_ascii
        cmp #$20
        bcc edloop
        cmp #$7f
        bcs edloop
        bcc ed_addchar
ed_open_action:
        jsr confirm_discard
        bcs ed_redraw
        jsr ed_open
        jmp ed_redraw
ed_new_action:
        jsr confirm_discard
        bcs ed_redraw
        lda #0
        sta edlen
        sta edlen+1
        sta dirty
        lda #<ed_new_text
        ldx #>ed_new_text
        jsr message
        jmp ed_redraw
ed_exit_action:
        jsr confirm_discard
        bcs ed_redraw
        lda sysdev
        sta $ba
        #UnregisterApp
        jmp DESK_START
ed_addchar:
        pha
        lda edlen+1
        cmp #3
        bcc ed_room
        pla
        lda #<ed_full_text
        ldx #>ed_full_text
        jsr message
        jmp ed_redraw
ed_room:
        jsr end_pointer
        pla
        ldy #0
        sta (edptr),y
        inc edlen
        bne ed_changed
        inc edlen+1
ed_changed:
        lda #1
        sta dirty
        lda #<ed_dirty_text
        ldx #>ed_dirty_text
        jsr message
        jsr ed_render
        jsr draw_status
        jmp edloop
ed_backspace:
        lda edlen
        ora edlen+1
        bne *+5
        jmp edloop
        lda edlen
        bne ed_delete_low
        dec edlen+1
ed_delete_low:
        dec edlen
        jmp ed_changed
end_pointer:
        clc
        lda edlen
        adc #<edbuf
        sta edptr
        lda edlen+1
        adc #>edbuf
        sta edptr+1
        rts
confirm_discard:
        lda dirty
        beq confirmed
        lda #<ed_confirm_text
        ldx #>ed_confirm_text
        jsr message
        jsr draw_status
confirm_loop:
        jsr OS_TICK
        jsr KEYIN
        beq confirm_loop
        and #$7f
        and #$df
        cmp #$59
        beq confirmed
        sec
        rts
confirmed:
        clc
        rts

; Open reads into staging and leaves the old document intact until the
; complete bounded text and directory cleanup have both succeeded.
ed_open:
        lda #0
        sta created
        lda #1
        jsr picker
        bcc *+5
        jmp io_failed
        jsr read_document
        bcc *+5
        jmp io_failed
        jsr validate_text
        bcc *+5
        jmp io_failed
        ldx #2
        jsr UFS_CLOSE
        bcc *+5
        jmp io_failed
        jsr accept_document
        lda #<ed_open_text
        ldx #>ed_open_text
        jmp message
ed_save:
        lda #0
        sta created
        lda #7
        jsr picker
        bcc *+5
        jmp io_failed
        inc created
        lda #0
        sta transferred
        sta transferred+1
save_loop:
        jsr remaining
        beq save_close
        jsr block_size
        clc
        lda transferred
        adc #<edbuf
        sta r0L
        lda transferred+1
        adc #>edbuf
        sta r0H
        ldx #2
        jsr UFS_WRITE
        bcs io_failed
        jsr advance_transfer
        jsr OS_TICK
        jmp save_loop
save_close:
        ldx #2
        jsr UFS_CLOSE
        bcs io_failed
        lda #<UFP_PATH
        sta r0L
        lda #>UFP_PATH
        sta r0H
        lda #1
        ldx #2
        jsr UFS_OPEN
        bcs io_failed
        jsr read_document
        bcs io_failed
        lda incoming
        cmp edlen
        bne save_differs
        lda incoming+1
        cmp edlen+1
        bne save_differs
        jsr buffer_pointers
compare_byte:
        lda ecnt
        ora ecnt+1
        beq save_verified
        ldy #0
        lda (edptr),y
        cmp (q),y
        bne save_differs
        jsr buffer_advance
        jmp compare_byte
save_differs:
        lda #UFS_VERIFY
        bne io_failed
save_verified:
        ldx #2
        jsr UFS_CLOSE
        bcs io_failed
        lda #0
        sta dirty
        sta ed_result
        lda #<ed_saved_text
        ldx #>ed_saved_text
        jmp message
io_failed:
        sta ed_result
        ; CLOSE is the only retry: never replay OPEN, READ or WRITE. Save
        ; failures retain the newly created file and the unsaved document.
        ldx #2
        jsr UFS_CLOSE
        bcc io_cleanup_done
        sta ed_result
io_cleanup_done:
        lda ed_result
        cmp #UFP_CANCELLED
        bne io_error
        lda #<ed_cancel_text
        ldx #>ed_cancel_text
        jmp message
io_error:
        lda ed_result
        lsr
        lsr
        lsr
        lsr
        tax
        lda hex_digits,x
        sta ed_error_text+11
        sta ed_partial_text+11
        lda ed_result
        and #15
        tax
        lda hex_digits,x
        sta ed_error_text+12
        sta ed_partial_text+12
        lda created
        beq io_no_created_file
        lda #1
        sta dirty
        lda #<ed_partial_text
        ldx #>ed_partial_text
        jmp message
io_no_created_file:
        lda #<ed_error_text
        ldx #>ed_error_text
        jmp message
picker:
        pha
        lda sysdev
        sta $ba
        lda #<default_name
        sta r0L
        lda #>default_name
        sta r0H
        ldx #2
        pla
        jmp UFP_PICK
read_document:
        lda UFS_SIZE+3
        ora UFS_SIZE+2
        bne too_large
        lda UFS_SIZE+1
        cmp #3
        bcc read_size
        bne too_large
        lda UFS_SIZE
        bne too_large
read_size:
        lda UFS_SIZE
        sta incoming
        lda UFS_SIZE+1
        sta incoming+1
        lda #0
        sta transferred
        sta transferred+1
read_loop:
        lda transferred
        cmp incoming
        bne read_block
        lda transferred+1
        cmp incoming+1
        beq read_done
read_block:
        clc
        lda transferred
        adc #<STAGE
        sta r0L
        lda transferred+1
        adc #>STAGE
        sta r0H
        lda #0
        sta r1L
        lda #2
        sta r1H
        ldx #2
        jsr UFS_READ
        bcs read_error
        jsr advance_transfer
        jsr OS_TICK
        jmp read_loop
read_done:
        lda #0
        clc
read_error:
        rts
too_large:
        lda #UFS_RANGE
        sec
        rts
remaining:
        sec
        lda edlen
        sbc transferred
        sta r1L
        lda edlen+1
        sbc transferred+1
        sta r1H
        ora r1L
        rts
block_size:
        lda r1H
        cmp #2
        bcc block_done
        lda #0
        sta r1L
        lda #2
        sta r1H
block_done:
        rts
advance_transfer:
        clc
        lda transferred
        adc UFS_COUNT
        sta transferred
        lda transferred+1
        adc UFS_COUNT+1
        sta transferred+1
        rts
buffer_pointers:
        lda #<edbuf
        sta edptr
        lda #>edbuf
        sta edptr+1
        lda #<STAGE
        sta q
        lda #>STAGE
        sta q+1
        lda incoming
        sta ecnt
        lda incoming+1
        sta ecnt+1
        rts
buffer_advance:
        inc edptr
        bne buffer_q
        inc edptr+1
buffer_q:
        inc q
        bne buffer_count
        inc q+1
buffer_count:
        lda ecnt
        bne buffer_low
        dec ecnt+1
buffer_low:
        dec ecnt
        rts
validate_text:
        jsr buffer_pointers
validate_loop:
        lda ecnt
        ora ecnt+1
        beq valid_text
        ldy #0
        lda (q),y
        cmp #10
        beq validate_next
        cmp #13
        beq validate_next
        cmp #$20
        bcc invalid_text
        cmp #$7f
        bcs invalid_text
validate_next:
        jsr buffer_advance
        jmp validate_loop
valid_text:
        clc
        rts
invalid_text:
        lda #$eb
        sec
        rts
accept_document:
        jsr buffer_pointers
accept_byte:
        lda ecnt
        ora ecnt+1
        beq accept_done
        ldy #0
        lda (q),y
        sta (edptr),y
        jsr buffer_advance
        jmp accept_byte
accept_done:
        lda incoming
        sta edlen
        lda incoming+1
        sta edlen+1
        lda #0
        sta dirty
        sta ed_result
        rts

; The append editor follows the end of the document. First scan all visual
; lines, then skip the earlier ones so even a note of 768 newlines is usable.
; CR/LF bytes from cartridge files are preserved; CRLF draws one newline.
ed_render:
        lda #EDY-1
        ldx #MAXLINES*EDLH+1
        jsr clear_area
        lda #4
ed_clear_vdc:
        pha
        jsr VDCLR
        pla
        clc
        adc #1
        cmp #19
        bne ed_clear_vdc
        jsr render_start
        lda #0
        sta rows
        sta rows+1
count_rows:
        jsr next_character
        bcs rows_counted
        jsr line_break
        bcc count_rows
        inc rows
        bne count_rows
        inc rows+1
        jmp count_rows
rows_counted:
        sec
        lda rows
        sbc #MAXLINES-1
        sta skip
        lda rows+1
        sbc #0
        sta skip+1
        bcs have_skip
        lda #0
        sta skip
        sta skip+1
have_skip:
        jsr render_start
skip_rows:
        lda skip
        ora skip+1
        beq render_visible
        jsr next_character
        jsr line_break
        bcc skip_rows
        lda skip
        bne skip_low
        dec skip+1
skip_low:
        dec skip
        jmp skip_rows
render_visible:
        lda #0
        sta eline
        sta linepos
render_character:
        jsr next_character
        bcs render_last
        sta byte
        jsr line_break
        lda byte
        cmp #13
        beq render_line
        cmp #10
        beq render_lf
        jsr ascii_text
        ldx linepos
        sta elbuf,x
        inc linepos
        lda col
        beq render_line
        jmp render_character
render_lf:
        lda previous_cr
        bne render_character
render_line:
        jsr ed_drawline
        inc eline
        lda eline
        cmp #MAXLINES
        bcs render_done
        lda #0
        sta linepos
        jmp render_character
render_last:
        jsr ed_drawline
render_done:
        rts
render_start:
        lda #<edbuf
        sta edptr
        lda #>edbuf
        sta edptr+1
        lda edlen
        sta ecnt
        lda edlen+1
        sta ecnt+1
        lda #0
        sta col
        sta last_cr
        rts
next_character:
        lda ecnt
        ora ecnt+1
        bne character_available
        sec
        rts
character_available:
        ldy #0
        lda (edptr),y
        pha
        inc edptr
        bne character_count
        inc edptr+1
character_count:
        lda ecnt
        bne character_low
        dec ecnt+1
character_low:
        dec ecnt
        pla
        clc
        rts
line_break:
        ldx last_cr
        stx previous_cr
        ldx #0
        stx last_cr
        cmp #13
        beq break_cr
        cmp #10
        bne break_printable
        ldx previous_cr
        bne no_break
        beq break_line
break_cr:
        inc last_cr
break_line:
        ldx #0
        stx col
        sec
        rts
break_printable:
        inc col
        ldx col
        cpx #LW
        beq break_line
no_break:
        clc
        rts
ed_drawline:
        ldx linepos
        lda #0
        sta elbuf,x
        lda #EDX
        sta X1
        lda #0
        sta X1+1
        sta Y1+1
        lda eline
        asl
        asl
        asl
        clc
        adc eline
        adc #EDY
        sta Y1
        lda #<elbuf
        sta r9L
        lda #>elbuf
        sta r9H
        jsr GPUTS
        lda #<elbuf
        sta r9L
        lda #>elbuf
        sta r9H
        lda eline
        clc
        adc #4
        ldx #2
        jmp VDTEXT
ed_frame:
        lda #8
        sta clear_x
        lda #39
        sta clear_columns
        lda #6
        ldx #183
        jsr clear_area
        #DrawRect 8, 6, 304, 182, 0
        lda #16
        sta clear_x
        lda #37
        sta clear_columns
        lda #0
        sta Y1+1
        #Text 16, 12, ed_title
        lda #0
        sta Y1+1
        #Text 16, 178, ed_hint
        lda #2
ed_frame_vdc:
        pha
        jsr VDCLR
        pla
        clc
        adc #1
        cmp #24
        bne ed_frame_vdc
        lda #<ed_title
        sta r9L
        lda #>ed_title
        sta r9H
        lda #2
        ldx #0
        jsr VDTEXT
        lda #<ed_hint
        sta r9L
        lda #>ed_hint
        sta r9H
        lda #23
        ldx #0
        jsr VDTEXT
        jsr ed_render
        jmp draw_status
message:
        sta statusptr
        stx statusptr+1
        rts
draw_status:
        lda #23
        ldx #10
        jsr clear_area
        lda #3
        jsr VDCLR
        lda #16
        sta X1
        lda #24
        sta Y1
        lda #0
        sta X1+1
        sta Y1+1
        jsr status_pointer
        jsr GPUTS
        jsr status_pointer
        lda #3
        ldx #0
        jmp VDTEXT
status_pointer:
        lda statusptr
        sta r9L
        lda statusptr+1
        sta r9H
        rts
; Exact scanlines; the legacy ClrRect macro rounds outward to eight-pixel
; bands, which erases adjacent text and the desktop clock at y189.
clear_area:
        sta clear_scan
        stx clear_left
clear_scanline:
        lda clear_scan
        and #7
        clc
        adc clear_x
        sta r0L
        lda clear_scan
        lsr
        lsr
        lsr
        tax
        lda bandsL,x
        clc
        adc r0L
        sta r0L
        lda bandsH,x
        adc #0
        sta r0H
        ldx clear_columns
        ldy #0
clear_cell:
        lda #0
        sta (r0),y
        clc
        lda r0L
        adc #8
        sta r0L
        bcc clear_cell_next
        inc r0H
clear_cell_next:
        dex
        bne clear_cell
        inc clear_scan
        dec clear_left
        bne clear_scanline
        rts
bandsL: .for i in range(25)
        .byte <($a000+i*320)
        .endfor
bandsH: .for i in range(25)
        .byte >($a000+i*320)
        .endfor
key_ascii:
        cmp #$41
        bcc ascii_return
        cmp #$5b
        bcs key_upper
        ora #$20
        rts
key_upper:
        cmp #$c1
        bcc ascii_return
        cmp #$db
        bcs ascii_return
        and #$7f
ascii_return:
        rts
ascii_text:
        cmp #$7b
        bcs ascii_dot
        cmp #$61
        bcc ascii_upper
        and #$df
        rts
ascii_upper:
        cmp #$41
        bcc ascii_return
        cmp #$5b
        bcs ascii_return
        ora #$80
        rts
ascii_dot:
        lda #$2e
        rts

; Bounded, read-only legacy import. Missing media, serial errors, malformed
; text and oversized files leave the empty editor intact. No SEQ writes.
ed_load:
        lda #3
        ldx sysdev
        ldy #0
        jsr SETLFS
        lda #10
        ldx #<dirpat
        ldy #>dirpat
        jsr SETNAM
        jsr OPEN
        bcc *+5
        jmp legacy_close
        ldx #3
        jsr CHKIN
        bcc *+5
        jmp legacy_close
        lda #0
        sta quotes
        sta ecnt
        lda #4
        sta ecnt+1
legacy_directory:
        jsr CHRIN
        pha
        jsr READST
        sta serial_status
        pla
        cmp #$22
        bne legacy_status
        inc quotes
legacy_status:
        lda serial_status
        bne legacy_directory_done
        lda ecnt
        bne legacy_dir_low
        dec ecnt+1
legacy_dir_low:
        dec ecnt
        lda ecnt
        ora ecnt+1
        bne legacy_directory
legacy_directory_done:
        jsr legacy_close
        lda serial_status
        and #$bf
        beq *+5
        jmp legacy_return
        lda quotes
        cmp #4
        bcc legacy_return
        lda #3
        ldx sysdev
        ldy #3
        jsr SETLFS
        lda #11
        ldx #<loadname
        ldy #>loadname
        jsr SETNAM
        jsr OPEN
        bcs legacy_close
        ldx #3
        jsr CHKIN
        bcs legacy_close
        lda #0
        sta incoming
        sta incoming+1
        sta q
        lda #>STAGE
        sta q+1
legacy_byte:
        jsr CHRIN
        pha
        jsr READST
        sta serial_status
        and #$bf
        bne legacy_drop
        lda incoming+1
        cmp #3
        bcs legacy_drop
        pla
        cmp #13
        bne legacy_ascii
        lda #10
legacy_ascii:
        jsr key_ascii
        ldy #0
        sta (q),y
        inc q
        bne legacy_size
        inc q+1
legacy_size:
        inc incoming
        bne legacy_end
        inc incoming+1
legacy_end:
        lda serial_status
        beq legacy_byte
        jsr legacy_close
        jsr validate_text
        bcs legacy_return
        jsr accept_document
        lda #<ed_import_text
        ldx #>ed_import_text
        jmp message
legacy_drop:
        pla
legacy_close:
        jsr CLRCHN
        lda #3
        jmp CLOSE
legacy_return:
        rts

ed_title: .text "Text editor",0
ed_hint: .text "F1 Save As  F3 Open  F5 New  Esc Back",0
ed_new_text: .text "New note - type to append",0
ed_dirty_text: .text "Unsaved changes",0
ed_confirm_text: .text "Unsaved: Y discard / other key back",0
ed_full_text: .text "Note is full (768 bytes)",0
ed_error_text: .text "File error 00; note kept",0
ed_partial_text: .text "Save error 00; new file retained",0
hex_digits: .text "0123456789ABCDEF"
ed_cancel_text: .text "Cancelled; note kept",0
ed_saved_text: .text "Saved and verified",0
ed_open_text: .text "Opened text file",0
ed_import_text: .text "Imported NOTES.T (read only)",0
; Cartridge defaults use ASCII; IEC names use KERNAL's unshifted bytes.
default_name: .byte $6e,$6f,$74,$65,$73,$2e,$74,$78,$74,0
loadname: .byte $4e,$4f,$54,$45,$53,$2e,$54,$2c,$53,$2c,$52
dirpat: .byte $24,$30,$3a,$4e,$4f,$54,$45,$53,$2e,$54
sysdev: .byte 8
edlen: .word 0
incoming: .word 0
transferred: .word 0
dirty: .byte 0
created: .byte 0
ready: .byte 0
ed_result: .byte 0
statusptr: .word 0
serial_status: .byte 0
quotes: .byte 0
rows: .word 0
skip: .word 0
col: .byte 0
last_cr: .byte 0
previous_cr: .byte 0
byte: .byte 0
linepos: .byte 0
clear_x: .byte 16
clear_columns: .byte 37
clear_scan: .byte 0
clear_left: .byte 0
elbuf: .fill LW+1,0
edit_code_end:
        .cerror * > $5f00, "editor code overlaps retained document"
* = $5f00
edbuf: .fill EDMAX,0
edit_end:
        .cerror * > UFP_LIBRARY, "editor overlaps modal selector"
