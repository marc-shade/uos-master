; Bank-0 client for the persistent AES component (docs/GEM-LAYER-DESIGN.md).
; Include once in the retained app core after api.inc and aes-api.inc. It is a
; second, block-scoped executor instance: owner 30, bank-1 AE_BASE..AE_LIMIT.
;
; ae_attach  adopt a resident AES and register this app (op AE_OP_ATTACH).
;            Carry set with A=N_BADHANDLE means none is resident: open the
;            AESVC.PRG stream as owner 32 and call ae_load instead.
; ae_load    load AESVC.PRG from the stream in N_FHANDLE, then register.
; ae_call    A = operation; packet in N_BUFFER; returns the AES's A/carry.
; ae_detach  forget the attachment; the AES stays resident for the next app.
; ae_unload  free the AES image (owner 30) so its pages return to the heap.
; On success of attach/load, N_BUFFER holds the AE_OP_ATTACH reply.
; After ae_load, ae_stream_taken tells whether the caller still owns its stream.
aes .block
BK_BASE = AE_BASE
BK_LIMIT = AE_LIMIT
BK_OWNER = N_AESOWNER
.include "banked.inc"
.include "banked-load.inc"
bk_identity: .text "naes"
        .byte AE_MAJOR
.bend
ae_call = aes.bk_call
ae_detach = aes.bk_detach
ae_unload = aes.bk_close
ae_callback = aes.bk_callback  ; patched into AE_BASE+22 on attach/load
ae_state = aes.bk_state
ae_attach:
        jsr aes.bk_attach
        bcc ae_register
        rts
ae_load:
        jsr aes.bk_load
        php
        pha
        lda aes.bk_file         ; nonzero: the loader took the caller's stream,
        ora aes.bk_state        ; which it closes; zero: preflight refused and
        sta ae_stream_taken     ; the caller still owns and must close it
        pla
        plp
        bcc ae_register
        pha                     ; an owner-30 image outlives this app: never
        lda aes.bk_state        ; leave a partial one behind after a failure
        beq +
        jsr aes.bk_close        ; carry set here keeps state 1 for a retry
+       pla
        sec
        rts
; The executor's parent cookie (app slot + allocation generation) identifies
; the foreground app to the AES, which discards per-app state on a change.
ae_register:
        ldx #3
-       lda aes.bk_cookie,x
        sta N_BUFFER,x
        dex
        bpl -
        lda #AE_OP_ATTACH
        jmp aes.bk_call
ae_stream_taken: .byte 0
