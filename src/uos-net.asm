;==========================================================================
; uos-net — Ultimate II+ command-interface driver: networking + clock sync
;
;   This file is part of UltOS (GPL v3, see uos.asm).
;
; Talks to the Ultimate II+ / 1541 Ultimate-II "command interface" at
; $df1c-$df1f (cartridge setting "Command Interface" must be Enabled): the
; same register protocol xlar54's ultimateii-dos-lib and the firmware's
; command_intf.cc implement. Targets: $01 = Ultimate DOS, $03 = network.
; Every call is synchronous; each protocol wait is bounded (~11 s) so a
; wedged cartridge cannot hang the OS.
;
; The clock: NET_SYNC checks the interface (ID register $c9), checks the
; network (an interface with a non-zero address), sends one SNTP request
; (UDP/123) to NTP_HOST, converts the transmit timestamp to local time
; with the zone from the settings record, sets the CIA #1 time-of-day
; clock the desktop displays, and pushes date/time into the Ultimate's
; own RTC (DOS SET_TIME) so file timestamps agree.
;
; Fixed jump table at $9100 (NET_BASE in routines.inc). NET_STATE.. are plain bytes
; the tests read back over the monitor / DMA.
;==========================================================================
.include "equates.inc"
.include "io.inc"
; routines.inc is NOT included: it publishes this module's own labels
; (NET_*), which 64tass would see as duplicates. The record bytes it needs
; are restated here; tests/ci_vdc.py asserts the table/label addresses
; against routines.inc after every build.
SETREC_VER      = $7352         ; 2 = zone bytes valid (see routines.inc)
SETREC_TZ       = $7353         ; signed quarter-hours from UTC
SETREC_TZMAG    = $7354         ; $a5 marker
NET_DATA        = $8800         ; 512-byte reply buffer (not part of the PRG)
; zero-page scratch: $70-$7f (a2..a8 in equates.inc, used by no module;
; BASIC's CHRGET lives there but BASIC never runs under UltOS)
t0 = $70
t1 = $71
t2 = $72
t3 = $73
rm0 = $74
rm1 = $75
rm2 = $76
rm3 = $77
d0 = $78
d1 = $79
d2 = $7a
d3 = $7b
q0 = $7c
q1 = $7d
tmpa = $7e
tmpc = $7f

UCI_CTRL        = $df1c         ; W: bit0 PUSH_CMD bit1 DATA_ACC bit2 ABORT bit3 CLR_ERR
UCI_STAT        = $df1c         ; R: bit7 DATA_AV bit6 STAT_AV bits5-4 STATE bit3 ERROR
                                ;    bit2 ABORT_P bit1 DATA_ACC bit0 CMD_BUSY
UCI_CMD         = $df1d         ; W: command bytes (target first)
UCI_ID          = $df1d         ; R: $c9 when the interface is present
UCI_RDAT        = $df1e         ; R: response data queue
UCI_SDAT        = $df1f         ; R: status data queue

NTP_PORT        = 123
TZ_DEFAULT      = $f0           ; -16 quarter-hours = UTC-4 (US Eastern, daylight)
TMO_OUTER       = 5             ; wait budget: 5*65536 polls, ~11 s at 1 MHz
NET_DATA_MAX    = 510           ; bytes kept of a reply (NET_DATA is 512)

* = $9100
        jmp NET_PRESENT         ; $9100 A=1 when the command interface answers
        jmp NET_CMD             ; $9103 r0->bytes (target first), A=len -> A=status code, C=1 timeout/absent
        jmp NET_GETIP           ; $9106 A=1 when an interface has an address (NET_IP, NET_IPSTR)
        jmp NET_OPEN            ; $9109 A=7 tcp / 8 udp, r0->host, r1=port -> A=socket (NET_SOCK), C=1 failed
        jmp NET_CLOSE           ; $910c A=socket
        jmp NET_READ            ; $910f A=socket, r1=max(<=508) -> NET_DATA+2.., NET_LEN; A: 0 ok 1 none 2 closed 3 error
        jmp NET_WRITE           ; $9112 A=socket, r0->data, X=len(1..200) -> A=status code
        jmp NET_SYNC            ; $9115 network check + SNTP -> TOD + Ultimate RTC; A=NET_STATE
        jmp NET_APPLYNTP        ; $9118 NET_DATA+2..: 48-byte reply -> local time/date + TOD; A=0 ok
        jmp NET_RTCTIME         ; $911b Ultimate RTC "YYYY/MM/DD HH:MM:SS" -> NET_DATA; A=status code
        jmp NET_TZSHIFT         ; $911e A=signed quarter-hours -> shift the TOD (zone change)
NET_STATE:  .byte $ff           ; $9121 $ff not tried, 0 ntp ok, 1 no reply, 2 no network, 3 no ultimate, 4 open failed
NET_HOUR:   .byte 0             ; $9122 local time, 24 h, binary
NET_MIN:    .byte 0             ; $9123
NET_SEC:    .byte 0             ; $9124
NET_YEAR:   .word 0             ; $9125
NET_MON:    .byte 0             ; $9127
NET_DAY:    .byte 0             ; $9128
NET_WDAY:   .byte 0             ; $9129 0 = sunday
NET_TZ:     .byte 0             ; $912a quarter-hours applied to the clock
NET_IP:     .fill 4, 0          ; $912b
NET_IPSTR:  .fill 16, 0         ; $912f dotted decimal, 0-terminated ("" = none)
NET_LEN:    .word 0             ; $913f payload length of the last reply / socket read
NET_SOCK:   .byte 0             ; $9141 last socket opened
NET_STAT:   .fill 32, 0         ; $9142 last status line "NN,TEXT", 0-terminated
NET_DIRMODE: .byte 0            ; $9162 1 = READ_DIR: null-separate + count each reply block
NET_DIRN:   .byte 0             ; $9163 directory entry count after a dir read

;--------------------------------------------------------------------------
NET_PRESENT:
        lda UCI_ID
        cmp #$c9
        bne np_no
        lda UCI_ID              ; twice: an open bus does not hold $c9
        cmp #$c9
        bne np_no
        lda #$01
        rts
np_no:  lda #$00
        rts

;--------------------------------------------------------------------------
; bounded polling: tmo_init then tmo_tick per poll, C=1 when the budget
; is spent (256*256*TMO_OUTER polls)
tmo_init:
        lda #$00
        sta tmo0
        sta tmo1
        lda #TMO_OUTER
        sta tmo2
        rts
tmo_tick:
        dec tmo0
        bne tt_ok
        dec tmo1
        bne tt_ok
        dec tmo2
        bne tt_ok
        sec
        rts
tt_ok:  clc
        rts

; wait for the protocol state (STAT bits 5-4) to be idle; C=1 timeout
wait_idle:
        jsr tmo_init
wi_l:   lda UCI_STAT
        and #$30
        beq wi_ok
        jsr tmo_tick
        bcc wi_l
        rts
wi_ok:  clc
        rts

; wait until the state is no longer "command busy" ($10); C=1 timeout
wait_done:
        jsr tmo_init
wd_l:   lda UCI_STAT
        and #$30
        cmp #$10
        bne wd_ok
        jsr tmo_tick
        bcc wd_l
        rts
wd_ok:  clc
        rts

;--------------------------------------------------------------------------
; NET_CMD: push the A bytes at (r0) as one command, collect every data
; block into NET_DATA (NET_LEN) and the status line into NET_STAT, release
; the queues. A = numeric status code ("00,OK" -> 0), C=1 when the
; interface is absent ($fe) or the transaction timed out ($ff).
NET_CMD:
        sta cmdlen
        lda #$00
        sta NET_LEN
        sta NET_LEN+1
        sta NET_STAT
        sta NET_DATA
        sta NET_DIRN
        jsr NET_PRESENT
        bne nc_go
        lda #$fe
        sec
        rts
nc_go:  jsr wait_idle
        bcc nc_push
        lda #$04                ; stuck in a previous transaction: abort it
        sta UCI_CTRL
        lda #$08
        sta UCI_CTRL
        jsr wait_idle
        bcs nc_tmo
nc_push:
        ldy #$00
nc_w:   lda (r0),y
        sta UCI_CMD
        iny
        cpy cmdlen
        bne nc_w
        lda #$01                ; PUSH_CMD
        sta UCI_CTRL
        lda UCI_STAT
        and #$08                ; ERROR: pushed while not idle
        beq nc_wait
        lda #$08                ; CLR_ERR
        sta UCI_CTRL
        jmp nc_tmo
nc_wait:
        jsr wait_done
        bcs nc_tmo
nc_more:
        jsr read_data
        jsr read_status
        lda NET_DIRMODE         ; directory mode: each reply block is one
        beq nc_nodir            ; entry -> keep read_data's $00 as a separator
        inc NET_LEN             ; (advance past it) and count the entry
        bne nc_dc
        inc NET_LEN+1
nc_dc:  inc NET_DIRN
nc_nodir:
        lda #$02                ; DATA_ACC: release the queues
        sta UCI_CTRL
        jsr tmo_init
nc_acc: lda UCI_STAT
        and #$02
        beq nc_acc_ok
        jsr tmo_tick
        bcc nc_acc
        jmp nc_tmo
nc_acc_ok:
        jsr wait_done
        bcs nc_tmo
        lda UCI_STAT
        and #$30
        beq nc_fin              ; idle: reply complete
        jmp nc_more             ; another data block (multi-part reply)
nc_fin: jsr stat_code
        clc
        rts
nc_tmo: lda #$04                ; ABORT, leave the machine idle for the next call
        sta UCI_CTRL
        lda #$ff
        sec
        rts

; append the data queue to NET_DATA at NET_LEN (capped, 0-terminated)
read_data:
        clc
        lda #<NET_DATA
        adc NET_LEN
        sta r2L
        lda #>NET_DATA
        adc NET_LEN+1
        sta r2H
rd_l:   lda UCI_STAT
        bpl rd_done             ; bit 7 = DATA_AV
        lda UCI_RDAT
        ldx NET_LEN+1
        cpx #>NET_DATA_MAX
        bcc rd_st
        ldx NET_LEN
        cpx #<NET_DATA_MAX
        bcs rd_l                ; buffer full: drain and drop
rd_st:  ldy #$00
        sta (r2),y
        inc r2L
        bne rd_i
        inc r2H
rd_i:   inc NET_LEN
        bne rd_l
        inc NET_LEN+1
        jmp rd_l
rd_done:
        lda #$00
        ldy #$00
        sta (r2),y
        rts

; the status queue -> NET_STAT (31 chars max, 0-terminated)
read_status:
        ldy #$00
rs_l:   lda UCI_STAT
        and #$40
        beq rs_done
        lda UCI_SDAT
        cpy #31
        bcs rs_l
        sta NET_STAT,y
        iny
        bne rs_l
rs_done:
        lda #$00
        sta NET_STAT,y
        rts

; A = two-digit code at the start of NET_STAT, $ff when malformed
stat_code:
        lda NET_STAT
        sec
        sbc #'0'
        cmp #10
        bcs sc_bad
        sta tmpa
        asl
        asl
        adc tmpa                ; *5 (no carry possible from the shifts of 0-9)
        asl                     ; *10
        sta tmpa
        lda NET_STAT+1
        sec
        sbc #'0'
        cmp #10
        bcs sc_bad
        clc
        adc tmpa
        rts
sc_bad: lda #$ff
        rts

;--------------------------------------------------------------------------
; NET_GETIP: first interface with a non-zero address -> NET_IP / NET_IPSTR
NET_GETIP:
        lda #$00
        sta NET_IP
        sta NET_IP+1
        sta NET_IP+2
        sta NET_IP+3
        sta NET_IPSTR
        lda #<c_ifcnt
        sta r0L
        lda #>c_ifcnt
        sta r0H
        lda #$02
        jsr NET_CMD
        bcs gi_no
        cmp #$00
        bne gi_no
        lda NET_LEN
        beq gi_no
        lda NET_DATA
        beq gi_no
        sta ifcnt
        lda #$00
        sta ifidx
gi_l:   lda ifidx
        sta c_getip+2
        lda #<c_getip
        sta r0L
        lda #>c_getip
        sta r0H
        lda #$03
        jsr NET_CMD
        bcs gi_nx
        cmp #$00
        bne gi_nx
        lda NET_LEN
        cmp #$04
        bcc gi_nx
        lda NET_DATA
        ora NET_DATA+1
        ora NET_DATA+2
        ora NET_DATA+3
        beq gi_nx
        ldx #$03
gi_cp:  lda NET_DATA,x
        sta NET_IP,x
        dex
        bpl gi_cp
        jsr fmt_ip
        lda #$01
        rts
gi_nx:  inc ifidx
        lda ifidx
        cmp ifcnt
        bcc gi_l
gi_no:  lda #$00
        rts
c_ifcnt:  .byte $03, $02        ; network: GET_INTERFACE_COUNT
c_getip:  .byte $03, $05, $00   ; network: GET_IPADDR interface n -> ip[4] mask[4] gw[4]

; NET_IPSTR = "a.b.c.d"
fmt_ip:
        ldx #$00
        ldy #$00
fi_l:   lda NET_IP,y
        jsr put_dec
        iny
        cpy #$04
        beq fi_d
        lda #'.'
        sta NET_IPSTR,x
        inx
        bne fi_l
fi_d:   lda #$00
        sta NET_IPSTR,x
        rts

; A -> decimal digits (no leading zeros) at NET_IPSTR,x; X advanced, Y kept
put_dec:
        sty tmpy
        sta tmpa
        ldy #$00                ; 0 = still suppressing leading zeros
        lda #100
        jsr pd_digit
        lda #10
        jsr pd_digit
        lda tmpa
        clc
        adc #'0'
        sta NET_IPSTR,x
        inx
        ldy tmpy
        rts
pd_digit:
        sta tmpd
        lda #$00
        sta tmpc
pd_l:   lda tmpa
        cmp tmpd
        bcc pd_e
        sbc tmpd
        sta tmpa
        inc tmpc
        jmp pd_l
pd_e:   lda tmpc
        bne pd_emit
        cpy #$00
        beq pd_r
pd_emit:
        clc
        adc #'0'
        sta NET_IPSTR,x
        inx
        iny
pd_r:   rts

;--------------------------------------------------------------------------
; NET_OPEN: A = 7 (tcp) / 8 (udp), r0 -> host name (ASCII, 0-terminated,
; the Ultimate resolves it), r1 = port. A = socket id, C=1 on failure
; (NET_STAT says why: "84,UNRESOLVED HOST", "11,ERROR ON CONNECT: n" ...)
NET_OPEN:
        sta cmdb+1
        lda #$03
        sta cmdb
        lda r1L
        sta cmdb+2
        lda r1H
        sta cmdb+3
        ldy #$00
no_cp:  lda (r0),y
        sta cmdb+4,y
        beq no_e
        iny
        cpy #40
        bne no_cp
        lda #$00
        sta cmdb+4,y
no_e:   tya
        clc
        adc #$05                ; header 4 + host + terminator
        pha
        lda #<cmdb
        sta r0L
        lda #>cmdb
        sta r0H
        pla
        jsr NET_CMD
        bcs no_f
        cmp #$00
        bne no_f
        lda NET_LEN
        beq no_f
        lda NET_DATA
        sta NET_SOCK
        clc
        rts
no_f:   sec
        rts

NET_CLOSE:
        sta cmdb+2
        lda #$03
        sta cmdb
        lda #$09
        sta cmdb+1
        lda #<cmdb
        sta r0L
        lda #>cmdb
        sta r0H
        lda #$03
        jmp NET_CMD

; NET_READ: A = socket, r1 = max bytes (<= 508). The Ultimate waits 40 ms
; for data. Payload at NET_DATA+2, NET_LEN = count.
; A = 0 data, 1 nothing yet, 2 closed by the peer, 3 error/timeout.
NET_READ:
        sta cmdb+2
        lda #$03
        sta cmdb
        lda #$10
        sta cmdb+1
        lda r1L
        sta cmdb+3
        lda r1H
        sta cmdb+4
        lda #<cmdb
        sta r0L
        lda #>cmdb
        sta r0H
        lda #$05
        jsr NET_CMD
        bcs nr_err
        pha
        lda NET_LEN
        cmp #$02
        bcc nr_e2
        lda NET_DATA            ; count word from the reply
        sta NET_LEN
        lda NET_DATA+1
        sta NET_LEN+1
        pla
        cmp #$00
        beq nr_ok
        cmp #$01                ; "01,CONNECTION CLOSED BY HOST"
        beq nr_closed
        lda NET_LEN
        and NET_LEN+1
        cmp #$ff                ; -1: nothing within the window
        beq nr_none
nr_err: lda #$03
        rts
nr_e2:  pla
        jmp nr_err
nr_ok:  lda #$00
        rts
nr_closed:
        lda #$00
        sta NET_LEN
        sta NET_LEN+1
        lda #$02
        rts
nr_none:
        lda #$00
        sta NET_LEN
        sta NET_LEN+1
        lda #$01
        rts

; NET_WRITE: A = socket, r0 -> data, X = length (1..200). A = status code.
NET_WRITE:
        sta cmdb+2
        stx cmdlen2
        lda #$03
        sta cmdb
        lda #$11
        sta cmdb+1
        ldy #$00
nw_cp:  lda (r0),y
        sta cmdb+3,y
        iny
        cpy cmdlen2
        bne nw_cp
        lda #<cmdb
        sta r0L
        lda #>cmdb
        sta r0H
        tya
        clc
        adc #$03
        jmp NET_CMD

;--------------------------------------------------------------------------
; NET_SYNC: the self-setting clock. A = NET_STATE afterwards.
NET_SYNC:
        jsr get_tz              ; normalise the zone bytes even when the
        jsr NET_PRESENT         ; sync cannot run (settings shows them)
        bne ns_p
        lda #$03
        jmp ns_set
ns_p:   jsr NET_GETIP
        bne ns_net
        lda #$02
        jmp ns_set
        ; servers in order: two anycast services that answer the real C128
        ; in 2-3 reads, then the pool (whose member the Ultimate resolved
        ; answered nothing within the window on 2026-09-06)
ns_net: lda #$00
        sta hidx
        lda #$04                ; failure code if no host even opens
        sta failcode
ns_host:
        ldx hidx
        lda ntp_hostL,x
        sta r0L
        lda ntp_hostH,x
        sta r0H
        lda #<NTP_PORT
        sta r1L
        lda #>NTP_PORT
        sta r1H
        lda #$08                ; udp
        jsr NET_OPEN
        bcc ns_open
        jmp ns_next
ns_open:
        lda #<ntp_req
        sta r0L
        lda #>ntp_req
        sta r0H
        ldx #48
        lda NET_SOCK
        jsr NET_WRITE
        lda #150                ; the Ultimate answers a read at once when
        sta tries               ; nothing is queued: ~1.5 s of polling
ns_rd:  lda #48
        sta r1L
        lda #$00
        sta r1H
        lda NET_SOCK
        jsr NET_READ
        cmp #$00
        beq ns_got
        cmp #$01
        bne ns_fail
        dec tries
        bne ns_rd
ns_fail:
        lda NET_SOCK
        jsr NET_CLOSE
        lda #$01
        sta failcode            ; a host was reachable but silent
ns_next:
        inc hidx
        lda hidx
        cmp #NTP_HOSTS
        bcc ns_host
        lda failcode
        jmp ns_set
ns_got: lda NET_LEN+1
        bne ns_len_ok
        lda NET_LEN
        cmp #44                 ; transmit timestamp ends at byte 43
        bcs ns_len_ok
        jmp ns_fail
ns_len_ok:
        jsr NET_APPLYNTP        ; before the close: NET_CMD reuses NET_DATA
        sta applyres
        lda NET_SOCK
        jsr NET_CLOSE
        lda applyres
        bne ns_bad
        jsr rtc_push
        lda #$00
ns_set: sta NET_STATE
        rts
ns_bad: lda #$01
        jmp ns_set

NTP_HOSTS = 3
ntp_hostL: .byte <ntp_h0, <ntp_h1, <ntp_h2
ntp_hostH: .byte >ntp_h0, >ntp_h1, >ntp_h2
ntp_h0:   .text "time.cloudflare.com", $00
ntp_h1:   .text "time.google.com", $00
ntp_h2:   .text "pool.ntp.org", $00
ntp_req:  .byte $23             ; LI 0, version 4, mode 3 (client)
          .fill 47, 0

; NET_APPLYNTP: the 48-byte reply at NET_DATA+2 -> NET_HOUR.. / NET_YEAR..
; and the CIA #1 TOD. A = 0 ok, 1 = zero timestamp (server unsynchronised)
NET_APPLYNTP:
        lda NET_DATA+2+43       ; transmit timestamp, seconds, big-endian
        sta t0
        lda NET_DATA+2+42
        sta t1
        lda NET_DATA+2+41
        sta t2
        lda NET_DATA+2+40
        sta t3
        ora t2
        ora t1
        ora t0
        bne an_ok
        lda #$01
        rts
an_ok:  jsr get_tz
        sta NET_TZ
        jsr add_tz
        lda #$80                ; 86400 = $00015180
        sta d0
        lda #$51
        sta d1
        lda #$01
        sta d2
        lda #$00
        sta d3
        jsr div32               ; t = days since 1900-01-01, rm = seconds of day
        lda t0
        sta days
        lda t1
        sta days+1
        lda rm0
        sta t0
        lda rm1
        sta t1
        lda rm2
        sta t2
        lda #$00
        sta t3
        lda #<3600
        sta d0
        lda #>3600
        sta d1
        lda #$00
        sta d2
        sta d3
        jsr div32
        lda t0
        sta NET_HOUR
        lda rm0
        sta t0
        lda rm1
        sta t1
        lda #$00
        sta t2
        sta t3
        lda #60
        sta d0
        lda #$00
        sta d1
        jsr div32
        lda t0
        sta NET_MIN
        lda rm0
        sta NET_SEC
        jsr civil_date
        jsr set_tod
        lda #$00
        rts

; the zone from the settings record (format 2: SETREC+2 = 2, +3 = zone,
; +4 = $a5); anything else -> TZ_DEFAULT, written back so the settings
; app shows what the clock uses
get_tz:
        lda SETREC_VER
        cmp #$02
        bne gt_def
        lda SETREC_TZMAG
        cmp #$a5
        beq gt_ok
gt_def: lda #$02
        sta SETREC_VER
        lda #TZ_DEFAULT
        sta SETREC_TZ
        lda #$a5
        sta SETREC_TZMAG
gt_ok:  lda SETREC_TZ
        rts

; t += NET_TZ * 900 (signed)
add_tz:
        lda NET_TZ
        beq at_d
        bpl at_pos
        eor #$ff
        clc
        adc #$01
        sta tmpc
at_nl:  sec
        lda t0
        sbc #<900
        sta t0
        lda t1
        sbc #>900
        sta t1
        lda t2
        sbc #$00
        sta t2
        lda t3
        sbc #$00
        sta t3
        dec tmpc
        bne at_nl
        rts
at_pos: sta tmpc
at_pl:  clc
        lda t0
        adc #<900
        sta t0
        lda t1
        adc #>900
        sta t1
        lda t2
        adc #$00
        sta t2
        lda t3
        adc #$00
        sta t3
        dec tmpc
        bne at_pl
at_d:   rts

; t (32-bit) / d (32-bit): quotient -> t, remainder -> rm
div32:
        lda #$00
        sta rm0
        sta rm1
        sta rm2
        sta rm3
        ldx #32
dv_l:   asl t0
        rol t1
        rol t2
        rol t3
        rol rm0
        rol rm1
        rol rm2
        rol rm3
        sec
        lda rm0
        sbc d0
        sta q0
        lda rm1
        sbc d1
        sta q1
        lda rm2
        sbc d2
        sta q2
        lda rm3
        sbc d3
        sta q3
        bcc dv_n
        lda q0
        sta rm0
        lda q1
        sta rm1
        lda q2
        sta rm2
        lda q3
        sta rm3
        inc t0
dv_n:   dex
        bne dv_l
        rts

; days since 1900-01-01 -> NET_YEAR / NET_MON / NET_DAY / NET_WDAY
civil_date:
        clc
        lda days
        adc #$01                ; 1900-01-01 was a Monday
        sta t0
        lda days+1
        adc #$00
        sta t1
        lda #$00
        sta t2
        sta t3
        lda #$07
        sta d0
        lda #$00
        sta d1
        sta d2
        sta d3
        jsr div32
        lda rm0
        sta NET_WDAY
        lda #<1900
        sta NET_YEAR
        lda #>1900
        sta NET_YEAR+1
cd_yl:  jsr days_in_year
        lda days+1
        cmp diy+1
        bcc cd_ml
        bne cd_ysub
        lda days
        cmp diy
        bcc cd_ml
cd_ysub:
        sec
        lda days
        sbc diy
        sta days
        lda days+1
        sbc diy+1
        sta days+1
        inc NET_YEAR
        bne cd_yl
        inc NET_YEAR+1
        jmp cd_yl
cd_ml:  lda #$01
        sta NET_MON
cd_mm:  ldx NET_MON
        lda mdays-1,x
        cpx #$02
        bne cd_m2
        ldy leap
        beq cd_m2
        lda #29
cd_m2:  sta tmpd
        lda days+1
        bne cd_msub
        lda days
        cmp tmpd
        bcc cd_md
cd_msub:
        sec
        lda days
        sbc tmpd
        sta days
        lda days+1
        sbc #$00
        sta days+1
        inc NET_MON
        jmp cd_mm
cd_md:  lda days
        clc
        adc #$01
        sta NET_DAY
        rts

; diy = 365 (+1 leap), leap = 1 when NET_YEAR is a leap year. Gregorian
; rule with the century exceptions 1900 and 2100 spelled out (valid
; 1900-2199, the whole NTP era this clock can see).
days_in_year:
        lda #$00
        sta leap
        lda NET_YEAR
        and #$03
        bne diy_n
        lda NET_YEAR+1
        cmp #>1900
        bne diy_c2
        lda NET_YEAR
        cmp #<1900
        beq diy_n
diy_c2: lda NET_YEAR+1
        cmp #>2100
        bne diy_y
        lda NET_YEAR
        cmp #<2100
        beq diy_n
diy_y:  inc leap
diy_n:  clc
        lda #<365
        adc leap
        sta diy
        lda #>365
        adc #$00
        sta diy+1
        rts
mdays:  .byte 31,28,31,30,31,30,31,31,30,31,30,31

; NET_HOUR/MIN/SEC -> CIA #1 TOD (12 h BCD, bit 7 = PM). The 6526 inverts
; AM/PM when the hour written is 12: read back once and correct.
set_tod:
        lda NET_HOUR
        ldx #$00
        cmp #12
        bcc st_am
        ldx #$80
        sbc #12
st_am:  cmp #$00
        bne st_h
        lda #12
st_h:   jsr bin2bcd
        stx tmpa
        ora tmpa
        sta todh
        lda NET_MIN
        jsr bin2bcd
        sta todm
        lda NET_SEC
        jsr bin2bcd
        sta tods
        jsr tod_write
        lda TODHRS              ; latches the TOD registers
        tax
        lda TODTEN              ; releases them
        cpx todh
        beq st_ok
        lda todh
        eor #$80
        sta todh
        jsr tod_write
st_ok:  rts
tod_write:
        lda todh
        sta TODHRS              ; stops the clock
        lda todm
        sta TODMIN
        lda tods
        sta TODSEC
        lda #$00
        sta TODTEN              ; restarts it
        rts
bin2bcd:                        ; A (0-99) -> BCD; X preserved
        stx tmpx
        ldx #$00
b2_l:   cmp #10
        bcc b2_d
        sbc #10
        inx
        bne b2_l
b2_d:   sta tmpa
        txa
        asl
        asl
        asl
        asl
        ora tmpa
        ldx tmpx
        rts
bcd2bin:                        ; BCD in A -> binary
        pha
        and #$0f
        sta tmpa
        pla
        lsr
        lsr
        lsr
        lsr
        tax
        lda #$00
b2b_l:  cpx #$00
        beq b2b_d
        clc
        adc #10
        dex
        jmp b2b_l
b2b_d:  clc
        adc tmpa
        rts

; the CIA TOD -> NET_HOUR/MIN/SEC (24 h binary)
read_tod:
        lda TODHRS
        sta todraw              ; keep the PM bit here: bcd2bin clobbers X
        lda TODMIN
        jsr bcd2bin
        sta NET_MIN
        lda TODSEC
        jsr bcd2bin
        sta NET_SEC
        lda TODTEN
        lda todraw
        and #$1f
        jsr bcd2bin
        cmp #12
        bne rt_n12
        lda #$00
rt_n12: bit todraw
        bpl rt_am
        clc
        adc #12
rt_am:  sta NET_HOUR
        rts

; push local date/time into the Ultimate's RTC (DOS SET_TIME, 8 bytes)
rtc_push:
        lda #$01
        sta cmdb
        lda #$27
        sta cmdb+1
        sec
        lda NET_YEAR
        sbc #<1900
        sta cmdb+2              ; year - 1900
        lda NET_MON
        sta cmdb+3
        lda NET_DAY
        sta cmdb+4
        lda NET_HOUR
        sta cmdb+5
        lda NET_MIN
        sta cmdb+6
        lda NET_SEC
        sta cmdb+7
        lda #<cmdb
        sta r0L
        lda #>cmdb
        sta r0H
        lda #$08
        jmp NET_CMD

NET_RTCTIME:
        lda #<c_gettime
        sta r0L
        lda #>c_gettime
        sta r0H
        lda #$02
        jmp NET_CMD             ; "YYYY/MM/DD HH:MM:SS" at NET_DATA, 0-terminated
c_gettime: .byte $01, $26

;--------------------------------------------------------------------------
; NET_TZSHIFT: A = signed quarter-hours; shifts the running TOD by that
; much (a zone change in settings takes effect at once, no network needed)
NET_TZSHIFT:
        sta tmpd
        jsr read_tod
        lda NET_HOUR
        jsr mul60
        clc
        lda t0
        adc NET_MIN
        sta t0
        bcc tz_a
        inc t1
tz_a:   lda tmpd
        bpl tz_pos
        eor #$ff
        clc
        adc #$01
        sta tmpc
tz_nl:  sec
        lda t0
        sbc #15
        sta t0
        lda t1
        sbc #$00
        sta t1
        dec tmpc
        bne tz_nl
        jmp tz_wrap
tz_pos: beq tz_wrap
        sta tmpc
tz_pl:  clc
        lda t0
        adc #15
        sta t0
        bcc tz_p2
        inc t1
tz_p2:  dec tmpc
        bne tz_pl
tz_wrap:
        lda t1
        bmi tz_neg
        cmp #>1440
        bcc tz_set
        bne tz_sub
        lda t0
        cmp #<1440
        bcc tz_set
tz_sub: sec
        lda t0
        sbc #<1440
        sta t0
        lda t1
        sbc #>1440
        sta t1
        jmp tz_set
tz_neg: clc
        lda t0
        adc #<1440
        sta t0
        lda t1
        adc #>1440
        sta t1
tz_set: lda #$00
        sta t2
        sta t3
        lda #60
        sta d0
        lda #$00
        sta d1
        sta d2
        sta d3
        jsr div32
        lda t0
        sta NET_HOUR
        lda rm0
        sta NET_MIN
        jsr set_tod
        clc
        lda NET_TZ
        adc tmpd
        sta NET_TZ
        rts
mul60:  sta tmpa                ; A -> t0/t1 = A * 60
        lda #$00
        sta t0
        sta t1
        ldx #60
m60_l:  clc
        lda t0
        adc tmpa
        sta t0
        bcc m60_n
        inc t1
m60_n:  dex
        bne m60_l
        rts

;--------------------------------------------------------------------------
; variables (driver-private)
tmo0:     .byte 0
hidx:     .byte 0
failcode: .byte 0
todraw:   .byte 0
tmo1:     .byte 0
tmo2:     .byte 0
cmdlen:   .byte 0
cmdlen2:  .byte 0
ifcnt:    .byte 0
ifidx:    .byte 0
tries:    .byte 0
applyres: .byte 0
tmpx:     .byte 0
tmpy:     .byte 0
days:     .word 0
diy:      .word 0
leap:     .byte 0
todh:     .byte 0
todm:     .byte 0
tods:     .byte 0
q2:       .byte 0
q3:       .byte 0
tmpd:     .byte 0
cmdb:     .fill 204, 0          ; command image: 3 header + up to 200 data / 4 + host
net_end:
