; Ultimate filesystem browser. DOS target 2 owns this app's working directory;
; target 1 remains available to the shell/network services. Directory packets
; are cached as eight complete names, never as truncated command operands.
.include "equates.inc"
.include "routines.inc"
.include "macros.inc"
.include "kernal.inc"

ROWS = 8
CACHE = $6000                   ; eight 512-byte filename slots, through $6fff
PATHBUF = $7000                 ; 512 bytes, below the saved settings at $7350
REQUEST = $7400                 ; transient command, at most 513 bytes here
sptr = $60
dptr = $62
remain = $64
number = $66
mx = $68
my = $6a

* = APP_START
        #RegisterApp
        lda $ba
        sta sysdev
        lda #$00
        sta base
        sta base+1
        sta selected
        sta held
        sta viewpath
        sta nameoff
        sta nameoff+1
        sta PATHBUF
        sta pathlen
        sta pathlen+1
        sta ready
        jsr refresh
        jsr paint

input_loop:
        lda #$01
        sta ready
        jsr OS_TICK
        jsr KEYIN
        bne key_event
        jsr READ_BUTTON
        bne released
        lda #$01
        sta held
        jmp input_loop
released:
        lda held
        beq input_loop
        lda #$00
        sta held
        jsr mouse_action
        beq input_loop
key_event:
        sta key
        lda #$00
        sta ready
        lda key
        cmp #$c1
        bcc key_ascii
        cmp #$db
        bcs key_ascii
        and #$7f               ; shifted PETSCII letters use the same shortcuts
key_ascii:
        cmp #$61
        bcc normalized
        cmp #$7b
        bcs normalized
        and #$df
normalized:
        ldx #key_count-1
key_find:
        cmp keys,x
        beq key_found
        dex
        bpl key_find
        jmp input_loop
key_found:
        lda actionsL,x
        sta dispatch+1
        lda actionsH,x
        sta dispatch+2
dispatch:
        jsr $ffff
        jsr paint
        jmp input_loop

keys:   .byte $11,$91,$0d,$1b,$55,$2f,$4e,$42,$52,$9d,$1d,$50
key_count = *-keys
actionsL: .byte <down,<up,<open_entry,<leave,<parent,<root,<nextpage,<prevpage,<refresh,<left,<right,<toggle_path
actionsH: .byte >down,>up,>open_entry,>leave,>parent,>root,>nextpage,>prevpage,>refresh,>left,>right,>toggle_path

leave:
        lda #$ff
        sta ready
        lda sysdev
        sta $ba
        #UnregisterApp
        jmp DESK_START
down:
        lda count
        beq action_done
        lda selected
        clc
        adc #1
        cmp count
        bcs nextpage
        sta selected
        jmp reset_view
up:
        lda selected
        beq up_page
        dec selected
        jmp reset_view
up_page:
        lda base
        ora base+1
        beq action_done
        jsr prevpage
        lda count
        beq action_done
        sec
        sbc #1
        sta selected
        rts
nextpage:
        lda more
        beq action_done
        clc
        lda base
        adc #ROWS
        sta base
        bcc page_changed
        inc base+1
        bne page_changed
        lda #$f8                ; do not wrap directory ordinals to zero
        sta base
        dec base+1
        rts
prevpage:
        lda base
        ora base+1
        beq action_done
        sec
        lda base
        sbc #ROWS
        sta base
        bcs page_changed
        dec base+1
page_changed:
        lda #$00
        sta selected
        jmp refresh
action_done:
        rts
reset_view:
        lda #$00
        sta nameoff
        sta nameoff+1
        sta viewpath
        rts
toggle_path:
        lda viewpath
        eor #1
        sta viewpath
        lda #$00
        sta nameoff
        sta nameoff+1
        rts
left:
        lda nameoff
        ora nameoff+1
        beq action_done
        sec
        lda nameoff
        sbc #32
        sta nameoff
        bcs action_done
        dec nameoff+1
        rts
right:
        jsr detail_source
        clc
        lda nameoff
        adc #32
        sta number
        lda nameoff+1
        adc #0
        sta number+1
        cmp remain+1
        bcc right_go
        bne action_done
        lda number
        cmp remain
        bcs action_done
right_go:
        lda number
        sta nameoff
        lda number+1
        sta nameoff+1
        rts

root:
        lda #$2f
        sta REQUEST+2
        lda #3
        bne chdir_short
parent:
        lda #$2e
        sta REQUEST+2
        sta REQUEST+3
        lda #4
chdir_short:
        sta r1L
        lda #0
        sta r1H
        jmp chdir
open_entry:
        lda count
        beq action_done
        jsr selected_source
        lda #<REQUEST+2
        sta dptr
        lda #>REQUEST+2
        sta dptr+1
        lda remain
        clc
        adc #2
        sta commandlen
        lda remain+1
        adc #0
        sta commandlen+1
        jsr copy_bytes
        lda commandlen
        sta r1L
        lda commandlen+1
        sta r1H
chdir:
        lda #$11
        sta REQUEST+1
        jsr command_stream
        bcs command_error
        cmp #0
        bne firmware_error
        lda #0
        sta base
        sta base+1
        sta selected
        jmp refresh

; Two-byte status/short-data commands use the legacy bounded collector.
command:
        sta REQUEST+1
        lda #2
        sta REQUEST
        lda #0
        sta NET_DIRMODE
        lda #<REQUEST
        sta r0L
        lda #>REQUEST
        sta r0H
        lda #2
        jmp NET_CMD
command_stream:
        lda #0
        sta r3L
        sta r3H
stream:
        lda #2
        sta REQUEST
        lda #<REQUEST
        sta r0L
        lda #>REQUEST
        sta r0H
        jmp NET_STREAM
command_error:
        bcc firmware_error
        lda #<transport_error
        ldx #>transport_error
        jmp set_status
firmware_error:
        lda #<NET_STAT
        sta sptr
        lda #>NET_STAT
        sta sptr+1
        lda #31
        sta remain
        lda #0
        sta remain+1
        ldx #31
        jsr text_chunk
        ldx #31
error_copy:
        lda line,x
        sta status,x
        dex
        bpl error_copy
        rts

refresh:
        jsr reset_view
        lda #0
        sta count
        sta more
        sta scanerror
        sta seen
        sta seen+1
        lda #$12
        jsr command
        bcs command_error
        cmp #0
        bne firmware_error
        lda NET_TRUNC
        beq path_fits
        jmp invalid_reply
path_fits:
        lda NET_LEN
        sta pathlen
        sta remain
        lda NET_LEN+1
        sta pathlen+1
        sta remain+1
        lda #<NET_DATA
        sta sptr
        lda #>NET_DATA
        sta sptr+1
        lda #<PATHBUF
        sta dptr
        lda #>PATHBUF
        sta dptr+1
        jsr copy_bytes
        lda #0
        tay
        sta (dptr),y
        lda #$13
        jsr command
        bcc directory_status
        jmp command_error
directory_status:
        cmp #1
        bne directory_nonempty
        jmp empty
directory_nonempty:
        cmp #0
        beq directory_start
        jmp firmware_error
directory_start:
        lda #$14
        sta REQUEST+1
        lda #2
        sta r1L
        lda #0
        sta r1H
        lda #<receive
        sta r3L
        lda #>receive
        sta r3H
        jsr stream
        bcc scan_finished
        cmp #$fd
        bne scan_failed
        lda scanerror
        bne scan_failed
        lda more
        bne listed
scan_failed:
        lda #0
        sta count
        sta more
        lda scanerror
        cmp #2
        bne scan_not_cancelled
        jmp cancelled
scan_not_cancelled:
        cmp #1
        bne scan_transport
        jmp invalid_reply
scan_transport:
        sec
        jmp command_error
scan_finished:
        cmp #0
        bne scan_firmware
listed:
        lda count
        beq empty
        lda selected
        cmp count
        bcc listing_status
        lda #0
        sta selected
listing_status:
        ldx #5
item_prefix:
        lda items_text,x
        sta status,x
        dex
        bpl item_prefix
        lda #6
        sta statuspos
        clc
        lda base
        adc #1
        sta number
        lda base+1
        adc #0
        sta number+1
        jsr decimal_word
        ldx statuspos
        lda #$2d
        sta status,x
        inc statuspos
        clc
        lda base
        adc count
        sta number
        lda base+1
        adc #0
        sta number+1
        jsr decimal_word
        ldx statuspos
        lda #$20
        sta status,x
        inx
        lda #$2e
        ldy more
        beq item_suffix
        lda #$2b
item_suffix:
        sta status,x
        inx
        lda #0
        sta status,x
        rts
scan_firmware:
        pha
        lda #0
        sta count
        pla
        clc
        jmp command_error
empty:
        lda #<empty_text
        ldx #>empty_text
        jmp set_status
cancelled:
        lda #<cancel_text
        ldx #>cancel_text
        jmp set_status
invalid_reply:
        lda #<invalid_text
        ldx #>invalid_text
set_status:
        sta sptr
        stx sptr+1
        ldy #0
status_copy:
        lda (sptr),y
        sta status,y
        beq status_done
        iny
        cpy #33
        bne status_copy
        lda #0
        sta status,y
status_done:
        rts

decimal_word:
        lda #0
        sta started
        ldy #0
decimal_digit:
        ldx #0
decimal_sub:
        lda number+1
        cmp divisors+1,y
        bcc decimal_emit
        bne decimal_take
        lda number
        cmp divisors,y
        bcc decimal_emit
decimal_take:
        sec
        lda number
        sbc divisors,y
        sta number
        lda number+1
        sbc divisors+1,y
        sta number+1
        inx
        bne decimal_sub
decimal_emit:
        txa
        ora started
        bne decimal_write
        cpy #8
        bne decimal_next
decimal_write:
        txa
        ora #$30
        ldx statuspos
        sta status,x
        inc statuspos
        inc started
decimal_next:
        iny
        iny
        cpy #10
        bne decimal_digit
        rts
divisors: .word 10000,1000,100,10,1

; One packet per entry. Skip using a 16-bit ordinal, retain eight names,
; then cancel on the ninth entry so a huge directory need not finish.
receive:
        jsr KEYIN
        cmp #$1b
        bne receive_data
        lda #2
        bne receive_bad
receive_data:
        lda NET_LEN
        ora NET_LEN+1
        beq receive_ok           ; status-only packet
        lda NET_PACKET_TRUNC
        bne receive_invalid
        lda NET_LEN+1
        bne receive_name
        lda NET_LEN
        cmp #2
        bcc receive_invalid
receive_name:
        lda #<NET_DATA+1
        sta sptr
        lda #>NET_DATA+1
        sta sptr+1
        sec
        lda NET_LEN
        sbc #1
        sta remain
        lda NET_LEN+1
        sbc #0
        sta remain+1
        ; Validate the entire component before accepting or skipping it.
        ldy #0
validate_name:
        lda (sptr),y
        beq receive_invalid
        cmp #$2f
        beq receive_invalid
        jsr advance_source
        lda remain
        ora remain+1
        bne validate_name
        lda seen+1
        cmp base+1
        bcc receive_skip
        bne receive_save
        lda seen
        cmp base
        bcs receive_save
receive_skip:
        inc seen
        bne receive_ok
        inc seen+1
receive_ok:
        clc
        rts
receive_invalid:
        lda #1
receive_bad:
        sta scanerror
        sec
        rts
receive_save:
        ldx count
        cpx #ROWS
        bcc receive_slot
        lda #1
        sta more
        sec
        rts
receive_slot:
        lda NET_DATA
        sta attrs,x
        sec
        lda NET_LEN
        sbc #1
        sta lengthsL,x
        sta remain
        lda NET_LEN+1
        sbc #0
        sta lengthsH,x
        sta remain+1
        txa
        asl
        clc
        adc #>CACHE
        sta dptr+1
        lda #0
        sta dptr
        lda #<NET_DATA+1
        sta sptr
        lda #>NET_DATA+1
        sta sptr+1
        jsr copy_bytes
        lda #0
        tay
        sta (dptr),y
        inc count
        clc
        rts

copy_bytes:
        lda remain
        ora remain+1
        beq copy_done
        ldy #0
copy_loop:
        lda (sptr),y
        sta (dptr),y
        inc dptr
        bne copy_advance
        inc dptr+1
copy_advance:
        jsr advance_source
        lda remain
        ora remain+1
        bne copy_loop
copy_done:
        rts
advance_source:
        inc sptr
        bne source_count
        inc sptr+1
source_count:
        lda remain
        bne source_low
        dec remain+1
source_low:
        dec remain
        rts

selected_source:
        ldx selected
row_source:
        lda lengthsL,x
        sta remain
        lda lengthsH,x
        sta remain+1
        txa
        asl
        clc
        adc #>CACHE
        sta sptr+1
        lda #0
        sta sptr
        rts
detail_source:
        lda viewpath
        bne path_source
        lda count
        bne selected_source
        sta remain
        sta remain+1
        rts
path_source:
        lda #<PATHBUF
        sta sptr
        lda #>PATHBUF
        sta sptr+1
        lda pathlen
        sta remain
        lda pathlen+1
        sta remain+1
        rts

; Convert a bounded raw substring to display text. Raw bytes in CACHE and
; PATHBUF remain untouched, including high bytes used by the filesystem.
text_chunk:
        stx width
        ldx #0
        ldy #0
chunk_loop:
        lda remain
        ora remain+1
        beq chunk_done
        lda (sptr),y
        beq chunk_done
        jsr ascii_text
        sta line,x
        jsr advance_source
        inx
        cpx width
        bne chunk_loop
chunk_done:
        lda #0
        sta line,x
        rts
ascii_text:
        cmp #$20
        bcc ascii_dot
        cmp #$7f
        bcs ascii_dot
        cmp #$61
        bcc ascii_upper
        cmp #$7b
        bcs ascii_done
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

paint:
        #ClrRect 16,8,288,180
        #DrawRect 16,8,288,180,1
        #PenWrite
        #Text 24,14,title
        lda #2
clear_vdc:
        pha
        jsr VDCLR
        pla
        clc
        adc #1
        cmp #24
        bne clear_vdc
        lda #<title
        sta r9L
        lda #>title
        sta r9H
        lda #2
        ldx #0
        jsr VDTEXT
        jsr path_source
        ldx #76
        jsr text_chunk
        lda #3
        ldx #0
        jsr vdc_line
        lda #0
        sta line+34
        lda #26
        jsr vic_line
        lda #0
        sta row
paint_rows:
        ldx row
        cpx count
        bcc paint_row
        jmp paint_details
paint_row:
        jsr row_source
        ldx #74
        jsr text_chunk
        lda remain
        ora remain+1
        beq row_vdc_fits
        lda #$3e
        sta line+73
row_vdc_fits:
        ; marker and kind prefix at columns 0/1; raw name starts at col 3.
        lda #<line
        sta r9L
        lda #>line
        sta r9H
        lda row
        clc
        adc #4
        ldx #3
        jsr VDTEXT
        ldx row
        lda lengthsH,x
        bne row_vic_long
        lda lengthsL,x
        cmp #32
        bcc row_vic_fits
row_vic_long:
        lda #$3e
        sta line+30
row_vic_fits:
        lda #0
        sta line+31
        lda row
        asl
        sta draw_y
        asl
        clc
        adc draw_y
        asl
        clc
        adc #40
        sta draw_y
        lda #38
        sta X1
        lda #0
        sta X1+1
        lda draw_y
        sta Y1
        jsr line_pointer
        jsr GPUTS
        lda #$20
        sta prefix
        lda row
        cmp selected
        bne prefix_kind
        lda #$3e
        sta prefix
prefix_kind:
        ldx row
        lda attrs,x
        and #$10
        beq prefix_file
        lda #$2f
        bne prefix_save
prefix_file:
        lda #$20
prefix_save:
        sta prefix+1
        lda #<prefix
        sta r9L
        lda #>prefix
        sta r9H
        lda #22
        sta X1
        lda #0
        sta X1+1
        lda draw_y
        sta Y1
        jsr GPUTS
        lda #<prefix
        sta r9L
        lda #>prefix
        sta r9H
        lda row
        clc
        adc #4
        ldx #0
        jsr VDTEXT
        inc row
        jmp paint_rows
paint_details:
        lda #<name_label
        ldx #>name_label
        ldy viewpath
        beq detail_label
        lda #<path_label
        ldx #>path_label
detail_label:
        sta r9L
        stx r9H
        lda #13
        ldx #0
        jsr VDTEXT
        jsr detail_source
        clc
        lda sptr
        adc nameoff
        sta sptr
        lda sptr+1
        adc nameoff+1
        sta sptr+1
        sec
        lda remain
        sbc nameoff
        sta remain
        lda remain+1
        sbc nameoff+1
        sta remain+1
        lda #0
        sta row
details_loop:
        ; Use 34-byte chunks on both displays so left/right has the same
        ; meaning. Three VIC lines and seven VDC lines reveal long names.
        ldx #34
        jsr text_chunk
        lda row
        cmp #3
        bcs details_vdc
        asl
        sta draw_y
        asl
        asl
        clc
        adc draw_y
        adc #134
        jsr vic_line
details_vdc:
        lda row
        clc
        adc #14
        ldx #0
        jsr vdc_line
        inc row
        lda row
        cmp #7
        bne details_loop
        lda #<status
        sta r9L
        lda #>status
        sta r9H
        #Text 24,164,status
        lda #<status
        sta r9L
        lda #>status
        sta r9H
        lda #22
        ldx #0
        jsr VDTEXT
        lda #<help
        sta r9L
        lda #>help
        sta r9H
        lda #23
        ldx #0
        jsr VDTEXT
        lda #0
        sta row
toolbar:
        ldx row
        lda buttonL,x
        sta r9L
        lda buttonH,x
        sta r9H
        ; x = 18 + row*36, calculated as a word for the last two buttons.
        txa
        asl
        asl
        sta draw_x
        lda #0
        sta X1+1
        lda draw_x
        asl
        asl
        asl
        rol X1+1
        clc
        adc draw_x
        sta X1
        lda X1+1
        adc #0
        sta X1+1
        clc
        lda X1
        adc #18
        sta X1
        bcc toolbar_y
        inc X1+1
toolbar_y:
        lda #176
        sta Y1
        jsr GPUTS
        inc row
        lda row
        cmp #8
        bne toolbar
        rts
line_pointer:
        lda #<line
        sta r9L
        lda #>line
        sta r9H
        rts
vic_line:
        sta Y1
        lda #24
        sta X1
        lda #0
        sta X1+1
        jsr line_pointer
        jmp GPUTS
vdc_line:
        pha
        jsr line_pointer
        pla
        jmp VDTEXT

; Release-edge mouse actions. Convert the full nine-bit VIC coordinate;
; subtraction must propagate its borrow across the X high bit.
mouse_action:
        php
        sei
        lda $d010
        and #1
        sta mx+1
        sec
        lda $d000
        sbc #24
        sta mx
        lda mx+1
        sbc #0
        sta mx+1
        lda $d001
        sec
        sbc #50
        sta my
        plp
        lda mx+1
        beq mouse_left
        cmp #1
        bne mouse_none
        lda mx
        cmp #48
        bcs mouse_none
        bcc mouse_y
mouse_left:
        lda mx
        cmp #16
        bcc mouse_none
mouse_y:
        lda my
        cmp #26
        bcc mouse_none
        cmp #35
        bcc mouse_path
        cmp #40
        bcc mouse_none
        cmp #136
        bcc mouse_row
        cmp #174
        bcc mouse_none
        cmp #186
        bcs mouse_none
        sec
        lda mx
        sbc #16
        sta mx
        lda mx+1
        sbc #0
        sta mx+1
        ldx #0
mouse_button:
        lda mx+1
        bne mouse_sub
        lda mx
        cmp #36
        bcc mouse_key
mouse_sub:
        sec
        lda mx
        sbc #36
        sta mx
        lda mx+1
        sbc #0
        sta mx+1
        inx
        bne mouse_button
mouse_key:
        lda buttonkeys,x
        rts
mouse_path:
        lda #$50
        rts
mouse_row:
        sec
        sbc #40
        ldx #0
mouse_row_div:
        cmp #12
        bcc mouse_select
        sbc #12
        inx
        bne mouse_row_div
mouse_select:
        cpx count
        bcs mouse_none
        lda #0
        sta ready
        stx selected
        jsr reset_view
        jsr paint
mouse_none:
        lda #0
        rts

title: .text "Ultimate files",0
help: .text "up/dn select  enter open  U parent  / root  N/B page  R retry  P path  ESC exit",0
items_text: .text "items "
name_label: .text "selected name (< > scroll)",0
path_label: .text "current path (< > scroll)",0
empty_text: .text "empty directory; U=parent / root",0
transport_error: .text "Ultimate unavailable; R=retry",0
invalid_text: .text "invalid or clipped reply; R=retry",0
cancel_text: .text "cancelled; R=retry ESC=desktop",0
btn_left: .text "<",0
btn_right: .text ">",0
btn_open: .text "open",0
btn_up: .text "up",0
btn_root: .text "root",0
btn_prev: .text "prev",0
btn_next: .text "next",0
btn_exit: .text "exit",0
buttonL: .byte <btn_left,<btn_right,<btn_open,<btn_up,<btn_root,<btn_prev,<btn_next,<btn_exit
buttonH: .byte >btn_left,>btn_right,>btn_open,>btn_up,>btn_root,>btn_prev,>btn_next,>btn_exit
buttonkeys: .byte $9d,$1d,$0d,$55,$2f,$42,$4e,$1b
base: .word 0
seen: .word 0
pathlen: .word 0
nameoff: .word 0
commandlen: .word 0
selected: .byte 0
count: .byte 0
more: .byte 0
scanerror: .byte 0
sysdev: .byte 0
ready: .byte 0
held: .byte 0
viewpath: .byte 0
key: .byte 0
width: .byte 0
row: .byte 0
draw_y: .byte 0
draw_x: .byte 0
statuspos: .byte 0
started: .byte 0
attrs: .fill ROWS,0
lengthsL: .fill ROWS,0
lengthsH: .fill ROWS,0
prefix: .byte 0,0,0
status: .fill 34,0
line: .fill 77,0
browser_end:
        .cerror * > CACHE, "browser code overlaps filename cache"
