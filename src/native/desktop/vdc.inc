; Native 640x200 VDC launcher. All mutable VRAM is backed by an owned handle.
; Foreground only, D=0 and IRQs enabled. Close before every app/workspace exit.
; A failed close retains the snapshot and blocks handoff until a retry succeeds.
; Register 28 selects addressing; an alias probe establishes physical capacity.
vd_open:
        jsr vd_gate
        lda #0
        sta vd_fault
        sta vd_phase
        sta vd_live
        sta vd_probe_live
        sta vd_pointer_visible
        sta vd_handle
        ldx #1
        jsr vd_getreg
        cmp #80
        bne vd_platform
        ldx #6
        jsr vd_getreg
        cmp #25
        bne vd_platform
        ldx #9
        jsr vd_getreg
        and #31
        cmp #7
        bne vd_platform
        ldx #8
        jsr vd_getreg
        and #3
        bne vd_platform
        ldx #22
        jsr vd_getreg
        cmp #$78
        bne vd_platform
        ldx #25
        jsr vd_getreg
        bmi vd_platform
        lda #0
        sta vd_index
vd_save_registers:
        ldy vd_index
        ldx vd_registers,y
        jsr vd_getreg
        sta vd_saved,y
        inc vd_index
        lda vd_index
        cmp #vd_register_count
        bne vd_save_registers
        inc vd_phase           ; saved registers precede the first mutation
        jsr vd_blank
        lda vd_saved+11        ; R28: select linear 64K addressing for the probe
        ora #$10
        ldx #28
        jsr vd_setreg
        lda #0
        sta vd_addr
        sta vd_addr+1
        jsr vd_peek
        sta vd_probe_low
        inc vd_addr+1
        jsr vd_peek
        sta vd_probe_high
        inc vd_probe_live
        lda #$aa
        jsr vd_poke
        dec vd_addr+1
        lda #$55
        jsr vd_poke
        inc vd_addr+1
        jsr vd_peek
        cmp #$aa
        beq +
        cmp #$55
        bne vd_platform
        lda #0
        beq ++
+       lda #1
+       sta vd_color          ; 16K chips alias bit 8 in 64K addressing
        jsr vd_restore_probe
        lda #$40
        sta vd_pages
        lda #0
        sta vd_base
        lda vd_saved+11
        and #$ef
        ldx vd_color
        beq +
        ora #$10
        ldx #$48
        stx vd_pages
        ldx #$40
        stx vd_base
+       ldx #28
        jsr vd_setreg
        lda N_CURRENT
        sta N_OWNER
        lda #$ff
        sta N_BANK
        lda vd_pages
        sta N_PAGES
        jsr N_ALLOC
        bcs vd_fail
        ldx #3
-       lda N_HANDLE,x
        sta vd_handle,x
        dex
        bpl -
        jsr vd_transfer_start
vd_snapshot:
        lda #0                ; zero byte count means one complete 256-byte page
        sta vd_count
        jsr vd_read_block
        jsr N_WRITE
        bcs vd_fail
        jsr vd_transfer_next
        bne vd_snapshot
        inc vd_phase          ; all bytes saved before the first bitmap write
        jsr vd_unpack
        lda #$20
        ldx #10
        jsr vd_setreg
        lda vd_base
        ldx #12
        jsr vd_setreg
        lda #0
        ldx #13
        jsr vd_setreg
        ldx #21
        jsr vd_setreg
        ldx #24
        jsr vd_setreg
        ldx #27
        jsr vd_setreg
        lda #$80
        ldx #20
        jsr vd_setreg
        jsr vd_render_selection
        lda #$f2
        ldx #26
        jsr vd_setreg
        lda #$87
        ldx vd_color
        beq +
        ora #$40
+       ldx #25
        jsr vd_setreg
        lda #1
        sta vd_live
        jmp vd_success
vd_platform:
        lda #N_PLATFORM
vd_fail:
        sta vd_fault
        ldx vd_stack
        txs
        sec
        rts
vd_success:
        lda #0
        clc
        rts
vd_gate:
        tsx
        inx
        inx                   ; remove this helper's own return address
        stx vd_stack
        lda #0
        sta N_READY
        rts

vd_close:
        jsr vd_gate
        lda #0
        sta vd_fault          ; retry the complete restore after a prior stall
        lda vd_phase
        beq vd_success
        jsr vd_blank
        jsr vd_restore_probe
        lda vd_phase
        cmp #2
        bcc vd_restore_registers
        lda vd_saved+11
        and #$ef
        ldx vd_color
        beq +
        ora #$10
+       ldx #28
        jsr vd_setreg
        jsr vd_transfer_start
vd_restore_memory:
        jsr N_READ
        bcs vd_fail
        lda #0
        sta vd_count
        jsr vd_write_block
        jsr vd_transfer_next
        bne vd_restore_memory
vd_restore_registers:
        ; Addressing is restored after VRAM, display control after all other
        ; registers. R18/R19 are last so the saved update address is exact.
        lda #vd_register_count-1
        sta vd_index
-       ldy vd_index
        cpy #3
        beq +
        cpy #4
        beq +
        cpy #8
        beq +
        lda vd_saved,y
        ldx vd_registers,y
        jsr vd_setreg
+       dec vd_index
        bpl -
        lda vd_saved+8
        ldx #25
        jsr vd_setreg
        lda vd_saved+3
        ldx #18
        jsr vd_setreg
        lda vd_saved+4
        ldx #19
        jsr vd_setreg
        lda #0
        sta vd_live
        sta vd_pointer_visible
        lda vd_handle
        beq +
        jsr vd_select_handle
        jsr N_FREE
        bcs vd_fail
        lda #0
        sta vd_handle
+       lda #0
        sta vd_phase
        jmp vd_success
vd_blank:
        lda #$22              ; same foreground/background; no attribute reads
        ldx #26
        jsr vd_setreg
        lda #7
        ldx #25
        jmp vd_setreg
vd_restore_probe:
        lda vd_probe_live
        beq +
        lda vd_saved+11
        ora #$10
        ldx #28
        jsr vd_setreg
        lda #0
        sta vd_addr
        lda #1
        sta vd_addr+1
        lda vd_probe_high
        jsr vd_poke
        dec vd_addr+1
        lda vd_probe_low
        jsr vd_poke
        lda #0
        sta vd_probe_live
+       rts

vd_select_handle:
        lda N_CURRENT
        sta N_OWNER
        ldx #3
-       lda vd_handle,x
        sta N_HANDLE,x
        dex
        bpl -
        rts
vd_transfer_start:
        jsr vd_select_handle
        lda #0
        sta N_OFFSET
        sta N_OFFSET+1
        sta N_COUNT
        sta vd_addr
        lda #1
        sta N_COUNT+1
        lda vd_base
        sta vd_addr+1
        lda vd_pages
        sta vd_left
        rts
vd_transfer_next:
        inc N_OFFSET+1
        inc vd_addr+1
        dec vd_left
        rts

; Every selected register and every data byte uses a bounded ready handshake.
; No foreground scratch in zero page, no long interrupt-disabled section.
vd_wait:
        pha
        lda #0
        sta vd_wait_low
        sta vd_wait_high
-       bit $d600
        bmi +
        inc vd_wait_low
        bne -
        inc vd_wait_high
        bne -
        pla
        lda #N_IOERROR
        jmp vd_fail
+       pla
        rts
vd_getreg:
        stx $d600
        jsr vd_wait
        lda $d601
        rts
vd_setreg:
        stx $d600
        jsr vd_wait
        sta $d601
        rts
vd_seek:
        lda vd_addr+1
        ldx #18
        jsr vd_setreg
        lda vd_addr
        ldx #19
        jsr vd_setreg
        ldx #31
        stx $d600
        jmp vd_wait
vd_read_seek:
        jsr vd_seek
        jsr vd_getbyte         ; prime the real VDC read latch, then re-address
        jmp vd_seek
vd_getbyte:
        jsr vd_wait
        lda $d601
        rts
vd_putbyte:
        jsr vd_wait
        sta $d601
        rts
vd_peek:
        jsr vd_read_seek
        jmp vd_getbyte
vd_poke:
        pha
        jsr vd_seek
        pla
        jmp vd_putbyte
vd_read_block:
        jsr vd_read_seek
        ldy #0
-       jsr vd_getbyte
        sta N_BUFFER,y
        iny
        cpy vd_count
        bne -
        rts
vd_write_block:
        jsr vd_seek
        ldy #0
-       lda N_BUFFER,y
        jsr vd_putbyte
        iny
        cpy vd_count
        bne -
        rts

; Packed scene uses non-overlapping earlier blocks, exploiting the VDC's
; block-copy unit. The build verifies every decoded byte and distance.
vd_unpack:
        lda #<vd_scene
        sta vd_next+1
        lda #>vd_scene
        sta vd_next+2
        lda #0
        sta vd_addr
        lda vd_base
        sta vd_addr+1
vd_token:
        jsr vd_next
        cmp #0
        beq vd_unpack_done
        bmi vd_copy_token
        cmp #64
        bcs vd_fill_token
        sta vd_length
        jsr vd_seek
        ldy vd_length
-       jsr vd_next
        jsr vd_putbyte
        dey
        bne -
        beq vd_token_advance
vd_fill_token:
        sec
        sbc #63
        sta vd_length
        jsr vd_seek
        jsr vd_next
        jsr vd_putbyte
        lda #0
        ldx #24
        jsr vd_setreg
        lda vd_length
        sec
        sbc #1
        beq vd_token_advance
        ldx #30
        jsr vd_setreg
        jmp vd_token_advance
vd_copy_token:
        sec
        sbc #125
        sta vd_length
        jsr vd_next
        sta vd_distance
        jsr vd_next
        sta vd_distance+1
        lda vd_addr
        sec
        sbc vd_distance
        pha
        lda vd_addr+1
        sbc vd_distance+1
        ldx #32
        jsr vd_setreg
        pla
        ldx #33
        jsr vd_setreg
        lda #$80
        ldx #24
        jsr vd_setreg
        jsr vd_seek
        lda vd_length
        ldx #30
        jsr vd_setreg
vd_token_advance:
        jsr vd_wait
        clc
        lda vd_addr
        adc vd_length
        sta vd_addr
        bcc +
        inc vd_addr+1
+       jmp vd_token
vd_unpack_done:
        rts
vd_next:
        lda $ffff
        inc vd_next+1
        bne +
        inc vd_next+2
+       rts

vd_select:
        lda vd_live
        beq vd_success
        lda vd_fault
        bne vd_return_fault
        jsr vd_gate
        jsr vd_hide_pointer
        jsr vd_render_selection
        jmp vd_success
vd_return_fault:
        sec
        rts
vd_render_selection:
        lda vd_color
        beq vd_markers
        lda #0
        sta vd_row
        sta vd_addr
        lda #$80
        sta vd_addr+1
        lda #80
        sta vd_count
vd_color_row:
        lda #$2f
        ldy #79
-       sta N_BUFFER,y
        dey
        bpl -
        ldx #5
-       lda vd_row
        sec
        sbc gd_card_rows,x
        cmp #3
        bcc vd_color_card
        dex
        bpl -
        bmi vd_color_write
vd_color_card:
        lda #$1f
        cpx gd_selected
        bne +
        lda #$d0
+       ldy #75
-       sta N_BUFFER,y
        dey
        cpy #3
        bne -
vd_color_write:
        jsr vd_write_block
        jsr vd_next_row
        inc vd_row
        lda vd_row
        cmp #25
        bne vd_color_row
vd_markers:
        lda #0
        sta vd_index
vd_marker:
        ldx vd_index
        lda pm_tops,x
        clc
        adc #6
        ldx #13
        jsr vd_xy
        ldy #0
-       jsr vd_seek
        lda #0
        ldx vd_index
        cpx gd_selected
        bne +
        lda vd_arrow,y
+       jsr vd_putbyte
        jsr vd_next_row
        iny
        cpy #8
        bne -
        inc vd_index
        lda vd_index
        cmp #6
        bne vd_marker
        lda gd_launch_error
        beq vd_unpack_done
        ; The VIC error renderer has prepared the same ASCII label and digits.
        lda #176
        ldx #0
        jsr vd_xy
        lda #80
        sta vd_count
        lda #0
        sta vd_row
vd_status_row:
        lda #0
        ldx #79
-       sta N_BUFFER,x
        dex
        bpl -
        ldx #0
vd_status_glyph:
        lda gfx_text_buffer,x
        sec
        sbc #32
        sta vd_font_low
        lda #0
        sta vd_font_high
        asl vd_font_low
        rol vd_font_high
        asl vd_font_low
        rol vd_font_high
        asl vd_font_low
        rol vd_font_high
        lda vd_font_low
        clc
        adc #<gfx_font
        sta vd_glyph_load+1
        lda vd_font_high
        adc #>gfx_font
        sta vd_glyph_load+2
        ldy vd_row
vd_glyph_load:
        lda $ffff,y
        sta N_BUFFER+4,x
        inx
        cpx gfx_text_length
        bne vd_status_glyph
        jsr vd_write_block
        jsr vd_next_row
        inc vd_row
        lda vd_row
        cmp #8
        bne vd_status_row
        rts

; A=row, X=byte column -> linear bitmap address, preserving Y.
vd_xy:
        stx vd_column
        ldx #0
        stx vd_addr+1
        asl
        rol vd_addr+1
        asl
        rol vd_addr+1
        asl
        rol vd_addr+1
        asl
        rol vd_addr+1
        sta vd_math
        ldx vd_addr+1
        stx vd_math+1
        asl
        rol vd_addr+1
        asl
        rol vd_addr+1
        clc
        adc vd_math
        sta vd_addr
        lda vd_addr+1
        adc vd_math+1
        clc
        adc vd_base
        sta vd_addr+1
        lda vd_addr
        clc
        adc vd_column
        sta vd_addr
        bcc +
        inc vd_addr+1
+       rts
vd_next_row:
        lda vd_addr
        clc
        adc #80
        sta vd_addr
        bcc +
        inc vd_addr+1
+       rts

vd_poll:
        lda vd_live
        beq vd_poll_done
        lda vd_fault
        bne vd_poll_done
        lda pm_seen
        cmp vd_pointer_visible
        bne vd_pointer_change
        lda pm_seen
        beq vd_poll_done
        lda pm_x
        cmp vd_pointer_x
        bne vd_pointer_change
        lda pm_x+1
        cmp vd_pointer_x+1
        bne vd_pointer_change
        lda pm_y
        cmp vd_pointer_y
        beq vd_poll_done
vd_pointer_change:
        jsr vd_gate
        jsr vd_hide_pointer
        lda pm_seen
        beq vd_poll_done
        lda pm_x
        sta vd_pointer_x
        lda pm_x+1
        sta vd_pointer_x+1
        lda pm_y
        sta vd_pointer_y
        jsr vd_pointer_geometry
vd_pointer_draw_row:
        jsr vd_read_block
        ldx vd_pointer_line
        lda vd_pointer_hi,x
        sta vd_mask
        lda vd_pointer_lo,x
        sta vd_mask+1
        lda #0
        sta vd_mask+2
        ldx vd_pointer_shift
        beq +
-       lsr vd_mask
        ror vd_mask+1
        ror vd_mask+2
        dex
        bne -
+       ldy #0
        ldx vd_pointer_at
-       lda N_BUFFER,y
        sta vd_under,x
        eor vd_mask,y
        sta N_BUFFER,y
        inx
        iny
        cpy vd_count
        bne -
        stx vd_pointer_at
        jsr vd_write_block
        jsr vd_next_row
        inc vd_pointer_line
        dec vd_pointer_rows
        bne vd_pointer_draw_row
        lda #1
        sta vd_pointer_visible
vd_poll_done:
        clc
        rts
vd_hide_pointer:
        lda vd_pointer_visible
        beq vd_poll_done
        jsr vd_pointer_geometry
vd_pointer_restore_row:
        ldy #0
        ldx vd_pointer_at
-       lda vd_under,x
        sta N_BUFFER,y
        inx
        iny
        cpy vd_count
        bne -
        stx vd_pointer_at
        jsr vd_write_block
        jsr vd_next_row
        dec vd_pointer_rows
        bne vd_pointer_restore_row
        lda #0
        sta vd_pointer_visible
        rts
vd_pointer_geometry:
        lda vd_pointer_x
        asl
        and #7
        sta vd_pointer_shift
        lda vd_pointer_x+1
        lsr
        lda vd_pointer_x
        ror
        lsr                   ; logical x*2/8 = x/4, full 640-pixel address range
        tax
        lda #80
        stx vd_column
        sec
        sbc vd_column
        cmp #3
        bcc +
        lda #3
+       sta vd_count
        lda #200
        sec
        sbc vd_pointer_y
        cmp #16
        bcc +
        lda #16
+       sta vd_pointer_rows
        lda vd_pointer_y
        jsr vd_xy
        lda #0
        sta vd_pointer_line
        sta vd_pointer_at
        rts

vd_registers: .byte 10,12,13,18,19,20,21,24,25,26,27,28,32,33
vd_register_count=*-vd_registers
vd_saved: .fill vd_register_count,0
vd_handle: .fill 4,0
vd_phase: .byte 0              ; 0 untouched, 1 registers/probe, 2 full snapshot
vd_live: .byte 0
vd_color: .byte 0
vd_fault: .byte 0
vd_stack: .byte 0
vd_base: .byte 0
vd_pages: .byte 0
vd_left: .byte 0
vd_index: .byte 0
vd_row: .byte 0
vd_column: .byte 0
vd_addr: .word 0
vd_math: .word 0
vd_distance: .word 0
vd_font_low: .byte 0
vd_font_high: .byte 0
vd_count: .byte 0
vd_length: .byte 0
vd_wait_low: .byte 0
vd_wait_high: .byte 0
vd_probe_live: .byte 0
vd_probe_low: .byte 0
vd_probe_high: .byte 0
vd_pointer_visible: .byte 0
vd_pointer_x: .word 0
vd_pointer_y: .byte 0
vd_pointer_shift: .byte 0
vd_pointer_rows: .byte 0
vd_pointer_line: .byte 0
vd_pointer_at: .byte 0
vd_mask: .fill 3,0
vd_under: .fill 48,0
.include "vdc-scene.inc"
