; Exclusive file copy dialog. GPL v3, see uos.asm.
; DOS 2 reads the browser selection in its unchanged CWD. DOS 1 creates an
; absolute destination. Both files are closed/reopened and compared in full.
; Partial/unverified files are retained; this module never deletes or retries
; a write. The resident service quarantines ambiguous handle ownership.
.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "ultimate-files.inc"
.include "ultimate-copy.inc"

DEST = $6900                    ; 893 bytes + NUL, matches OPEN's full bound
BLOCK = $6d00                   ; source bytes, 512
VERIFY = $6f00                  ; reopened destination bytes, 512
CANCELLED = $e9                 ; dialog result, not a file-service error
p = $60
q = $62
n = $64

* = APP_START
        ldx #$ff
        txs
        #RegisterApp
        lda #0
        sta phase
        sta ready
        sta held
        sta result
        sta close_error
        sta valid
        sta diagnostic
        sta length
        sta length+1
        sta cursor
        sta cursor+1
        sta scroll
        sta scroll+1
        sta DEST
        ldx #11
zero_progress:
        sta total,x
        dex
        bpl zero_progress
        lda $ba
        bne system_device
        lda #8
system_device:
        sta sysdev
        lda COPY_HANDOFF
        cmp #$55
        bne invalid_handoff
        lda COPY_HANDOFF+1
        cmp #$43
        bne invalid_handoff
        lda COPY_HANDOFF+2
        cmp #1
        bne invalid_handoff
        lda COPY_DIRECTION
        cmp #1
        bne invalid_handoff
        inc valid
        lda COPY_SYSDEV
        sta sysdev
        lda #0
        sta COPY_DIRECTION
        jsr default_destination
        jmp draw_dialog
invalid_handoff:
        lda #UFS_BADARG
        sta result
        lda #3
        sta phase
draw_dialog:
        jsr frame
        jsr draw_fields
input_loop:
        lda #1
        sta ready
        jsr OS_TICK
        jsr get_key
        beq input_loop
        pha
        lda #0
        sta ready
        pla
        cmp #$1b
        bne input_mode
        jmp return_browser
input_mode:
        ldx phase
        beq edit_key
        and #$7f
        and #$df
        cmp #$52
        beq retry_close
        cmp #$45
        bne input_loop
        lda valid
        beq input_loop
        lda UFS_MODE
        ora UFS_MODE+1
        bne input_loop
        lda #0
        sta phase
        sta result
        sta close_error
        sta diagnostic
        jmp draw_dialog
retry_close:
        jsr close_handles
        jsr draw_fields
        jmp input_loop

edit_key:
        cmp #$0d
        bne edit_controls
        jsr run_copy
        jsr draw_fields
        jmp input_loop
edit_controls:
        cmp #$9d
        beq edit_left
        cmp #$1d
        beq edit_right
        cmp #$13               ; HOME
        beq edit_home
        cmp #$15               ; Ctrl-U clears the whole destination
        beq edit_clear
        cmp #$14               ; DEL removes the byte before the cursor
        beq edit_delete
        jsr petscii_ascii
        cmp #$20
        bcc input_loop
        cmp #$7f
        bcs input_loop
        jsr insert_byte
        jmp edit_redraw
edit_left:
        lda cursor
        ora cursor+1
        beq edit_redraw
        lda cursor
        bne edit_dec
        dec cursor+1
edit_dec:
        dec cursor
        jmp edit_redraw
edit_right:
        lda cursor+1
        cmp length+1
        bne edit_inc
        lda cursor
        cmp length
        beq edit_redraw
edit_inc:
        inc cursor
        bne edit_redraw
        inc cursor+1
        jmp edit_redraw
edit_clear:
        lda #0
        sta length
        sta length+1
        sta DEST
edit_home:
        lda #0
        sta cursor
        sta cursor+1
        jmp edit_redraw
edit_delete:
        jsr delete_byte
edit_redraw:
        jsr draw_destination
        jmp input_loop

; Every operand and UI counter lives outside public r0-r15. File calls,
; drawing and OS_TICK may destroy all public scratch registers.
run_copy:
        lda #0
        sta result
        sta close_error
        sta diagnostic
        ldx #11
run_zero:
        sta total,x
        dex
        bpl run_zero
        lda UFS_MODE
        ora UFS_MODE+1
        beq check_destination
        lda #UFS_BUSY
        jmp fail_local
check_destination:
        lda DEST
        cmp #$2f
        bne bad_destination
        lda length
        ora length+1
        beq bad_destination
        jsr end_pointer
        jsr dec_p
        ldy #0
        lda (p),y
        cmp #$2f
        beq bad_destination
        cmp #$5c
        bne start_copy
bad_destination:
        lda #UFS_BADARG
        jmp fail_local
start_copy:
        lda #1
        sta phase
        jsr draw_fields
        jsr poll_cancel
        bcs copy_return
        jsr open_source
        bcs fail_service
        ldx #3
save_total:
        lda UFS_SIZE,x
        sta total,x
        dex
        bpl save_total
        lda #7
        jsr open_destination
        bcs fail_service
copy_loop:
        jsr poll_cancel
        bcs copy_return
        jsr read_source
        bcs fail_service
        lda amount
        ora amount+1
        beq start_verification
        lda #<BLOCK
        sta r0L
        lda #>BLOCK
        sta r0H
        lda amount
        sta r1L
        lda amount+1
        sta r1H
        ldx #1
        jsr UFS_WRITE
        bcs fail_service
        ldx #0
        jsr advance_progress
        jsr progress_if_due
        jmp copy_loop
copy_return:
        rts
fail_service:
        sta result
        ldx #31
save_diagnostic:
        lda UFS_STATUS,x
        sta diagnostic,x
        dex
        bpl save_diagnostic
        jmp finish_operation
fail_local:
        sta result
finish_operation:
        jsr close_handles
        lda #3
        sta phase
        rts

start_verification:
        jsr close_handles
        bcs verification_close_failed
        lda #2
        sta phase
        jsr draw_fields
        jsr poll_cancel
        bcs copy_return
        jsr open_source
        bcs fail_service
        jsr check_size
        bcs fail_local
        lda #1
        jsr open_destination
        bcs fail_service
        jsr check_size
        bcs fail_local
verify_loop:
        jsr poll_cancel
        bcs copy_return
        jsr read_source
        bcs fail_service
        lda #<VERIFY
        sta r0L
        lda #>VERIFY
        sta r0H
        lda #0
        sta r1L
        lda #2
        sta r1H
        ldx #1
        jsr UFS_READ
        bcs fail_service
        lda UFS_COUNT
        cmp amount
        bne verification_mismatch
        lda UFS_COUNT+1
        cmp amount+1
        bne verification_mismatch
        lda amount
        ora amount+1
        beq verification_done
        jsr compare_block
        bcs verification_mismatch
        ldx #4
        jsr advance_progress
        jsr progress_if_due
        jmp verify_loop
verification_mismatch:
        lda #UFS_VERIFY
        jmp fail_local
verification_done:
        ; The final close must also complete before showing success.
        jsr close_handles
        bcs verification_close_failed
        lda #3
        sta phase
        rts
verification_close_failed:
        lda close_error
        jmp fail_service

check_size:
        ldx #3
size_byte:
        lda UFS_SIZE,x
        cmp total,x
        bne size_changed
        dex
        bpl size_byte
        clc
        rts
size_changed:
        lda #UFS_VERIFY
        sec
        rts
open_source:
        lda #<COPY_SOURCE
        sta r0L
        lda #>COPY_SOURCE
        sta r0H
        ldx #2
        lda #1
        jmp UFS_OPEN
open_destination:
        pha
        lda #<DEST
        sta r0L
        lda #>DEST
        sta r0H
        ldx #1
        pla
        jmp UFS_OPEN
read_source:
        lda #<BLOCK
        sta r0L
        lda #>BLOCK
        sta r0H
        lda #0
        sta r1L
        lda #2
        sta r1H
        ldx #2
        jsr UFS_READ
        php
        pha
        lda UFS_COUNT
        sta amount
        lda UFS_COUNT+1
        sta amount+1
        pla
        plp
        rts
close_handles:
        jsr UFS_CLOSEALL
        sta close_error
        rts
advance_progress:
        clc
        lda copied,x
        adc amount
        sta copied,x
        lda copied+1,x
        adc amount+1
        sta copied+1,x
        lda copied+2,x
        adc #0
        sta copied+2,x
        lda copied+3,x
        adc #0
        sta copied+3,x
        rts
progress_if_due:
        ; Account/check input every block, repaint every 4 KiB. Rendering
        ; both proportional-font counters per 512 bytes dominated copy time.
        ; Phase changes and the final/error screen always repaint the tail.
        lda copied,x
        bne progress_not_due
        lda copied+1,x
        and #15
        bne progress_not_due
        jmp draw_progress
progress_not_due:
        rts
compare_block:
        lda #<BLOCK
        sta p
        lda #>BLOCK
        sta p+1
        lda #<VERIFY
        sta q
        lda #>VERIFY
        sta q+1
        lda amount
        sta n
        lda amount+1
        sta n+1
        ldy #0
compare_byte:
        lda (p),y
        cmp (q),y
        bne compare_bad
        inc p
        bne compare_p
        inc p+1
compare_p:
        inc q
        bne compare_q
        inc q+1
compare_q:
        lda n
        bne compare_dec
        dec n+1
compare_dec:
        dec n
        lda n
        ora n+1
        bne compare_byte
        clc
        rts
compare_bad:
        sec
        rts
poll_cancel:
        jsr OS_TICK
        jsr get_key
        cmp #$1b
        beq cancel_operation
        clc
        rts
cancel_operation:
        lda #CANCELLED
        jsr fail_local
        sec
        rts

return_browser:
        lda valid
        beq return_without_selection
        lda #2
        sta COPY_DIRECTION
return_without_selection:
        lda sysdev
        sta $ba
        #UnregisterApp
        lda #<browser_module
        sta r0L
        lda #>browser_module
        sta r0H
        jsr FILLFILE
        jmp LAUNCH_APP

default_destination:
        lda #<COPY_PATH
        sta p
        lda #>COPY_PATH
        sta p+1
        lda #<DEST
        sta q
        lda #>DEST
        sta q+1
        ldy #0
default_byte:
        lda (p),y
        beq default_suffix
        sta (q),y
        inc p
        bne default_src
        inc p+1
default_src:
        inc q
        bne default_dst
        inc q+1
default_dst:
        inc length
        bne default_bound
        inc length+1
default_bound:
        ; The browser accepts at most 510 path bytes. Refuse stale/corrupt
        ; handoffs instead of scanning into the settings record at $7350.
        lda length+1
        cmp #1
        bne default_byte
        lda length
        cmp #$ff
        bcc default_byte
        lda #0
        sta DEST
        sta length
        sta length+1
        rts
default_suffix:
        ldy #0
default_suffix_byte:
        lda default_name,y
        sta (q),y
        beq default_done
        inc length
        bne default_suffix_next
        inc length+1
default_suffix_next:
        iny
        bne default_suffix_byte
default_done:
        lda length
        sta cursor
        lda length+1
        sta cursor+1
        rts

; Insertion editor with 16-bit length/cursor. NUL moves with the tail.
end_pointer:
        clc
        lda length
        adc #<DEST
        sta p
        lda length+1
        adc #>DEST
        sta p+1
        rts
cursor_pointer:
        clc
        lda cursor
        adc #<DEST
        sta q
        lda cursor+1
        adc #>DEST
        sta q+1
        rts
dec_p:
        lda p
        bne dec_p_low
        dec p+1
dec_p_low:
        dec p
        rts
insert_byte:
        sta typed
        lda length+1
        cmp #>893
        bcc insert_room
        lda length
        cmp #<893
        bcs editor_done
insert_room:
        jsr end_pointer
        jsr cursor_pointer
insert_shift:
        ldy #0
        lda (p),y
        iny
        sta (p),y
        lda p
        cmp q
        bne insert_previous
        lda p+1
        cmp q+1
        beq insert_store
insert_previous:
        jsr dec_p
        jmp insert_shift
insert_store:
        lda typed
        ldy #0
        sta (q),y
        inc length
        bne insert_cursor
        inc length+1
insert_cursor:
        inc cursor
        bne editor_done
        inc cursor+1
editor_done:
        rts
delete_byte:
        lda cursor
        ora cursor+1
        beq editor_done
        lda cursor
        bne delete_cursor
        dec cursor+1
delete_cursor:
        dec cursor
        jsr cursor_pointer
delete_shift:
        ldy #1
        lda (q),y
        dey
        sta (q),y
        cmp #0
        beq delete_length
        inc q
        bne delete_shift
        inc q+1
        jmp delete_shift
delete_length:
        lda length
        bne delete_low
        dec length+1
delete_low:
        dec length
        rts
petscii_ascii:
        cmp #$41
        bcc petscii_done
        cmp #$5b
        bcs petscii_shifted
        ora #$20
        rts
petscii_shifted:
        cmp #$c1
        bcc petscii_done
        cmp #$db
        bcs petscii_done
        and #$7f
petscii_done:
        rts

get_key:
        jsr KEYIN
        bne key_done
        jsr READ_BUTTON
        bne mouse_released
        lda #1
        sta held
        lda #0
key_done:
        rts
mouse_released:
        lda held
        beq key_done
        lda #0
        sta held
        php
        sei
        lda $d010
        and #1
        sta mouse_x+1
        sec
        lda $d000
        sbc #24
        sta mouse_x
        lda mouse_x+1
        sbc #0
        sta mouse_x+1
        sec
        lda $d001
        sbc #50
        plp
        cmp #176
        bcc mouse_none
        cmp #186
        bcs mouse_none
        lda mouse_x+1
        beq mouse_low
        cmp #1
        bne mouse_none
        lda mouse_x
        cmp #48
        bcc mouse_cancel
        bcs mouse_none
mouse_low:
        lda mouse_x
        cmp #24
        bcc mouse_none
        cmp #144
        bcc mouse_enter
        cmp #200
        bcc mouse_none
mouse_cancel:
        lda #$1b
        rts
mouse_enter:
        lda phase
        bne mouse_none
        lda #$0d
        rts
mouse_none:
        lda #0
        rts

; Draw only the fields that change. Text owns ten scanlines (ascenders and
; descenders included); the bottom desktop clock remains outside the dialog.
frame:
        #PenWrite
        lda #2
frame_vdc:
        pha
        jsr VDCLR
        pla
        clc
        adc #1
        cmp #24
        bne frame_vdc
        lda #<title
        ldx #>title
        jsr text_line
        ldx #0
        jsr draw_line
        lda #<from_text
        ldx #>from_text
        jsr text_line
        ldx #1
        jsr draw_line
        jsr blank_line
        lda valid
        beq source_draw
        ldy #0
source_text:
        lda COPY_SOURCE,y
        beq source_draw
        jsr ascii_text
        sta line,y
        iny
        cpy #35
        bne source_text
source_draw:
        ldx #2
        jsr draw_line
        lda #<to_text
        ldx #>to_text
        jsr text_line
        ldx #3
        jsr draw_line
        lda #<editor_help
        ldx #>editor_help
        jsr text_line
        ldx #6
        jmp draw_line
draw_fields:
        jsr draw_destination
        jsr draw_progress
        ldx phase
        lda result
        beq status_pointer
        ldx #4
        cmp #CANCELLED
        bne status_pointer
        inx
status_pointer:
        lda status_low,x
        pha
        lda status_high,x
        tax
        pla
        jsr text_line
        ldx #9
        jsr draw_line
        jsr blank_line
        lda UFS_MODE
        ora UFS_MODE+1
        beq draw_error
        lda phase
        cmp #3
        bne draw_error
        lda #<close_text
        ldx #>close_text
        jsr text_line
        lda close_error
        ldy #7
        jsr hex_byte
        jmp diagnostic_draw
draw_error:
        lda result
        beq diagnostic_draw
        cmp #CANCELLED
        beq diagnostic_draw
        lda #<error_text
        ldx #>error_text
        jsr text_line
        lda result
        ldy #7
        jsr hex_byte
        ldy #0
diagnostic_byte:
        lda diagnostic,y
        beq diagnostic_draw
        jsr ascii_text
        sta line+11,y
        iny
        cpy #24
        bne diagnostic_byte
diagnostic_draw:
        ldx #10
        jsr draw_line
        lda #<edit_buttons
        ldx #>edit_buttons
        ldy phase
        beq buttons_pointer
        lda #<done_buttons
        ldx #>done_buttons
        cpy #3
        beq buttons_pointer
        lda #<work_buttons
        ldx #>work_buttons
buttons_pointer:
        jsr text_line
        ldx #11
        jmp draw_line

draw_destination:
        sec
        lda cursor
        sbc scroll
        sta offset
        lda cursor+1
        sbc scroll+1
        bcc scroll_left
        bne scroll_right
        lda offset
        cmp #35
        bcc scroll_ready
scroll_right:
        sec
        lda cursor
        sbc #34
        sta scroll
        lda cursor+1
        sbc #0
        sta scroll+1
        lda #34
        sta offset
        bne scroll_ready
scroll_left:
        lda cursor
        sta scroll
        lda cursor+1
        sta scroll+1
        lda #0
        sta offset
scroll_ready:
        jsr blank_line
        clc
        lda scroll
        adc #<DEST
        sta p
        lda scroll+1
        adc #>DEST
        sta p+1
        ldy #0
destination_byte:
        lda (p),y
        beq destination_draw
        jsr ascii_text
        sta line,y
        iny
        cpy #35
        bne destination_byte
destination_draw:
        ldx #4
        jsr draw_line
        jsr blank_line
        lda phase
        bne cursor_draw
        ldx offset
        lda #$5e
        sta line,x
cursor_draw:
        ldx #5
        jmp draw_line

draw_progress:
        lda #0
        sta progress_index
progress_row:
        ldx progress_index
        lda progress_low,x
        pha
        lda progress_high,x
        tax
        pla
        jsr text_line
        lda progress_index
        asl
        asl
        clc
        adc #3
        tax
        ldy #7
progress_digits:
        stx digit_index
        lda copied,x
        jsr hex_byte
        ldx digit_index
        dex
        txa
        and #3
        cmp #3
        bne progress_digits
        ldx #3
        ldy #18
total_digits:
        stx digit_index
        lda total,x
        jsr hex_byte
        ldx digit_index
        dex
        bpl total_digits
        lda progress_index
        clc
        adc #7
        tax
        jsr draw_line
        inc progress_index
        lda progress_index
        cmp #2
        bne progress_row
        rts
blank_line:
        lda #$20
        ldx #34
blank_byte:
        sta line,x
        dex
        bpl blank_byte
        lda #0
        sta line+35
        rts
text_line:
        sta p
        stx p+1
        jsr blank_line
        ldy #0
text_byte:
        lda (p),y
        beq text_done
        sta line,y
        iny
        cpy #35
        bne text_byte
text_done:
        rts
draw_line:
        stx draw_index
        lda pixel_rows,x
        sec
        sbc #1
        sta clear_y
        lda #10
        sta clear_h
        jsr clear_row_start
        ldx draw_index
        lda pixel_rows,x
        sta Y1
        lda #24
        sta X1
        lda #0
        sta X1+1
        sta Y1+1
        cpx #4
        beq draw_cells
        cpx #5
        beq draw_cells
        jsr line_pointer
        jsr GPUTS
        jmp draw_vdc_line
draw_cells:
        ; The proportional VIC font cannot align a cursor with blank spaces.
        ; Give the editable path and its caret matching eight-pixel cells.
        lda #0
        sta cell
cell_next:
        ldx cell
        lda line,x
        cmp #$20
        beq cell_skip
        sta glyph
        lda #0
        sta X1+1
        lda cell
        asl
        asl
        asl
        rol X1+1
        clc
        adc #24
        sta X1
        bcc cell_y
        inc X1+1
cell_y:
        ldx draw_index
        lda pixel_rows,x
        sta Y1
        lda #0
        sta Y1+1
        lda #<glyph
        sta r9L
        lda #>glyph
        sta r9H
        jsr GPUTS
cell_skip:
        inc cell
        lda cell
        cmp #35
        bne cell_next
draw_vdc_line:
        jsr line_pointer
        ldx draw_index
        lda vdc_rows,x
        ldx #0
        jmp VDTEXT
line_pointer:
        lda #<line
        sta r9L
        lda #>line
        sta r9H
        rts
clear_row_start:
        lda clear_y
        lsr
        lsr
        lsr
        sta r0H
        lda #0
        sta r0L
        lda r0H
        lsr
        ror r0L
        lsr
        ror r0L
        clc
        adc r0H
        adc #$a0
        sta r0H
        lda clear_y
        and #7
        clc
        adc #24
        adc r0L
        sta r0L
        bcc clear_row
        inc r0H
clear_row:
        lda r0L
        sta r1L
        lda r0H
        sta r1H
        ldx #35
        ldy #0
clear_column:
        lda #0
        sta (r1),y
        clc
        lda r1L
        adc #8
        sta r1L
        bcc clear_next_column
        inc r1H
clear_next_column:
        dex
        bne clear_column
        inc r0L
        bne clear_next_y
        inc r0H
clear_next_y:
        inc clear_y
        lda clear_y
        and #7
        bne clear_next_row
        clc
        lda r0L
        adc #<$138
        sta r0L
        lda r0H
        adc #>$138
        sta r0H
clear_next_row:
        dec clear_h
        bne clear_row
        rts
hex_byte:
        pha
        lsr
        lsr
        lsr
        lsr
        tax
        lda digits,x
        sta line,y
        iny
        pla
        and #15
        tax
        lda digits,x
        sta line,y
        iny
        rts
ascii_text:
        cmp #$20
        bcc ascii_dot
        cmp #$7b
        bcs ascii_dot
        cmp #$61
        bcc ascii_upper
        and #$df
        rts
ascii_upper:
        cmp #$41
        bcc ascii_done
        cmp #$5b
        bcs ascii_done
        ora #$80
ascii_done:
        rts
ascii_dot:
        lda #$2e
        rts

title: .text "Copy file",0
from_text: .text "From (selected name):",0
to_text: .text "To (full path, new file):",0
editor_help: .text "Left/right Home Del Ctrl-U clear",0
edit_status: .text "Enter starts a new file copy",0
copy_status: .text "Copying - Esc cancels",0
verify_status: .text "Checking saved copy - Esc cancels",0
done_status: .text "Copy verified",0
fail_status: .text "Failed - destination unverified",0
cancel_status: .text "Cancelled - destination unverified",0
error_text: .text "Error $00: ",0
close_text: .text "Close $00 - R retry, Esc files",0
edit_buttons: .text "Enter copy            Esc files",0
work_buttons: .text "                      Esc cancel",0
done_buttons: .text "E edit path           Esc files",0
copied_text: .text "Copied 00000000 / 00000000h bytes",0
checked_text: .text "Check  00000000 / 00000000h bytes",0
browser_module: .text "uos-ultimate",0
default_name: .byte $63,$6f,$70,$79,$2e,$62,$69,$6e,0 ; ASCII copy.bin
digits: .text "0123456789abcdef"
status_low: .byte <edit_status,<copy_status,<verify_status,<done_status,<fail_status,<cancel_status
status_high: .byte >edit_status,>copy_status,>verify_status,>done_status,>fail_status,>cancel_status
progress_low: .byte <copied_text,<checked_text
progress_high: .byte >copied_text,>checked_text
pixel_rows: .byte 14,32,44,62,74,85,100,116,128,144,158,176
vdc_rows: .byte 2,4,5,7,8,9,11,13,14,16,18,22
total: .fill 4,0
copied: .fill 4,0
checked: .fill 4,0
amount: .word 0
length: .word 0
cursor: .word 0
scroll: .word 0
mouse_x: .word 0
phase: .byte 0                   ; 0 edit, 1 copy, 2 verify, 3 finished
ready: .byte 0                   ; 1 only while accepting dialog input
valid: .byte 0
held: .byte 0
sysdev: .byte 0
result: .byte 0
close_error: .byte 0
typed: .byte 0
offset: .byte 0
progress_index: .byte 0
digit_index: .byte 0
draw_index: .byte 0
cell: .byte 0
glyph: .byte 0,0
clear_y: .byte 0
clear_h: .byte 0
diagnostic: .fill 32,0
line: .fill 36,0
copy_end:
        .cerror * > DEST, "copy dialog overlaps its full destination buffer"
