; GEM desktop (docs/GEM-DESKTOP.md): drive icons and folder windows on the
; AES. Written as "browse" on the GEM boot disk, so launched apps return here.
.include "api.inc"
.include "aes-api.inc"
AE_POINTER = 1
GM_WINDOWS = 4
GM_RECORD = 20                 ; name 16, type, flags, blocks (word)
GM_MAX_ENTRIES = 255
GM_PAGES = (GM_MAX_ENTRIES*GM_RECORD+255)/256
GM_PAPER = $61                 ; window work: blue ink on white
GM_SELECTED = $16              ; selected row: white on blue
GM_DESK = $16                  ; desktop: white icons on blue
GM_ICON_SELECTED = $61
GM_ICONS = 3
* = N_APPBASE
gm_image:
        .text "napp"
        .byte 1,1,14,0
        .word gm_end-gm_image
        .byte (gm_end-gm_image+48+255)/256,0
        .word gm_start-gm_image
        .word 0
        .text "gem desktop",0
        .fill N_APPBASE+32-*,0

gm_start:
        cld
        lda N_BROWSERERROR      ; a program the dispatcher could not start
        sta gm_start_error
        lda #0
        sta N_BROWSERERROR
        lda #$ff
        sta gm_icon_sel
        jsr gm_surface_setup
        bcs gm_fatal_text
        jsr gm_aes_setup
        bcs gm_fatal
        lda gm_start_error
        beq gm_loop
        jsr gm_hex_error        ; "[3][Could not start that|program: error $xx][OK]"
        lda #<gm_start_alert
        ldx #>gm_start_alert
        ldy #1
        jsr gm_alert
gm_loop:
        lda #MU_MESAG|MU_BUTTON|MU_KEYBD
        sta ae_ev_params
        lda #2                  ; up to a double click
        sta ae_ev_params+1
        lda #1
        sta ae_ev_params+2
        sta ae_ev_params+3
        jsr ae_event
        bcs gm_fatal
        lda ae_ev_result
        and #MU_MESAG
        beq +
        jsr gm_message
+       lda ae_ev_result
        and #MU_BUTTON
        beq +
        jsr gm_click
+       lda ae_ev_result
        and #MU_KEYBD
        beq +
        jsr gm_key
+       jmp gm_loop
; The AES is unusable: back to the card launcher, which reports the code.
gm_fatal:
        sta N_BROWSERERROR
        jsr pm_close
        jsr N_VCLOSE
gm_fatal_text:
        jmp gm_launcher

; ---- surface, pointer ----------------------------------------------------------
gm_surface_setup:
        lda N_CURRENT
        sta N_OWNER
        lda #0
        sta N_BANK
        lda #$c0
        sta N_PAGE
        lda #36
        sta N_PAGES
        jsr N_RESERVE
        bcs gm_setup_done
        ldx #3
-       lda N_HANDLE,x
        sta gm_surface,x
        sta ae_surface,x
        dex
        bpl -
        lda #0
        sta N_OFFSET
        sta N_OFFSET+1
        sta N_COUNT
        lda #2
        sta N_COUNT+1
-       lda #0
        ldx N_OFFSET+1
        cpx #$20
        bcc +
        lda #GM_DESK
+       sta N_VALUE
        jsr N_FILL
        bcs gm_setup_done
        inc N_OFFSET+1
        inc N_OFFSET+1
        lda N_OFFSET+1
        cmp #$24
        bne -
        jsr gm_bind
        bcs gm_setup_done
        jsr gfx_clip_defaults
        jsr gm_draw_icons
        bcs gm_setup_done
        jsr gm_select_surface
        jsr N_VSHOW
        bcs gm_setup_done
        jmp pm_install
gm_setup_done:
        rts
gm_select_surface:
        lda N_CURRENT
        sta N_OWNER
        ldx #3
-       lda gm_surface,x
        sta N_HANDLE,x
        dex
        bpl -
        rts
gm_bind:
        jsr gm_select_surface
        jmp gfx_bind
pm_control_count = 0
pm_select_surface = gm_select_surface
pm_find_hit:
        ldx #$ff                ; controls are AES objects, not pointer hits
        rts

; ---- AES -------------------------------------------------------------------------
gm_aes_setup:
        jsr ae_attach
        bcc gm_aes_ready
        cmp #N_BADHANDLE
        beq +
        sec
        rts
+       jsr gm_open_aesvc       ; none resident: load it from this folder
        bcs gm_aes_failed
        jsr ae_load
        php
        pha
        lda ae_stream_taken
        bne +
        jsr gm_close_file       ; the loader refused before taking it
+       pla
        plp
        bcs gm_aes_failed
gm_aes_ready:
        lda #WS_SURFACE
        sta N_BUFFER
        ldx #3
-       lda gm_surface,x
        sta N_BUFFER+1,x
        dex
        bpl -
        jsr gm_wcall
        bcs gm_aes_failed
        lda #<gm_menu
        ldx #>gm_menu
        jmp ae_menu_install
gm_aes_failed:
        rts
; Open AESVC.PRG beside this program (IEC name or Ultimate sibling path).
gm_open_aesvc:
        lda N_DEVICE
        sta N_FDEVICE
        lda N_APPFORMAT
        sta N_FFORMAT
        cmp #3
        bne gm_open_iec
        ldx #0
        stx gm_math
-       lda N_SOURCEPATH,x
        sta N_UPATH,x
        cmp #$2f
        bne +
        txa
        clc
        adc #1
        sta gm_math             ; length through the last slash
+       inx
        cpx N_NAMELEN
        bne -
        lda gm_math
        clc
        adc #9
        bcs gm_open_bad
        sta N_FNAMELEN
        ldx gm_math
        ldy #0
-       lda gm_aesvc_name,y
        sta N_UPATH,x
        inx
        iny
        cpy #9
        bne -
        beq gm_open_now
gm_open_iec:
        lda #9
        sta N_FNAMELEN
        ldx #8
-       lda gm_aesvc_name,x
        sta N_FNAME,x
        dex
        bpl -
gm_open_now:
        lda #N_APPOWNER
        sta N_FOWNER
        lda #1
        sta N_FTYPE
        lda #0
        sta N_FMODE
        ldx #3
-       sta N_FHANDLE,x
        dex
        bpl -
        jsr N_FOPEN
        bcs +
        ldx #3
-       lda N_FHANDLE,x
        sta gm_file,x
        dex
        bpl -
        clc
+       rts
gm_open_bad:
        lda #N_BADARG
        sec
        rts
gm_close_file:
        lda #N_APPOWNER
        sta N_FOWNER
        ldx #3
-       lda gm_file,x
        sta N_FHANDLE,x
        dex
        bpl -
        jmp N_FCLOSE
gm_wcall:
        lda #AE_OP_WINDOW
        jmp ae_call
; A/X = alert string, Y = default button. Keyboard and pointer until chosen.
gm_alert:
        jsr ae_alert_open
        bcs gm_alert_done
-       lda #1
        sta N_READY
        jsr N_KEYIN
        ldx #0
        stx N_READY
        pha
        jsr pm_poll
        lda pm_x
        sta ae_pointer_x
        lda pm_x+1
        sta ae_pointer_x+1
        lda pm_y
        sta ae_pointer_y
        lda pm_buttons
        beq +
        lda #1
+       sta ae_pointer_buttons
        pla
        jsr ae_alert_step
        bcs gm_alert_done
        lda N_BUFFER
        beq -
        clc
gm_alert_done:
        rts

; ---- messages --------------------------------------------------------------------
gm_message:
        lda ae_ev_result+7
        cmp #MN_SELECTED
        bne +
        jmp gm_menu_choice
+       cmp #WM_REDRAW
        bne +
        ldx ae_ev_result+10
        bne gm_redraw_window
        jmp gm_redraw_desktop
+       ldx ae_ev_result+10     ; window messages: find our slot
        jsr gm_slot_of
        bcc +
        rts
+       stx gm_slot
        lda ae_ev_result+7
        cmp #WM_TOPPED
        bne +
        lda #WF_TOP
        jmp gm_wset_simple
+       cmp #WM_CLOSED
        bne +
        jmp gm_close_slot
+       cmp #WM_FULLED
        bne +
        jmp gm_fulled
+       cmp #WM_ARROWED
        bne +
        jmp gm_arrowed
+       cmp #WM_VSLID
        bne +
        jmp gm_vslid
+       cmp #WM_MOVED           ; moved and sized: take the rectangle
        beq +
        cmp #WM_SIZED
        bne gm_message_done
+       ldx #3
-       lda ae_ev_result+11,x
        sta gm_rect,x
        dex
        bpl -
        jsr gm_set_rect
        jmp gm_update_slider
gm_message_done:
        rts
gm_redraw_window:
        jsr gm_slot_of
        bcs gm_message_done
        stx gm_slot
        ldx #3
-       lda ae_ev_result+11,x
        sta gm_clip,x
        dex
        bpl -
        jmp gm_paint_window

; ---- desktop icons ----------------------------------------------------------------
; Icons at columns 34..37: glyph rows y, y+1, label row y+2.
gm_redraw_desktop:
        ldx #3
-       lda ae_ev_result+11,x
        sta gm_clip,x
        dex
        bpl -
        jsr gm_bind
        bcs gm_icons_done
        lda #WS_GET             ; visible desktop rectangles
        sta N_BUFFER
        lda #0
        sta N_BUFFER+1
        lda #WF_FIRSTXYWH
        sta N_BUFFER+2
-       jsr gm_wcall
        bcs gm_icons_clip_reset
        lda N_BUFFER+2
        beq gm_icons_clip_reset
        jsr gm_clip_to_rect     ; rectangle within the redraw area
        bcs +
        jsr gm_draw_icons
        bcs gm_icons_clip_reset
+       lda #WS_GET
        sta N_BUFFER
        lda #WF_NEXTXYWH
        sta N_BUFFER+2
        jmp -
gm_icons_clip_reset:
        php
        pha
        jsr gfx_clip_defaults
        pla
        plp
gm_icons_done:
        rts
; Draw every icon with the current clip.
gm_draw_icons:
        lda #0
        sta gm_i
-       lda gm_i
        cmp #GM_ICONS
        bcs +
        jsr gm_draw_icon
        bcs ++
        inc gm_i
        bne -
+       clc
+       rts
gm_draw_icon:
        ldx gm_i
        lda gm_icon_art,x
        sta gm_art
        lda gm_icon_y,x
        sta gm_row
        lda #0
        sta gm_j
-       lda gm_j                ; 8 glyphs: 4 columns x 2 rows
        and #3
        clc
        adc #34
        jsr gm_times8
        sta gfx_x0
        stx gfx_x0+1
        lda gm_j
        lsr
        lsr
        clc
        adc gm_row
        jsr gm_times8
        sta gfx_y0
        stx gfx_y0+1
        lda gm_art              ; art: 16 rows x 4 bytes
        asl
        asl
        asl
        asl
        asl
        asl                     ; *64
        sta gm_math
        lda gm_j
        and #4                  ; lower glyph row: +32
        asl
        asl
        asl
        clc
        adc gm_math
        sta gm_math
        lda gm_j
        and #3
        clc
        adc gm_math
        tax
        ldy #0
-       lda gm_icon_bits,x
        sta gfx_bits,y
        inx
        inx
        inx
        inx
        iny
        cpy #8
        bne -
        lda #3
        sta gfx_pen
        jsr gfx_glyph
        bcs gm_icon_done
        inc gm_j
        lda gm_j
        cmp #8
        bne --
        ldx gm_i                ; colours: selected icons inverted
        lda #GM_DESK
        cpx gm_icon_sel
        bne +
        lda #GM_ICON_SELECTED
+       sta gfx_color
        lda #34
        sta gfx_x0
        lda #38
        sta gfx_x1
        lda gm_row
        sta gfx_y0
        clc
        adc #2
        sta gfx_y1
        jsr gm_cells_hi0
        jsr gfx_colors
        bcs gm_icon_done
        ldx gm_i                ; label, centred under the 32-pixel icon
        lda gm_icon_label_lo,x
        sta gm_copy+1
        lda gm_icon_label_hi,x
        sta gm_copy+2
        ldy #0
gm_copy:
        lda $ffff,y
        beq +
        sta gfx_text_buffer,y
        iny
        bne gm_copy
+       sty gfx_text_length
        tya                     ; x = 34*8 + (32 - len*8)/2 = 288 - len*4
        asl
        asl
        sta gm_math
        sec
        lda #<288
        sbc gm_math
        sta gfx_x0
        lda #>288
        sbc #0
        sta gfx_x0+1
        lda gm_row
        clc
        adc #2
        jsr gm_times8
        sta gfx_y0
        stx gfx_y0+1
        lda #0                  ; clear the label row first
        sta gfx_pen
        jsr gm_label_clear
        bcs gm_icon_done
        lda #1
        sta gfx_pen
        jsr gfx_text
gm_icon_done:
        rts
gm_label_clear:
        lda gfx_x0              ; keep the text origin
        pha
        lda gfx_x0+1
        pha
        lda gfx_y0
        pha
        lda #<(31*8)
        sta gfx_x0
        lda #>(31*8)
        sta gfx_x0+1
        lda #<320
        sta gfx_x1
        lda #>320
        sta gfx_x1+1
        pla
        sta gfx_y0
        pha
        clc
        adc #8
        sta gfx_y1
        lda #0
        sta gfx_y1+1
        jsr gfx_rect
        pla
        sta gfx_y0
        pla
        sta gfx_x0+1
        pla
        sta gfx_x0
        rts
; Icon under cell (gm_cx, gm_cy): X = icon or $ff.
gm_icon_hit:
        ldx #$ff
        lda gm_cx
        cmp #31
        bcc ++
        ldx #GM_ICONS-1
-       lda gm_cy
        sec
        sbc gm_icon_y,x
        cmp #3
        bcc +
        dex
        bpl -
+       rts
+       ldx #$ff
        rts

; ---- clicks and keys ---------------------------------------------------------------
gm_click:
        lda ae_ev_result+3      ; pointer cell
        lsr
        lda ae_ev_result+2
        ror
        lsr
        lsr
        sta gm_cx
        lda ae_ev_result+4
        lsr
        lsr
        lsr
        sta gm_cy
        lda #WS_FIND
        sta N_BUFFER
        lda gm_cx
        sta N_BUFFER+1
        lda gm_cy
        sta N_BUFFER+2
        jsr gm_wcall
        bcs gm_click_done
        ldx N_BUFFER
        beq gm_click_desktop
        jsr gm_slot_of          ; a click in the top window's work area
        bcs gm_click_done
        stx gm_slot
        jsr gm_row_under
        bcs gm_click_done
        jsr gm_select_entry
        lda ae_ev_result+6
        cmp #2
        bcc gm_click_done
        jmp gm_open_entry
gm_click_desktop:
        jsr gm_icon_hit
        cpx #$ff
        beq gm_deselect_icon
        cpx gm_icon_sel
        beq +
        stx gm_new_icon
        jsr gm_repaint_icon_sel
+       lda ae_ev_result+6
        cmp #2
        bcc gm_click_done
        jmp gm_open_icon
gm_deselect_icon:
        lda #$ff
        sta gm_new_icon
        jmp gm_repaint_icon_sel
gm_click_done:
        rts
; Repaint the old and new selected icons (the desktop stays uncovered there
; unless a window covers it: redraw through the desktop's visible rectangles).
gm_repaint_icon_sel:
        lda gm_icon_sel
        pha
        lda gm_new_icon
        sta gm_icon_sel
        pla
        jsr gm_redraw_icon_cells
        lda gm_icon_sel
gm_redraw_icon_cells:
        cmp #$ff
        beq +
        tax
        lda #31
        sta ae_ev_result+11
        lda gm_icon_y,x
        sta ae_ev_result+12
        lda #9
        sta ae_ev_result+13
        lda #3
        sta ae_ev_result+14
        jmp gm_redraw_desktop
+       rts

gm_key:
        lda ae_ev_result+1
        cmp #13
        bne +
        jmp gm_open_selection
+       cmp #$11                ; cursor down / up in the top window
        beq gm_key_move
        cmp #$91
        beq gm_key_move
        rts
gm_key_move:
        sta gm_math
        jsr gm_top_slot
        bcs gm_key_done
        stx gm_slot
        ldy gm_win_sel,x
        lda gm_math
        cmp #$11
        bne +
        iny
        tya
        cmp gm_win_count,x
        bcs gm_key_done
        bcc gm_key_set
+       cpy #$ff
        beq gm_key_done
        dey
        bmi gm_key_done
gm_key_set:
        tya
        jsr gm_select_index
        jmp gm_scroll_to_selection
gm_key_done:
        rts

; ---- menu ------------------------------------------------------------------------------
gm_menu_choice:
        lda ae_ev_result+10     ; title
        bne +
        lda #<gm_about
        ldx #>gm_about
        ldy #1
        jmp gm_alert
+       cmp #1
        bne gm_menu_options
        lda ae_ev_result+11
        beq gm_open_selection   ; File: Open
        cmp #2
        bne +
        jsr gm_top_slot         ; File: Close
        bcs +
        stx gm_slot
        jmp gm_close_slot
+       rts
gm_menu_options:
        lda ae_ev_result+11
        bne +
        jmp gm_launcher_leave
+       rts
; Open the selected entry of the top window, else the selected icon.
gm_open_selection:
        jsr gm_top_slot
        bcs +
        stx gm_slot
        lda gm_win_sel,x
        cmp #$ff
        beq +
        jmp gm_open_entry
+       lda gm_icon_sel
        cmp #$ff
        beq +
        jmp gm_open_icon
+       rts

; ---- windows: open a drive ----------------------------------------------------------
gm_open_icon:
        ldx gm_icon_sel
        cpx #2                  ; Trash opens nothing yet (no deleted files kept)
        bcc +
        rts
+       lda gm_icon_dev_lo,x
        bne +
        lda N_BOOTDEVICE        ; icon 0: the boot drive in its format
        sta gm_dev
        lda N_BOOTFORMAT
        sta gm_fmt
        jmp gm_open_drive
+       sta gm_dev
        lda #0                  ; icon 1: device 9 as a D64
        sta gm_fmt
gm_open_drive:
        ldx #0                  ; a free slot
-       lda gm_win_handle,x
        beq +
        inx
        cpx #GM_WINDOWS
        bne -
        lda #<gm_full_alert
        ldx #>gm_full_alert
        ldy #1
        jmp gm_alert
+       stx gm_slot
        jsr gm_scan
        bcc +
        jsr gm_hex_error
        lda #<gm_drive_alert
        ldx #>gm_drive_alert
        ldy #1
        jmp gm_alert
+       lda #WS_CREATE
        sta N_BUFFER
        lda #<(WK_NAME|WK_CLOSER|WK_FULLER|WK_MOVER|WK_SIZER|WK_UPARROW|WK_DNARROW)
        sta N_BUFFER+2
        lda #>WK_VSLIDE
        sta N_BUFFER+3
        lda #0                  ; full: columns 0..30, rows 1..24
        sta N_BUFFER+4
        lda #1
        sta N_BUFFER+5
        lda #31
        sta N_BUFFER+6
        lda #24
        sta N_BUFFER+7
        jsr gm_wcall
        bcs gm_open_fail
        ldx gm_slot
        lda N_BUFFER
        sta gm_win_handle,x
        lda gm_dev
        sta gm_win_dev,x
        lda gm_fmt
        sta gm_win_fmt,x
        lda #0
        sta gm_win_top,x
        lda #$ff
        sta gm_win_sel,x
        lda #WS_SET             ; title "Drive nn"
        sta N_BUFFER
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #WF_NAME
        sta N_BUFFER+2
        ldy #0
-       lda gm_drive_title,y
        sta N_BUFFER+3,y
        iny
        cpy #6
        bne -
        lda gm_dev
        jsr gm_decimal2
        cpx #$30                ; one digit below 10
        bne +
        sta N_BUFFER+9
        lda #0
        sta N_BUFFER+10
        beq ++
+       sta N_BUFFER+10
        stx N_BUFFER+9
        lda #0
        sta N_BUFFER+11
+       jsr gm_wcall
        lda #WS_OPEN            ; staggered by slot
        sta N_BUFFER
        ldx gm_slot
        lda gm_win_handle,x
        sta N_BUFFER+1
        txa
        clc
        adc #1
        sta N_BUFFER+2
        adc #1
        sta N_BUFFER+3
        lda #28
        sta N_BUFFER+4
        lda #16
        sta N_BUFFER+5
        jsr gm_wcall
        bcs gm_open_fail
        jmp gm_update_slider    ; from the opened work area, not the full one
gm_open_fail:
        ldx gm_slot
        jmp gm_free_slot

; Snapshot the directory of gm_dev/gm_fmt into a new owner-32 allocation.
gm_scan:
        lda N_CURRENT
        sta N_OWNER
        lda #GM_PAGES
        sta N_PAGES
        lda #$ff
        sta N_BANK
        jsr N_ALLOC
        bcs gm_scan_done
        ldx gm_slot
        lda N_HANDLE
        sta gm_mem0,x
        lda N_HANDLE+1
        sta gm_mem1,x
        lda N_HANDLE+2
        sta gm_mem2,x
        lda N_HANDLE+3
        sta gm_mem3,x
        lda #0
        sta gm_count
        sta gm_page
gm_scan_page:
        lda N_CURRENT
        sta N_FOWNER
        lda gm_dev
        sta N_FDEVICE
        lda gm_fmt
        sta N_FFORMAT
        lda gm_page
        sta N_DPAGE
        jsr N_DIRPAGE
        bcs gm_scan_fail
        lda N_DNEXT
        sta gm_page
        lda N_DCOUNT
        beq gm_scan_end
        ldx #0                  ; keep the page before N_BUFFER is reused
-       lda N_BUFFER,x
        sta gm_dirpage,x
        inx
        bne -
        ldy #0                  ; staging in N_BUFFER: live entries only
        sty gm_staged
        ldx #0
gm_scan_record:
        lda gm_dirpage,x
        beq gm_scan_skip
        lda gm_count
        clc
        adc gm_staged
        cmp #GM_MAX_ENTRIES
        bcs gm_scan_skip
        stx gm_math
        ldy gm_staged           ; N_BUFFER offset = staged*20
        lda gm_times20,y
        tay
        txa                     ; name: 16 bytes from record offset 2
        pha
        clc
        adc #2
        tax
        lda #16
        sta gm_math2
-       lda gm_dirpage,x
        sta N_BUFFER,y
        inx
        iny
        dec gm_math2
        bne -
        pla
        tax
        lda gm_dirpage,x        ; type, flags, blocks
        sta N_BUFFER,y
        lda gm_dirpage+1,x
        sta N_BUFFER+1,y
        lda gm_dirpage+18,x
        sta N_BUFFER+2,y
        lda gm_dirpage+19,x
        sta N_BUFFER+3,y
        inc gm_staged
        ldx gm_math
gm_scan_skip:
        txa
        clc
        adc #32
        tax
        bne gm_scan_record
        lda gm_staged
        beq gm_scan_next
        jsr gm_select_mem       ; write the staged records
        lda gm_count
        jsr gm_mul20
        sta N_OFFSET
        stx N_OFFSET+1
        lda gm_staged
        jsr gm_mul20
        sta N_COUNT
        stx N_COUNT+1
        jsr N_WRITE
        bcs gm_scan_fail
        lda gm_count
        clc
        adc gm_staged
        sta gm_count
gm_scan_next:
        lda gm_page
        cmp #$ff
        bne gm_scan_page
gm_scan_end:
        ldx gm_slot
        lda gm_count
        sta gm_win_count,x
        clc
gm_scan_done:
        rts
gm_scan_fail:
        pha
        ldx gm_slot
        jsr gm_free_mem
        pla
        sec
        rts

; ---- windows: painting ----------------------------------------------------------------
; Clear the work area inside gm_clip, then draw the visible rows clipped to
; each visible rectangle.
gm_paint_window:
        ldx gm_slot
        lda #WS_FILL
        sta N_BUFFER
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #0
        sta N_BUFFER+2
        lda #GM_PAPER
        sta N_BUFFER+3
        ldx #3
-       lda gm_clip,x
        sta N_BUFFER+4,x
        dex
        bpl -
        jsr gm_wcall
        bcs gm_paint_done
        jsr gm_work             ; gm_wx/wy/ww/wh
        bcs gm_paint_done
        jsr gm_read_rows        ; the visible records into gm_rows
        bcs gm_paint_done
        jsr gm_bind
        bcs gm_paint_done
        lda #WS_GET
        sta N_BUFFER
        ldx gm_slot
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #WF_FIRSTXYWH
        sta N_BUFFER+2
-       jsr gm_wcall
        bcs gm_paint_reset
        lda N_BUFFER+2
        beq gm_paint_reset
        jsr gm_clip_to_rect
        bcs +
        jsr gm_draw_rows
        bcs gm_paint_reset
+       lda #WS_GET
        sta N_BUFFER
        lda #WF_NEXTXYWH
        sta N_BUFFER+2
        jmp -
gm_paint_reset:
        php
        pha
        jsr gfx_clip_defaults
        pla
        plp
gm_paint_done:
        rts
; Rows of the work area (current clip): text, and the selected row's colour.
gm_draw_rows:
        lda #0
        sta gm_i
gm_row_loop:
        lda gm_i
        cmp gm_wh
        bcs gm_rows_done
        ldx gm_slot
        clc
        adc gm_win_top,x
        bcs gm_rows_done
        cmp gm_win_count,x
        bcs gm_rows_done
        sta gm_item
        jsr gm_format_row       ; gfx_text_buffer/length
        lda gm_wx
        jsr gm_times8
        sta gfx_x0
        stx gfx_x0+1
        lda gm_wy
        clc
        adc gm_i
        jsr gm_times8
        sta gfx_y0
        stx gfx_y0+1
        lda #1
        sta gfx_pen
        jsr gfx_text
        bcs gm_rows_fail
        ldx gm_slot
        lda gm_item
        cmp gm_win_sel,x
        bne +
        lda gm_wx               ; selected: inverted cells
        sta gfx_x0
        clc
        adc gm_ww
        sta gfx_x1
        lda gm_wy
        clc
        adc gm_i
        sta gfx_y0
        adc #1
        sta gfx_y1
        jsr gm_cells_hi0
        lda #GM_SELECTED
        sta gfx_color
        jsr gfx_colors
        bcs gm_rows_fail
+       inc gm_i
        jmp gm_row_loop
gm_rows_done:
        clc
gm_rows_fail:
        rts
; "NAME16 TYP BLKS" for entry gm_item from gm_rows.
gm_format_row:
        lda gm_item            ; copy the 20-byte record (offset up to 460)
        ldx gm_slot
        sec
        sbc gm_win_top,x
        jsr gm_mul20
        clc
        adc #<gm_rows
        sta gm_rec_src+1
        txa
        adc #>gm_rows
        sta gm_rec_src+2
        ldx #GM_RECORD-1
gm_rec_src:
        lda $ffff,x
        sta gm_rec,x
        dex
        bpl gm_rec_src
        ldx #0
        ldy #0
-       lda gm_rec,x            ; name: PETSCII padded with $a0 -> ASCII
        cmp #$a0
        beq +
        and #$7f
        cmp #32
        bcs ++
+       lda #32
+       sta gfx_text_buffer,y
        inx
        iny
        cpy #16
        bne -
        lda #32
        sta gfx_text_buffer+16
        lda gm_rec+16           ; type
        and #7
        cmp #5
        bcc +
        lda #0
+       sta gm_math
        asl
        adc gm_math             ; *3
        tay
        lda gm_types,y
        sta gfx_text_buffer+17
        lda gm_types+1,y
        sta gfx_text_buffer+18
        lda gm_types+2,y
        sta gfx_text_buffer+19
        lda #32
        sta gfx_text_buffer+20
        lda gm_rec+18           ; blocks, 4 digits right aligned
        sta gm_num
        lda gm_rec+19
        sta gm_num+1
        ldy #24
        jsr gm_decimal4
        lda #25
        sta gfx_text_length
        rts
; Read the records of rows 0..wh-1 into gm_rows.
gm_read_rows:
        ldx gm_slot
        lda gm_win_count,x
        sec
        sbc gm_win_top,x
        beq gm_read_none
        bcc gm_read_none
        cmp gm_wh
        bcc +
        lda gm_wh
+       jsr gm_mul20
        sta N_COUNT
        stx N_COUNT+1
        jsr gm_select_mem
        ldx gm_slot
        lda gm_win_top,x
        jsr gm_mul20
        sta N_OFFSET
        stx N_OFFSET+1
        jsr N_READ
        bcs gm_read_done
        ldx #0                  ; at most 24*20 = 480 bytes
-       lda N_BUFFER,x
        sta gm_rows,x
        lda N_BUFFER+256,x
        sta gm_rows+256,x
        inx
        bne -
gm_read_none:
        clc
gm_read_done:
        rts
; Work rectangle of the slot's window.
gm_work:
        lda #WS_GET
        sta N_BUFFER
        ldx gm_slot
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #WF_WORKXYWH
        sta N_BUFFER+2
        jsr gm_wcall
        bcs +
        lda N_BUFFER
        sta gm_wx
        lda N_BUFFER+1
        sta gm_wy
        lda N_BUFFER+2
        sta gm_ww
        lda N_BUFFER+3
        sta gm_wh
+       rts
; Rectangle N_BUFFER[0..3] (cells) intersected with gm_clip -> graphics clip.
; Carry set when the intersection is empty.
gm_clip_to_rect:
        lda N_BUFFER
        cmp gm_clip
        bcs +
        lda gm_clip
+       sta gm_ix0
        lda N_BUFFER+1
        cmp gm_clip+1
        bcs +
        lda gm_clip+1
+       sta gm_iy0
        lda N_BUFFER
        clc
        adc N_BUFFER+2
        sta gm_ix1
        lda gm_clip
        clc
        adc gm_clip+2
        cmp gm_ix1
        bcs +
        sta gm_ix1
+       lda N_BUFFER+1
        clc
        adc N_BUFFER+3
        sta gm_iy1
        lda gm_clip+1
        clc
        adc gm_clip+3
        cmp gm_iy1
        bcs +
        sta gm_iy1
+       lda gm_ix0
        cmp gm_ix1
        bcs gm_clip_empty
        lda gm_iy0
        cmp gm_iy1
        bcs gm_clip_empty
        lda gm_ix0
        jsr gm_times8
        sta gfx_x0
        stx gfx_x0+1
        lda gm_ix1
        jsr gm_times8
        sta gfx_x1
        stx gfx_x1+1
        lda gm_iy0
        jsr gm_times8
        sta gfx_y0
        stx gfx_y0+1
        lda gm_iy1
        jsr gm_times8
        sta gfx_y1
        stx gfx_y1+1
        jsr gfx_set_clip
        rts
gm_clip_empty:
        sec
        rts

; ---- scrolling ----------------------------------------------------------------------
gm_arrowed:
        jsr gm_work
        ldx gm_slot
        lda ae_ev_result+11
        cmp #2                  ; 2 line up, 3 line down, 0/1 page up/down
        bne +
        lda gm_win_top,x
        beq gm_scroll_done
        dec gm_win_top,x
        jmp gm_scrolled
+       cmp #3
        bne +
        lda #1
        jmp gm_scroll_down
+       cmp #0
        bne gm_page_down
        lda gm_win_top,x        ; page up
        sec
        sbc gm_wh
        bcs +
        lda #0
+       sta gm_win_top,x
        jmp gm_scrolled
gm_page_down:
        lda gm_wh
gm_scroll_down:
        clc
        adc gm_win_top,x
        sta gm_math
        jsr gm_max_top
        cmp gm_math
        bcc +
        lda gm_math
+       sta gm_win_top,x
gm_scrolled:
        jsr gm_update_slider
        jmp gm_repaint_all
gm_scroll_done:
        rts
; A = the largest top row: max(0, count - wh).
gm_max_top:
        ldx gm_slot
        lda gm_win_count,x
        sec
        sbc gm_wh
        bcs +
        lda #0
+       rts
gm_vslid:
        jsr gm_work
        jsr gm_max_top
        ldx ae_ev_result+11     ; top = pos * max / 255 (rounded)
        jsr gm_mul
        lda gm_prod
        clc
        adc #127
        lda gm_prod+1
        adc #0
        ldx gm_slot
        sta gm_win_top,x
        jmp gm_scrolled
; Keep the selection visible after keyboard moves.
gm_scroll_to_selection:
        jsr gm_work
        ldx gm_slot
        lda gm_win_sel,x
        cmp gm_win_top,x
        bcs +
        sta gm_win_top,x
        jmp gm_scrolled
+       sec
        sbc gm_win_top,x
        cmp gm_wh
        bcc gm_repaint_all
        lda gm_win_sel,x
        sec
        sbc gm_wh
        clc
        adc #1
        sta gm_win_top,x
        jmp gm_scrolled
; Repaint the whole work area of the slot.
gm_repaint_all:
        jsr gm_work
        lda gm_wx
        sta gm_clip
        lda gm_wy
        sta gm_clip+1
        lda gm_ww
        sta gm_clip+2
        lda gm_wh
        sta gm_clip+3
        jmp gm_paint_window
; Slider size = wh*255/count, position = top*255/max(1, count-wh).
gm_update_slider:
        jsr gm_work
        ldx gm_slot
        lda #255
        sta gm_math3
        lda gm_win_count,x
        beq +
        cmp gm_wh
        bcc +
        beq +
        lda gm_wh
        ldx #255
        jsr gm_mul
        ldx gm_slot
        lda gm_win_count,x
        jsr gm_div              ; gm_prod / A
        sta gm_math3
+       lda #WF_VSLSIZE
        ldy gm_math3
        jsr gm_wset_value
        jsr gm_max_top
        sta gm_math3
        lda #0
        ldy gm_math3
        beq +
        ldx gm_slot
        lda gm_win_top,x
        ldx #255
        jsr gm_mul
        lda gm_math3
        jsr gm_div
+       tay
        lda #WF_VSLIDE
        jmp gm_wset_value
; A = field, Y = value byte.
gm_wset_value:
        sty N_BUFFER+3
gm_wset_simple:
        sta N_BUFFER+2
        lda #WS_SET
        sta N_BUFFER
        ldx gm_slot
        lda gm_win_handle,x
        sta N_BUFFER+1
        jmp gm_wcall
gm_set_rect:
        ldx #3
-       lda gm_rect,x
        sta N_BUFFER+3,x
        dex
        bpl -
        lda #WF_CURRXYWH
        jmp gm_wset_simple
gm_fulled:
        lda #WS_GET             ; full size, or back to the previous one
        sta N_BUFFER
        ldx gm_slot
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #WF_FULLXYWH
        sta N_BUFFER+2
        jsr gm_wcall
        ldx #3
-       lda N_BUFFER,x
        sta gm_rect,x
        dex
        bpl -
        lda #WS_GET
        sta N_BUFFER
        ldx gm_slot
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #WF_CURRXYWH
        sta N_BUFFER+2
        jsr gm_wcall
        ldx #3
-       lda N_BUFFER,x
        cmp gm_rect,x
        bne +
        dex
        bpl -
        lda #WS_GET
        sta N_BUFFER
        ldx gm_slot
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #WF_PREVXYWH
        sta N_BUFFER+2
        jsr gm_wcall
        ldx #3
-       lda N_BUFFER,x
        sta gm_rect,x
        dex
        bpl -
+       jsr gm_set_rect
        jmp gm_update_slider

; ---- selection and opening entries -------------------------------------------------------
; Row under gm_cy in the slot's work area: A = entry, carry set if none.
gm_row_under:
        jsr gm_work
        lda gm_cy
        sec
        sbc gm_wy
        bcc +
        ldx gm_slot
        clc
        adc gm_win_top,x
        cmp gm_win_count,x
        bcs +
        clc
        rts
+       sec
        rts
gm_select_entry:
gm_select_index:
        ldx gm_slot
        cmp gm_win_sel,x
        beq +
        sta gm_win_sel,x
        jmp gm_repaint_all
+       rts
; Launch the selected entry through the dispatcher (it checks the program).
gm_open_entry:
        ldx gm_slot
        lda gm_win_sel,x
        sta gm_item
        jsr gm_work
        ldx gm_slot             ; read the one record
        lda gm_item
        jsr gm_mul20
        sta N_OFFSET
        stx N_OFFSET+1
        lda #GM_RECORD
        sta N_COUNT
        lda #0
        sta N_COUNT+1
        jsr gm_select_mem
        jsr N_READ
        bcs gm_launch_fail
        ldx #0
-       lda N_BUFFER,x
        cmp #$a0
        beq +
        sta N_APPNAME,x
        inx
        cpx #16
        bne -
+       cpx #0
        beq gm_launch_fail
        stx N_NAMELEN
        ldx gm_slot
        lda gm_win_dev,x
        sta N_DEVICE
        lda gm_win_fmt,x
        sta N_APPFORMAT
        jsr pm_close
        lda #0
        jmp N_REPLACE
gm_launch_fail:
        rts
gm_launcher_leave:
        jsr pm_close
gm_launcher:
        lda N_BOOTFORMAT        ; the card launcher is "cards" on the boot disk
        sta N_APPFORMAT
        lda N_BOOTDEVICE
        sta N_DEVICE
        ldx #4
-       lda gm_cards_name,x
        sta N_APPNAME,x
        dex
        bpl -
        lda #5
        sta N_NAMELEN
        lda #0                  ; A is the exit result
        jmp N_REPLACE

; ---- windows: slots -------------------------------------------------------------------------
gm_slot_of:                     ; X = AES handle -> X = slot, carry set if none
        txa
        ldx #GM_WINDOWS-1
-       cmp gm_win_handle,x
        beq +
        dex
        bpl -
        sec
        rts
+       clc
        rts
gm_top_slot:
        lda #WS_GET
        sta N_BUFFER
        lda #WF_TOP
        sta N_BUFFER+2
        jsr gm_wcall
        bcs +
        ldx N_BUFFER
        beq +
        jmp gm_slot_of
+       sec
        rts
gm_close_slot:
        ldx gm_slot
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #WS_CLOSE
        sta N_BUFFER
        jsr gm_wcall
        ldx gm_slot
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #WS_DELETE
        sta N_BUFFER
        jsr gm_wcall
        ldx gm_slot
gm_free_slot:
        lda #0
        sta gm_win_handle,x
gm_free_mem:
        stx gm_math4
        jsr gm_select_mem_x
        jsr N_FREE
        ldx gm_math4
        lda #0
        sta gm_mem0,x
        rts
gm_select_mem:
        ldx gm_slot
gm_select_mem_x:
        lda N_CURRENT
        sta N_OWNER
        lda gm_mem0,x
        sta N_HANDLE
        lda gm_mem1,x
        sta N_HANDLE+1
        lda gm_mem2,x
        sta N_HANDLE+2
        lda gm_mem3,x
        sta N_HANDLE+3
        rts

; ---- arithmetic and text --------------------------------------------------------------------
gm_times8:                      ; A*8 -> A lo, X hi
        ldx #0
        stx gm_t8
        asl
        rol gm_t8
        asl
        rol gm_t8
        asl
        rol gm_t8
        ldx gm_t8
        rts
gm_mul20:                       ; A*20 -> A lo, X hi
        ldx #20
gm_mul:                         ; A*X -> gm_prod; also A lo, X hi
        sta gm_mul_a
        stx gm_mul_b
        lda #0
        sta gm_prod
        sta gm_prod+1
        ldx #8
-       lsr gm_mul_b
        bcc +
        clc
        lda gm_prod+1
        adc gm_mul_a
        sta gm_prod+1
+       ror gm_prod+1
        ror gm_prod
        dex
        bne -
        lda gm_prod
        ldx gm_prod+1
        rts
gm_div:                         ; gm_prod / A -> A (quotient < 256)
        sta gm_divisor
        lda #0
        ldx #16
-       asl gm_prod
        rol gm_prod+1
        rol
        cmp gm_divisor
        bcc +
        sbc gm_divisor
        inc gm_prod
+       dex
        bne -
        lda gm_prod
        rts
gm_cells_hi0:
        lda #0
        sta gfx_x0+1
        sta gfx_x1+1
        sta gfx_y0+1
        sta gfx_y1+1
        rts
; A (0..99) -> X tens digit, A units digit (ASCII; a leading 0 stays).
gm_decimal2:
        ldx #$30
-       cmp #10
        bcc +
        sbc #10
        inx
        bne -
+       ora #$30
        rts
; gm_num (0..9999) as 4 right-aligned digits ending at gfx_text_buffer+Y.
gm_decimal4:
        ldx #4
-       lda #0                  ; divide by 10
        stx gm_math2
        ldx #16
-       asl gm_num
        rol gm_num+1
        rol
        cmp #10
        bcc +
        sbc #10
        inc gm_num
+       dex
        bne -
        ora #$30
        sta gfx_text_buffer,y
        dey
        ldx gm_math2
        dex
        bne --
        ldx #3                  ; leading zeros to spaces
        iny
-       lda gfx_text_buffer,y
        cmp #$30
        bne +
        lda #32
        sta gfx_text_buffer,y
        iny
        dex
        bne -
+       rts
gm_hex_error:                   ; N_BROWSERERROR / A as two hex digits in the alerts
        pha
        lsr
        lsr
        lsr
        lsr
        tax
        lda gm_hex_digits,x
        sta gm_start_alert_hex
        sta gm_drive_alert_hex
        pla
        and #15
        tax
        lda gm_hex_digits,x
        sta gm_start_alert_hex+1
        sta gm_drive_alert_hex+1
        rts

; ---- data ----------------------------------------------------------------------------------------
gm_hex_digits: .byte 48,49,50,51,52,53,54,55,56,57,65,66,67,68,69,70
gm_aesvc_name: .text "aesvc.prg"
gm_cards_name: .text "cards"
gm_drive_title: .byte 68,114,105,118,101,32      ; "Drive "
gm_types: .byte 68,69,76,83,69,81,80,82,71,85,83,82,82,69,76   ; DEL SEQ PRG USR REL
gm_icon_y: .byte 2,6,20
gm_icon_art: .byte 0,0,1
gm_icon_dev_lo: .byte 0,9,0     ; 0: the boot drive
gm_icon_label_lo: .byte <gm_label_boot,<gm_label_9,<gm_label_trash
gm_icon_label_hi: .byte >gm_label_boot,>gm_label_9,>gm_label_trash
gm_label_boot: .byte 66,111,111,116,0                    ; Boot
gm_label_9: .byte 68,114,105,118,101,32,57,0            ; Drive 9
gm_label_trash: .byte 84,114,97,115,104,0               ; Trash
; 32x16 icons, 4 bytes per row: drive, trash
gm_icon_bits:
        .byte $7f,$ff,$ff,$fe, $40,$00,$00,$02, $40,$00,$00,$02, $47,$ff,$ff,$e2
        .byte $40,$00,$00,$02, $40,$00,$00,$02, $40,$00,$00,$02, $40,$00,$00,$02
        .byte $40,$00,$00,$02, $40,$00,$00,$02, $40,$00,$00,$02, $40,$00,$00,$1a
        .byte $40,$00,$00,$1a, $40,$00,$00,$02, $7f,$ff,$ff,$fe, $00,$00,$00,$00
        .byte $00,$0f,$f0,$00, $3f,$ff,$ff,$fc, $3f,$ff,$ff,$fc, $10,$00,$00,$08
        .byte $12,$49,$24,$88, $12,$49,$24,$88, $12,$49,$24,$88, $12,$49,$24,$88
        .byte $12,$49,$24,$88, $12,$49,$24,$88, $12,$49,$24,$88, $12,$49,$24,$88
        .byte $12,$49,$24,$88, $10,$00,$00,$08, $1f,$ff,$ff,$f8, $00,$00,$00,$00
gm_times20: .byte 0,20,40,60,80,100,120,140
; Desk:About uOS...;File:Open^O|-|Close^W;Options:Launcher^L
gm_menu: .byte 68,101,115,107,58,65,98,111,117,116,32,117,79,83,46,46,46,59
        .byte 70,105,108,101,58,79,112,101,110,94,79,124,45,124,67,108,111,115,101,94,87,59
        .byte 79,112,116,105,111,110,115,58,76,97,117,110,99,104,101,114,94,76,0
; [1][uOS GEM desktop|AES 1.4 on the C128][OK]
gm_about: .byte 91,49,93,91,117,79,83,32,71,69,77,32,100,101,115,107,116,111,112,124
        .byte 65,69,83,32,49,46,52,32,111,110,32,116,104,101,32,67,49,50,56,93,91,79,75,93,0
; [3][Could not start that|program: error $xx][OK]
gm_start_alert: .byte 91,51,93,91,67,111,117,108,100,32,110,111,116,32,115,116,97,114,116,32
        .byte 116,104,97,116,124,112,114,111,103,114,97,109,58,32,101,114,114,111,114,32,36
gm_start_alert_hex: .byte 48,48,93,91,79,75,93,0
; [3][Could not read this|drive: error $xx][OK]
gm_drive_alert: .byte 91,51,93,91,67,111,117,108,100,32,110,111,116,32,114,101,97,100,32,116
        .byte 104,105,115,124,100,114,105,118,101,58,32,101,114,114,111,114,32,36
gm_drive_alert_hex: .byte 48,48,93,91,79,75,93,0
; [1][Four folder windows|are already open.][OK]
gm_full_alert: .byte 91,49,93,91,70,111,117,114,32,102,111,108,100,101,114,32,119,105,110,100
        .byte 111,119,115,124,97,114,101,32,97,108,114,101,97,100,121,32,111,112,101,110,46,93,91,79,75,93,0

gm_surface: .fill 4,0
gm_file: .fill 4,0
gm_start_error: .byte 0
gm_icon_sel: .byte $ff
gm_new_icon: .byte 0
gm_slot: .byte 0
gm_dev: .byte 0
gm_fmt: .byte 0
gm_count: .byte 0
gm_page: .byte 0
gm_staged: .byte 0
gm_item: .byte 0
gm_cx: .byte 0
gm_cy: .byte 0
gm_i: .byte 0
gm_j: .byte 0
gm_art: .byte 0
gm_row: .byte 0
gm_math: .byte 0
gm_math2: .byte 0
gm_math3: .byte 0
gm_math4: .byte 0
gm_t8: .byte 0
gm_num: .word 0
gm_mul_a: .byte 0
gm_mul_b: .byte 0
gm_prod: .word 0
gm_divisor: .byte 0
gm_wx: .byte 0
gm_wy: .byte 0
gm_ww: .byte 0
gm_wh: .byte 0
gm_ix0: .byte 0
gm_iy0: .byte 0
gm_ix1: .byte 0
gm_iy1: .byte 0
gm_clip: .fill 4,0
gm_rect: .fill 4,0
gm_win_handle: .fill GM_WINDOWS,0
gm_win_dev: .fill GM_WINDOWS,0
gm_win_fmt: .fill GM_WINDOWS,0
gm_win_count: .fill GM_WINDOWS,0
gm_win_top: .fill GM_WINDOWS,0
gm_win_sel: .fill GM_WINDOWS,$ff
gm_mem0: .fill GM_WINDOWS,0
gm_mem1: .fill GM_WINDOWS,0
gm_mem2: .fill GM_WINDOWS,0
gm_mem3: .fill GM_WINDOWS,0
gm_rec: .fill GM_RECORD,0
gm_rows: .fill 512,0
gm_dirpage: .fill 256,0
.include "aes-client.inc"
.include "graphics/graphics-core.inc"
.include "graphics/text-core.inc"
.include "input/pointer.inc"
gm_end:
.cerror gm_end > N_APPLIMIT, "the GEM desktop exceeds its slot"
