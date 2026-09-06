;==========================================================================
; UltOS
; Scott Hutter
;
;   This file is part of UltOS.
;
;    UltOS is free software: you can redistribute it and/or modify
;    it under the terms of the GNU General Public License as published by
;    the Free Software Foundation, either version 3 of the License, or
;    (at your option) any later version.
;
;    UltOS is distributed in the hope that it will be useful,
;    but WITHOUT ANY WARRANTY; without even the implied warranty of
;    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
;    GNU General Public License for more details.
;
;    You should have received a copy of the GNU General Public License
;    along with UltOS.  If not, see <https://www.gnu.org/licenses/>.
;==========================================================================

brkVectorlo     = $0316
brkVectorhi     = $0317

MAINLOOP        = $0811
FIND_CTL        = $0814
FS_APP          = $0817
FS_SCREEN       = $081a
FS_RECT         = $081d
CLR_RECT        = $0820
LOAD_IMM        = $0823
APP_LOADER      = $0826
FILLFILE        = $0829
KEYIN           = $082c
GETCAP          = $082f
LAUNCH_APP      = $0832  ; file buffer -> LOADER + jmp APP_START, core-resident
VDTEXT          = $0835  ; 80-col companion: A=row X=col r9->PETSCII (no-op if no VDC)
VDCLR           = $0838  ; 80-col companion: A=row -> blank the row (no-op if no VDC)
; settings record (FR-S3): saved as "UOS-SET" by the settings app, loaded
; back at boot into the app region
SETREC          = $7350
SETREC_DISP     = $7355  ; display mode  (0=40 1=80 2=both)
SETREC_BG       = $7356  ; desktop background colour (0-15 VIC colour)
; record format 2 (2026-09-06) uses the three formerly reserved bytes that
; every saved record already carries: version, time zone, zone marker.
; Older records load 0 there and the clock falls back to TZ_DEFAULT.
SETREC_VER      = $7352  ; 2 = the zone bytes below are valid
SETREC_TZ       = $7353  ; time zone, signed quarter-hours from UTC (-48..+56)
SETREC_TZMAG    = $7354  ; $a5 when SETREC_TZ was written by the OS
; uVDC second-display driver (origin $cc00)
; uos-vdc exports via a FIXED JUMP TABLE at $cc00 (3 bytes per slot). Never
; point these at the routines' own addresses: those shift with every driver
; edit, and stale copies here made the core jump into the middle of other
; routines (the root cause of the 80-column boot hangs).
VDC_GETREG      = $cc00
VDC_SETREG      = $cc03
VDC_SEEK        = $cc06
VDC_PUTS        = $cc09
VDC_PUTCHR      = $cc0c
VDC_CLS         = $cc0f
VDC_FONTUP      = $cc12
VDC_INIT        = $cc15
VDC_PRESENT     = $cc18
VDC_TEXT        = $cc1b  ; A=row X=col r9->PETSCII text on the 80-col display
VDC_CLR         = $cc1e  ; A=row -> blank the row
VDC_BANNER      = $cc21  ; header rows 0-1
VDC_LIVE        = $cc24  ; byte: 1 once VDSETUP brought the 8563 up
; uVDC caller pointers (zero page convention shared with driver)
vdcbpL          = $23
vdcbpH          = $24
vdcdpL          = $25
vdcdpH          = $26

DESK_START      = $1000
DESK_END        = $2fff

APP_START       = $5000
APP_END         = $8fff

APP_CTL_TBL     = $9000
APP_CTL_CTR     = $9000
APP_CTL_BUF     = $9001
APP_CTL_END     = $9100  ; 25 ten-byte control slots; TESTCLICK indexes them
                         ; with X anyway (was bounded by APP_ID_TBL = $9b00,
                         ; 2026-09-06: $9100-$9aff now holds uos-net)
APP_ID_TBL      = $9b00

REU_SIZE        = $9c00
REU_STASH       = $9c03
REU_FETCH       = $9c06
REU_PARAMS      = $9c09

; uos-net: Ultimate II+ command interface (network + SNTP clock), fixed
; jump table at NET_BASE ($9100-$9aff, above the control table); the data
; bytes after the table are read back by the tests. NET_DATA is the
; 512-byte reply buffer in the free $8800 page pair.
NET_BASE        = $9100
NET_PRESENT     = NET_BASE+$00  ; A=1 when the command interface answers
NET_CMD         = NET_BASE+$03  ; r0->bytes (target first), A=len -> A=status code, C=1 absent/timeout
NET_GETIP       = NET_BASE+$06  ; A=1 when an interface has an address (NET_IP/NET_IPSTR)
NET_OPEN        = NET_BASE+$09  ; A=7 tcp / 8 udp, r0->host, r1=port -> A=socket, C=1 failed
NET_CLOSE       = NET_BASE+$0c  ; A=socket
NET_READ        = NET_BASE+$0f  ; A=socket, r1=max -> NET_DATA+2.., NET_LEN; A: 0 ok 1 none 2 closed 3 error
NET_WRITE       = NET_BASE+$12  ; A=socket, r0->data, X=len (1..200) -> A=status code
NET_SYNC        = NET_BASE+$15  ; network check + SNTP -> CIA TOD + Ultimate RTC; A=NET_STATE
NET_APPLYNTP    = NET_BASE+$18  ; NET_DATA+2.. = 48-byte NTP reply -> time/date/TOD; A=0 ok
NET_RTCTIME     = NET_BASE+$1b  ; Ultimate RTC "YYYY/MM/DD HH:MM:SS" -> NET_DATA; A=status code
NET_TZSHIFT     = NET_BASE+$1e  ; A=signed quarter-hours -> shift the running TOD
NET_STATE       = NET_BASE+$21  ; $ff not tried, 0 ntp synced, 1 no reply, 2 no network, 3 no ultimate, 4 open failed
NET_HOUR        = NET_BASE+$22  ; local time 24 h binary
NET_MIN         = NET_BASE+$23
NET_SEC         = NET_BASE+$24
NET_YEAR        = NET_BASE+$25  ; word
NET_MON         = NET_BASE+$27
NET_DAY         = NET_BASE+$28
NET_WDAY        = NET_BASE+$29  ; 0 = sunday
NET_TZ          = NET_BASE+$2a  ; quarter-hours applied
NET_IP          = NET_BASE+$2b  ; 4 bytes
NET_IPSTR       = NET_BASE+$2f  ; dotted decimal, 0-terminated ("" = none)
NET_LEN         = NET_BASE+$3f  ; word: payload length of the last reply / read
NET_SOCK        = NET_BASE+$41
NET_STAT        = NET_BASE+$42  ; 32 bytes: last status line "NN,TEXT"
NET_DATA        = $8800  ; 512-byte reply buffer (socket payload at +2)

; drv1351 entry points: $9e00 = install1 (port 1), $9e03 = install2 (port 2),
; $9e06 = remove, $9e09 = KEYIN_EXT.
; Port 2 is the default on purpose: a device in control port 1 pulls the
; keyboard-matrix row lines ($dc01), and the KERNAL scan reads that as
; keypresses — on the real C128 a 1351 in port 1 flooded the shell's command
; line with phantom 'W's (verified A/B with hw_phantom.py, 2026-09-05).
; Port 2 is the C64 convention precisely to avoid that.
; (Origin moved $9f00 -> $9e00 on 2026-09-06 to make room for KEYIN_EXT.)
INIT_MOUSE      = $9e03
; KEYIN_EXT: the OS keyboard read (KEYIN = $082c jumps here). KERNAL GETIN
; plus what the C64-mode KERNAL cannot see on a C128: the ESC key and the
; dedicated cursor keys live on the VIC-IIe extended matrix ($d02f), so
; they are scanned here (one event per press); RUN/STOP is an ESC alias
; for C64 keyboards. Returns A = PETSCII ($1b ESC, $91/$11/$9d/$1d cursors)
KEYIN_EXT       = $9e09
KEY_EXTSEEN     = $9e0c  ; byte: sticky 1 once the C128 ESC line was seen low (tests)

BITMAP_START    = $a000

GFX_INIT        = $c000
GFX_SETPIXEL    = $c00f
GFX_DRAWBYTEPATTERN = $c021
GFX_ON          = $c006
GFX_OFF         = $c009
GFX_SETCOLOR    = $c00c
GFX_LINE        = $c015
GFX_CIRCLE      = $c018
GPUTC           = $c01b
GPUTS           = $c01e

