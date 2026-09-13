; Forward LZSA2 decoder adapted for uOS from Emmanuel Marty's small v2 decoder.
; Upstream commit 15ee2dfe118eeb8f7683ca44f64821c3a61ca1e5.
; Modified: 64tass syntax; private absolute nibble state; checked input/output,
; CRC16 and backreference gates in boot-unpack.asm; zero initial repeat offset.
; No zero-page bytes are borrowed. Errors unwind to the boot caller's saved SP.
; The original zlib license notice follows unchanged.
;  Copyright (C) 2019 Emmanuel Marty
;
;  This software is provided 'as-is', without any express or implied
;  warranty.  In no event will the authors be held liable for any damages
;  arising from the use of this software.
;
;  Permission is granted to anyone to use this software for any purpose,
;  including commercial applications, and to alter it and redistribute it
;  freely, subject to the following restrictions:
;
;  1. The origin of this software must not be misrepresented; you must not
;     claim that you wrote the original software. If you use this software
;     in a product, an acknowledgment in the product documentation would be
;     appreciated but is not required.
;  2. Altered source versions must be plainly marked as such, and must not be
;     misrepresented as being the original software.
;  3. This notice may not be removed or altered from any source distribution.
; -----------------------------------------------------------------------------

DECOMPRESS_LZSA2:
   LDY #$00
   STY NIBCOUNT

DECODE_TOKEN:
   JSR boot_get                           ; read token byte: XYZ|LL|MMM
   PHA                                  ; preserve token on stack

   AND #$18                             ; isolate literals count (LL)
   BEQ NO_LITERALS                      ; skip if no literals to copy
   LSR                                  ; shift literals count into place
   LSR
   LSR
   CMP #$03                             ; LITERALS_RUN_LEN_V2?
   BCC PREPARE_COPY_LITERALS            ; if less, count is directly embedded in token

   JSR GETNIBBLE                        ; get extra literals length nibble
                                        ; add nibble to len from token
   ADC #$02                             ; (LITERALS_RUN_LEN_V2) minus carry
   CMP #$12                             ; LITERALS_RUN_LEN_V2 + 15 ?
   BCC PREPARE_COPY_LITERALS            ; if less, literals count is complete

   JSR boot_get                           ; get extra byte of variable literals count
   CMP #$EE                             ; 238 is reserved for literals
   BEQ boot_bad
   CMP #$F0                             ; 239 introduces a 16-bit count
   BCS boot_bad
   SEC
   SBC #$EE                             ; overflow?

PREPARE_COPY_LITERALS:
   TAX
   BCC PREPARE_COPY_LITERALS_HIGH       ; if not, literals count is complete

                                        ; handle 16 bits literals count
                                        ; literals count = directly these 16 bits
   JSR GETLARGESRC                      ; grab low 8 bits in X, high 8 bits in A
   TAY                                  ; put high 8 bits in Y

PREPARE_COPY_LITERALS_HIGH:
   TXA
   BEQ COPY_LITERALS
   INY

COPY_LITERALS:
   JSR GETPUT                           ; copy one byte of literals
   DEX
   BNE COPY_LITERALS
   DEY
   BNE COPY_LITERALS

NO_LITERALS:
   PLA                                  ; retrieve token from stack
   PHA                                  ; preserve token again
   ASL
   BCS REPMATCH_OR_LARGE_OFFSET         ; 1YZ: rep-match or 13/16 bit offset

   ASL                                  ; 0YZ: 5 or 9 bit offset
   BCS OFFSET_9_BIT

                                        ; 00Z: 5 bit offset

   LDX #$FF                             ; set offset bits 15-8 to 1

   JSR GETCOMBINEDBITS                  ; rotate Z bit into bit 0, read nibble for bits 4-1
   ORA #$E0                             ; set bits 7-5 to 1
   BNE GOT_OFFSET_LO                    ; go store low byte of match offset and prepare match

OFFSET_9_BIT                            ; 01Z: 9 bit offset
   ROL                                  ; carry: Z bit; A: xxxxxxx1 (carry known set from BCS OFFSET_9_BIT)
   ADC #$00                             ; if Z bit is set, add 1 to A (bit 0 of A is now 0), otherwise bit 0 is 1
   ORA #$FE                             ; set offset bits 15-9 to 1. reversed Z is already in bit 0
   BNE GOT_OFFSET_HI                    ; go store high byte, read low byte of match offset and prepare match
                                        ; (*same as JMP GOT_OFFSET_HI but shorter)

REPMATCH_OR_LARGE_OFFSET:
   ASL                                  ; 13 bit offset?
   BCS REPMATCH_OR_16_BIT               ; handle rep-match or 16-bit offset if not

                                        ; 10Z: 13 bit offset

   JSR GETCOMBINEDBITS                  ; rotate Z bit into bit 8, read nibble for bits 12-9
   ADC #$DE                             ; set bits 15-13 to 1 and substract 2 (to substract 512)
   BNE GOT_OFFSET_HI                    ; go store high byte, read low byte of match offset and prepare match
                                        ; (*same as JMP GOT_OFFSET_HI but shorter)

REPMATCH_OR_16_BIT                      ; rep-match or 16 bit offset
   BMI REP_MATCH                        ; reuse previous offset if so (rep-match)

                                        ; 110: handle 16 bit offset
   JSR boot_get                           ; grab high 8 bits
GOT_OFFSET_HI:
   TAX
   JSR boot_get                           ; grab low 8 bits
GOT_OFFSET_LO:
   STA OFFSLO                           ; store low byte of match offset
   STX OFFSHI                           ; store high byte of match offset

REP_MATCH:
   ; Forward decompression - add match offset

   CLC                                  ; add dest + match offset
   LDA boot_write+1                         ; low 8 bits
OFFSLO = *+1
   ADC #$00
   STA COPY_MATCH_LOOP+1                ; store back reference address
OFFSHI = *+1
   LDA #$00                             ; high 8 bits
   ADC boot_write+2
   STA COPY_MATCH_LOOP+2                ; store high 8 bits of address
   SEC                                  ; lengths always include minmatch 2



   PLA                                  ; retrieve token from stack again
   AND #$07                             ; isolate match len (MMM)
   ADC #$01                             ; add MIN_MATCH_SIZE_V2 and carry
   CMP #$09                             ; MIN_MATCH_SIZE_V2 + MATCH_RUN_LEN_V2?
   BCC PREPARE_COPY_MATCH               ; if less, length is directly embedded in token

   JSR GETNIBBLE                        ; get extra match length nibble
                                        ; add nibble to len from token
   ADC #$08                             ; (MIN_MATCH_SIZE_V2 + MATCH_RUN_LEN_V2) minus carry
   CMP #$18                             ; MIN_MATCH_SIZE_V2 + MATCH_RUN_LEN_V2 + 15?
   BCC PREPARE_COPY_MATCH               ; if less, match length is complete

   JSR boot_get                           ; get extra byte of variable match length
   CMP #$EA                             ; 232 is EOD, 233 a 16-bit count
   BCS boot_bad
   SEC
   SBC #$E8                             ; overflow?

PREPARE_COPY_MATCH:
   TAX
   BCC PREPARE_COPY_MATCH_Y             ; if not, the match length is complete
   BEQ DECOMPRESSION_DONE               ; if EOD code, bail

                                        ; Handle 16 bits match length
   JSR GETLARGESRC                      ; grab low 8 bits in X, high 8 bits in A
   TAY                                  ; put high 8 bits in Y

PREPARE_COPY_MATCH_Y:
   JSR boot_match                       ; validate before reading a backreference
   TXA
   BEQ COPY_MATCH_LOOP
   INY

COPY_MATCH_LOOP:
   LDA $AAAA                            ; get one byte of backreference
   JSR boot_put                           ; copy to destination



   ; Forward decompression -- put backreference bytes forward

   INC COPY_MATCH_LOOP+1
   BNE GETMATCH_DONE
   INC COPY_MATCH_LOOP+2
GETMATCH_DONE:
   DEX
   BNE COPY_MATCH_LOOP
   DEY
   BNE COPY_MATCH_LOOP
   JMP DECODE_TOKEN

GETCOMBINEDBITS:
   EOR #$80
   ASL
   PHP

   JSR GETNIBBLE                        ; get nibble into bits 0-3 (for offset bits 1-4)
   PLP                                  ; merge Z bit as the carry bit (for offset bit 0)
   ROL                                  ; nibble -> bits 1-4; carry(!Z bit) -> bit 0 ; carry cleared
DECOMPRESSION_DONE:
   RTS

GETNIBBLE:
NIBBLES = *+1
   LDA #$AA
   LSR NIBCOUNT
   BCS HAS_NIBBLES

   INC NIBCOUNT
   JSR boot_get                           ; get 2 nibbles
   STA NIBBLES
   LSR
   LSR
   LSR
   LSR
   SEC

HAS_NIBBLES:
   AND #$0F                             ; isolate low 4 bits of nibble
   RTS



   ; Forward decompression -- get and put bytes forward

GETPUT:
   JSR boot_get
   JMP boot_put
GETLARGESRC:
   JSR boot_get
   TAX
   JMP boot_get
NIBCOUNT: .byte 0
