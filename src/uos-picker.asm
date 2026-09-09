; Disk-loaded modal Open / Save As library, GPL v3, see uos.asm.
; The caller stays below $6200. This library returns an owned UFS handle;
; resident CLOSE restores the borrowed directory after the caller finishes.
.include "equates.inc"
.include "routines.inc"
.include "ultimate-files.inc"
.include "file-dialog.inc"
p = $50
q = $52
n = $54
t = $56

* = UFP_LIBRARY
        jmp entry
        .byte 1
entry:
        lda #0
        sta error
        sta editing
        sta held
        sta leaflen
        sta cursor
        sta UFP_LEAF
        sta base
        sta base+1
        sta selected
        sta backwards
        sta detailoff
        sta detailoff+1
        sta viewpath
        sta ready
        lda UFP_MODE
        cmp #7
        bne preflight
        lda UFP_DEFAULT
        sta p
        lda UFP_DEFAULT+1
        sta p+1
        ora p
        beq preflight
        ldy #0
default_byte:
        lda p+1
        cmp #$50
        bcc bad_argument
        cmp #$62
        bcs bad_argument
        lda (p),y
        sta UFP_LEAF,y
        beq default_done
        iny
        cpy #128
        beq bad_argument
        ; Check the address of every byte, including the terminator.
        tya
        clc
        adc p
        lda p+1
        adc #0
        cmp #$62
        bcc default_byte
bad_argument:
        lda #UFS_BADARG
        rts
default_done:
        sty leaflen
        sty cursor
preflight:
        lda #7
        jsr command
        bcs entry_return
        cmp #85
        beq get_original
        cmp #0
        bne entry_return
        lda #UFS_BUSY
entry_return:
        rts
get_original:
        jsr get_path
        bcs entry_return
        lda UFP_CONTEXT
        sta UFP_CWD
        lda #$11
        sta UFP_CWD+1
        lda pathlen
        clc
        adc #2
        sta UFP_CWDLEN
        lda pathlen+1
        adc #0
        sta UFP_CWDLEN+1
        lda #<UFP_DIRECTORY
        sta p
        lda #>UFP_DIRECTORY
        sta p+1
        lda #<UFP_CWD+2
        sta q
        lda #>UFP_CWD+2
        sta q+1
        jsr path_count
        jsr copy_bytes
        lda #1
        sta UFP_PENDING
        jsr mt_clear
        jsr refresh
redraw:
        jsr paint
input_loop:
        lda #1
        sta ready
        jsr OS_TICK
        jsr KEYIN
        bne key_event
        jsr READ_BUTTON
        bne released
        lda #1
        sta held
        bne input_loop
released:
        lda held
        beq input_loop
        lda #0
        sta held
        jsr mouse
        beq input_loop
key_event:
        ldx #0
        stx ready
        ldx editing
        beq browse_key
        jmp edit_key
browse_key:
        cmp #$1b
        bne browse_action
        lda #UFP_CANCELLED
        jmp cancel
browse_action:
        cmp #$0d
        beq select_entry
        cmp #$85
        beq use_folder
        cmp #$11
        bne *+5
        jmp down
        cmp #$91
        bne *+5
        jmp up
        cmp #$1d
        bne *+5
        jmp right
        cmp #$9d
        bne *+5
        jmp left
        and #$7f
        cmp #$61
        bcc browse_normalized
        cmp #$7b
        bcs browse_normalized
        and #$df
browse_normalized:
        cmp #$4e
        bne *+5
        jmp next
        cmp #$42
        bne *+5
        jmp previous
        cmp #$55
        bne not_parent
        jmp parent
not_parent:
        cmp #$2f
        bne not_root
        jmp root
not_root:
        cmp #$4f                ; O enters a selected image filesystem, too
        bne not_folder
        jmp folder
not_folder:
        cmp #$50
        bne not_path
        lda viewpath
        eor #1
        sta viewpath
        jmp reset_detail
not_path:
        cmp #$52
        beq *+5
        jmp input_loop
        jsr refresh
        jmp redraw
use_folder:
        lda UFP_MODE
        cmp #7
        beq *+5
        jmp input_loop
        inc editing
        jmp redraw
select_entry:
        lda count
        bne *+5
        jmp input_loop
        ldx selected
        lda attrs,x
        and #$18
        beq *+5
        jmp folder
        lda UFP_MODE
        cmp #7
        beq use_folder
        jmp open_selected
down:
        lda selected
        clc
        adc #1
        cmp count
        bcs next
        sta selected
        jmp reset_detail
up:
        lda selected
        beq previous
        dec selected
        jmp reset_detail
next:
        lda more
        bne *+5
        jmp input_loop
        clc
        lda base
        adc count
        sta base
        lda base+1
        adc #0
        sta base+1
        jsr refresh
        jmp redraw
previous:
        lda base
        ora base+1
        bne *+5
        jmp input_loop
        lda #1
        sta backwards
        jsr refresh
        jmp redraw
left:
        lda detailoff
        ora detailoff+1
        bne *+5
        jmp input_loop
        lda detailoff
        sec
        sbc #32
        sta detailoff
        bcs detail_redraw
        dec detailoff+1
        jmp detail_redraw
right:
        jsr detail_source
        lda detailoff
        clc
        adc #32
        sta t
        lda detailoff+1
        adc #0
        sta t+1
        cmp n+1
        bcc right_go
        beq *+5
        jmp input_loop
        lda t
        cmp n
        bcc *+5
        jmp input_loop
right_go:
        lda t
        sta detailoff
        lda t+1
        sta detailoff+1
detail_redraw:
        jsr paint_detail
        jmp input_loop
reset_detail:
        lda #0
        sta detailoff
        sta detailoff+1
        jmp redraw

folder:
        lda count
        bne folder_go
        jmp input_loop
folder_go:
        jsr selected_source
        sec
        lda p
        sbc #2
        sta r0L
        lda p+1
        sbc #0
        sta r0H
        clc
        lda n
        adc #2
        sta r1L
        lda n+1
        adc #0
        sta r1H
        jmp change_dir
root:
        lda #$2f
        sta request+2
        lda #3
        bne short_dir
parent:
        lda #$2e
        sta request+2
        sta request+3
        lda #4
short_dir:
        sta r1L
        lda #0
        sta r1H
        lda UFP_CONTEXT
        sta request
        lda #$11
        sta request+1
        jsr request_pointer
change_dir:
        jsr stream
        bcs action_error
        cmp #0
        bne action_error
        lda #0
        sta base
        sta base+1
        jsr refresh
        jmp redraw
action_error:
        sta error
        jsr capture_error
        jmp redraw

; New names are ASCII components. A path is chosen in the folder browser.
edit_key:
        cmp #$1b
        bne edit_controls
        lda #0
        sta editing
        sta error
        jmp redraw
edit_controls:
        cmp #13
        bne edit_not_enter
        jmp create_file
edit_not_enter:
        cmp #$13
        beq edit_home
        cmp #$15
        beq edit_clear
        cmp #$9d
        beq edit_left
        cmp #$1d
        beq edit_right
        cmp #$14
        beq edit_delete
        jsr mt_key_ascii
        cmp #$20
        bcc edit_redraw
        cmp #$7f
        bcs edit_redraw
        ldx leaflen
        cpx #127
        bcs edit_redraw
        pha
edit_shift:
        lda UFP_LEAF,x
        sta UFP_LEAF+1,x
        cpx cursor
        beq edit_insert
        dex
        bpl edit_shift
edit_insert:
        pla
        sta UFP_LEAF,x
        inc cursor
        inc leaflen
        bne edit_redraw
edit_clear:
        lda #0
        sta leaflen
        sta UFP_LEAF
edit_home:
        lda #0
        sta cursor
        beq edit_redraw
edit_left:
        lda cursor
        beq edit_redraw
        dec cursor
        jmp edit_redraw
edit_right:
        lda cursor
        cmp leaflen
        beq edit_redraw
        inc cursor
        jmp edit_redraw
edit_delete:
        ldx cursor
        beq edit_redraw
        dec cursor
edit_delete_loop:
        lda UFP_LEAF,x
        sta UFP_LEAF-1,x
        inx
        cmp #0
        bne edit_delete_loop
        dec leaflen
edit_redraw:
        jsr paint_leaf
        jmp input_loop
create_file:
        lda leaflen
        beq invalid_leaf
        ldx #0
validate_leaf:
        lda UFP_LEAF,x
        cmp #$20
        bcc invalid_leaf
        cmp #$7f
        bcs invalid_leaf
        cmp #$2f
        beq invalid_leaf
        cmp #$5c
        beq invalid_leaf
        cmp #$2a
        beq invalid_leaf
        cmp #$3f
        beq invalid_leaf
        cmp #$3a
        beq invalid_leaf
        cmp #$22
        beq invalid_leaf
        cmp #$3c
        beq invalid_leaf
        cmp #$3e
        beq invalid_leaf
        cmp #$7c
        beq invalid_leaf
        inx
        cpx leaflen
        bne validate_leaf
        lda UFP_LEAF-1,x
        cmp #$20
        beq invalid_leaf
        cmp #$2e
        beq invalid_leaf
        lda #<UFP_LEAF
        sta p
        lda #>UFP_LEAF
        sta p+1
        lda leaflen
        sta n
        lda #0
        sta n+1
        jmp retain_selection
invalid_leaf:
        lda #UFS_BADARG
        jmp action_error
open_selected:
        jsr selected_source
retain_selection:
        lda n
        sta chosenlen
        lda n+1
        sta chosenlen+1
        lda #<UFP_NAME
        sta q
        lda #>UFP_NAME
        sta q+1
        jsr copy_bytes
        lda #0
        tay
        sta (q),y
        ; Copying the selection over the cache destroys cached records.
        ; A failed OPEN reloads the directory before showing it again.
        jsr compose_path
        lda #<UFP_NAME
        sta r0L
        lda #>UFP_NAME
        sta r0H
        lda UFP_MODE
        cmp #7
        bne selected_open
        ; The service must validate every creation component, including the
        ; chosen directory. A relative leaf would bypass its 127-byte guard.
        lda #<UFP_PATH
        sta r0L
        lda #>UFP_PATH
        sta r0H
selected_open:
        ldx UFP_CONTEXT
        lda UFP_MODE
        jsr UFS_OPEN
        bcs open_failed
        lda #0
        rts
open_failed:
        sta saved_error
        jsr capture_error
        ldx #31
save_open_status:
        lda error_status,x
        sta saved_status,x
        dex
        bpl save_open_status
        ldx UFP_CONTEXT
        jsr UFS_CLOSE
        bcs cancel_close_failed
        jsr refresh
        ldx #31
restore_open_status:
        lda saved_status,x
        sta error_status,x
        dex
        bpl restore_open_status
        lda saved_error
        sta error
        jmp redraw
cancel:
        sta saved_error
        ldx UFP_CONTEXT
        jsr UFS_CLOSE
        bcs cancel_close_failed
        jsr UFP_RECOVER
        bcs cancel_close_failed
        lda saved_error
        rts
cancel_close_failed:
        rts                    ; resident ownership/path remain recoverable

compose_path:
        lda #<UFP_DIRECTORY
        sta p
        lda #>UFP_DIRECTORY
        sta p+1
        lda #<UFP_PATH
        sta q
        lda #>UFP_PATH
        sta q+1
        jsr path_count
        jsr copy_bytes
        ldy #0
        ; GET_PATH ends with '/', checked below; never invent path spelling.
        lda #<UFP_NAME
        sta p
        lda #>UFP_NAME
        sta p+1
        lda chosenlen
        sta n
        lda chosenlen+1
        sta n+1
        jsr copy_bytes
        lda #0
        sta (q),y
        sec
        lda q
        sbc #<UFP_PATH
        sta UFP_PATHLEN
        lda q+1
        sbc #>UFP_PATH
        sta UFP_PATHLEN+1
        rts

command:
        sta request+1
        lda UFP_CONTEXT
        sta request
        lda #2
        sta r1L
        lda #0
        sta r1H
        jsr request_pointer
stream:
        lda #0
        sta r3L
        sta r3H
        sta NET_DIRMODE
        jmp NET_STREAM
request_pointer:
        lda #<request
        sta r0L
        lda #>request
        sta r0H
        rts
get_path:
        lda #$12
        jsr command
        bcs path_return
        cmp #0
        bne path_fail
        lda NET_TRUNC
        bne path_invalid
        lda NET_LEN+1
        cmp #2
        bcs path_invalid
        cmp #1
        bne path_short
        lda NET_LEN
        cmp #255
        bcs path_invalid
path_short:
        lda NET_LEN
        sta pathlen
        sta n
        lda NET_LEN+1
        sta pathlen+1
        sta n+1
        ora n
        beq path_invalid
        lda NET_DATA
        cmp #$2f
        bne path_invalid
        lda #<NET_DATA
        sta p
        lda #>NET_DATA
        sta p+1
        lda #<UFP_DIRECTORY
        sta q
        lda #>UFP_DIRECTORY
        sta q+1
        ldy #0
path_byte:
        lda (p),y
        beq path_invalid
        sta last_path
        sta (q),y
        jsr advance
        bne path_byte
        lda last_path
        cmp #$2f
        bne path_invalid
        lda #0
        sta (q),y
        clc
path_return:
        rts
path_invalid:
        lda #UFS_PROTOCOL
path_fail:
        sec
        rts

refresh:
        lda #0
        sta error
        sta count
        sta more
        sta seen
        sta seen+1
        sta page_start
        sta page_start+1
        sta selected
        sta detailoff
        sta detailoff+1
        jsr cache_reset
        jsr get_path
        bcs refresh_error
        lda #$13
        jsr command
        bcs refresh_error
        cmp #1
        beq scan_done
        cmp #0
        bne refresh_error
        lda #$14
        sta request+1
        jsr request_pointer
        lda #2
        sta r1L
        lda #0
        sta r1H
        lda #<receive
        sta r3L
        lda #>receive
        sta r3H
        jsr NET_STREAM
        bcc scan_status
        cmp #$fd
        bne refresh_error
        lda error
        bne refresh_error
        lda more
        bne scan_done
scan_status:
        cmp #0
        beq scan_done
refresh_error:
        sta error
        jsr capture_error
        lda #0
        sta count
        sta more
scan_done:
        lda backwards
        beq scan_return
        lda page_start
        sta base
        lda page_start+1
        sta base+1
        lda #0
        sta backwards
scan_return:
        rts
capture_error:
        cmp #$e0
        bcc capture_status
        cmp #$fc
        bcs capture_status
        lda #0
        sta error_status
        rts
capture_status:
        ldx #31
capture_status_byte:
        lda NET_STAT,x
        sta error_status,x
        dex
        bpl capture_status_byte
        rts
cache_reset:
        lda #0
        sta count
        sta free
        lda #$76
        sta free+1
        rts

; Pages contain up to eight *complete* variable-length records. Previous
; rescans page boundaries from zero, so it needs no finite history stack.
receive:
        jsr KEYIN
        cmp #$1b
        bne receive_data
        lda #UFP_CANCELLED
        beq *+5
        jmp receive_error
receive_data:
        lda NET_LEN
        ora NET_LEN+1
        bne *+5
        jmp receive_ok
        lda NET_PACKET_TRUNC
        beq *+5
        jmp receive_invalid
        lda NET_LEN+1
        bne receive_name
        lda NET_LEN
        cmp #2
        bcs *+5
        jmp receive_invalid
receive_name:
        lda #<NET_DATA+1
        sta p
        lda #>NET_DATA+1
        sta p+1
        sec
        lda NET_LEN
        sbc #1
        sta n
        lda NET_LEN+1
        sbc #0
        sta n+1
        ldy #0
validate_name:
        lda (p),y
        bne *+5
        jmp receive_invalid
        cmp #$2f
        beq receive_invalid
        cmp #$5c
        beq receive_invalid
        inc p
        bne validate_next
        inc p+1
validate_next:
        jsr decrement
        bne validate_name
        lda seen+1
        cmp base+1
        bne receive_compare
        lda seen
        cmp base
receive_compare:
        ldx backwards
        bne receive_previous
        bcc receive_skip
        bcs receive_room
receive_previous:
        bcs receive_full
receive_room:
        clc
        lda free
        adc NET_LEN
        sta end
        lda free+1
        adc NET_LEN+1
        sta end+1
        clc
        lda end
        adc #2
        sta end
        bcc room_compare
        inc end+1
room_compare:
        lda end+1
        cmp #$80
        bcc room_count
        bne receive_full_page
        lda end
        bne receive_full_page
room_count:
        lda count
        cmp #8
        bcc receive_save
receive_full_page:
        lda backwards
        beq receive_full
        jsr cache_reset
        lda seen
        sta page_start
        lda seen+1
        sta page_start+1
        jmp receive_room
receive_full:
        lda #1
        sta more
        sec
        rts
receive_invalid:
        lda #UFS_PROTOCOL
receive_error:
        sta error
        sec
        rts
receive_ok:
        clc
        rts
receive_skip:
        inc seen
        bne receive_ok
        inc seen+1
        bne receive_ok
        lda #UFS_RANGE
        bne receive_error
receive_save:
        ldx count
        lda NET_DATA
        sta attrs,x
        lda free
        sta q
        clc
        adc #2
        sta ptrsL,x
        lda free+1
        sta q+1
        adc #0
        sta ptrsH,x
        lda end
        sta free
        lda end+1
        sta free+1
        sec
        lda NET_LEN
        sbc #1
        sta lensL,x
        sta n
        lda NET_LEN+1
        sbc #0
        sta lensH,x
        sta n+1
        ldy #0
        lda UFP_CONTEXT
        sta (q),y
        iny
        lda #$11
        sta (q),y
        lda ptrsL,x
        sta q
        lda ptrsH,x
        sta q+1
        lda #<NET_DATA+1
        sta p
        lda #>NET_DATA+1
        sta p+1
        jsr copy_bytes
        lda #0
        sta (q),y
        inc count
        jmp receive_skip

selected_source:
        ldx selected
row_source:
        lda ptrsL,x
        sta p
        lda ptrsH,x
        sta p+1
        lda lensL,x
        sta n
        lda lensH,x
        sta n+1
        rts
detail_source:
        lda viewpath
        beq detail_name
        lda #<UFP_DIRECTORY
        sta p
        lda #>UFP_DIRECTORY
        sta p+1
path_count:
        lda pathlen
        sta n
        lda pathlen+1
        sta n+1
        rts
detail_name:
        lda count
        bne selected_source
        lda #0
        sta n
        sta n+1
        rts
copy_bytes:
        ldy #0
        lda n
        ora n+1
        beq copy_done
copy_byte:
        lda (p),y
        sta (q),y
        jsr advance
        bne copy_byte
copy_done:
        rts
advance:
        inc p
        bne advance_dest
        inc p+1
advance_dest:
        inc q
        bne decrement
        inc q+1
decrement:
        lda n
        bne decrement_low
        dec n+1
decrement_low:
        dec n
        lda n
        ora n+1
        rts

paint:
        lda #<title_open
        ldx #>title_open
        ldy UFP_MODE
        cpy #7
        bne paint_title
        lda #<title_save
        ldx #>title_save
paint_title:
        sta r9L
        stx r9H
        lda #0
        jsr mt_text
        lda #0
        sta row
paint_row:
        lda #0
        sta mt_line
        ldx row
        cpx count
        bcs paint_row_draw
        jsr row_source
        lda #$20
        cpx selected
        bne paint_row_mark
        lda #$3e
paint_row_mark:
        sta mt_line
        lda #$20
        ldy attrs,x
        tya
        and #$18
        beq paint_file
        lda #$2f
        bne paint_type
paint_file:
        lda #$20
paint_type:
        sta mt_line+1
        ldx #2
        jsr slice
paint_row_draw:
        lda row
        clc
        adc #2
        jsr mt_draw
        inc row
        lda row
        cmp #8
        bne paint_row
        jsr paint_detail
        lda #<hint
        sta r9L
        lda #>hint
        sta r9H
        lda #15
        jsr mt_text
        lda #<buttons
        sta r9L
        lda #>buttons
        sta r9H
        lda #16
        jsr mt_text
        lda #<ok_text
        sta r9L
        lda #>ok_text
        sta r9H
        lda #1
        jsr mt_text
        lda error
        beq paint_more
        lda #<error_text
        sta r9L
        lda #>error_text
        sta r9H
        lda #1
        jsr mt_text
        lda error
        lsr
        lsr
        lsr
        lsr
        tax
        lda digits,x
        sta mt_line+6
        lda error
        and #15
        tax
        lda digits,x
        sta mt_line+7
        ldy #10
        ldx #0
paint_error_status:
        lda error_status,x
        beq paint_error_end
        jsr mt_ascii
        sta mt_line,y
        iny
        inx
        cpy #36
        bne paint_error_status
paint_error_end:
        lda #0
        sta mt_line,y
        lda #1
        jsr mt_draw
paint_more:
        lda editing
        bne paint_leaf
        lda #0
        sta mt_line
        lda #13
        jsr mt_draw
        lda #<browse_text
        sta r9L
        lda #>browse_text
        sta r9H
        lda #14
        jmp mt_text
paint_detail:
        jsr detail_source
        lda n
        ora n+1
        beq detail_empty
        clc
        lda p
        adc detailoff
        sta p
        lda p+1
        adc detailoff+1
        sta p+1
        sec
        lda n
        sbc detailoff
        sta n
        lda n+1
        sbc detailoff+1
        sta n+1
detail_empty:
        lda #0
        sta row
detail_row:
        ldx #0
        jsr slice
        lda row
        clc
        adc #10
        jsr mt_draw
        inc row
        lda row
        cmp #3
        bne detail_row
        rts
paint_leaf:
        lda cursor
        ldx #0
leaf_scroll:
        cmp #32
        bcc leaf_scrolled
        sbc #32
        inx
        bne leaf_scroll
leaf_scrolled:
        sta caret
        txa
        asl
        asl
        asl
        asl
        asl
        clc
        adc #<UFP_LEAF
        sta p
        lda #>UFP_LEAF
        adc #0
        sta p+1
        lda leaflen
        sec
        sbc p
        sta n
        lda #0
        sta n+1
        ldx #0
        jsr slice
        lda #13
        jsr mt_draw
        lda #$20
        ldx #35
caret_clear:
        sta mt_line,x
        dex
        bpl caret_clear
        lda #0
        sta mt_line+36
        ldx caret
        lda #$5e
        sta mt_line,x
        lda #14
        jmp mt_draw
slice:
        ldy #0
slice_byte:
        lda n
        ora n+1
        beq slice_done
        lda (p),y
        jsr mt_ascii
        sta mt_line,x
        inc p
        bne slice_next
        inc p+1
slice_next:
        jsr decrement
        inx
        cpx #36
        bne slice_byte
slice_done:
        lda #0
        sta mt_line,x
        rts

mouse:
        lda $d010
        and #1
        sta t+1
        lda $d000
        sec
        sbc #24
        sta t
        lda t+1
        sbc #0
        sta t+1
        beq mouse_low
        cmp #1
        bne mouse_none
        lda t
        cmp #48
        bcs mouse_none
        bcc mouse_y
mouse_low:
        lda t
        cmp #16
        bcc mouse_none
mouse_y:
        lda $d001
        sec
        sbc #50
        cmp #176
        bcs mouse_buttons
        cmp #36
        bcc mouse_none
        sec
        sbc #36
        ldx #0
mouse_row:
        cmp #10
        bcc mouse_select
        sbc #10
        inx
        cpx #8
        bcc mouse_row
mouse_none:
        lda #0
        rts
mouse_select:
        cpx count
        bcs mouse_none
        stx selected
        lda #0
        sta detailoff
        sta detailoff+1
        jsr paint
        lda #0
        rts
mouse_buttons:
        cmp #186
        bcs mouse_none
        lda t+1
        bne mouse_cancel
        lda t
        cmp #72
        bcc mouse_open
        ldx editing
        bne mouse_edit_buttons
        cmp #128
        bcc mouse_use
        cmp #192
        bcc mouse_next
mouse_cancel:
        lda #$1b
        rts
mouse_edit_buttons:
        cmp #192
        bcs mouse_cancel
        bcc mouse_none
mouse_open:
        lda #13
        rts
mouse_use:
        lda #$85
        rts
mouse_next:
        lda #$4e
        rts

.include "modal-text.inc"
title_open: .text "Open file",0
title_save: .text "Save As - create a new file",0
ok_text: .text "Select a file or folder",0
error_text: .text "Error 00: ",0
browse_text: .text "Arrows select  Enter open  F1 name",0
hint: .text "U up / root N next B back P path",0
buttons: .text "Open   Name    Next    Cancel",0
digits: .text "0123456789ABCDEF"
request: .fill 4,0
pathlen: .word 0
last_path: .byte 0
chosenlen: .word 0
base: .word 0
seen: .word 0
page_start: .word 0
free: .word 0
end: .word 0
backwards: .byte 0
count: .byte 0
more: .byte 0
selected: .byte 0
editing: .byte 0
ready: .byte 0
held: .byte 0
error: .byte 0
saved_error: .byte 0
error_status: .fill 32,0
saved_status: .fill 32,0
viewpath: .byte 0
detailoff: .word 0
leaflen: .byte 0
cursor: .byte 0
caret: .byte 0
row: .byte 0
attrs: .fill 8,0
ptrsL: .fill 8,0
ptrsH: .fill 8,0
lensL: .fill 8,0
lensH: .fill 8,0
picker_end:
        .cerror * > UFP_LEAF, "file selector overlaps filename buffer"
