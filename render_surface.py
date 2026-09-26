#!/usr/bin/env python3
"""Render a 9216-byte native VIC surface (bitmap + colour cells) to PNG."""
import sys
from PIL import Image

# VICE's default C64/C128 VIC-II palette ("pepto")
PALETTE = [(0, 0, 0), (255, 255, 255), (104, 55, 43), (112, 164, 178), (111, 61, 134),
           (88, 141, 67), (53, 40, 121), (184, 199, 111), (111, 79, 37), (67, 57, 0),
           (154, 103, 89), (68, 68, 68), (108, 108, 108), (154, 210, 132), (108, 94, 181),
           (149, 149, 149)]


def render(data, scale=2):
    img = Image.new('RGB', (320, 200))
    px = img.load()
    for y in range(200):
        for x in range(320):
            cell = data[8192+y//8*40+x//8]
            bit = data[y//8*320+x//8*8+y % 8] & (128 >> (x % 8))
            px[x, y] = PALETTE[(cell >> 4) if bit else (cell & 15)]
    return img.resize((320*scale, 200*scale), Image.NEAREST)


if __name__ == '__main__':
    render(open(sys.argv[1], 'rb').read()).save(sys.argv[2])
