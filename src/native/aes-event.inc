; AES events (GEM evnt_multi) and messages (appl_write), bank 1.
; See docs/NATIVE-AES.md#events. The bank-0 client samples input and the
; jiffy clock and calls EVENT once per sample; this code keeps the state
; between samples of one wait: timer start, click counting, message queue.
MU_KEYBD = 1
MU_BUTTON = 2
MU_M1 = 4
MU_M2 = 8
MU_MESAG = 16
MU_TIMER = 32
EV_QUEUE_SIZE = 16                 ; messages of 8 bytes
EV_DCLICK = 20                ; double-click window in jiffies

; EVENT. N_BUFFER in: 0 mask, 1 clicks wanted (1..3), 2 button mask, 3 button
; state, 4..8 rectangle 1 (0 enter / 1 leave, x, y, w, h in cells), 9..13
; rectangle 2, 14..15 timer jiffies, 16 key, 17..18 x, 19 y, 20 buttons,
; 21..23 jiffy clock ($a0..$a2 order), 24 = 1 on the first sample of a wait.
; Out: 0 fired mask (0 = keep waiting), 1 key, 2..3 x, 4 y, 5 buttons,
; 6 click count, 7..14 message.
ev_event:
        lda N_BUFFER+23         ; now, little-endian 24-bit
        sta ev_now
        lda N_BUFFER+22
        sta ev_now+1
        lda N_BUFFER+21
        sta ev_now+2
        lda N_BUFFER+24
        beq +
        ldx #2                  ; a new wait: the timer starts now and the
-       lda ev_now,x            ; current button state counts as a change
        sta ev_start,x
        dex
        bpl -
        lda #0
        sta ev_matched
        sta ev_counting
+       lda #0
        sta ev_fired
        sta ev_clicks
        lda N_BUFFER            ; keyboard
        and #MU_KEYBD
        beq +
        lda N_BUFFER+16
        beq +
        lda #MU_KEYBD
        jsr ev_fire
+       lda N_BUFFER
        and #MU_BUTTON
        beq +
        jsr ev_button
+       lda N_BUFFER
        and #MU_M1
        beq +
        ldx #4
        jsr ev_rectangle
        bcc +
        lda #MU_M1
        jsr ev_fire
+       lda N_BUFFER
        and #MU_M2
        beq +
        ldx #9
        jsr ev_rectangle
        bcc +
        lda #MU_M2
        jsr ev_fire
+       lda N_BUFFER
        and #MU_TIMER
        beq +
        jsr ev_elapsed          ; carry set once now - start >= interval
        bcc +
        lda #MU_TIMER
        jsr ev_fire
+       lda N_BUFFER            ; one queued message per wake; it is returned
        and #MU_MESAG           ; with any other events that fired together
        beq ev_reply
        lda ev_count
        beq ev_reply
        ldx ev_head
        ldy #0
-       lda ev_queue,x
        sta ev_message,y
        inx
        iny
        cpy #8
        bne -
        txa
        and #EV_QUEUE_SIZE*8-1
        sta ev_head
        dec ev_count
        lda #MU_MESAG
        jsr ev_fire
ev_reply:
        lda ev_fired
        sta ev_out
        lda N_BUFFER+16
        sta ev_out+1
        ldx #3
-       lda N_BUFFER+17,x       ; x (2), y, buttons
        sta ev_out+2,x
        dex
        bpl -
        lda ev_clicks
        sta ev_out+6
        ldx #14
-       lda ev_out,x
        sta N_BUFFER,x
        dex
        bpl -
        lda #0
        clc
        rts
ev_fire:
        ora ev_fired
        sta ev_fired
        rts

; Count transitions into the wanted state. One click fires at once; more fire
; when enough arrive or the double-click window closes.
ev_button:
        lda N_BUFFER+20
        and N_BUFFER+2
        cmp N_BUFFER+3
        beq +
        lda #0                  ; not in the wanted state
        sta ev_matched
        beq ev_button_window
+       lda ev_matched
        bne ev_button_window    ; still held: not a new transition
        lda #1
        sta ev_matched
        lda ev_counting
        bne +
        lda #1
        sta ev_counting
        lda #0
        sta ev_press_count
        clc                     ; deadline = now + window
        lda ev_now
        adc #EV_DCLICK
        sta ev_deadline
        lda ev_now+1
        adc #0
        sta ev_deadline+1
        lda ev_now+2
        adc #0
        sta ev_deadline+2
+       inc ev_press_count
        lda ev_press_count
        cmp N_BUFFER+1
        bcs ev_button_fire
ev_button_window:
        lda ev_counting
        beq ev_button_done
        lda ev_now              ; window over when now >= deadline
        cmp ev_deadline
        lda ev_now+1
        sbc ev_deadline+1
        lda ev_now+2
        sbc ev_deadline+2
        bcc ev_button_done
ev_button_fire:
        lda ev_press_count
        sta ev_clicks
        lda #0
        sta ev_counting
        lda #MU_BUTTON
        jmp ev_fire
ev_button_done:
        rts

; X = packet offset of flag,x,y,w,h. Carry set when the condition holds.
ev_rectangle:
        lda N_BUFFER+18         ; pointer cell: x/8 (word) and y/8
        lsr
        lda N_BUFFER+17
        ror
        lsr
        lsr
        sta ev_cx
        lda N_BUFFER+19
        lsr
        lsr
        lsr
        sta ev_cy
        lda #0
        sta ev_inside
        lda ev_cx
        sec
        sbc N_BUFFER+1,x
        bcc ev_rect_done        ; left of the rectangle
        cmp N_BUFFER+3,x
        bcs ev_rect_done
        lda ev_cy
        sec
        sbc N_BUFFER+2,x
        bcc ev_rect_done
        cmp N_BUFFER+4,x
        bcs ev_rect_done
        inc ev_inside
ev_rect_done:
        lda N_BUFFER,x          ; 0: fire inside; 1: fire outside
        eor ev_inside
        and #1
        cmp #1                  ; 0 xor 1 = inside wanted and inside
        rts

ev_elapsed:
        sec
        lda ev_now
        sbc ev_start
        sta ev_math
        lda ev_now+1
        sbc ev_start+1
        sta ev_math+1
        lda ev_now+2
        sbc ev_start+2
        bne ev_elapsed_yes      ; >= 65536 jiffies
        lda ev_math
        cmp N_BUFFER+14
        lda ev_math+1
        sbc N_BUFFER+15
        rts                     ; carry set when elapsed >= interval
ev_elapsed_yes:
        sec
        rts

; POST (appl_write). N_BUFFER 0..7: message. Carry set, N_NOMEM when full.
ev_post:
        lda ev_count
        cmp #EV_QUEUE_SIZE
        bcc +
        lda #N_NOMEM
        rts
+       clc
        lda ev_head
        ldx ev_count
        beq +
-       adc #8
        dex
        bne -
+       and #EV_QUEUE_SIZE*8-1
        tax
        ldy #0
-       lda N_BUFFER,y
        sta ev_queue,x
        inx
        iny
        cpy #8
        bne -
        inc ev_count
        lda #0
        clc
        rts

; A new foreground app: its queue and wait state are meaningless now.
ev_reset:
        lda #0
        sta ev_count
        sta ev_head
        sta ev_counting
        sta ev_matched
        rts

ev_now: .fill 3,0
ev_start: .fill 3,0
ev_deadline: .fill 3,0
ev_math: .word 0
ev_fired: .byte 0
ev_clicks: .byte 0
ev_matched: .byte 0
ev_counting: .byte 0
ev_press_count: .byte 0
ev_cx: .byte 0
ev_cy: .byte 0
ev_inside: .byte 0
ev_count: .byte 0
ev_head: .byte 0
ev_out: .fill 7,0
ev_message: .fill 8,0
ev_queue: .fill EV_QUEUE_SIZE*8,0
