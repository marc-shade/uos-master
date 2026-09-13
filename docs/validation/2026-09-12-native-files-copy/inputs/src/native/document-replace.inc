; Replace one validated logical span. An allocation failure leaves its bytes,
; gap and length unchanged. No allocation is needed when the replacement fits
; in the current gap plus the removed span, even if the heap is exhausted.
doc_replace:
        lda d_replace_count+2
        bne doc_badarg
        lda d_replace_count+1
        cmp #2
        bcc +
        bne doc_badarg
        lda d_replace_count
        bne doc_badarg
+       jsr doc_prepare
        bcs doc_return
        #doc_sub3 d_pos,d_limit
        #doc_cmp3 d_limit,d_count
        bcc doc_range
        #doc_load3 D_END,d_limit
        #doc_load3 D_GAP,d_at
        #doc_sub3 d_at,d_limit
        #doc_add3 d_count,d_limit
        #doc_cmp3 d_limit,d_replace_count
        bcs doc_replace_room
        jsr doc_grow
        bcs doc_return
doc_replace_room:
        jsr doc_seek_gap
        bcs doc_return
        #doc_load3 D_GAP,d_at
        #doc_copy3 d_replace_count,d_left
        jsr doc_write_input
        bcs doc_return
        #doc_store3 d_at,D_GAP
        #doc_load3 D_END,d_limit
        #doc_add3 d_count,d_limit
        #doc_store3 d_limit,D_END
        #doc_load3 D_LEN,d_limit
        #doc_sub3 d_count,d_limit
        #doc_add3 d_replace_count,d_limit
        #doc_store3 d_limit,D_LEN
        jmp doc_dirty
d_replace_count: .fill 3,0
