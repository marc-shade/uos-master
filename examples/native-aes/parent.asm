; Standalone AES example: attach to the persistent AES, or load AESVC.PRG
; from this app's folder when none is resident. Esc leaves it resident.
.include "api.inc"
.include "aes-api.inc"
* = N_APPBASE
app_image:
        .text "napp"
        .byte 1,1,14,0
        .word app_end-app_image
        .byte (app_end-app_image+255)/256,0
        .word app_entry-app_image,0
        .text "aes demo",0
        .fill N_APPBASE+32-*,0
app_entry:
        cld
        jsr ae_attach
        bcc demo_attached
        cmp #N_BADHANDLE
        beq +
        jmp demo_failed
+
        lda N_DEVICE
        sta N_FDEVICE
        lda N_APPFORMAT
        sta N_FFORMAT
        cmp #3
        bne demo_iec_name
        ldx #0
        stx demo_path_length
-       lda N_SOURCEPATH,x
        sta N_UPATH,x
        cmp #$2f
        bne +
        txa
        clc
        adc #1
        sta demo_path_length
+       inx
        cpx N_NAMELEN
        bne -
        lda demo_path_length
        clc
        adc #9
        bcs demo_argument
        sta N_FNAMELEN
        ldx demo_path_length
        ldy #0
-       lda demo_name,y
        sta N_UPATH,x
        inx
        iny
        cpy #9
        bne -
        beq demo_open
demo_iec_name:
        lda #9
        sta N_FNAMELEN
        ldx #8
-       lda demo_name,x
        sta N_FNAME,x
        dex
        bpl -
demo_open:
        lda #N_APPOWNER
        sta N_FOWNER
        lda #1
        sta N_FTYPE
        lda #0
        sta N_FMODE
        ldx #3
-       sta N_FHANDLE,x       ; early OPEN refusal may not produce a new token
        dex
        bpl -
        jsr N_FOPEN
        php
        pha
        ldx #3
-       lda N_FHANDLE,x
        sta demo_file,x
        dex
        bpl -
        pla
        plp
        bcs demo_failed
        jsr ae_load
        php
        pha
        lda ae_stream_taken
        beq +                 ; preflight refusal leaves the stream with caller
        lda #0
        sta demo_file
+       pla
        plp
        bcs demo_failed
        inc demo_loaded
demo_attached:
        jsr demo_reply
        ldx #15
-       lda demo_ev_defaults,x
        sta ae_ev_params,x
        dex
        bpl -
        lda #1
        sta demo_active
        lda #0
        beq demo_failed
demo_argument:
        lda #N_BADARG
demo_failed:
        sta demo_error
        jsr demo_draw
input_loop:
        lda #1
        sta N_READY
        jsr N_KEYIN
        beq input_loop
        ldx #0
        stx N_READY
        cmp #27
        beq demo_exit
        cmp #$55              ; U: unload the AES, then exit
        beq demo_unload
        cmp #$45              ; E: wait for the events in ae_ev_params
        bne +
        lda demo_active
        beq input_loop
        lda #1
        sta demo_waiting
        jsr ae_event
        ldx #0
        stx demo_waiting
        sta demo_error
        jsr demo_draw
        jmp input_loop
+       cmp #$50              ; P: post one message to the AES queue
        bne +
        lda demo_active
        beq input_loop
        ldx #7
-       lda demo_message,x
        sta N_BUFFER,x
        dex
        bpl -
        jsr ae_post
        sta demo_error
        jsr demo_draw
        jmp input_loop
+       cmp #$4d              ; M: a menu bar over this app's VIC surface
        bne +
        jsr demo_menu_run
        sta demo_error
        jsr demo_draw
        jmp input_loop
+       cmp #$41              ; A: an AES alert over this app's VIC surface
        bne +
        jsr demo_alert_run
        sta demo_error
        jsr demo_draw
        jmp input_loop
+
        cmp #13
        bne input_loop
        lda demo_active
        beq input_loop
        lda #AE_OP_STATUS
        jsr ae_call
        sta demo_error
        bcs +
        jsr demo_reply
+       jsr demo_draw
        jmp input_loop
demo_unload:
        lda demo_active
        beq demo_exit
        jsr ae_unload
        bcs demo_failed
        lda #0
        sta demo_active
        beq demo_leave
demo_exit:
        lda demo_active
        beq demo_leave
        jsr ae_detach
        bcs demo_failed
        lda #0
        sta demo_active
demo_leave:
        jsr demo_close_file
        bcs demo_failed
        lda #0
        jmp N_EXIT
; Reserve and initialize the 36-page VIC surface once (as the desktop does),
; present it, run one alert to completion, then return to the text screens.
; Key $ff stands for "pointer moved/clicked": this example has no pointer
; driver, so the host sets ae_pointer_* and sends $ff (example-only input).
demo_alert_run:
        jsr demo_surface_open
        bcs demo_alert_done
        lda #<demo_alert
        ldx #>demo_alert
        ldy #2                ; Cancel is the default
        jsr ae_alert_open
        bcs demo_alert_hide
        jmp demo_alert_loop
; Reserve/initialize the surface once, then present it. Carry set on error.
demo_surface_open:
        lda demo_active
        bne +
        lda #N_BADHANDLE
        sec
        rts
+       lda ae_surface
        bne demo_alert_show
        lda N_CURRENT
        sta N_OWNER
        lda #0
        sta N_BANK
        lda #$c0
        sta N_PAGE
        lda #36
        sta N_PAGES
        jsr N_RESERVE
        bcs demo_alert_done
        ldx #3
-       lda N_HANDLE,x
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
        lda #$16
+       sta N_VALUE
        jsr N_FILL
        bcs demo_alert_done
        inc N_OFFSET+1
        inc N_OFFSET+1
        lda N_OFFSET+1
        cmp #$24
        bne -
demo_alert_show:
        lda N_CURRENT
        sta N_OWNER
        ldx #3
-       lda ae_surface,x
        sta N_HANDLE,x
        dex
        bpl -
        jmp N_VSHOW
demo_alert_loop:
        lda #1
        sta N_READY
        jsr N_KEYIN
        beq demo_alert_loop
        ldx #0
        stx N_READY
        cmp #$ff
        bne +
        lda #0
+       jsr ae_alert_step
        bcs demo_alert_hide
        lda N_BUFFER
        beq demo_alert_loop
        sta demo_choice
        jsr N_VCLOSE
        lda #0
        clc
demo_alert_done:
        rts
demo_alert_hide:
        pha
        jsr N_VCLOSE
        pla
        sec
        rts
; Install the menu, wait for messages and keys until Escape, then remove it.
; Options:Grid toggles its check mark. The last choice is shown afterwards.
demo_menu_run:
        jsr demo_surface_open
        bcs demo_menu_done
        lda #<demo_menu
        ldx #>demo_menu
        jsr ae_menu_install
        bcs demo_menu_hide
        lda #1                ; File:Open... starts disabled
        ldx #1
        ldy #2
        jsr ae_menu_set
        bcs demo_menu_hide
        lda #16|1             ; messages and keys
        sta ae_ev_params
        lda #1
        sta demo_waiting
demo_menu_loop:
        jsr ae_event
        bcs demo_menu_end
        lda ae_ev_result
        and #16
        beq demo_menu_key
        lda ae_ev_result+7
        cmp #10               ; MN_SELECTED
        bne demo_menu_key
        lda ae_ev_result+10
        sta demo_menu_title
        lda ae_ev_result+11
        sta demo_menu_item
        inc demo_menu_count
        cmp #0                ; Options (title 2) : Grid (item 0) toggles
        bne demo_menu_key
        lda demo_menu_title
        cmp #2
        bne demo_menu_key
        lda demo_grid
        eor #1
        sta demo_grid
        tay
        lda #2
        ldx #0
        jsr ae_menu_set
        bcs demo_menu_end
demo_menu_key:
        lda ae_ev_result
        and #1
        beq demo_menu_loop
        lda ae_ev_result+1
        cmp #27
        bne demo_menu_loop
        lda #0
demo_menu_end:
        pha
        lda #0
        sta demo_waiting
        lda #<demo_empty      ; remove the menu (its pixels stay the app's)
        ldx #>demo_empty
        jsr ae_menu_install
        pla
demo_menu_hide:
        pha
        jsr N_VCLOSE
        pla
        cmp #1
        rts
demo_menu_done:
        rts
demo_reply:
        ldx #12
-       lda N_BUFFER,x
        sta demo_status,x
        dex
        bpl -
        rts
demo_close_file:
        lda demo_file
        beq +
        ldx #3
-       lda demo_file,x
        sta N_FHANDLE,x
        dex
        bpl -
        lda #N_APPOWNER
        sta N_FOWNER
        jsr N_FCLOSE
        bcs ++
        lda #0
        sta demo_file
+       clc
+       rts

demo_draw:
        lda #0
        sta demo_screen
demo_draw_screen:
        lda $d7
        rol
        lda #0
        rol
        cmp demo_screen
        beq +
        jsr $ff5f
+       lda #$93
        jsr $ffd2
        lda #<demo_title
        ldx #>demo_title
        jsr demo_puts
        lda demo_status
        jsr demo_hex
        lda demo_status+1
        jsr demo_hex
        lda #<demo_attach_text
        ldx #>demo_attach_text
        jsr demo_puts
        lda demo_status+5
        jsr demo_hex
        lda demo_status+4
        jsr demo_hex
        lda #<demo_apps_text
        ldx #>demo_apps_text
        jsr demo_puts
        lda demo_status+7
        jsr demo_hex
        lda demo_status+6
        jsr demo_hex
        lda #<demo_loaded_text
        ldx #>demo_loaded_text
        jsr demo_puts
        lda demo_loaded
        jsr demo_hex
        lda #<demo_choice_text
        ldx #>demo_choice_text
        jsr demo_puts
        lda demo_choice
        jsr demo_hex
        lda #<demo_event_text
        ldx #>demo_event_text
        jsr demo_puts
        ldy #0
-       lda ae_ev_result,y
        jsr demo_hex_y
        iny
        cpy #7
        bne -
        lda #<demo_message_text
        ldx #>demo_message_text
        jsr demo_puts
        ldy #7
-       lda ae_ev_result,y
        jsr demo_hex_y
        iny
        cpy #15
        bne -
        lda #<demo_error_text
        ldx #>demo_error_text
        jsr demo_puts
        lda demo_error
        jsr demo_hex
        lda #<demo_help
        ldx #>demo_help
        jsr demo_puts
        inc demo_screen
        lda demo_screen
        cmp #2
        bne demo_draw_screen
        rts
demo_puts:
        sta demo_put+1
        stx demo_put+2
demo_put:
        lda $ffff
        beq +
        jsr $ffd2
        inc demo_put+1
        bne demo_put
        inc demo_put+2
        bne demo_put
+       rts
demo_hex_y:                    ; demo_hex, preserving Y
        sta demo_hex_save
        tya
        pha
        lda demo_hex_save
        jsr demo_hex
        pla
        tay
        rts
demo_hex_save: .byte 0
demo_hex:
        pha
        lsr
        lsr
        lsr
        lsr
        jsr demo_digit
        pla
        and #15
demo_digit:
        tax
        lda demo_digits,x
        jmp $ffd2
demo_file: .fill 4,0
demo_path_length: .byte 0
demo_active: .byte 0
demo_loaded: .byte 0
demo_error: .byte 0
demo_screen: .byte 0
demo_status: .fill 13,0
demo_choice: .byte 0
demo_menu_title: .byte 0
demo_menu_item: .byte 0
demo_menu_count: .byte 0
demo_grid: .byte 0
demo_empty: .byte 0
demo_menu: .byte 68,101,115,107,58,65,98,111,117,116,32,65,69,83,46,46,46,59,70,105,108,101,58,78,101,119,94,78,124,79,112,101,110,46,46,46,94,79,124,45,124,81,117,105,116,94,81,59,79,112,116,105,111,110,115,58,71,114,105,100,124,83,110,97,112,0
demo_waiting: .byte 0
demo_ev_defaults: .byte 1|32,1,1,1, 0,0,0,0,0, 0,0,0,0,0, 60,0 ; keyboard or 60 jiffies
demo_message: .byte 41,0,7,0,1,2,3,4    ; AC_OPEN-style: type, 0, sender 7, data
demo_event_text: .text 13,"event (hex): ",0
demo_message_text: .text 13,"message (hex): ",0
demo_choice_text: .text 13,"alert choice (hex): $",0
demo_alert: .byte 91,51,93,91,68,101,108,101,116,101,32,78,79,84,69,83,46,84,88,84,63,124,84,104,105,115,32,99,97,110,110,111,116,32,98,101,32,117,110,100,111,110,101,46,93,91,68,101,108,101,116,101,124,67,97,110,99,101,108,93,0
demo_name: .text "aesvc.prg"
demo_digits: .text "0123456789abcdef"
demo_title: .text "aes demo",13,"version (hex): $",0
demo_attach_text: .text 13,"attaches (hex): $",0
demo_apps_text: .text 13,"apps (hex): $",0
demo_loaded_text: .text 13,"loaded here (hex): $",0
demo_error_text: .text 13,"last error (hex): $",0
demo_help: .text 13,13,"return: aes status",13
           .text "esc: exit, aes stays resident",13
           .text "u: unload aes and exit",13
           .text "a: aes alert over the vic surface",13
           .text "e: wait for events  p: post a message",13
           .text "m: menu bar over the vic surface",13,0
.include "aes-client.inc"
app_end:
.cerror app_end > N_APPLIMIT, "example parent exceeds its slot"
