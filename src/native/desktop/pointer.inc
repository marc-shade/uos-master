; Desktop hit targets; the proportional driver is shared with native apps.
pm_control_count=5
pm_select_surface=gd_select_surface
pm_find_hit:
        ldx #$ff
        lda pm_x+1
        bne +
        lda pm_x
        cmp #16
        bcc pm_find_done
        bcs pm_find_y
+       lda pm_x
        cmp #48
        bcs pm_find_done
pm_find_y:
        ldx #4
-       lda pm_y
        sec
        sbc pm_tops,x
        cmp #20
        bcc pm_find_done
        dex
        bpl -
pm_find_done:
        rts
pm_tops: .byte 32,56,80,104,128
.include "../input/pointer.inc"
