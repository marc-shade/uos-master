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
; settings record (FR-S3): saved as "UOS-SET" by the settings app, loaded
; back at boot into the app region
SETREC          = $7350
SETREC_DISP     = $7355
; uVDC second-display driver (origin $cc00)
VDC_GETREG      = $cc00
VDC_SETREG      = $cc07
VDC_SEEK        = $cc14
VDC_PUTS        = $cc31
VDC_PUTCHR      = $cc7b
VDC_CLS         = $cc88
VDC_FONTUP      = $cce4
VDC_INIT        = $cd1b
VDC_PRESENT     = $cd56
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
APP_ID_TBL      = $9b00

REU_SIZE        = $9c00
REU_STASH       = $9c03
REU_FETCH       = $9c06
REU_PARAMS      = $9c09

; drv1351 entry points: $9f00 = install1 (port 1), $9f03 = install2 (port 2).
; Port 2 is the default on purpose: a device in control port 1 pulls the
; keyboard-matrix row lines ($dc01), and the KERNAL scan reads that as
; keypresses — on the real C128 a 1351 in port 1 flooded the shell's command
; line with phantom 'W's (verified A/B with hw_phantom.py, 2026-09-05).
; Port 2 is the C64 convention precisely to avoid that.
INIT_MOUSE      = $9f03

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

