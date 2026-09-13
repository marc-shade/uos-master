; Resident Ultimate binary file service. GPL v3, see uos.asm.
; This deliberately exposes read and exclusive creation, not overwrite,
; delete or rename: the firmware's FAT file locks are disabled. It never
; closes a foreign file or silently replays an uncertain write. A successful
; selector lease is restored when its service-owned file closes.
.include "equates.inc"
.include "routines.inc"
.include "ultimate-files.inc"
.include "file-dialog.inc"

* = UFS_OPEN
        jmp open_file
        jmp close_file
        jmp read_file
        jmp write_file
        jmp seek_file
        jmp tell_file
        jmp close_all
        .byte 1
result: .byte 0
count:  .word 0
size:   .fill 4, 0
pos:    .fill 4, 0
eof:    .byte 0
modes:  .byte 0, 0
status: .fill 32, 0
        .cerror result != UFS_RESULT || count != UFS_COUNT || size != UFS_SIZE, "file result ABI"
        .cerror pos != UFS_POS || eof != UFS_EOF || modes != UFS_MODE || status != UFS_STATUS, "file state ABI"

; Acquire a DOS context without touching the caller's argument registers.
; The packet callback below is private and uses only public ZP scratch.
begin:
        pha
        cpx #1
        bcc begin_arg
        cpx #3
        bcs begin_arg
        lda busy
        bne begin_busy
        stx target
        dex
        stx index
        txa
        asl
        asl
        sta slot
        lda #1
        sta busy
        lda #0
        sta result
        sta count
        sta count+1
        sta eof
        sta status
        sta packet_error
        sta NET_DIRMODE
        pla
        clc
        rts
begin_arg:
        pla
        lda #UFS_BADARG
        sec
        rts
begin_busy:
        pla
        lda #UFS_BUSY
        sec
        rts

owned:
        ldx index
        lda modes,x
        beq no_file
        cmp #$ff
        beq uncertain
        clc
        rts
no_file:
        lda #UFS_NOTOPEN
        sec
        rts
uncertain:
        lda #UFS_UNCERTAIN
        sec
        rts

ok:
        lda #0
finish:
        sta result
        ldx slot
        ldy #0
finish_copy:
        lda sizes,x
        sta size,y
        lda positions,x
        sta pos,y
        inx
        iny
        cpy #4
        bne finish_copy
        lda #0
        sta busy
        lda result
        beq success
        sec
        rts
success:
        ldx #3
finish_eof:
        lda size,x
        cmp pos,x
        bne finish_not_eof
        dex
        bpl finish_eof
        inc eof
finish_not_eof:
        lda #0
        clc
        rts
quarantine:
        pha
        ldx index
        lda #$ff
        sta modes,x
        pla
        jmp finish

; Build OPEN from a caller-owned string in $5000..$7fff. The whole command
; fits the cartridge FIFO; the terminator is checked but is not transmitted.
open_file:
        jsr begin
        bcc open_begin
        rts
open_begin:
        cmp #1
        beq open_mode
        cmp #7
        beq open_mode
        lda #UFS_BADARG
        jmp finish
open_mode:
        sta wanted_mode
        ldx index
        lda modes,x
        beq open_name
        lda #UFS_BUSY
        jmp finish
open_name:
        lda pick_pending
        cmp #2
        bne open_directory_ok
        lda target
        cmp pick_context
        bne open_directory_ok
        lda #UFS_UNCERTAIN
        jmp finish
open_directory_ok:
        lda target
        sta UFS_COMMAND
        lda #2
        sta UFS_COMMAND+1
        lda wanted_mode
        sta UFS_COMMAND+2
        lda #<UFS_COMMAND+3
        sta r4L
        lda #>UFS_COMMAND+3
        sta r4H
        lda #3
        sta command_len
        lda #0
        sta command_len+1
        sta name_component
        ldy #0
name_byte:
        lda r0H
        cmp #$50
        bcc name_bad
        cmp #$80
        bcs name_bad
        lda (r0),y
        beq name_end
        pha
        lda command_len+1
        cmp #>896
        bne name_room
        lda command_len
        cmp #<896
        bcc name_room
        pla
name_bad:
        lda #UFS_BADARG
        jmp finish
name_room:
        pla
        ldx wanted_mode
        cpx #7
        bne name_store
        ; Firmware resolves each component through FileInfo(128). Creating a
        ; longer leaf can succeed but leave a file it cannot stat or delete.
        ; Keep the full transport bound for reads; constrain new paths before
        ; issuing any command, including both firmware path separators.
        cmp #$2f
        beq name_separator
        cmp #$5c
        beq name_separator
        inc name_component
        bpl name_store
        lda #UFS_BADARG
        jmp finish
name_separator:
        ldx #0
        stx name_component
name_store:
        sta (r4),y
        inc r4L
        bne name_dst
        inc r4H
name_dst:
        inc r0L
        bne name_src
        inc r0H
name_src:
        inc command_len
        bne name_byte
        inc command_len+1
        jmp name_byte
name_end:
        lda command_len+1
        bne open_probe
        lda command_len
        cmp #3
        beq name_bad
open_probe:
        ; Firmware OPEN overwrites its file pointer. FILE_INFO must explicitly
        ; report 85 (no file open) before claiming an unowned target. CLOSE's
        ; separate 84 (no file to close) is not a FILE_INFO success condition.
        lda #7
        jsr short_two
        bcs open_probe_error
        cmp #85
        beq open_issue
        cmp #0
        bne open_probe_error
        lda #UFS_BUSY
open_probe_error:
        jmp finish
open_issue:
        ldx index
        lda #$ff
        sta modes,x
        jsr send_full
        bcs open_failed
        cmp #0
        bne open_rejected
        ; Capture the file size. Metadata is needed to distinguish actual EOF
        ; from a short READ whose firmware forgot to send an error status.
        lda #7
        jsr short_two
        bcs open_failed
        cmp #0
        bne open_failed
        lda NET_LEN+1
        bne open_info
        lda NET_LEN
        cmp #12
        bcs open_info
        lda #UFS_PROTOCOL
        bne open_failed
open_info:
        lda NET_DATA+11
        and #$18                ; directory / volume records are not files
        beq open_regular
        lda #UFS_PROTOCOL
        bne open_failed
open_regular:
        ldx slot
        ldy #0
open_size:
        lda NET_DATA,y
        sta sizes,x
        lda #0
        sta positions,x
        inx
        iny
        cpy #4
        bne open_size
        ldx index
        lda wanted_mode
        sta modes,x
        jmp ok
open_rejected:
        ; A numeric firmware rejection means OPEN returned without a file.
        cmp #100
        bcs open_failed
        pha
        ldx index
        lda #0
        sta modes,x
        pla
open_failed:
        jmp finish             ; uncertain ownership remains available to CLOSE

close_file:
        jsr begin
        bcc close_begin
        rts
close_begin:
        ldx index
        lda modes,x
        bne close_issue
        jmp pick_close_finish  ; never close an unowned firmware handle
close_issue:
        lda #3
        jsr short_two
        bcs close_failed
        cmp #0
        beq close_done
        cmp #84
        beq close_done
close_failed:
        jmp quarantine
close_done:
        ldx index
        lda #0
        sta modes,x
        jmp pick_close_finish

tell_file:
        jsr begin
        bcc tell_begin
        rts
tell_begin:
        jsr owned
        bcs tell_error
        jmp ok
tell_error:
        jmp finish

; Validate a binary buffer without allowing destination writes into resident
; services or the persisted settings record. Read/write buffers obey the same
; ranges: $5000..$734f or $7359..$7fff, wholly within one range.
buffer:
        lda r1H
        cmp #2
        bcc buffer_small
        bne buffer_bad
        lda r1L
        bne buffer_bad
buffer_small:
        lda r1L
        ora r1H
        beq buffer_bad
        lda r0H
        cmp #$50
        bcc buffer_bad
        clc
        lda r0L
        adc r1L
        sta endptr
        lda r0H
        adc r1H
        sta endptr+1
        bcs buffer_bad
        cmp #$80
        bcc buffer_settings
        bne buffer_bad
        lda endptr
        bne buffer_bad
buffer_settings:
        lda r0H
        cmp #$73
        bcc buffer_before
        bne buffer_good
        lda r0L
        cmp #$59
        bcs buffer_good
buffer_before:
        lda endptr+1
        cmp #$73
        bcc buffer_good
        bne buffer_bad
        lda endptr
        cmp #$51
        bcs buffer_bad
buffer_good:
        lda r0L
        sta bufptr
        lda r0H
        sta bufptr+1
        lda r1L
        sta expected
        lda r1H
        sta expected+1
        clc
        rts
buffer_bad:
        lda #UFS_BADARG
        sec
        rts

read_file:
        jsr begin
        bcc read_begin
        rts
read_begin:
        jsr owned
        bcs read_argument
        jsr buffer
        bcs read_argument
        ; remaining = known size - tracked position, full 32-bit arithmetic.
        ldx slot
        ldy #0
        sec
read_remaining:
        lda sizes,x
        sbc positions,x
        sta offset,y
        php                     ; CPY must not replace the borrow between bytes
        inx
        iny
        cpy #4
        beq read_remaining_done
        plp
        jmp read_remaining
read_remaining_done:
        plp
        lda offset+2
        ora offset+3
        bne read_issue
        lda offset+1
        cmp expected+1
        bcc read_clip
        bne read_issue
        lda offset
        cmp expected
        bcs read_issue
read_clip:
        lda offset
        sta expected
        lda offset+1
        sta expected+1
        ora expected
        bne read_issue
        jmp ok                 ; EOF needs no zero-length firmware command
read_argument:
        jmp finish
read_issue:
        lda #0
        sta compare
        jsr read_block
        bcs read_failed
        jsr advance
        jmp ok
read_failed:
        jmp quarantine

write_file:
        jsr begin
        bcc write_begin
        rts
write_begin:
        jsr owned
        bcs write_argument
        cmp #7
        beq write_buffer
        lda #UFS_READONLY
        bne write_argument
write_buffer:
        jsr buffer
        bcs write_argument
        ; Reject 32-bit wrap before sending any data.
        ldx slot
        clc
        lda positions,x
        adc expected
        lda positions+1,x
        adc expected+1
        lda positions+2,x
        adc #0
        lda positions+3,x
        adc #0
        bcc write_copy
        lda #UFS_RANGE
write_argument:
        jmp finish
write_copy:
        lda #<UFS_COMMAND+4
        sta r4L
        lda #>UFS_COMMAND+4
        sta r4H
        lda expected
        sta r5L
        lda expected+1
        sta r5H
        ldy #0
write_byte:
        lda (r0),y
        sta (r4),y
        inc r0L
        bne write_src
        inc r0H
write_src:
        inc r4L
        bne write_dst
        inc r4H
write_dst:
        jsr decrement
        bne write_byte
        lda target
        sta UFS_COMMAND
        lda #5
        sta UFS_COMMAND+1
        lda #0
        sta UFS_COMMAND+2
        sta UFS_COMMAND+3
        clc
        lda expected
        adc #4
        sta command_len
        lda expected+1
        adc #0
        sta command_len+1
        lda expected+1
        cmp #2
        bne write_first
        dec command_len        ; 512-byte request: first send 511 bytes
write_first:
        jsr send_full
        bcc write_first_status
        jmp write_failed
write_first_status:
        cmp #0
        beq write_tail
        jmp write_failed
write_tail:
        lda expected+1
        cmp #2
        bne write_verify
        ; On the reference II+, a sector-sized WRITE lets FAT pass the
        ; command FIFO's I/O address straight to USB DMA, which saves wrong
        ; bytes. Sub-sector writes use FAT's RAM cache. Keep the original
        ; payload intact and send byte 512 in a separate five-byte command.
        lda #5
        sta short_command+1
        lda #0
        sta short_command+2
        sta short_command+3
        lda UFS_COMMAND+515
        sta short_command+4
        lda #5
        jsr send_short
        bcs write_failed
        cmp #0
        bne write_failed
write_verify:
        ; WRITE reports no transferred count, and FAT can return FR_OK after
        ; a short write. Seek back and compare every requested byte. The same
        ; newly-created handle has read permission; no overwrite mode is used.
        ldx slot
        ldy #0
write_seek:
        lda positions,x
        sta short_command+2,y
        inx
        iny
        cpy #4
        bne write_seek
        jsr seek_command
        bcs write_failed
        cmp #0
        bne write_failed
        lda #<UFS_COMMAND+4
        sta bufptr
        lda #>UFS_COMMAND+4
        sta bufptr+1
        lda #1
        sta compare
        jsr read_block
        bcs write_failed
        jsr advance
        ; The verified write may have extended this newly-created file.
        ldx slot
        inx
        inx
        inx
        ldy #4
write_extent:
        lda sizes,x
        cmp positions,x
        bcc write_grew
        bne write_done
        dex
        dey
        bne write_extent
write_done:
        jmp ok
write_grew:
        ldx slot
        ldy #4
write_size:
        lda positions,x
        sta sizes,x
        inx
        dey
        bne write_size
        jmp ok
write_failed:
        jmp quarantine

seek_file:
        jsr begin
        bcc seek_begin
        rts
seek_begin:
        jsr owned
        bcs seek_argument
        ldx slot
        inx
        inx
        inx
        ldy #3
seek_range:
        lda r0,y
        sta offset,y
        cmp sizes,x
        bcc seek_allowed
        bne seek_bad_range
        dex
        dey
        bpl seek_range
        bmi seek_allowed
seek_bad_range:
        lda #UFS_RANGE
seek_argument:
        jmp finish
seek_allowed:
        ldy #3
seek_copy:
        lda r0,y
        sta offset,y
        sta short_command+2,y
        dey
        bpl seek_copy
        jsr seek_command
        bcs seek_failed
        cmp #0
        bne seek_failed
        ldx slot
        ldy #0
seek_position:
        lda offset,y
        sta positions,x
        inx
        iny
        cpy #4
        bne seek_position
        jmp ok
seek_failed:
        jmp quarantine

; Commands use either the large private request or a six-byte resident header.
; The latter must leave the WRITE payload intact during verification.
seek_command:
        lda #6
        sta short_command+1
        lda #6
        jmp send_short
short_two:
        sta short_command+1
        lda #2
send_short:
        sta r1L
        lda #0
        sta r1H
        lda target
        sta short_command
        lda #<short_command
        sta r0L
        lda #>short_command
        sta r0H
        jmp send_plain
send_full:
        lda #<UFS_COMMAND
        sta r0L
        lda #>UFS_COMMAND
        sta r0H
        lda command_len
        sta r1L
        lda command_len+1
        sta r1H
send_plain:
        lda #0
        sta r3L
        sta r3H
send:
        jsr NET_STREAM
        php
        pha
        ldx #31
send_status:
        lda NET_STAT,x
        sta status,x
        dex
        bpl send_status
        pla
        plp
        bcs send_return
        ldx NET_TRUNC
        bne send_invalid
        ldx packet_error
        bne send_packet
send_return:
        rts
send_invalid:
        lda #UFS_PROTOCOL
        sec
        rts
send_packet:
        txa
        sec
        rts

; A single request <=512 can still arrive in multiple packets. Count and
; validate all of them; never use the 510-byte text aggregation buffer.
read_block:
        lda target
        sta short_command
        lda #4
        sta short_command+1
        lda expected
        sta short_command+2
        lda expected+1
        sta short_command+3
        lda #<short_command
        sta r0L
        lda #>short_command
        sta r0H
        lda #4
        sta r1L
        lda #0
        sta r1H
        sta count
        sta count+1
        sta packet_error
        lda #<receive
        sta r3L
        lda #>receive
        sta r3H
        jsr send
        ldx packet_error
        bne read_packet_error
        bcs read_return
        cmp #0
        beq read_count
        cmp #$ff
        bne read_status_error
        ldx status
        bne read_invalid
        ; Empty status is explicitly successful for DOS READ_DATA only.
read_count:
        lda count
        cmp expected
        bne read_short
        lda count+1
        cmp expected+1
        bne read_short
        lda #0
        clc
read_return:
        rts
read_packet_error:
        txa
read_status_error:
        sec
        rts
read_invalid:
        lda #UFS_PROTOCOL
        sec
        rts
read_short:
        lda #UFS_SHORT
        sec
        rts

receive:
        lda NET_PACKET_TRUNC
        bne packet_invalid
        clc
        lda count
        adc NET_LEN
        sta total
        lda count+1
        adc NET_LEN+1
        bcs packet_invalid
        sta total+1
        cmp expected+1
        bcc packet_fits
        bne packet_invalid
        lda total
        cmp expected
        bcc packet_fits
        beq packet_fits
packet_invalid:
        lda #UFS_PROTOCOL
        bne packet_fail
packet_fits:
        lda #<NET_DATA
        sta r4L
        lda #>NET_DATA
        sta r4H
        lda bufptr
        sta r6L
        lda bufptr+1
        sta r6H
        lda NET_LEN
        sta r5L
        lda NET_LEN+1
        sta r5H
        ora r5L
        beq packet_done
        ldy #0
packet_byte:
        lda (r4),y
        ldx compare
        beq packet_store
        cmp (r6),y
        bne packet_differs
        beq packet_next
packet_store:
        sta (r6),y
packet_next:
        inc r4L
        bne packet_src
        inc r4H
packet_src:
        inc r6L
        bne packet_dst
        inc r6H
packet_dst:
        jsr decrement
        bne packet_byte
packet_done:
        lda total
        sta count
        lda total+1
        sta count+1
        lda r6L
        sta bufptr
        lda r6H
        sta bufptr+1
        clc
        rts
packet_differs:
        lda #UFS_VERIFY
packet_fail:
        sta packet_error
        sec
        rts

decrement:
        lda r5L
        bne decrement_low
        dec r5H
decrement_low:
        dec r5L
        lda r5L
        ora r5H
        rts
advance:
        ldx slot
        clc
        lda positions,x
        adc count
        sta positions,x
        lda positions+1,x
        adc count+1
        sta positions+1,x
        lda positions+2,x
        adc #0
        sta positions+2,x
        lda positions+3,x
        adc #0
        sta positions+3,x
        rts

close_all:
        lda busy
        beq close_all_begin
        lda #UFS_BUSY
        sec
        rts
close_all_begin:
        ldx #1
        jsr close_file
        pha
        ldx #31
close_all_save:
        lda status,x
        sta close_status,x
        dex
        bpl close_all_save
        ldx #2
        jsr close_file
        sta result
        pla
        beq close_all_second
        sta result
        ldx #31
close_all_restore:
        lda close_status,x
        sta status,x
        dex
        bpl close_all_restore
close_all_second:
        lda result
        cmp #1                  ; C=0 only when A=0
        rts

busy:           .byte 0
name_component: .byte 0
target:         .byte 0
index:          .byte 0
slot:           .byte 0
wanted_mode:    .byte 0
command_len:    .word 0
short_command:  .fill 6, 0
expected:       .word 0
bufptr:         .word 0
endptr:         .word 0
offset:         .fill 4, 0
total:          .word 0
compare:        .byte 0
packet_error:   .byte 0
sizes:          .fill 8, 0
positions:      .fill 8, 0
close_status:   .fill 32, 0
files_end:
        .cerror * > UFS_VIEW, "file service overlaps resident viewer"

* = UFS_VIEW
.include "ultimate-view.inc"
        .cerror * > UFP_PICK, "resident file viewer overlaps selector gateway"
.include "file-dialog-gateway.inc"
        .cerror * > $5000, "resident file service overlaps apps"
