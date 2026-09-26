; GEM desktop (docs/GEM-DESKTOP.md): drive icons and folder windows on the
; AES. Written as "browse" on the GEM boot disk, so launched apps return here.
.include "api.inc"
.include "aes-api.inc"
AE_POINTER = 1
GM_WINDOWS = 4
GM_RECORD = 21                 ; name 16, type, flags, blocks (word), directory ordinal
GM_CHUNK = 24                  ; records per N_BUFFER transfer (504 bytes)
GM_MAX_ENTRIES = 195            ; 16 pages of records: the $5000 workspace, a window's snapshot
GM_WORKSPACE = $5000             ; bank-0 workspace reserved at start (like Files)
GM_PAGES = (GM_MAX_ENTRIES*GM_RECORD+255)/256
GM_PAPER = $61                 ; window work: blue ink on white
GM_SELECTED = $16              ; selected row: white on blue
GM_DESK = $16                  ; desktop: white icons on blue
GM_ICON_SELECTED = $61
GM_ICONS = 4                   ; Boot, Drive 9, Trash, and USB when the Ultimate answers
GM_USB = 3
GM_APP_PAGES = 96              ; the core, then the GDDLG.PRG module window
GM_MOP_INFO = 1                ; module operations
GM_MOP_PREFS = 2
GM_MOP_FORMAT = 3
GM_MOP_CONTROL = 4
GM_REC_COUNT = 9               ; desktop record: window count, then windows
GM_REC_WINDOWS = 10
* = N_APPBASE
gm_image:
        .text "napp"
        .byte 1,1,14,<(gm_module-gm_image)
        .word gm_module-gm_image
        .byte GM_APP_PAGES,>(gm_module-gm_image)
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
        lda N_CURRENT           ; the sort workspace: bank 0 $5000..$5fff
        sta N_OWNER
        lda #0
        sta N_BANK
        lda #>GM_WORKSPACE
        sta N_PAGE
        lda #16
        sta N_PAGES
        jsr N_RESERVE
        bcs gm_setup_done
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
        lda gm_desk_color
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
        jsr gm_ult_probe
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
        jsr ae_menu_install
        bcs gm_aes_failed
        jsr gm_restore          ; the desktop as it was left, or as saved
        jmp gm_view_checks
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
        jmp gm_close_or_up
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
        cmp gm_icons_n
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
        lda gm_desk_color
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
        ldx gm_icons_n
        dex
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
        lda #0
        sta gm_drag
        jsr gm_click_at
        jmp gm_release
gm_pointer_cell:
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
        rts
gm_click_at:
        jsr gm_pointer_cell
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
        bcs +
        inc gm_drag             ; a single press on a row may drag it
        rts
+       jmp gm_open_entry
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
+       cmp #$38                ; 8 or 9: select that drive's icon and open it
        beq gm_key_drive
        cmp #$39
        beq gm_key_drive
        cmp #$11                ; cursor down / up in the top window
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
gm_key_drive:
        and #15
        ldx #0                  ; the boot drive's icon
        cmp N_BOOTDEVICE
        beq +
        ldx #1                  ; drive 9's icon
        cmp #9
        bne gm_key_done
+       cpx gm_icon_sel
        beq +
        stx gm_new_icon
        jsr gm_repaint_icon_sel
+       jmp gm_open_icon

; ---- menu ------------------------------------------------------------------------------
gm_menu_choice:
        lda ae_ev_result+10     ; title
        bne +
        lda ae_ev_result+11     ; Desk: About, or the Control Panel
        bne gm_menu_control
        lda #<gm_about
        ldx #>gm_about
        ldy #1
        jmp gm_alert
gm_menu_control:
        lda #GM_MOP_CONTROL
        jmp gm_module_run
+       cmp #1
        bne gm_menu_options
        lda ae_ev_result+11
        beq gm_open_selection   ; File: Open
        cmp #1
        bne +
        jmp gm_show_info
+       cmp #3
        bne +
        jmp gm_delete
+       cmp #4
        bne +
        lda #GM_MOP_FORMAT
        jmp gm_module_run
+       cmp #6
        bne +
        jsr gm_top_slot         ; File: Close
        bcs +
        stx gm_slot
        jmp gm_close_slot
+       rts
gm_menu_options:
        cmp #2
        bne +
        jmp gm_menu_view
+       lda ae_ev_result+11
        bne +
        lda #GM_MOP_PREFS
        jmp gm_module_run
+       cmp #1
        bne +
        jmp gm_save_desktop
+       cmp #2
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
        cpx #2                  ; Trash opens nothing (no deleted files kept)
        bne +
        rts
+       jsr gm_icon_drive
gm_open_drive:
        ldx #0                  ; a free slot
-       lda gm_win_handle,x
        beq +
        inx
        cpx #GM_WINDOWS
        bne -
        lda gm_restoring        ; restoring: quietly open nothing
        bne gm_open_quiet
        lda #<gm_full_alert
        ldx #>gm_full_alert
        ldy #1
        jmp gm_alert
+       stx gm_slot
        lda gm_fmt              ; a new USB window starts at the root
        cmp #3
        bne +
        jsr gm_path_root
+       jsr gm_scan
        bcc +
        ldx gm_restoring
        bne gm_open_quiet
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
        jsr gm_set_title
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
        lda gm_restoring        ; restoring: the saved rectangle
        beq +
        ldx #3
-       lda gm_orect,x
        sta N_BUFFER+2,x
        dex
        bpl -
+       jsr gm_wcall
        bcs gm_open_fail
        jmp gm_update_slider    ; from the opened work area, not the full one
gm_open_fail:
        ldx gm_slot
        jmp gm_free_slot
gm_open_quiet:
        rts

; X = drive icon -> gm_dev, gm_fmt (3: Ultimate DOS)
gm_icon_drive:
        lda gm_icon_dev_lo,x
        bne +
        lda N_BOOTDEVICE        ; icon 0: the boot drive in its format
        sta gm_dev
        lda N_BOOTFORMAT
        sta gm_fmt
        rts
+       sta gm_dev
        lda #0                  ; icon 1: device 9 as a D64
        cpx #GM_USB
        bne +
        lda #3                  ; USB: Ultimate DOS context 1
+       sta gm_fmt
        rts
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
        lda gm_fmt
        cmp #3
        bne gm_scan_page
        jmp gm_scan_ult
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
        ldx #0
gm_scan_record:
        lda gm_dirpage,x
        beq gm_scan_skip
        ldy gm_count
        cpy #GM_MAX_ENTRIES
        bcs gm_scan_skip
        lda gm_addr_lo,y        ; gm_sortbuf record gm_count
        sta gm_rec_dst+1
        lda gm_addr_hi,y
        sta gm_rec_dst+2
        stx gm_math
        ldy #0
-       lda gm_dirpage+2,x      ; name
        jsr gm_rec_put
        inx
        cpy #16
        bne -
        ldx gm_math
        lda gm_dirpage,x        ; type, flags, blocks, directory ordinal
        jsr gm_rec_put
        lda gm_dirpage+1,x
        jsr gm_rec_put
        lda gm_dirpage+18,x
        jsr gm_rec_put
        lda gm_dirpage+19,x
        jsr gm_rec_put
        lda gm_count
        jsr gm_rec_put
        inc gm_count
gm_scan_skip:
        txa
        clc
        adc #32
        tax
        bne gm_scan_record
        lda gm_page
        cmp #$ff
        bne gm_scan_page
gm_scan_end:
        ldx gm_slot
        lda gm_count
        sta gm_win_count,x
        jsr gm_sort_write
        bcs gm_scan_fail
gm_scan_done:
        rts
gm_scan_fail:
        pha
        ldx gm_slot
        jsr gm_free_mem
        pla
        sec
        rts

; ---- View: sorting a snapshot --------------------------------------------------------
; Order gm_count records of gm_sortbuf by gm_view and write them to the slot's
; allocation. Carry set on a heap error.
gm_sort_write:
        ldx #0
-       cpx gm_count
        beq +
        txa
        sta gm_order,x
        inx
        bne -
+       jsr gm_sort
        lda #0
        sta gm_k
gm_write_chunk:
        lda gm_count
        sec
        sbc gm_k                ; records left
        bne +
        clc
        rts
+       jsr gm_chunk_size
        lda #<N_BUFFER
        sta gm_rec_dst+1
        lda #>N_BUFFER
        sta gm_rec_dst+2
        lda #0
        sta gm_j
-       lda gm_k
        clc
        adc gm_j
        tax
        ldy gm_order,x
        lda gm_addr_lo,y
        sta gm_rec_src2+1
        lda gm_addr_hi,y
        sta gm_rec_src2+2
        jsr gm_copy_rec
        inc gm_j
        lda gm_j
        cmp gm_m
        bne -
        jsr gm_chunk_heap
        jsr N_WRITE
        bcs gm_chunk_fail
        jsr gm_chunk_next
        jmp gm_write_chunk
gm_chunk_fail:
        rts
; Reload the slot's snapshot into gm_sortbuf, then sort and write it back.
gm_resort_slot:
        ldx gm_slot
        lda gm_win_count,x
        sta gm_count
        lda #$ff
        sta gm_win_sel,x
        lda #0
        sta gm_k
gm_load_chunk:
        lda gm_count
        sec
        sbc gm_k
        beq gm_sort_write
        jsr gm_chunk_size
        jsr gm_chunk_heap
        jsr N_READ
        bcs gm_chunk_fail
        lda #<N_BUFFER
        sta gm_rec_src2+1
        lda #>N_BUFFER
        sta gm_rec_src2+2
        lda #0
        sta gm_j
-       lda gm_k
        clc
        adc gm_j
        tay
        lda gm_addr_lo,y
        sta gm_rec_dst+1
        lda gm_addr_hi,y
        sta gm_rec_dst+2
        jsr gm_copy_rec
        inc gm_j
        lda gm_j
        cmp gm_m
        bne -
        jsr gm_chunk_next
        jmp gm_load_chunk
gm_chunk_size:                  ; A records left -> gm_m, at most GM_CHUNK
        cmp #GM_CHUNK
        bcc +
        lda #GM_CHUNK
+       sta gm_m
        rts
gm_chunk_heap:                  ; the slot's records gm_k..gm_k+gm_m-1
        jsr gm_select_mem
        lda gm_k
        jsr gm_mulrec
        sta N_OFFSET
        stx N_OFFSET+1
        lda gm_m
        jsr gm_mulrec
        sta N_COUNT
        stx N_COUNT+1
        rts
gm_chunk_next:
        lda gm_k
        clc
        adc gm_m
        sta gm_k
        rts
; Copy one record from gm_rec_src2 to gm_rec_dst; advance both addresses.
gm_copy_rec:
        ldy #0
gm_rec_src2:
        lda $ffff,y
        jsr gm_rec_put
        cpy #GM_RECORD
        bne gm_rec_src2
        lda gm_rec_src2+1
        clc
        adc #GM_RECORD
        sta gm_rec_src2+1
        bcc +
        inc gm_rec_src2+2
+       lda gm_rec_dst+1
        clc
        adc #GM_RECORD
        sta gm_rec_dst+1
        bcc +
        inc gm_rec_dst+2
+       rts
gm_rec_put:
gm_rec_dst:
        sta $ffff,y
        iny
        rts
; Shell sort of gm_order[0..gm_count) with gm_compare.
gm_sort:
        ldx #GM_GAP_COUNT-1
gm_gap_loop:
        stx gm_gapi
        lda gm_gaps,x
        sta gm_gap
        cmp gm_count
        bcs gm_next_gap
        sta gm_i2
gm_ins_outer:
        ldx gm_i2
        lda gm_order,x
        sta gm_ins_val
        stx gm_pos
gm_ins_inner:
        lda gm_pos
        sec
        sbc gm_gap
        bcc gm_ins_place
        tax
        lda gm_order,x
        sta gm_other
        jsr gm_compare
        bcc gm_ins_place
        ldx gm_pos
        lda gm_other
        sta gm_order,x
        lda gm_pos
        sec
        sbc gm_gap
        sta gm_pos
        jmp gm_ins_inner
gm_ins_place:
        ldx gm_pos
        lda gm_ins_val
        sta gm_order,x
        inc gm_i2
        lda gm_i2
        cmp gm_count
        bcc gm_ins_outer
gm_next_gap:
        ldx gm_gapi
        dex
        bpl gm_gap_loop
        rts
; Carry set when record gm_other sorts after record gm_ins_val. Name order maps
; the $a0 padding below every character; size puts larger files first; the
; directory ordinal breaks ties, and alone is "Unsorted".
gm_compare:
        ldy gm_other
        lda gm_addr_lo,y
        sta gm_fa+1
        lda gm_addr_hi,y
        sta gm_fa+2
        ldy gm_ins_val
        lda gm_addr_lo,y
        sta gm_fb+1
        lda gm_addr_hi,y
        sta gm_fb+2
        ldx gm_view
        cpx #3
        beq gm_cmp_ordinal
        cpx #1
        bne +
        ldy #16                 ; type
        jsr gm_cmp_raw
        bne gm_cmp_out
+       cpx #2
        bne gm_cmp_name
        ldy #19                 ; blocks, larger first
        jsr gm_cmp_rev
        bne gm_cmp_out
        ldy #18
        jsr gm_cmp_rev
        bne gm_cmp_out
gm_cmp_name:
        ldy #0
-       jsr gm_fb
        jsr gm_name_key
        sta gm_cmpb
        jsr gm_fa
        jsr gm_name_key
        cmp gm_cmpb
        bne gm_cmp_out
        iny
        cpy #16
        bne -
gm_cmp_ordinal:
        ldy #20
        jsr gm_cmp_raw
gm_cmp_out:
        bne +
        clc
+       rts
gm_cmp_raw:
        jsr gm_fb
        sta gm_cmpb
        jsr gm_fa
        cmp gm_cmpb
        rts
gm_cmp_rev:
        jsr gm_fa
        sta gm_cmpb
        jsr gm_fb
        cmp gm_cmpb
        rts
gm_fa:
        lda $ffff,y
        rts
gm_fb:
        lda $ffff,y
        rts
gm_name_key:
        cmp #$a0
        bne +
        lda #0
        rts
+       and #$7f
        rts
; View menu: sort every open window again.
gm_menu_view:
        lda ae_ev_result+11
gm_set_view:                    ; A = 0 name, 1 type, 2 size, 3 unsorted
        cmp gm_view
        beq gm_view_done
        sta gm_view
        jsr gm_view_checks
        lda #GM_WINDOWS-1
        sta gm_vslot
-       ldx gm_vslot
        lda gm_win_handle,x
        beq +
        stx gm_slot
        jsr gm_resort_slot
        bcs gm_view_fail
        jsr gm_repaint_all
+       dec gm_vslot
        bpl -
gm_view_done:
        rts
gm_view_fail:
        jsr gm_hex_error
        lda #<gm_drive_alert
        ldx #>gm_drive_alert
        ldy #1
        jmp gm_alert
; Check the current View item, clear the others.
gm_view_checks:
        lda #3
        sta gm_vslot
-       ldy #0
        lda gm_vslot
        cmp gm_view
        bne +
        iny
+       tax
        lda #2
        jsr ae_menu_set
        bcs +
        dec gm_vslot
        bpl -
        clc
+       rts

; ---- Show Info ------------------------------------------------------------------------
; The selected entry of the top window, else the selected drive icon.
gm_show_info:
        lda #0
        sta gm_alen
        lda #<gm_s_head
        ldx #>gm_s_head
        jsr gm_astr
        jsr gm_top_slot
        bcs gm_info_icon
        stx gm_slot
        lda gm_win_sel,x
        cmp #$ff
        beq gm_info_icon
        lda gm_win_fmt,x        ; Show Info and rename are IEC for now
        cmp #3
        bne +
        jmp gm_not_usb
+       jsr gm_read_record
        bcs gm_info_fail
        lda #GM_MOP_INFO
        jmp gm_module_run
; Append gm_rec's name, up to its padding, as printable alert text.
gm_aname:
        ldy #0
gm_info_name:
        lda gm_rec,y
        cmp #$a0
        beq gm_aname_done       ; the padding ends the name
        jsr gm_printable
        jsr gm_aput
        iny
        cpy #16
        bne gm_info_name
gm_aname_done:
        rts
; Append "Type: TYP  Blocks: N" for gm_rec.
gm_atype:
        lda #<(gm_s_type+1)
        ldx #>(gm_s_type+1)
        jsr gm_astr
        lda gm_rec+16
        and #7
        cmp #7
        bcc +
        lda #0
+       sta gm_math
        asl
        adc gm_math
        tay
        ldx #3
-       lda gm_types,y
        stx gm_math
        jsr gm_aput
        ldx gm_math
        iny
        dex
        bne -
        lda #<gm_s_blocks
        ldx #>gm_s_blocks
        jsr gm_astr
        lda gm_rec+18
        sta gm_num
        lda gm_rec+19
        sta gm_num+1
        jmp gm_anum
gm_info_end:
        lda #<gm_s_ok
        ldx #>gm_s_ok
        jsr gm_astr
        lda #0
        jsr gm_aput
        lda #<gm_abuf
        ldx #>gm_abuf
        ldy #1
        jmp gm_alert
gm_info_fail:
        jmp gm_view_fail
; A drive icon: its file count and blocks used, from the directory pages.
gm_info_icon:
        ldx gm_icon_sel
        cpx #GM_USB
        bne +
        jmp gm_not_usb
+       cpx #2
        bcc +
        rts                     ; nothing selected, or Trash
+       jsr gm_icon_drive
        lda #<gm_drive_title
        ldx #>gm_drive_title
        jsr gm_astr
        lda gm_dev
        sta gm_num
        lda #0
        sta gm_num+1
        jsr gm_anum
        lda #0
        sta gm_count
        sta gm_page
        sta gm_total
        sta gm_total+1
gm_info_page:
        lda N_CURRENT
        sta N_FOWNER
        lda gm_dev
        sta N_FDEVICE
        lda gm_fmt
        sta N_FFORMAT
        lda gm_page
        sta N_DPAGE
        jsr N_DIRPAGE
        bcs gm_info_fail
        lda N_DNEXT
        sta gm_page
        lda N_DCOUNT
        beq gm_info_sum
        ldx #0
-       lda N_BUFFER,x
        beq +
        inc gm_count
        lda gm_total
        clc
        adc N_BUFFER+18,x
        sta gm_total
        lda gm_total+1
        adc N_BUFFER+19,x
        sta gm_total+1
+       txa
        clc
        adc #32
        tax
        bne -
        lda gm_page
        cmp #$ff
        bne gm_info_page
gm_info_sum:
        lda #<gm_s_files
        ldx #>gm_s_files
        jsr gm_astr
        lda gm_count
        sta gm_num
        lda #0
        sta gm_num+1
        jsr gm_anum
        lda #<gm_s_used
        ldx #>gm_s_used
        jsr gm_astr
        lda gm_total
        sta gm_num
        lda gm_total+1
        sta gm_num+1
        jsr gm_anum
        lda gm_dev              ; free space, as the drive's listing says it
        sta dc_device
        jsr dc_blocks_free
        bcs +
        lda #<gm_s_free
        ldx #>gm_s_free
        jsr gm_astr
        lda dc_free
        sta gm_num
        lda dc_free+1
        sta gm_num+1
        jsr gm_anum
+       jmp gm_info_end
; Alert text builder: gm_abuf/gm_alen.
gm_astr:                        ; append the zero-terminated string at A/X
        sta gm_astr_src+1
        stx gm_astr_src+2
        ldy #0
gm_astr_src:
        lda $ffff,y
        beq +
        jsr gm_aput
        iny
        bne gm_astr_src
+       rts
gm_aput:                        ; keeps Y
        ldx gm_alen
        sta gm_abuf,x
        inc gm_alen
        rts
gm_anum:                        ; append gm_num (0..9999) in decimal
        ldy #3
        jsr gm_decimal4
        ldy #0
-       lda gfx_text_buffer,y
        cmp #32
        beq +
        jsr gm_aput
+       iny
        cpy #4
        bne -
        rts

; ---- Delete and Trash --------------------------------------------------------------
; The selected entry of gm_slot -> gm_rec. Carry set on a heap error.
gm_read_record:
        ldx gm_slot
        lda gm_win_sel,x
        jsr gm_mulrec
        sta N_OFFSET
        stx N_OFFSET+1
        lda #GM_RECORD
        sta N_COUNT
        lda #0
        sta N_COUNT+1
        jsr gm_select_mem
        jsr N_READ
        bcs +
        ldx #GM_RECORD-1
-       lda N_BUFFER,x
        sta gm_rec,x
        dex
        bpl -
        clc
+       rts
; File:Delete (Ctrl-D), or an entry dropped on Trash: confirm, scratch it on
; the drive, check the drive's count, and list the drive's windows again.
gm_delete:
        jsr gm_top_slot
        bcs gm_del_none
        stx gm_slot
        lda gm_win_sel,x
        cmp #$ff
        beq gm_del_none
        jsr gm_read_record
        bcc +
        jmp gm_view_fail
+       ldx gm_slot             ; USB: any name; the drive gets the full path
        lda gm_win_fmt,x
        cmp #3
        beq gm_del_ask
        ldx #0                  ; "S0:" and the exact name; no DOS pattern characters
gm_del_copy:
        lda gm_rec,x
        cmp #$a0
        beq gm_del_named
        ldy #gm_bad_chars_end-gm_bad_chars-1
-       cmp gm_bad_chars,y
        beq gm_del_badname
        dey
        bpl -
        sta dc_text+3,x
        inx
        cpx #16
        bne gm_del_copy
gm_del_named:
        txa
        beq gm_del_badname      ; an empty name
        clc
        adc #3
        sta dc_length
        lda #$53                ; S0:
        sta dc_text
        lda #$30
        sta dc_text+1
        lda #$3a
        sta dc_text+2
gm_del_ask:
        lda gm_confirm          ; Preferences may turn the question off
        beq gm_del_go
        lda #0                  ; "[2][Delete NAME?|This cannot be undone.][Delete|Cancel]"
        sta gm_alen
        lda #<gm_s_delete
        ldx #>gm_s_delete
        jsr gm_astr
        jsr gm_aname
        lda #<gm_s_undone
        ldx #>gm_s_undone
        jsr gm_astr
        lda #0
        jsr gm_aput
        lda #<gm_abuf
        ldx #>gm_abuf
        ldy #2                  ; Cancel is the default
        jsr gm_alert
        bcs gm_del_none
        lda N_BUFFER
        cmp #1
        bne gm_del_none
gm_del_go:
        ldx gm_slot
        lda gm_win_fmt,x
        cmp #3
        bne +
        jmp gm_ult_delete
+       lda gm_win_dev,x
        sta dc_device
        sta gm_dev
        lda gm_win_fmt,x
        sta gm_fmt
        jsr dc_command
        bcs gm_del_error
        cmp #1                  ; 01, FILES SCRATCHED, exactly one file
        bne gm_del_status
        lda dc_track
        cmp #1
        bne gm_del_status
        jmp gm_refresh_drive
gm_del_none:
        rts
gm_del_badname:
        lda #<gm_badname_alert
        ldx #>gm_badname_alert
        ldy #1
        jmp gm_alert
gm_del_error:                   ; "[3][Could not delete|NAME|error $xx][OK]"
        pha
        jsr gm_del_head
gm_error_hex:                   ; stacked A: "error $xx][OK]"
        lda #<gm_s_error
        ldx #>gm_s_error
        jsr gm_astr
        pla
        pha
        lsr
        lsr
        lsr
        lsr
        tax
        lda gm_hex_digits,x
        jsr gm_aput
        pla
        and #15
        tax
        lda gm_hex_digits,x
        jsr gm_aput
        jmp gm_info_end
gm_del_status:                  ; "[3][Could not delete|NAME|<drive status>][OK]"
        jsr gm_del_head
gm_status_text:
        ldy #0
gm_del_text:
        cpy dc_status_length
        beq gm_del_text_end
        cpy #30
        beq gm_del_text_end
        lda dc_status,y
        jsr gm_printable
        jsr gm_aput
        iny
        bne gm_del_text
gm_del_text_end:
        jmp gm_info_end
; A (PETSCII or ASCII) -> printable alert text: controls become spaces, and
; the alert syntax characters [ ] | and DEL become '?'.
gm_printable:
        and #$7f
        cmp #32
        bcs +
        lda #32
+       cmp #$5b
        beq +
        cmp #$5d
        beq +
        cmp #$7c
        beq +
        cmp #$7f
        bne ++
+       lda #$3f
+       rts
gm_del_head:
        lda #<gm_s_nodelete
        ldx #>gm_s_nodelete
gm_fail_head:                   ; A/X = "[3][Could not ...|", then the name and '|'
        pha
        lda #0
        sta gm_alen
        pla
        jsr gm_astr
        jsr gm_aname
        lda #<gm_s_bar
        ldx #>gm_s_bar
        jmp gm_astr
; List every window of gm_dev/gm_fmt again after the drive changed.
gm_refresh_drive:
        lda #GM_WINDOWS-1
        sta gm_vslot
gm_refresh_loop:
        ldx gm_vslot
        lda gm_win_handle,x
        beq gm_refresh_next
        lda gm_win_dev,x
        cmp gm_dev
        bne gm_refresh_next
        lda gm_win_fmt,x
        cmp gm_fmt
        bne gm_refresh_next
        stx gm_slot
        jsr gm_free_mem
        jsr gm_scan
        bcc +
        jsr gm_close_slot       ; the drive cannot be listed now
        jmp gm_refresh_next
+       ldx gm_slot
        lda #$ff
        sta gm_win_sel,x
        jsr gm_work
        jsr gm_max_top
        ldx gm_slot
        cmp gm_win_top,x
        bcs +
        sta gm_win_top,x
+       jsr gm_update_slider
        jsr gm_repaint_all
gm_refresh_next:
        dec gm_vslot
        bpl gm_refresh_loop
        rts
; After a press still held: wait for the release. A listing row dragged from
; the top window and dropped on Trash is deleted.
gm_release:
        lda ae_ev_result+5
        and #1
        beq gm_release_done
        lda #MU_BUTTON
        sta ae_ev_params
        lda #1
        sta ae_ev_params+1
        sta ae_ev_params+2
        lda #0
        sta ae_ev_params+3
        jsr ae_event
        bcs gm_release_done
        lda gm_drag
        beq gm_release_done
        jsr gm_pointer_cell
        lda #WS_FIND
        sta N_BUFFER
        lda gm_cx
        sta N_BUFFER+1
        lda gm_cy
        sta N_BUFFER+2
        jsr gm_wcall
        bcs gm_release_done
        lda N_BUFFER
        bne gm_release_done
        jsr gm_icon_hit
        cpx #2
        bne gm_release_done
        jmp gm_delete
gm_release_done:
        rts

; ---- desktop persistence ------------------------------------------------------------
; The desktop record (64 bytes): "GDS",1; confirm; view; colour; 0; window
; count; then per window, bottom to top: device, format, x, y, w, h, top row,
; selection. It goes to the AES session before a launch (restored when the
; desktop returns) and to DESKTOP.INF with Options:Save Desktop.
GM_RECORD_SIZE = 64
gm_session_build:
        ldx #GM_RECORD_SIZE-1
        lda #0
-       sta gm_session,x
        dex
        bpl -
        ldx #3
-       lda gm_magic,x
        sta gm_session,x
        dex
        bpl -
        lda gm_confirm
        sta gm_session+4
        lda gm_view
        sta gm_session+5
        lda gm_desk_color
        sta gm_session+6
        lda $0a22               ; KERNAL RPTFLG: key repeat
        sta gm_session+7
        lda gm_dclick
        sta gm_session+8
        lda #GM_REC_WINDOWS
        sta gm_spos
        jsr gm_top_slot         ; the top window goes last, so it reopens on top
        bcc +
        ldx #$ff
+       stx gm_stop
        ldx #0
-       stx gm_sslot
        cpx gm_stop
        beq +
        jsr gm_session_window
+       ldx gm_sslot
        inx
        cpx #GM_WINDOWS
        bne -
        ldx gm_stop
        bmi gm_session_built
        stx gm_sslot
; Append slot gm_sslot (if open) to the record.
gm_session_window:
        ldx gm_sslot
        lda gm_win_handle,x
        beq gm_session_built
        lda gm_win_fmt,x        ; USB windows (paths) are not kept
        cmp #3
        beq gm_session_built
        lda #WS_GET
        sta N_BUFFER
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #WF_CURRXYWH
        sta N_BUFFER+2
        jsr gm_wcall
        bcs gm_session_built
        ldy gm_spos
        ldx gm_sslot
        lda gm_win_dev,x
        sta gm_session,y
        lda gm_win_fmt,x
        sta gm_session+1,y
        lda N_BUFFER
        sta gm_session+2,y
        lda N_BUFFER+1
        sta gm_session+3,y
        lda N_BUFFER+2
        sta gm_session+4,y
        lda N_BUFFER+3
        sta gm_session+5,y
        lda gm_win_top,x
        sta gm_session+6,y
        lda gm_win_sel,x
        sta gm_session+7,y
        tya
        clc
        adc #8
        sta gm_spos
        inc gm_session+GM_REC_COUNT
gm_session_built:
        rts
; Before leaving: keep the desktop in the AES for the return.
gm_session_save:
        jsr gm_session_build
        ldx #0
-       lda #0
        cpx #GM_RECORD_SIZE
        bcs +
        lda gm_session,x
+       sta N_BUFFER,x
        inx
        bne -
        jmp ae_session_write
; At start: the AES session, else DESKTOP.INF, else the defaults.
gm_restore:
        lda #$ff                ; the AES's current double-click speed
        jsr ae_dclick
        bcs +
        sta gm_dclick
+       jsr ae_session_read
        bcs gm_restore_file
        ldx #GM_RECORD_SIZE-1
-       lda N_BUFFER,x
        sta gm_session,x
        dex
        bpl -
        jsr gm_session_valid
        bcc gm_restore_apply
gm_restore_file:
        jsr gm_load_desktop
        bcs gm_restore_color
gm_restore_apply:
        lda gm_session+4
        and #1
        sta gm_confirm
        lda gm_session+5
        sta gm_view
        lda gm_session+6
        sta gm_desk_color
        lda gm_session+7
        sta $0a22               ; key repeat
        lda gm_session+8
        sta gm_dclick
        jsr ae_dclick
        lda #1
        sta gm_restoring
        lda #0
        sta gm_sslot            ; record index
        lda #GM_REC_WINDOWS
        sta gm_spos
gm_restore_loop:
        lda gm_sslot
        cmp gm_session+GM_REC_COUNT
        bcs gm_restore_done
        ldy gm_spos
        lda gm_session,y
        sta gm_dev
        lda gm_session+1,y
        sta gm_fmt
        ldx #0
-       lda gm_session+2,y
        sta gm_orect,x
        iny
        inx
        cpx #4
        bne -
        jsr gm_open_drive       ; nothing opens if the drive cannot be read now
        ldx gm_slot
        lda gm_win_handle,x
        beq gm_restore_next
        jsr gm_work
        jsr gm_max_top
        ldy gm_spos
        cmp gm_session+6,y      ; the saved top row, if the listing still has it
        bcc +
        lda gm_session+6,y
+       ldx gm_slot
        sta gm_win_top,x
        lda gm_session+7,y
        cmp gm_win_count,x
        bcc +
        lda #$ff
+       sta gm_win_sel,x
        jsr gm_update_slider
gm_restore_next:
        lda gm_spos
        clc
        adc #8
        sta gm_spos
        inc gm_sslot
        jmp gm_restore_loop
gm_restore_done:
        lda #0
        sta gm_restoring
gm_restore_color:
        lda #WS_SET             ; the AES paints the desktop in this colour
        sta N_BUFFER
        lda #0
        sta N_BUFFER+1
        lda #WF_DESKCOLOR
        sta N_BUFFER+2
        lda gm_desk_color
        sta N_BUFFER+3
        jmp gm_wcall
; gm_session: carry clear when it is a desktop record.
gm_session_valid:
        ldx #3
-       lda gm_session,x
        cmp gm_magic,x
        bne +
        dex
        bpl -
        lda gm_session+5
        cmp #4
        bcs +
        lda gm_session+8        ; double-click speed 0..4
        cmp #5
        bcs +
        lda gm_session+GM_REC_COUNT
        cmp #GM_WINDOWS+1
        rts                     ; carry clear when at most four windows
+       sec
        rts
; DESKTOP.INF on the boot drive -> gm_session. Carry set if absent or invalid.
gm_load_desktop:
        lda #0
        jsr gm_desktop_open
        bcs gm_load_done
        lda #GM_RECORD_SIZE
        sta N_FCOUNT
        lda #0
        sta N_FCOUNT+1
        jsr gm_file_select
        jsr N_FREAD
        bcs gm_load_close       ; (closing may reuse N_BUFFER and the counts)
        ldx #GM_RECORD_SIZE-1
-       lda N_BUFFER,x
        sta gm_session,x
        dex
        bpl -
        lda N_FACTUAL+1
        bne +
        lda N_FACTUAL
        cmp #GM_REC_WINDOWS
        bcc gm_load_short
+       jsr gm_close_file
        bcs gm_load_done
        jmp gm_session_valid
gm_load_short:
        sec
gm_load_close:
        php
        jsr gm_close_file
        plp
gm_load_done:
        rts
; A = mode (0 read, 1 create): open DESKTOP.INF on the boot drive.
gm_desktop_open:
        sta N_FMODE
        lda N_CURRENT
        sta N_FOWNER
        lda N_BOOTDEVICE
        sta N_FDEVICE
        lda N_BOOTFORMAT
        sta N_FFORMAT
        ldx #10
-       lda gm_inf_name,x
        sta N_FNAME,x
        dex
        bpl -
        lda #11
        sta N_FNAMELEN
        lda #0
        sta N_FTYPE             ; SEQ
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
gm_file_select:
        lda N_CURRENT
        sta N_FOWNER
        ldx #3
-       lda gm_file,x
        sta N_FHANDLE,x
        dex
        bpl -
        rts
; Options:Save Desktop: replace DESKTOP.INF on the boot drive.
gm_save_desktop:
        jsr gm_session_build
        lda N_BOOTDEVICE        ; scratch the old one (none is not an error)
        sta dc_device
        ldx #13
-       lda gm_inf_scratch,x
        sta dc_text,x
        dex
        bpl -
        lda #14
        sta dc_length
        jsr dc_command
        bcs gm_save_error
        cmp #1
        bne gm_save_status
        lda #1                  ; create
        jsr gm_desktop_open
        bcs gm_save_error
        ldx #GM_RECORD_SIZE-1
-       lda gm_session,x
        sta N_BUFFER,x
        dex
        bpl -
        lda #GM_RECORD_SIZE
        sta N_FCOUNT
        lda #0
        sta N_FCOUNT+1
        jsr gm_file_select
        jsr N_FWRITE
        bcs gm_save_write_error
        jsr gm_close_file       ; a failed close is an error too
        bcs gm_save_error
        rts
gm_save_write_error:
        pha
        jsr gm_close_file
        pla
gm_save_error:                  ; "[3][Could not save the|desktop: error $xx][OK]"
        pha
        lda #<gm_s_nosave
        ldx #>gm_s_nosave
        pha
        lda #0
        sta gm_alen
        pla
        jsr gm_astr
        jmp gm_error_hex
gm_save_status:
        lda #<gm_s_nosave
        ldx #>gm_s_nosave
        pha
        lda #0
        sta gm_alen
        pla
        jsr gm_astr
        jmp gm_status_text

; ---- the dialog modules (GDDLG.PRG, GDSET.PRG) ------------------------------------
; A = GM_MOP_*: run that dialog in the module window, loading its module from
; this program's folder when another one (or none) is there.
gm_module_run:
        sta gm_mop
        ldx #1                  ; Show Info and Format: GDDLG; the rest: GDSET
        cmp #GM_MOP_INFO
        beq +
        cmp #GM_MOP_FORMAT
        beq +
        inx
+       cpx gm_mloaded
        beq gm_module_call
        stx gm_mwanted
        lda #0
        sta gm_mloaded
        lda N_MSTATE
        beq +
        jsr N_MCLOSE
        bcs gm_module_fail
+       lda gm_mwanted          ; the file name
        asl
        asl
        asl
        clc
        adc gm_mwanted          ; *9
        tay
        ldx #0
-       lda gm_mod_names-9,y
        sta N_FNAME,x
        iny
        inx
        cpx #9
        bne -
        stx N_FNAMELEN
        jsr N_MLOAD
        bcs gm_module_fail
        ldx #2
-       lda N_MTOKEN,x
        sta gm_mtoken,x
        dex
        bpl -
        lda gm_mwanted
        sta gm_mloaded
gm_module_call:
        ldx #2
-       lda gm_mtoken,x
        sta N_MTOKEN,x
        dex
        bpl -
        jsr N_MCALL
        bcc +
        ldx N_MERROR            ; a gate error: load again next time
        beq +
        ldx #0
        stx gm_mloaded
        lda N_MERROR
        jmp gm_module_fail
+       rts
gm_module_fail:                 ; "[3][Could not load GDDLG.PRG.|error $xx][OK]"
        pha
        lda #0
        sta gm_alen
        lda #<gm_s_nomodule
        ldx #>gm_s_nomodule
        jsr gm_astr
        lda gm_mwanted          ; the module's name
        asl
        asl
        asl
        clc
        adc gm_mwanted
        tay
        lda #9                  ; (gm_aput uses X)
        sta gm_math4
-       lda gm_mod_names-9,y
        jsr gm_aput
        iny
        dec gm_math4
        bne -
        lda #<gm_s_nomodule2
        ldx #>gm_s_nomodule2
        jsr gm_astr
        jmp gm_error_hex

; ---- USB storage: the Ultimate's DOS through directory cursors -------------------
; (docs/NATIVE-ULTIMATE.md). A USB window keeps its absolute path in
; gm_win_path (a page per slot); records hold the first 16 name bytes and the
; entry's position, so a full name is read again from the cursor when needed.
gm_ult_probe:                   ; the USB icon only when DOS target 1 answers
        lda #1
        sta N_UARG
        lda #N_U_IDENTIFY
        sta N_UOP
        lda N_CURRENT
        sta N_FOWNER
        jsr N_UQUERY
        lda #3
        bcs +
        lda #4
+       sta gm_icons_n
        rts
; gm_slot's path page -> the self-modified load and store below.
gm_path_page:
        lda gm_slot
        clc
        adc #>gm_win_path
        sta gm_pr+2
        sta gm_pw+2
        rts
gm_pr:
        lda $ff00,y
        rts
gm_pw:
        sta $ff00,y
        rts
gm_path_root:                   ; gm_slot's path = "/"
        jsr gm_path_page
        ldy #0
        lda #$2f
        jsr gm_pw
        ldx gm_slot
        lda #1
        sta gm_win_plen,x
        rts
gm_path_to_upath:               ; gm_slot's path -> N_UPATH, N_FNAMELEN
        jsr gm_path_page
        ldx gm_slot
        lda gm_win_plen,x
        sta N_FNAMELEN
        ldy #0
-       cpy N_FNAMELEN
        beq +
        jsr gm_pr
        sta N_UPATH,y
        iny
        bne -
+       rts
gm_upath_to_path:               ; N_UPATH, N_FNAMELEN -> gm_slot's path
        jsr gm_path_page
        ldx gm_slot
        lda N_FNAMELEN
        sta gm_win_plen,x
        ldy #0
-       cpy N_FNAMELEN
        beq +
        lda N_UPATH,y
        jsr gm_pw
        iny
        bne -
+       rts
; Open a directory cursor at gm_slot's path on DOS context gm_dev; the
; canonical path the service returns becomes the window's path.
gm_ult_open:
        jsr gm_path_to_upath
        lda N_CURRENT
        sta N_FOWNER
        lda gm_dev
        sta N_FDEVICE
        lda #3
        sta N_FFORMAT
        lda #2
        sta N_FMODE
        lda #0
        sta N_FTYPE
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
        jsr gm_upath_to_path
        clc
+       rts
gm_ult_read:                    ; one packet: attribute, then the name
        jsr gm_file_select
        lda #0
        sta N_FCOUNT
        lda #2
        sta N_FCOUNT+1
        jmp N_FREAD
; The listing (from gm_scan, after the allocation): records into gm_sortbuf.
gm_scan_ult:
        jsr gm_ult_open
        bcs gm_ult_scan_fail0
gm_ult_scan_next:
        jsr gm_ult_read
        bcs gm_ult_scan_fail
        lda N_FACTUAL
        ora N_FACTUAL+1
        beq gm_ult_scan_done
        ldy gm_count
        cpy #GM_MAX_ENTRIES
        bcs gm_ult_scan_done    ; the snapshot is full
        lda gm_addr_lo,y
        sta gm_rec_dst+1
        lda gm_addr_hi,y
        sta gm_rec_dst+2
        lda N_FACTUAL           ; name length 1..255
        sec
        sbc #1
        sta gm_nlen
        ldy #0
        ldx #0
-       lda #$a0                ; the first 16 bytes, padded like a CBM name
        cpx gm_nlen
        bcs +
        lda N_BUFFER+1,x
+       jsr gm_rec_put
        inx
        cpx #16
        bne -
        lda N_BUFFER            ; type 5 DIR or 6 file; the attribute as flags
        and #$10
        beq +
        lda #5
        bne ++
+       lda #6
+       jsr gm_rec_put
        lda N_BUFFER
        jsr gm_rec_put
        lda #0                  ; no size in a directory packet
        jsr gm_rec_put
        jsr gm_rec_put
        lda gm_count            ; the position in the cursor
        jsr gm_rec_put
        inc gm_count
        jmp gm_ult_scan_next
gm_ult_scan_done:
        jsr gm_close_file
        bcs gm_ult_scan_fail0
        jmp gm_scan_end
gm_ult_scan_fail:
        pha
        jsr gm_close_file
        pla
gm_ult_scan_fail0:
        jmp gm_scan_fail
; A = an entry's position in gm_slot's directory: N_UPATH/N_FNAMELEN = its
; full path, gm_ult_attr = its attribute. Carry set: A = error.
gm_ult_fullname:
        sta gm_target
        ldx gm_slot
        lda gm_win_dev,x
        sta gm_dev
        jsr gm_ult_open
        bcs gm_fn_done
        lda #0
        sta gm_k
gm_fn_next:
        jsr gm_ult_read
        bcs gm_fn_close
        lda N_FACTUAL
        ora N_FACTUAL+1
        beq gm_fn_missing
        lda gm_k
        cmp gm_target
        beq gm_fn_found
        inc gm_k
        jmp gm_fn_next
gm_fn_found:
        lda N_BUFFER
        sta gm_ult_attr
        lda N_FACTUAL
        sec
        sbc #1
        sta gm_nlen
        ldx #0
-       lda N_BUFFER+1,x
        sta gm_name,x
        inx
        cpx gm_nlen
        bne -
        jsr gm_close_file
        bcs gm_fn_done
        jsr gm_path_to_upath    ; the directory, then '/' if needed, then the name
        ldx N_FNAMELEN
        lda N_UPATH-1,x
        cmp #$2f
        beq +
        lda #$2f
        sta N_UPATH,x
        inx
        beq gm_fn_long
+       ldy #0
-       lda gm_name,y
        sta N_UPATH,x
        inx
        beq gm_fn_long
        iny
        cpy gm_nlen
        bne -
        stx N_FNAMELEN
        clc
        rts
gm_fn_long:
        lda #$23                ; the path would exceed 255 bytes
        sec
        rts
gm_fn_missing:                  ; the listing changed under the window
        lda #N_RANGE
gm_fn_close:
        pha
        jsr gm_close_file
        pla
        sec
gm_fn_done:
        rts
; Open the selected USB entry: a folder opens in the window, a file is
; handed to the dispatcher with its full path (it checks the program).
gm_ult_open_entry:
        jsr gm_read_record
        bcs gm_usb_error
        lda gm_rec+20
        jsr gm_ult_fullname
        bcs gm_usb_error
        lda gm_ult_attr
        and #$10
        bne gm_ult_enter
        jsr gm_text_suffix      ; .TXT or .SEQ: a text document
        bcs +
        jmp gm_usb_document
+       lda N_FNAMELEN
        sta N_NAMELEN
        ldx gm_slot
        lda gm_win_dev,x
        sta N_DEVICE
        lda #3
        sta N_APPFORMAT
        jsr gm_session_save
        jsr pm_close
        lda #0
        jmp N_REPLACE
gm_ult_enter:
        jsr gm_upath_to_path
; List gm_slot's (new) path again in the same window.
gm_ult_rescan:
        ldx gm_slot
        lda gm_win_dev,x
        sta gm_dev
        lda #3
        sta gm_fmt
        jsr gm_free_mem
        jsr gm_scan
        bcc +
        pha
        jsr gm_close_slot
        pla
        jmp gm_usb_error
+       ldx gm_slot
        lda #0
        sta gm_win_top,x
        lda #$ff
        sta gm_win_sel,x
        jsr gm_set_title
        jsr gm_update_slider
        jmp gm_repaint_all
; The close box: on a USB folder below the root, go up one level (as TOS).
gm_close_or_up:
        ldx gm_slot
        lda gm_win_fmt,x
        cmp #3
        bne gm_close_full
        lda gm_win_plen,x
        cmp #2
        bcc gm_close_full
        jsr gm_path_page
        ldx gm_slot
        ldy gm_win_plen,x
        dey                     ; the last byte; a trailing '/' is skipped
        jsr gm_pr
        cmp #$2f
        bne +
        dey
+
-       jsr gm_pr               ; back to the previous '/'
        cmp #$2f
        beq +
        dey
        bne -
+       iny                     ; keep that '/'
        tya
        ldx gm_slot
        sta gm_win_plen,x
        jmp gm_ult_rescan
gm_close_full:
        jmp gm_close_slot
; gm_slot's title: "Drive nn", or "USB " and the end of the path.
gm_set_title:
        lda #WS_SET
        sta N_BUFFER
        ldx gm_slot
        lda gm_win_handle,x
        sta N_BUFFER+1
        lda #WF_NAME
        sta N_BUFFER+2
        lda gm_win_fmt,x
        cmp #3
        beq gm_title_usb
        ldy #0
-       lda gm_drive_title,y
        sta N_BUFFER+3,y
        iny
        cpy #6
        bne -
        ldx gm_slot
        lda gm_win_dev,x
        jsr gm_decimal2
        cpx #$30                ; one digit below 10
        bne +
        sta N_BUFFER+9
        lda #0
        sta N_BUFFER+10
        beq gm_title_set
+       sta N_BUFFER+10
        stx N_BUFFER+9
        lda #0
        sta N_BUFFER+11
gm_title_set:
        jmp gm_wcall
gm_title_usb:
        ldy #3
-       lda gm_usb_title,y
        sta N_BUFFER+3,y
        dey
        bpl -
        jsr gm_path_page
        ldx gm_slot
        lda gm_win_plen,x
        sta gm_math
        sec                     ; the last 12 path bytes
        sbc #12
        bcs +
        lda #0
+       tay
        ldx #7
gm_title_char:
        cpy gm_math
        beq gm_title_end
        jsr gm_pr
        cmp #32
        bcc gm_title_q
        cmp #127
        bcc gm_title_ok
gm_title_q:
        lda #$3f                ; not printable
gm_title_ok:
        sta N_BUFFER,x
        inx
        iny
        bne gm_title_char
gm_title_end:
        lda #0
        sta N_BUFFER,x
        jmp gm_wcall
gm_not_usb:
        lda #<gm_s_notusb
        ldx #>gm_s_notusb
        ldy #1
        jmp gm_alert
gm_usb_error:                   ; "[3][Could not read USB|storage: error $xx][OK]"
        pha
        lsr
        lsr
        lsr
        lsr
        tax
        lda gm_hex_digits,x
        sta gm_s_usbhex
        pla
        and #15
        tax
        lda gm_hex_digits,x
        sta gm_s_usbhex+1
        lda #<gm_s_usbfail
        ldx #>gm_s_usbfail
        ldy #1
        jmp gm_alert
gm_ult_attr: .byte 0

; USB delete: DELETE_FILE with the entry's full path, then FILE_STAT; only
; DOS 82 FILE NOT FOUND with an empty reply proves the removal (as Files).
gm_ult_delete:
        lda gm_rec+20
        jsr gm_ult_fullname
        bcs gm_ult_del_error
        lda #$09                ; DELETE_FILE
        jsr gm_ucmd
        bcs gm_ult_del_error
        lda N_FACTUAL
        ora N_FACTUAL+1
        bne gm_ult_del_unknown
        lda #$08                ; FILE_STAT
        jsr gm_ucmd
        bcc gm_ult_del_unknown  ; still there
        lda N_FACTUAL
        ora N_FACTUAL+1
        ora N_FSTATUS
        bne gm_ult_del_unknown
        lda N_FDOS
        cmp #82
        bne gm_ult_del_unknown
        jmp gm_ult_rescan
gm_ult_del_unknown:
        lda #<gm_s_unproven
        ldx #>gm_s_unproven
        ldy #1
        jsr gm_alert
        jmp gm_ult_rescan
gm_ult_del_error:
        jmp gm_del_error
; A = Ultimate DOS opcode: N_BUFFER = context, opcode, the path in N_UPATH
; (FILE_STAT adds a NUL: its firmware handler takes the body as a C string).
gm_ucmd:
        sta N_BUFFER+1
        ldx gm_slot
        lda gm_win_dev,x
        sta N_BUFFER
        lda N_CURRENT
        sta N_FOWNER
        ldx #0
-       lda N_UPATH,x
        sta N_BUFFER+2,x
        inx
        cpx N_FNAMELEN
        bne -
        stx N_FCOUNT
        lda #0
        sta N_FCOUNT+1
        lda N_BUFFER+1
        cmp #$08
        bne +
        lda #0
        sta N_BUFFER+2,x
        inc N_FCOUNT
        bne +
        inc N_FCOUNT+1
+       jmp N_UCOMMAND

; ---- documents (docs/NATIVE-DOCUMENT-LAUNCH.md) ------------------------------------
; A text file opens in the Editor through the one-launch document contract;
; closing the Editor returns to "browse", this desktop, whose windows the AES
; session brings back.
gm_iec_document:                ; N_BUFFER = the record: IEC name and type
        ldx gm_slot
        lda gm_win_dev,x
        sta N_BROWSERDEV
        lda gm_win_fmt,x
        sta N_BROWSERFMT
        ldx #0
-       lda N_BUFFER,x
        cmp #$a0
        beq +
        sta N_BROWSERNAME,x
        inx
        cpx #16
        bne -
+       stx N_BROWSERNAME_LEN
        lda N_BUFFER+16         ; SEQ 1, PRG 2, USR 3 -> 0, 1, 2
        and #7
        sec
        sbc #1
        sta N_DOCTYPE
        jmp gm_document_launch
gm_usb_document:                ; gm_name/gm_nlen = the leaf; the window's path
        ldx gm_slot
        lda gm_win_dev,x
        sta N_BROWSERDEV
        lda #3
        sta N_BROWSERFMT
        jsr gm_path_page
        ldx gm_slot
        lda gm_win_plen,x
        sta N_BROWSERLEN
        ldy #0
-       cpy N_BROWSERLEN
        beq +
        jsr gm_pr
        sta N_BROWSERPATH,y
        iny
        bne -
+       ldx #0
-       lda gm_name,x
        sta N_BROWSERNAME,x
        inx
        cpx gm_nlen
        bne -
        stx N_BROWSERNAME_LEN
        lda #0
        sta N_DOCTYPE
gm_document_launch:
        lda #1                  ; Editor text
        sta N_DOCKIND
        lda #0
        sta N_DOCRETURN         ; back to this desktop, not system Files
        lda #$80
        sta N_DOCREQUEST
        ldx #5
-       lda gm_editor_name,x
        sta N_APPNAME,x
        dex
        bpl -
        lda #6
        sta N_NAMELEN
        lda N_BOOTDEVICE        ; the Editor from the boot disk
        sta N_DEVICE
        lda N_BOOTFORMAT
        sta N_APPFORMAT
        jsr gm_session_save
        jsr pm_close
        lda #0
        jmp N_REPLACE
; gm_name/gm_nlen: carry clear when it ends in .TXT or .SEQ (any case).
gm_text_suffix:
        lda gm_nlen
        cmp #5                  ; at least "X.TXT"
        bcc gm_suffix_no
        tax
        lda gm_name-4,x
        cmp #$2e
        bne gm_suffix_no
        lda gm_name-3,x         ; the three letters, upper-cased
        and #$df
        sta gm_suffix
        lda gm_name-2,x
        and #$df
        sta gm_suffix+1
        lda gm_name-1,x
        and #$df
        sta gm_suffix+2
        lda gm_suffix
        cmp #$54                ; TXT
        bne +
        lda gm_suffix+1
        cmp #$58
        bne gm_suffix_no
        lda gm_suffix+2
        cmp #$54
        bne gm_suffix_no
        clc
        rts
+       cmp #$53                ; SEQ
        bne gm_suffix_no
        lda gm_suffix+1
        cmp #$45
        bne gm_suffix_no
        lda gm_suffix+2
        cmp #$51
        bne gm_suffix_no
        clc
        rts
gm_suffix_no:
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
        jsr gm_mulrec
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
        cmp #7
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
        lda gm_rec+16           ; USB entries have no size in the listing
        and #7
        cmp #5
        bcc +
        lda #32
        ldy #4
-       sta gfx_text_buffer+20,y
        dey
        bne -
        beq ++
+       lda gm_rec+18           ; blocks, 4 digits right aligned
        sta gm_num
        lda gm_rec+19
        sta gm_num+1
        ldy #24
        jsr gm_decimal4
+       lda #25
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
+       jsr gm_mulrec
        sta N_COUNT
        stx N_COUNT+1
        jsr gm_select_mem
        ldx gm_slot
        lda gm_win_top,x
        jsr gm_mulrec
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
        lda gm_win_fmt,x
        cmp #3
        bne +
        jmp gm_ult_open_entry
+       lda gm_win_sel,x
        sta gm_item
        jsr gm_work
        ldx gm_slot             ; read the one record
        lda gm_item
        jsr gm_mulrec
        sta N_OFFSET
        stx N_OFFSET+1
        lda #GM_RECORD
        sta N_COUNT
        lda #0
        sta N_COUNT+1
        jsr gm_select_mem
        jsr N_READ
        bcs gm_launch_fail
        lda N_BUFFER+16         ; a SEQ file is a text document for the Editor
        and #7
        cmp #1
        bne +
        jmp gm_iec_document
+       ldx #0
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
        jsr gm_session_save     ; the windows come back when the desktop does
        jsr pm_close
        lda #0
        jmp N_REPLACE
gm_launch_fail:
        rts
gm_launcher_leave:
        jsr gm_session_save
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
gm_mulrec:                      ; A*GM_RECORD -> A lo, X hi
        ldx #GM_RECORD
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
gm_drive_title: .byte 68,114,105,118,101,32,0    ; "Drive "
gm_types: .byte 68,69,76,83,69,81,80,82,71,85,83,82,82,69,76   ; DEL SEQ PRG USR REL
        .byte 68,73,82,32,32,32            ; DIR, and a USB file (no CBM type)
gm_icon_y: .byte 2,6,20,10
gm_icon_art: .byte 0,0,1,0
gm_icon_dev_lo: .byte 0,9,0,1   ; 0: the boot drive; USB: DOS context 1
gm_icon_label_lo: .byte <gm_label_boot,<gm_label_9,<gm_label_trash,<gm_label_usb
gm_icon_label_hi: .byte >gm_label_boot,>gm_label_9,>gm_label_trash,>gm_label_usb
gm_label_boot: .byte 66,111,111,116,0                    ; Boot
gm_label_9: .byte 68,114,105,118,101,32,57,0            ; Drive 9
gm_label_trash: .byte 84,114,97,115,104,0               ; Trash
gm_label_usb: .byte 85,83,66,0                        ; USB
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
; Desk:About uOS...|-|Control Panel...;File:Open^O|Show Info^I
; |-|Delete^D|Format...|-|Close^W;View:Name|Type|Size|Unsorted
; ;Options:Preferences...|Save Desktop|Launcher^L
gm_menu:
        .byte 68,101,115,107,58,65,98,111,117,116,32,117,79,83,46,46,46,124,45,124,67,111,110,116
        .byte 114,111,108,32,80,97,110,101,108,46,46,46,59,70,105,108,101,58,79,112,101,110,94,79
        .byte 124,83,104,111,119,32,73,110,102,111,94,73,124,45,124,68,101,108,101,116,101,94,68,124
        .byte 70,111,114,109,97,116,46,46,46,124,45,124,67,108,111,115,101,94,87,59,86,105,101,119
        .byte 58,78,97,109,101,124,84,121,112,101,124,83,105,122,101,124,85,110,115,111,114,116,101,100
        .byte 59,79,112,116,105,111,110,115,58,80,114,101,102,101,114,101,110,99,101,115,46,46,46,124
        .byte 83,97,118,101,32,68,101,115,107,116,111,112,124,76,97,117,110,99,104,101,114,94,76,0
; Show Info alert pieces
gm_s_head: .byte 91,49,93,91,0                          ; [1][
gm_s_type: .byte 124,84,121,112,101,58,32,0             ; |Type:
gm_s_blocks: .byte 32,32,66,108,111,99,107,115,58,32,0  ;   Blocks:
gm_s_files: .byte 124,70,105,108,101,115,58,32,0        ; |Files:
gm_s_used: .byte 124,66,108,111,99,107,115,32,117,115,101,100,58,32,0   ; |Blocks used:
gm_s_ok: .byte 93,91,79,75,93,0                         ; ][OK]
gm_gaps: .byte 1,4,10,23,57,132
; [2][Delete NAME?|This cannot be undone.][Delete|Cancel]
gm_s_delete: .byte 91,50,93,91,68,101,108,101,116,101,32,0
gm_s_undone: .byte 63,124,84,104,105,115,32,99,97,110,110,111,116,32,98,101,32,117,110,100,111,110,101,46
        .byte 93,91,68,101,108,101,116,101,124,67,97,110,99,101,108,93,0
gm_s_nodelete: .byte 91,51,93,91,67,111,117,108,100,32,110,111,116,32,100,101,108,101,116,101,124,0  ; [3][Could not delete|
gm_s_bar: .byte 124,0
gm_s_error: .byte 101,114,114,111,114,32,36,0           ; error $
; [1][This name cannot be|deleted from here.][OK]
gm_badname_alert: .byte 91,49,93,91,84,104,105,115,32,110,97,109,101,32,99,97,110,110,111,116,32,98,101,124
        .byte 100,101,108,101,116,101,100,32,102,114,111,109,32,104,101,114,101,46,93,91,79,75,93,0
gm_bad_chars: .byte $2a,$3f,$2c,$3d,$3a,$22,$40   ; * ? , = : " @: DOS syntax in a name
gm_bad_chars_end:
GM_GAP_COUNT = 6
; [1][uOS GEM desktop|AES 1.6 on the C128][OK]
gm_about: .byte 91,49,93,91,117,79,83,32,71,69,77,32,100,101,115,107,116,111,112,124
        .byte 65,69,83,32,49,46,54,32,111,110,32,116,104,101,32,67,49,50,56,93,91,79,75,93,0
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

gm_confirm: .byte 1
gm_editor_name: .text "editor"
gm_suffix: .fill 3,0
gm_s_unproven: .byte 91,51,93,91,84,104,101,32,100,114,105,118,101,32,100,105,100,32,110,111,116,32,112,114,111,118,101,124,116,104,101,32,100,101,108,101,116,105,111,110,59,32,115,101,101,32,116,104,101,32,108,105,115,116,46,93,91,79,75,93,0   ; [3][The drive did not prove|the deletion; see the list.][OK]
gm_icons_n: .byte 3
gm_target: .byte 0
gm_nlen: .byte 0
gm_s_notusb: .byte 91,49,93,91,78,111,116,32,97,118,97,105,108,97,98,108,101,32,111,110,32,85,83,66,124,115,116,111,114,97,103,101,32,105,110,32,116,104,101,32,100,101,115,107,116,111,112,32,121,101,116,46,93,91,79,75,93,0   ; [1][Not available on USB|storage in the desktop yet.][OK]
gm_s_usbfail: .byte 91,51,93,91,67,111,117,108,100,32,110,111,116,32,114,101,97,100,32,85,83,66,124,115,116,111,114,97,103,101,58,32,101,114,114,111,114,32,36
gm_s_usbhex: .byte 48,48
        .byte 93,91,79,75,93,0
gm_usb_title: .byte 85,83,66,32
gm_s_free: .byte 124,66,108,111,99,107,115,32,102,114,101,101,58,32,0   ; |Blocks free: 
gm_desk_color: .byte $16
gm_restoring: .byte 0
gm_orect: .fill 4,0
gm_spos: .byte 0
gm_sslot: .byte 0
gm_stop: .byte 0
gm_session: .fill 64,0
gm_magic: .byte 71,68,83,2                           ; "GDS", version 2
gm_dclick: .byte 2                                   ; double-click speed 0..4
gm_inf_name: .byte 68,69,83,75,84,79,80,46,73,78,70  ; DESKTOP.INF
gm_inf_scratch: .byte 83,48,58,68,69,83,75,84,79,80,46,73,78,70   ; S0:DESKTOP.INF
gm_s_nosave: .byte 91,51,93,91,67,111,117,108,100,32,110,111,116,32,115,97,118,101,32,116,104,101,32,100,101,115,107,116,111,112,46,124,0   ; [3][Could not save the desktop.|
gm_mop: .byte 0
gm_mtoken: .fill 3,0
gm_mod_names: .byte 71,68,68,76,71,46,80,82,71   ; module 1
        .byte 71,68,83,69,84,46,80,82,71   ; module 2
gm_mloaded: .byte 0
gm_mwanted: .byte 0
gm_s_nomodule: .byte 91,51,93,91,67,111,117,108,100,32,110,111,116,32,108,111,97,100,32,0   ; [3][Could not load 
gm_s_nomodule2: .byte 46,124,0   ; .|
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
gm_drag: .byte 0
gm_view: .byte 0                ; View: 0 name, 1 type, 2 size, 3 unsorted
gm_vslot: .byte 0
gm_k: .byte 0
gm_m: .byte 0
gm_gap: .byte 0
gm_gapi: .byte 0
gm_i2: .byte 0
gm_ins_val: .byte 0
gm_pos: .byte 0
gm_other: .byte 0
gm_cmpb: .byte 0
gm_total: .word 0
gm_alen: .byte 0
gm_abuf: .fill 96,0
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
gm_dirpage: .fill 256,0
gm_win_plen: .fill GM_WINDOWS,0
gm_name: .fill 256,0             ; a full USB name
        .align 256
gm_win_path: .fill GM_WINDOWS*256,0   ; each USB window's absolute path
gm_addr_lo:
        .for i=0, i<GM_MAX_ENTRIES, i+=1
        .byte <(gm_sortbuf+i*GM_RECORD)
        .next
gm_addr_hi:
        .for i=0, i<GM_MAX_ENTRIES, i+=1
        .byte >(gm_sortbuf+i*GM_RECORD)
        .next
gm_sortbuf = GM_WORKSPACE
.cerror GM_MAX_ENTRIES*GM_RECORD > 16*256, "the sort workspace holds 16 pages"
; Buffers that are never live together share storage: the visible rows are
; read only while painting, the sort buffer only while scanning or sorting,
; and the sort order only after a scan has finished with its directory page.
gm_rows = gm_sortbuf
gm_order = gm_dirpage
.cerror GM_MAX_ENTRIES > 256 || 24*GM_RECORD > GM_MAX_ENTRIES*GM_RECORD, "shared buffers too small"
.include "aes-client.inc"
.include "dos-command.inc"
.include "graphics/graphics-core.inc"
.include "graphics/text-core.inc"
.include "input/pointer.inc"
; ---- module window (docs/NATIVE-MODULES.md) ------------------------------------------
; Two modules share the window; each has its own copy of the forms library
; (docs/NATIVE-FORMS.md). GDDLG.PRG: Show Info with rename, Format.
; GDSET.PRG: Preferences, Control Panel. Entry: gm_mop selects the dialog.
gm_module:
gm_dlg:
        .text "nmod"
        .byte 1,1,14,0
        .word gm_dlg_end-gm_dlg
        .word 0
        .word dlg.entry-gm_dlg
        .word 0
dlg .block
entry:
        ldx #3                  ; forms draw on the desktop's surface
-       lda gm_surface,x
        sta fo_surface,x
        dex
        bpl -
        lda gm_mop
        cmp #GM_MOP_INFO
        bne +
        jmp gm_info_dialog
+       jmp gm_format
; File:Show Info on an entry: name (editable), type and blocks, read-only.
; OK with a changed name renames the file on the drive.
gm_info_dialog:
        ldx #0                  ; the name into the field
-       lda gm_rec,x
        cmp #$a0
        beq +
        sta gm_name_buf,x
        inx
        cpx #16
        bne -
+       stx gm_name_field
        lda #0
        sta gm_name_buf,x
        sta gm_alen             ; "Type: SEQ  Blocks: 1"
        jsr gm_atype
        ldx gm_alen
        lda #0
        sta gm_abuf,x
        ldx #0
-       lda gm_abuf,x
        sta gm_info_line,x
        beq +
        inx
        bne -
+       lda gm_rec+17           ; read-only: shown, not changeable on IEC
        and #$40
        beq +
        lda #FOS_SELECTED
+       ora #FOS_DISABLED
        sta gm_info_form+5+4*8+2
        lda #<gm_info_form
        ldx #>gm_info_form
        jsr gm_form
        bcs gm_dialog_fail
        cmp #5                  ; OK
        bne gm_dialog_done
        ldx #0                  ; the same name: nothing to do
-       cpx gm_name_field
        beq +
        lda gm_name_buf,x
        cmp gm_rec,x
        bne gm_rename
        inx
        bne -
+       cpx #16
        beq gm_dialog_done
        lda gm_rec,x
        cmp #$a0
        bne gm_rename
gm_dialog_done:
        rts
gm_dialog_fail:
        jmp gm_view_fail
; Rename: "R0:NEW=OLD" to the window's drive, then list it again.
gm_rename:
        lda gm_name_field
        beq gm_rename_bad
        ldy #3
        ldx #0
-       lda gm_name_buf,x       ; the new name
        jsr gm_dos_char
        bcs gm_rename_bad
        sta dc_text,y
        iny
        inx
        cpx gm_name_field
        bne -
        lda #$3d                ; =
        sta dc_text,y
        iny
        ldx #0
-       lda gm_rec,x            ; the old name
        cmp #$a0
        beq +
        jsr gm_dos_char
        bcs gm_rename_bad
        sta dc_text,y
        iny
        inx
        cpx #16
        bne -
+       sty dc_length
        lda #$52                ; R0:
        sta dc_text
        lda #$30
        sta dc_text+1
        lda #$3a
        sta dc_text+2
        ldx gm_slot
        lda gm_win_dev,x
        sta dc_device
        sta gm_dev
        lda gm_win_fmt,x
        sta gm_fmt
        jsr dc_command
        bcs gm_rename_error
        cmp #0
        bne gm_rename_status
        jmp gm_refresh_drive
gm_rename_bad:
        jmp gm_del_badname
gm_rename_error:
        pha
        lda #<gm_s_norename
        ldx #>gm_s_norename
        jsr gm_fail_head
        jmp gm_error_hex
gm_rename_status:
        lda #<gm_s_norename
        ldx #>gm_s_norename
        jsr gm_fail_head
        jmp gm_status_text
; A = name byte: carry set for DOS syntax characters. Keeps X and Y.
gm_dos_char:
        stx gm_math4
        ldx #gm_bad_chars_end-gm_bad_chars-1
-       cmp gm_bad_chars,x
        beq +
        dex
        bpl -
        ldx gm_math4
        clc
        rts
+       ldx gm_math4
        sec
        rts
; A/X = form: open it, run it, close it. A = the exit object.
gm_form:
        sta gm_form_ptr
        stx gm_form_ptr+1
        jsr gm_bind
        bcs gm_form_done
        jsr gfx_clip_defaults
        lda gm_form_ptr
        ldx gm_form_ptr+1
        jsr fo_open
        bcs gm_form_done
        jsr fo_do
        bcs gm_form_close_error
        sta gm_form_exit
        jsr fo_close
        bcs gm_form_done
        lda gm_form_exit
gm_form_done:
        rts
gm_form_close_error:            ; keep the first error, still restore
        pha
        jsr fo_close
        pla
        sec
        rts

gm_fname_field: .byte 0,0,16    ; N_FEDIT records: disk name and ID (IEC filename filter)
        .word gm_fname_buf
        .byte 0,0,3
gm_fname_buf: .fill 17,0
gm_fid_field: .byte 0,0,2
        .word gm_fid_buf
        .byte 0,0,3
gm_fid_buf: .fill 3,0
gm_format_form: .byte $ff,0,30,11,10
        .byte FOT_TEXT,0,0,2,1,20
        .word gm_t_format
        .byte FOT_TEXT,0,0,2,3,6
        .word gm_t_drive
        .byte FOT_RADIO,$10,0,9,3,5
        .word gm_t_8
        .byte FOT_RADIO,$10,0,15,3,5
        .word gm_t_9
        .byte FOT_TEXT,0,0,2,4,5
        .word gm_t_name
        .byte FOT_FIELD,0,0,9,4,17
        .word gm_fname_field
        .byte FOT_TEXT,0,0,2,5,3
        .word gm_t_id
        .byte FOT_FIELD,0,0,9,5,3
        .word gm_fid_field
        .byte FOT_BUTTON,FOF_DEFAULT|FOF_EXIT,0,6,8,10
        .word gm_t_formatb
        .byte FOT_BUTTON,FOF_CANCEL|FOF_EXIT,0,18,8,8
        .word gm_t_cancel
gm_form_exit: .byte 0
gm_form_ptr: .word 0
gm_name_field: .byte 0,0,16     ; N_FEDIT record: length, caret, maximum,
        .word gm_name_buf       ; buffer, 40/80-column views, IEC filename filter
        .byte 0,0,3
gm_name_buf: .fill 17,0
gm_info_line: .fill 32,0
; Show Info: x (centred), y, w, h, objects
gm_info_form: .byte $ff,0,30,10,7
        .byte FOT_TEXT,0,0,2,1,20
        .word gm_t_info
        .byte FOT_TEXT,0,0,2,3,5
        .word gm_t_name
        .byte FOT_FIELD,0,0,8,3,17
        .word gm_name_field
        .byte FOT_TEXT,0,0,2,4,26
        .word gm_info_line
        .byte FOT_CHECK,0,FOS_DISABLED,2,5,12
        .word gm_t_readonly
        .byte FOT_BUTTON,FOF_DEFAULT|FOF_EXIT,0,8,7,8
        .word gm_t_ok
        .byte FOT_BUTTON,FOF_CANCEL|FOF_EXIT,0,18,7,8
        .word gm_t_cancel
gm_t_info: .byte 73,116,101,109,32,73,110,102,111,114,109,97,116,105,111,110,0   ; Item Information
gm_t_name: .byte 78,97,109,101,58,0   ; Name:
gm_t_readonly: .byte 82,101,97,100,45,111,110,108,121,0   ; Read-only
gm_t_format: .byte 70,111,114,109,97,116,32,100,105,115,107,0   ; Format disk
gm_t_drive: .byte 68,114,105,118,101,58,0   ; Drive:
gm_t_8: .byte 56,0   ; 8
gm_t_9: .byte 57,0   ; 9
gm_t_id: .byte 73,68,58,0   ; ID:
gm_t_formatb: .byte 70,111,114,109,97,116,0   ; Format
gm_s_noformat: .byte 91,51,93,91,67,111,117,108,100,32,110,111,116,32,102,111,114,109,97,116,32,116,104,101,32,100,105,115,107,46,124,0   ; [3][Could not format the disk.|
gm_format_need: .byte 91,49,93,91,65,32,100,105,115,107,32,110,101,101,100,115,32,97,32,110,97,109,101,124,97,110,100,32,97,110,32,73,68,46,93,91,79,75,93,0   ; [1][A disk needs a name|and an ID.][OK]
gm_format_ask: .byte 91,51,93,91,70,111,114,109,97,116,32,100,114,105,118,101,32
gm_format_ask_drive: .byte 56
        .byte 63,124,69,118,101,114,121,32,102,105,108,101,32,111,110,32,105,116,124,119,105,108,108,32,98,101,32,101,114,97,115,101,100,46,93,91,70,111,114,109,97,116,124,67,97,110,99,101,108,93,0
gm_t_ok: .byte 79,75,0   ; OK
gm_t_cancel: .byte 67,97,110,99,101,108,0   ; Cancel
gm_s_norename: .byte 91,51,93,91,67,111,117,108,100,32,110,111,116,32,114,101,110,97,109,101,124,0   ; [3][Could not rename|

; File:Format: drive 8 or 9, disk name and ID, then a confirmation; the drive
; gets "N0:NAME,ID" and every window of that drive is listed again.
gm_format:
        lda #0
        sta gm_fname_field      ; empty name and ID each time
        sta gm_fid_field
        sta gm_fname_buf
        sta gm_fid_buf
        lda #FOS_SELECTED
        sta gm_format_form+5+2*8+2
        lda #0
        sta gm_format_form+5+3*8+2
        lda #<gm_format_form
        ldx #>gm_format_form
        jsr gm_form
        bcc +
        jmp gm_view_fail
+       cmp #8                  ; Format
        bne gm_format_done
        ldx gm_fname_field
        beq gm_format_bad       ; a disk needs a name
        lda gm_fid_field
        beq gm_format_bad
        lda #8                  ; the chosen drive
        ldx gm_format_form+5+3*8+2
        beq +
        lda #9
+       sta dc_device
        sta gm_dev
        ldx #0                  ; format as the icon opens it
        cmp N_BOOTDEVICE
        bne +
        ldx N_BOOTFORMAT
+       stx gm_fmt
        clc                     ; "[3][Format drive 8?|Every file on it|will be erased.][Format|Cancel]"
        adc #$30
        sta gm_format_ask_drive
        lda #<gm_format_ask
        ldx #>gm_format_ask
        ldy #2
        jsr gm_alert
        bcs gm_format_done
        lda N_BUFFER
        cmp #1
        bne gm_format_done
        ldy #3                  ; N0:NAME,ID
        ldx #0
-       lda gm_fname_buf,x
        sta dc_text,y
        iny
        inx
        cpx gm_fname_field
        bne -
        lda #$2c
        sta dc_text,y
        iny
        ldx #0
-       lda gm_fid_buf,x
        sta dc_text,y
        iny
        inx
        cpx gm_fid_field
        bne -
        sty dc_length
        lda #$4e
        sta dc_text
        lda #$30
        sta dc_text+1
        lda #$3a
        sta dc_text+2
        jsr dc_command
        bcs gm_format_error
        cmp #0
        bne gm_format_status
        jmp gm_refresh_drive
gm_format_done:
        rts
gm_format_bad:
        lda #<gm_format_need
        ldx #>gm_format_need
        ldy #1
        jmp gm_alert
gm_format_error:
        pha
        jsr gm_format_head
        jmp gm_error_hex
gm_format_status:
        jsr gm_format_head
        jmp gm_status_text
gm_format_head:
        lda #0
        sta gm_alen
        lda #<gm_s_noformat
        ldx #>gm_s_noformat
        jmp gm_astr

.include "forms.inc"
.bend
gm_dlg_end:
.cerror gm_dlg_end > N_APPBASE+GM_APP_PAGES*256, "GDDLG.PRG exceeds the module window: ", gm_dlg_end

        .logical gm_module
gm_set:
        .text "nmod"
        .byte 1,1,14,0
        .word gm_set_end-gm_set
        .word 0
        .word set.entry-gm_set
        .word 0
set .block
gm_dialog_done:
        rts
gm_dialog_fail:
        jmp gm_view_fail
entry:
        ldx #3                  ; forms draw on the desktop's surface
-       lda gm_surface,x
        sta fo_surface,x
        dex
        bpl -
        lda gm_mop
        cmp #GM_MOP_PREFS
        bne +
        jmp gm_prefs
+       jmp gm_control
; Options:Preferences: confirm deletes, and the sort order.
gm_prefs:
        lda gm_confirm
        beq +
        lda #FOS_SELECTED
+       sta gm_pref_form+5+1*8+2
        ldx #0
        ldy #0
-       lda #0
        cpy gm_view
        bne +
        lda #FOS_SELECTED
+       sta gm_pref_form+5+3*8+2,x ; objects 3..6, 8 bytes apart
        txa
        clc
        adc #8
        tax
        iny
        cpy #4
        bne -
        ldx #0                  ; desktop colour radios: objects 8..10
        ldy #0
-       lda #0
        pha
        lda gm_desk_colors,y
        cmp gm_desk_color
        bne +
        pla
        lda #FOS_SELECTED
        pha
+       pla
        sta gm_pref_form+5+8*8+2,x
        txa
        clc
        adc #8
        tax
        iny
        cpy #3
        bne -
        lda #<gm_pref_form
        ldx #>gm_pref_form
        jsr gm_form
        bcs gm_dialog_fail
        cmp #11                 ; OK
        bne gm_dialog_done
        ldx #0                  ; the chosen colour
        ldy #0
-       lda gm_pref_form+5+8*8+2,x
        and #FOS_SELECTED
        bne +
        txa
        clc
        adc #8
        tax
        iny
        cpy #3
        bne -
        beq gm_prefs_view
+       lda gm_desk_colors,y
        cmp gm_desk_color
        beq gm_prefs_view
        sta gm_desk_color
        jsr gm_restore_color    ; the AES repaints; WM_REDRAW brings the icons
gm_prefs_view:
        lda gm_pref_form+5+1*8+2
        and #FOS_SELECTED
        sta gm_confirm
        ldx #0
        ldy #0
-       lda gm_pref_form+5+3*8+2,x
        and #FOS_SELECTED
        bne +
        txa
        clc
        adc #8
        tax
        iny
        cpy #4
        bne -
        rts
+       tya
        jmp gm_set_view
; A/X = form: open it, run it, close it. A = the exit object.
gm_form:
        sta gm_form_ptr
        stx gm_form_ptr+1
        jsr gm_bind
        bcs gm_form_done
        jsr gfx_clip_defaults
        lda gm_form_ptr
        ldx gm_form_ptr+1
        jsr fo_open
        bcs gm_form_done
        jsr fo_do
        bcs gm_form_close_error
        sta gm_form_exit
        jsr fo_close
        bcs gm_form_done
        lda gm_form_exit
gm_form_done:
        rts
gm_form_close_error:            ; keep the first error, still restore
        pha
        jsr fo_close
        pla
        sec
        rts

gm_form_exit: .byte 0
gm_form_ptr: .word 0
gm_pref_form: .byte $ff,0,30,13,13
        .byte FOT_TEXT,0,0,2,1,20
        .word gm_t_prefs
        .byte FOT_CHECK,0,0,2,3,18
        .word gm_t_confirm
        .byte FOT_TEXT,0,0,2,4,18
        .word gm_t_sortby
        .byte FOT_RADIO,$10,0,4,5,8
        .word gm_t_sname
        .byte FOT_RADIO,$10,0,14,5,8
        .word gm_t_stype
        .byte FOT_RADIO,$10,0,4,6,8
        .word gm_t_ssize
        .byte FOT_RADIO,$10,0,14,6,12
        .word gm_t_sunsorted
        .byte FOT_TEXT,0,0,2,7,9
        .word gm_t_desktop
        .byte FOT_RADIO,$20,0,4,8,7
        .word gm_t_blue
        .byte FOT_RADIO,$20,0,12,8,7
        .word gm_t_grey
        .byte FOT_RADIO,$20,0,20,8,8
        .word gm_t_black
        .byte FOT_BUTTON,FOF_DEFAULT|FOF_EXIT,0,8,10,8
        .word gm_t_ok
        .byte FOT_BUTTON,FOF_CANCEL|FOF_EXIT,0,18,10,8
        .word gm_t_cancel
gm_t_desktop: .byte 68,101,115,107,116,111,112,58,0   ; Desktop:
gm_t_blue: .byte 66,108,117,101,0                    ; Blue
gm_t_grey: .byte 71,114,101,121,0                    ; Grey
gm_t_black: .byte 66,108,97,99,107,0                 ; Black
gm_desk_colors: .byte $16,$1c,$10                    ; white icons on blue, grey, black
gm_t_ok: .byte 79,75,0   ; OK
gm_t_cancel: .byte 67,97,110,99,101,108,0   ; Cancel
gm_t_prefs: .byte 80,114,101,102,101,114,101,110,99,101,115,0   ; Preferences
gm_t_confirm: .byte 67,111,110,102,105,114,109,32,100,101,108,101,116,101,115,0   ; Confirm deletes
gm_t_sortby: .byte 83,111,114,116,32,119,105,110,100,111,119,115,32,98,121,58,0   ; Sort windows by:
gm_t_sname: .byte 78,97,109,101,0   ; Name
gm_t_stype: .byte 84,121,112,101,0   ; Type
gm_t_ssize: .byte 83,105,122,101,0   ; Size
gm_t_sunsorted: .byte 85,110,115,111,114,116,101,100,0   ; Unsorted
; Desk:Control Panel: key repeat (KERNAL RPTFLG) and double-click speed (AES
; evnt_dclick). Both are kept with the desktop.
gm_control:
        ldx #2                  ; key repeat radios: objects 2..4
-       lda #0
        ldy gm_rpt_values,x
        cpy $0a22
        bne +
        lda #FOS_SELECTED
+       sta gm_ctrl_rpt_state,x
        dex
        bpl -
        lda $0a22               ; another value: shown as cursor keys only
        ldx #2
-       cmp gm_rpt_values,x
        beq +
        dex
        bpl -
        lda #FOS_SELECTED
        sta gm_ctrl_rpt_state+1
+       ldx #4                  ; speed radios: objects 6..10
-       lda #0
        cpx gm_dclick
        bne +
        lda #FOS_SELECTED
+       sta gm_ctrl_speed_state,x
        dex
        bpl -
        ldx #0                  ; copy the states into the form's objects
-       lda gm_ctrl_rpt_state,x
        ldy gm_ctrl_rpt_offset,x
        sta gm_ctrl_form,y
        inx
        cpx #3
        bne -
        ldx #0
-       lda gm_ctrl_speed_state,x
        ldy gm_ctrl_speed_offset,x
        sta gm_ctrl_form,y
        inx
        cpx #5
        bne -
        lda #<gm_ctrl_form
        ldx #>gm_ctrl_form
        jsr gm_form
        bcc +
        jmp gm_view_fail
+       cmp #11                 ; OK
        bne gm_control_done
        ldx #2
-       ldy gm_ctrl_rpt_offset,x
        lda gm_ctrl_form,y
        and #FOS_SELECTED
        beq +
        lda gm_rpt_values,x
        sta $0a22
+       dex
        bpl -
        ldx #4
-       ldy gm_ctrl_speed_offset,x
        lda gm_ctrl_form,y
        and #FOS_SELECTED
        beq +
        stx gm_dclick
+       dex
        bpl -
        lda gm_dclick
        jmp ae_dclick
gm_control_done:
        rts
gm_rpt_values: .byte $80,$00,$40                     ; all keys, cursor keys only, none
gm_ctrl_rpt_offset: .byte 5+2*8+2,5+3*8+2,5+4*8+2   ; state bytes of objects 2..4
gm_ctrl_speed_offset: .byte 5+6*8+2,5+7*8+2,5+8*8+2,5+9*8+2,5+10*8+2
gm_ctrl_rpt_state: .fill 3,0
gm_ctrl_speed_state: .fill 5,0
gm_ctrl_form: .byte $ff,0,30,11,13
        .byte FOT_TEXT,0,0,2,1,20
        .word gm_t_control
        .byte FOT_TEXT,0,0,2,3,12
        .word gm_t_repeat
        .byte FOT_RADIO,$10,0,4,4,6
        .word gm_t_all
        .byte FOT_RADIO,$10,0,11,4,9
        .word gm_t_cursor
        .byte FOT_RADIO,$10,0,21,4,7
        .word gm_t_none
        .byte FOT_TEXT,0,0,2,5,26
        .word gm_t_dclick
        .byte FOT_RADIO,$20,0,4,6,4
        .word gm_t_1
        .byte FOT_RADIO,$20,0,9,6,4
        .word gm_t_2
        .byte FOT_RADIO,$20,0,14,6,4
        .word gm_t_3
        .byte FOT_RADIO,$20,0,19,6,4
        .word gm_t_4
        .byte FOT_RADIO,$20,0,24,6,4
        .word gm_t_5
        .byte FOT_BUTTON,FOF_DEFAULT|FOF_EXIT,0,6,8,8
        .word gm_t_ok
        .byte FOT_BUTTON,FOF_CANCEL|FOF_EXIT,0,18,8,8
        .word gm_t_cancel
gm_t_control: .byte 67,111,110,116,114,111,108,32,80,97,110,101,108,0   ; Control Panel
gm_t_repeat: .byte 75,101,121,32,114,101,112,101,97,116,58,0   ; Key repeat:
gm_t_all: .byte 65,108,108,0   ; All
gm_t_cursor: .byte 67,117,114,115,111,114,0   ; Cursor
gm_t_none: .byte 78,111,110,101,0   ; None
gm_t_dclick: .byte 68,111,117,98,108,101,45,99,108,105,99,107,32,40,115,108,111,119,45,102,97,115,116,41,58,0   ; Double-click (slow-fast):
gm_t_1: .byte 49,0   ; 1
gm_t_2: .byte 50,0   ; 2
gm_t_3: .byte 51,0   ; 3
gm_t_4: .byte 52,0   ; 4
gm_t_5: .byte 53,0   ; 5

.include "forms.inc"
.bend
gm_set_end:
.cerror gm_set_end > N_APPBASE+GM_APP_PAGES*256, "GDSET.PRG exceeds the module window: ", gm_set_end

        .here
gm_end = gm_module
.cerror gm_module > N_APPLIMIT, "the GEM desktop core exceeds its slot"
