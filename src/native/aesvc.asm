; AESVC.PRG: persistent AES component, bank 1 AE_BASE, owner 30.
; Step 1 of docs/GEM-LAYER-DESIGN.md: identity, attach and status. The image
; stays resident across app exits, so its own bytes carry the session state.
.include "api.inc"
.include "aes-api.inc"
BK_BASE = AE_BASE
gfx_heap_read = aes_heap_read  ; the graphics library calls back to bank 0
gfx_heap_write = aes_heap_write
gfx_heap_fill = aes_heap_fill
* = BK_BASE
aes_image:
        .text "nbk1"
        .byte 1,1,14,0
        .word aes_end-aes_image
        .byte (aes_end-aes_image+255)/256,1
        .word aes_entry-aes_image,0
        ldx #$0e
        jmp $02ab             ; checked common STX $ff00 / RTS
        .byte 0
        .word 0               ; each attaching app patches its callback here
        .fill 8,0
aes_identity:                 ; image offset 32, checked by bk_attach
        .text "naes"
        .byte AE_MAJOR,AE_MINOR
        .byte AE_CAP_ALERT|AE_CAP_EVENT|AE_CAP_MENU ; capability bits
        .byte 0
        .cerror aes_identity-aes_image != 32, "AES identity must be at offset 32"

; A = operation. Packets in N_BUFFER; results in A/carry.
aes_entry:
        cmp #AE_OP_COUNT
        bcs aes_badarg
        cmp #AE_OP_ALERT
        bne +
        jmp al_open
+       cmp #AE_OP_STEP
        bne +
        jmp al_step
+       cmp #AE_OP_EVENT
        bne +
        jmp ev_event
+       cmp #AE_OP_POST
        bne +
        jmp ev_post
+       cmp #AE_OP_MENU
        bne +
        jmp mn_install
+       cmp #AE_OP_MENU_SET
        bne +
        jmp mn_set
+       cmp #AE_OP_ATTACH
        bne aes_reply
        ldx #3
-       lda N_BUFFER,x        ; a different cookie means a different app
        cmp aes_app,x
        bne aes_new_app
        dex
        bpl -
        lda #0
        beq aes_count
aes_new_app:
        ldx #3
-       lda N_BUFFER,x
        sta aes_app,x
        dex
        bpl -
        inc aes_apps
        bne +
        inc aes_apps+1
+       jsr al_discard        ; the previous app's surface is gone
        jsr ev_reset          ; and so are its queued messages
        jsr mn_reset          ; and its menu bar
        lda #1
aes_count:
        sta aes_changed
        inc aes_attaches
        bne aes_reply
        inc aes_attaches+1
; Reply: major, minor, capabilities, 0, attaches (word), distinct apps
; (word), 1 when this attach changed the foreground app, current app cookie.
aes_reply:
        ldx #12
-       lda aes_state,x
        sta N_BUFFER,x
        dex
        bpl -
        lda #0
        clc
        rts
aes_badarg:
        lda #N_BADARG
        sec
        rts

aes_state:
        .byte AE_MAJOR,AE_MINOR,AE_CAP_ALERT|AE_CAP_EVENT|AE_CAP_MENU,0
aes_attaches: .word 0
aes_apps: .word 0
aes_changed: .byte 0
aes_app: .fill 4,0
aes_heap_read:
        lda #2
        jmp bk_native
aes_heap_write:
        lda #3
        jmp bk_native
aes_heap_fill:
        lda #4
        jmp bk_native
.include "banked-client.inc"
.include "aes-alert.inc"
.include "aes-event.inc"
.include "aes-menu.inc"
.include "graphics/graphics-core.inc"
.include "graphics/text-core.inc"
aes_end:
.cerror aes_end > AE_LIMIT, "AES exceeds its bank-1 region"
