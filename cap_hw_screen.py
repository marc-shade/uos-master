#!/usr/bin/env python3
"""Screenshot the REAL C128's VIC-II hires bitmap (uOS) over Ultimate II+ DMA.

The bitmap lives at $a000-$bf3f, under the BASIC ROM. The Ultimate's DMA
readmem returns the ROM there regardless of the CPU's banking (verified: the
read is byte-identical to basic-901226-01 and $01 is not on the bus), so the
CPU itself must lift the RAM out. This installs a one-shot IRQ wedge — hooked
atomically through $0314 in a single DMA write, so it runs whatever app owns
the CPU — that banks BASIC out ($01=$36, KERNAL stays in), copies 4000 bytes
to free RAM at $4000-$4f9f, restores $01 and the zero page it borrowed
($fb-$fe: the gfx engine's font pointer lives there), unhooks itself, chains
to the previous handler, and raises a flag at $03fb. Two passes cover the
8000-byte bitmap. Rendered mono, 2x, via PBM -> magick.

usage: cap_hw_screen.py OUT.png
"""
import importlib.util
import os
import subprocess
import sys
import time

from importlib.machinery import SourceFileLoader
_cbm = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _cbm))
_cbm.exec_module(cbm)

BITMAP = 0xA000
STAGE = 0x4000            # 4000 bytes: $4000-$4f9f (free RAM between desktop and apps)
WEDGE = 0x0340            # cassette buffer; uOS only uses $033c/$033d there
FLAG = 0x03FB
IRQV = 0x0314
CHUNK = 4000              # 15 full pages + 160 bytes


def wedge_code(src, old_lo, old_hi):
    lo, hi = src & 0xFF, src >> 8
    code = bytes([
        0xA5, 0xFB, 0x48,             # lda $fb / pha
        0xA5, 0xFC, 0x48,             # lda $fc / pha
        0xA5, 0xFD, 0x48,             # lda $fd / pha
        0xA5, 0xFE, 0x48,             # lda $fe / pha
        0xA5, 0x01, 0x48,             # lda $01 / pha
        0xA9, 0x36, 0x85, 0x01,       # lda #$36 / sta $01   (BASIC out, KERNAL in)
        0xA9, lo, 0x85, 0xFB,         # src -> $fb/$fc
        0xA9, hi, 0x85, 0xFC,
        0xA9, STAGE & 0xFF, 0x85, 0xFD,   # dst -> $fd/$fe
        0xA9, STAGE >> 8, 0x85, 0xFE,
        0xA2, 0x0F,                   # ldx #15 pages
        0xA0, 0x00,                   # page: ldy #0
        0xB1, 0xFB, 0x91, 0xFD,       # loop: lda ($fb),y / sta ($fd),y
        0xC8, 0xD0, 0xF9,             # iny / bne loop
        0xE6, 0xFC, 0xE6, 0xFE,       # inc $fc / inc $fe
        0xCA, 0xD0, 0xF0,             # dex / bne page
        0xA0, 0x00,                   # ldy #0
        0xB1, 0xFB, 0x91, 0xFD,       # tail: lda ($fb),y / sta ($fd),y
        0xC8, 0xC0, 0xA0, 0xD0, 0xF7, # iny / cpy #160 / bne tail
        0x68, 0x85, 0x01,             # pla / sta $01
        0x68, 0x85, 0xFE,             # pla / sta $fe
        0x68, 0x85, 0xFD,             # pla / sta $fd
        0x68, 0x85, 0xFC,             # pla / sta $fc
        0x68, 0x85, 0xFB,             # pla / sta $fb
        0xA9, 0x01, 0x8D, FLAG & 0xFF, FLAG >> 8,      # lda #1 / sta FLAG
        0xA9, old_lo, 0x8D, 0x14, 0x03,                # restore $0314
        0xA9, old_hi, 0x8D, 0x15, 0x03,                # restore $0315
        0x4C, old_lo, old_hi,                          # jmp old handler
    ])
    assert len(code) <= 0xBB, len(code)   # must stay clear of $03fb
    return code


def grab(u, verbose=True):
    rd = lambda a, n: bytes(u.read_mem(a, n))

    def wr(a, d):
        for i in range(0, len(d), 128):
            u.write_mem(a + i, d[i:i + 128])

    old = rd(IRQV, 2)
    if old == bytes([WEDGE & 0xFF, WEDGE >> 8]):
        raise SystemExit("a previous wedge is still hooked at $0314 — machine state unclear")
    out = b""
    for part in range(2):
        src = BITMAP + part * CHUNK
        wr(FLAG, b"\x00")
        wr(WEDGE, wedge_code(src, old[0], old[1]))
        wr(IRQV, bytes([WEDGE & 0xFF, WEDGE >> 8]))    # ONE write: atomic vs the CPU
        t0 = time.time()
        while time.time() - t0 < 10 and rd(FLAG, 1)[0] != 1:
            time.sleep(0.2)
        if rd(FLAG, 1)[0] != 1:
            raise SystemExit(f"wedge never ran for chunk {part} ($0314 now {rd(IRQV,2).hex()})")
        if rd(IRQV, 2) != old:
            raise SystemExit("wedge ran but $0314 was not restored")
        out += rd(STAGE, CHUNK)
        if verbose:
            print(f"  chunk {part}: copied ${src:04x}.. in {time.time()-t0:.2f}s", file=sys.stderr)
    return out


def render(bmp, out):
    W, H = 320, 200
    pbm = os.path.splitext(out)[0] + ".pbm"
    with open(pbm, "wb") as f:
        f.write(b"P4\n%d %d\n" % (W, H))
        for y in range(H):
            f.write(bytes(bmp[(y // 8) * 320 + cx * 8 + (y % 8)] for cx in range(W // 8)))
    subprocess.run(["magick", pbm, "-scale", "200%", out], check=True)
    os.remove(pbm)


def main():
    out = sys.argv[1]
    u = cbm.Ultimate()
    bmp = grab(u)
    render(bmp, out)
    ink = sum(bin(b).count("1") for b in bmp)
    print(f"wrote {out}  ({ink} set pixels of 64000; BASIC-ROM signature would be 26160)")


if __name__ == "__main__":
    main()
