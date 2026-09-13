; Native graphical launcher with a port-1 1351 pointer and keyboard controls.
; GPL v3. Uses the existing app dispatcher and owned display lifetime.
.include "api.inc"
* = N_APPBASE
gd_image:
        .text "napp"
        .byte 1,1,10,0
        .word gd_end-gd_image
        .byte (gd_end-gd_image+255)/256,0
        .word gd_entry-gd_image
        .word 0
        .text "uos desktop",0
        .fill N_APPBASE+32-*,0
gd_entry:
        cld
        lda N_BROWSERERROR
        sta gd_launch_error
        lda N_DESKTOPSEL
        cmp #5
        bcc +
        lda #0
+       sta gd_selected
        sta N_DESKTOPSEL
        lda #0
        sta N_BROWSERERROR
        sta gd_bitmap
        sta gd_error
        sta gd_handle
        jsr gd_text_both
        lda N_CURRENT
        sta N_OWNER
        lda #0
        sta N_BANK
        lda #$c0
        sta N_PAGE
        lda #36
        sta N_PAGES
        jsr N_RESERVE
        bcs gd_failed
        ldx #3
gd_keep_handle:
        lda N_HANDLE,x
        sta gd_handle,x
        dex
        bpl gd_keep_handle
        lda #0
        sta N_OFFSET
        sta N_OFFSET+1
        sta N_COUNT
        lda #2
        sta N_COUNT+1
gd_fill:
        lda #0
        ldx N_OFFSET+1
        cpx #$20
        bcc +
        lda #$16
+       sta N_VALUE
        jsr N_FILL
        bcs gd_failed
        inc N_OFFSET+1
        inc N_OFFSET+1
        lda N_OFFSET+1
        cmp #$24
        bne gd_fill
        jsr draw_scene
        bcs gd_failed
        jsr gd_highlight
        bcs gd_failed
        jsr gd_graphics_status
        bcs gd_failed
        jsr gd_select_surface
        jsr N_VSHOW
        bcs gd_failed
        lda #1
        sta gd_bitmap
        jsr pm_install
        bcs gd_failed
        jmp gd_loop
gd_failed:
        sta gd_error
        jsr pm_close
        jsr N_VCLOSE
        lda #0
        sta gd_bitmap
        ; A failed reservation has no owned handle. Free an allocated surface
        ; if setup failed after reservation; the app cleanup is still a backstop.
        lda gd_handle
        beq +
        jsr gd_select_surface
        jsr N_FREE
        bcs +
        lda #0
        sta gd_handle
+       jsr gd_text_both
gd_loop:
        lda #1
        sta N_READY
gd_get_key:
        jsr N_KEYIN
        beq gd_idle
        ldx #0
        stx N_READY
        cmp #27
        beq gd_workspace
        cmp #13
        beq gd_launch
        cmp #9
        beq gd_next
        cmp #$11
        beq gd_next
        cmp #$1d
        beq gd_next
        cmp #$91
        beq gd_previous
        cmp #$9d
        beq gd_previous
        cmp #$13
        beq gd_first
        and #$df
        cmp #$43
        beq gd_calc
        cmp #$45
        beq gd_editor
        cmp #$46
        beq gd_files
        cmp #$55
        beq gd_ultimate
        cmp #$41
        beq gd_claude
        jmp gd_loop
gd_idle:
        jsr pm_poll
        lda pm_event
        beq gd_loop
        cmp #2
        beq gd_launch
        lda pm_hit
        jmp gd_select
gd_calc:
        lda #0
        beq gd_shortcut
gd_editor:
        lda #1
        bne gd_shortcut
gd_files:
        lda #2
        bne gd_shortcut
gd_ultimate:
        lda #3
        bne gd_shortcut
gd_claude:
        lda #4
gd_shortcut:
        sta gd_selected
        sta N_DESKTOPSEL
        jmp gd_launch
gd_first:
        lda #0
        beq gd_select
gd_next:
        lda gd_selected
        clc
        adc #1
        cmp #5
        bcc gd_select
        lda #0
        beq gd_select
gd_previous:
        lda gd_selected
        bne +
        lda #5
+       sec
        sbc #1
gd_select:
        sta gd_selected
        sta N_DESKTOPSEL
        lda gd_bitmap
        beq gd_redraw_text
        jsr gd_highlight
        bcs gd_failed
        ; Text rendering stays on the already selected VDC console while
        ; the VIC surface is visible. Do not toggle console modes here.
        jsr gd_text
        jmp gd_loop
gd_redraw_text:
        jsr gd_text_both
        jmp gd_loop
gd_workspace:
        jsr pm_close
        jmp N_WORKSPACE
gd_launch:
        jsr pm_close
        lda #0
        sta N_APPFORMAT
        lda N_BOOTDEVICE
        sta N_DEVICE
        ldx gd_selected
        lda gd_name_lengths,x
        sta N_NAMELEN
        lda gd_name_offsets,x
        tax
        ldy #0
gd_name_copy:
        lda gd_names,x
        sta N_APPNAME,y
        inx
        iny
        cpy N_NAMELEN
        bne gd_name_copy
        jmp N_REPLACE
gd_select_surface:
        lda N_CURRENT
        sta N_OWNER
        ldx #3
-       lda gd_handle,x
        sta N_HANDLE,x
        dex
        bpl -
        rts
gd_highlight:
        lda #0
        sta gd_index
gd_highlight_next:
        lda #2
        sta gfx_x0
        lda #38
        sta gfx_x1
        ldx gd_index
        lda gd_card_rows,x
        sta gfx_y0
        clc
        adc #3
        sta gfx_y1
        lda #0
        sta gfx_x0+1
        sta gfx_x1+1
        sta gfx_y0+1
        sta gfx_y1+1
        lda #$1b
        cpx gd_selected
        bne +
        lda #$07
+       sta gfx_color
        jsr gfx_colors
        bcs gd_highlight_return
        inc gd_index
        lda gd_index
        cmp #5
        bne gd_highlight_next
        lda #0
        clc
gd_highlight_return:
        rts
gd_graphics_status:
        lda gd_launch_error
        beq gd_status_ok
        lda #8
        sta gfx_x0
        lda #164
        sta gfx_y0
        lda #0
        sta gfx_x0+1
        sta gfx_y0+1
        lda #1
        sta gfx_pen
        ldx #gd_error_label_end-gd_error_label-1
-       lda gd_error_label,x
        sta gfx_text_buffer,x
        dex
        bpl -
        lda gd_launch_error
        lsr
        lsr
        lsr
        lsr
        tax
        lda gd_hex,x
        sta gfx_text_buffer+gd_error_label_end-gd_error_label
        lda gd_launch_error
        and #15
        tax
        lda gd_hex,x
        sta gfx_text_buffer+gd_error_label_end-gd_error_label+1
        lda #gd_error_label_end-gd_error_label+2
        sta gfx_text_length
        jmp gfx_text
gd_status_ok:
        lda #0
        clc
        rts
gd_text_both:
        lda #0
        sta gd_screen
gd_text_screen:
        lda $d7
        rol
        lda #0
        rol
        cmp gd_screen
        beq +
        jsr $ff5f
+       jsr gd_text
        inc gd_screen
        lda gd_screen
        cmp #2
        bne gd_text_screen
        rts
gd_text:
        lda #$93
        jsr $ffd2
        lda #<gd_title
        ldx #>gd_title
        jsr gd_puts
        lda #0
        sta gd_index
gd_text_item:
        lda #32
        ldx gd_index
        cpx gd_selected
        bne +
        lda #62
+       jsr $ffd2
        ldx gd_index
        lda gd_item_lo,x
        sta gd_item_load+1
        lda gd_item_hi,x
        tax
gd_item_load:
        lda #0
        jsr gd_puts
        inc gd_index
        lda gd_index
        cmp #5
        bne gd_text_item
        lda #<gd_help
        ldx #>gd_help
        jsr gd_puts
        lda gd_launch_error
        beq +
        lda #<gd_text_error
        ldx #>gd_text_error
        jsr gd_puts
        lda gd_launch_error
        jsr gd_hex_out
+       lda gd_error
        beq gd_text_done
        lda #<gd_fallback
        ldx #>gd_fallback
        jsr gd_puts
gd_text_done:
        rts
gd_puts:
        sta gd_put_next+1
        stx gd_put_next+2
gd_put_next:
        lda $ffff
        beq gd_put_return
        jsr $ffd2
        inc gd_put_next+1
        bne gd_put_next
        inc gd_put_next+2
        bne gd_put_next
gd_put_return:
        rts
gd_hex_out:
        pha
        lsr
        lsr
        lsr
        lsr
        tax
        lda gd_hex,x
        jsr $ffd2
        pla
        and #15
        tax
        lda gd_hex,x
        jmp $ffd2
gd_selected:     .byte 0
cloop = gd_loop
gd_bitmap:       .byte 0
gd_error:        .byte 0
gd_launch_error: .byte 0
gd_handle:       .fill 4,0
gd_screen:       .byte 0
gd_index:        .byte 0
gd_card_rows:    .byte 4,7,10,13,16
gd_name_lengths: .byte 4,6,5,8,6
gd_name_offsets: .byte 0,4,10,15,23
gd_names:       .text "calceditorfilesultimateclaude"
gd_hex:         .text "0123456789abcdef"
gd_title:       .text "uos desktop",13,13,0
gd_item_calc:   .text " c  calculator",13,"    numbers and saved history",13,13,0
gd_item_editor: .text " e  text editor",13,"    documents on disk and usb",13,13,0
gd_item_files:  .text " f  files",13,"    drives, usb folders and apps",13,13,0
gd_item_ultimate: .text " u  ultimate",13,"    drives, network and clock",13,13,0
gd_item_claude: .text " a  claude",13,"    claude code terminal",13,13,0
gd_item_lo: .byte <gd_item_calc,<gd_item_editor,<gd_item_files,<gd_item_ultimate,<gd_item_claude
gd_item_hi: .byte >gd_item_calc,>gd_item_editor,>gd_item_files,>gd_item_ultimate,>gd_item_claude
gd_help: .text "arrows/tab select. enter opens.",13,"c/e/f/u/a open apps. esc workspace.",13,13,0
gd_text_error: .text "app could not open: ",0
gd_fallback: .text 13,"graphics unavailable.",13,"text controls remain active.",0
gd_error_label: .byte 65,112,112,32,99,111,117,108,100,32,110,111,116,32,111,112,101,110,58,32
gd_error_label_end:
.include "desktop/scene.inc"
.include "desktop/text-scene.inc"
.include "graphics/graphics-core.inc"
.include "graphics/text-core.inc"
.include "desktop/pointer.inc"
gd_end:
.cerror gd_end > N_APPBASE+$2000, "desktop exceeds the 8 KiB app budget"
