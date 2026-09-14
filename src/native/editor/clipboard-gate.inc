; Return from the renderer before replacing its checked module window.
ed_clip_launch:
        sta ed_clip_key
        lda #3
        jsr ed_module_load
        bcs ed_picker_failed
        jsr N_MCALL
        bcc +
        lda #25
        sta ed_status
+       jmp ed_refresh
ed_clip_key: .byte 0
ed_clip_copied: .text "copied to clipboard",0
ed_clip_pasted: .text "pasted from clipboard",0
ed_clip_select: .text "select text to copy or cut",0
ed_clip_empty: .text "clipboard is empty",0
ed_clip_large: .text "clipboard limit: 15 kib",0
ed_clip_error: .text "clipboard error; text retained",0
ed_clip_cleared: .text "clipboard cleared",0
