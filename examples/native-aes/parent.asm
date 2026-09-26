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
demo_name: .text "aesvc.prg"
demo_digits: .text "0123456789abcdef"
demo_title: .text "aes demo",13,"version (hex): $",0
demo_attach_text: .text 13,"attaches (hex): $",0
demo_apps_text: .text 13,"apps (hex): $",0
demo_loaded_text: .text 13,"loaded here (hex): $",0
demo_error_text: .text 13,"last error (hex): $",0
demo_help: .text 13,13,"return: aes status",13
           .text "esc: exit, aes stays resident",13
           .text "u: unload aes and exit",13,0
.include "aes-client.inc"
app_end:
.cerror app_end > N_APPLIMIT, "example parent exceeds its slot"
