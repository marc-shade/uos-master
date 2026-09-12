"""Desktop layout data and an independent per-pixel surface oracle."""
from graphics.font import font

OPS = [(0, (16, 27, 304, 28), 1)]
for top in (40, 80, 120):
    OPS.extend([(0, (16, top, 304, top+32), 1),
                (0, (17, top+1, 303, top+31), 0)])
# Small calculator, document and folder silhouettes.
OPS.extend([(0, (24, 47, 48, 66), 1), (0, (26, 49, 46, 54), 0)])
for y in (57, 62):
    for x in (27, 34, 41):
        OPS.append((0, (x, y, x+4, y+2), 0))
OPS.extend([(0, (27, 86, 46, 108), 1), (0, (28, 87, 45, 107), 0)])
for y in (92, 97, 102):
    OPS.append((0, (31, y, 42, y+1), 1))
OPS.extend([(0, (24, 130, 48, 146), 1), (0, (24, 127, 35, 131), 1),
            (0, (26, 133, 46, 144), 0)])
TEXT = [
    (16, 8, 1, b'uOS 128'), (184, 8, 1, b'Desktop'),
    (16, 30, 1, b'Your C128 workspace'),
    (64, 48, 1, b'Calculator'), (64, 60, 1, b'Numbers and saved history'),
    (64, 88, 1, b'Text editor'), (64, 100, 1, b'Documents on disk and USB'),
    (64, 128, 1, b'Files'), (64, 140, 1, b'Drives, USB folders, apps'),
    (8, 176, 1, b'Arrows/Tab select   C/E/F open'),
    (8, 188, 1, b'Enter opens   Esc workspace'),
]


def surface(selected=0, error=0):
    assert 0 <= selected < 3 and 0 <= error <= 255
    data = bytearray(bytes(8192) + b'\x16' * 1024)
    for mode, (x0, y0, x1, y1), value in OPS:
        assert mode == 0 and value in (0, 1)
        for y in range(max(0, y0), min(200, y1)):
            for x in range(max(0, x0), min(320, x1)):
                at = y//8*320 + x//8*8 + y%8
                mask = 128 >> (x%8)
                if value: data[at] |= mask
                else: data[at] &= mask ^ 255
    labels = TEXT + ([(8, 160, 1, f'App could not open: {error:02X}'.encode())] if error else [])
    glyphs = font()
    for x0, y0, pen, label in labels:
        assert pen == 1
        for column, code in enumerate(label):
            for dy, row in enumerate(glyphs[(code-32)*8:][:8]):
                for dx in range(8):
                    x, y = x0+column*8+dx, y0+dy
                    if 0 <= x < 320 and 0 <= y < 200 and row & (128 >> dx):
                        data[y//8*320+x//8*8+y%8] |= 128 >> (x%8)
    for index, top in enumerate((5, 10, 15)):
        for y in range(top, top+4):
            for x in range(2, 38):
                data[8192+y*40+x] = 0x07 if index == selected else 0x1b
    return bytes(data)


def console(columns, selected=0, error=0, fallback=False):
    lines = ['UOS DESKTOP', '']
    for index, (name, description) in enumerate([
        ('C  CALCULATOR', 'NUMBERS AND SAVED HISTORY'),
        ('E  TEXT EDITOR', 'DOCUMENTS ON DISK AND USB'),
        ('F  FILES', 'DRIVES, USB FOLDERS AND APPS'),
    ]):
        lines.extend([('>' if selected == index else ' ') + ' ' + name, '    '+description, ''])
    lines.extend(['ARROWS/TAB SELECT. ENTER OPENS.', 'C/E/F OPEN APPS. ESC WORKSPACE.', ''])
    # Assembly prints no newline after the error value unless the fallback follows.
    lines.append(f'APP COULD NOT OPEN: {error:02X}' if error else '')
    if fallback:
        lines.extend(['GRAPHICS UNAVAILABLE.', 'TEXT CONTROLS REMAIN ACTIVE.'])
    result = bytearray(b' ' * (columns*25))
    for y, line in enumerate(lines):
        for x, char in enumerate(line.encode()):
            result[y*columns+x] = char-64 if 64 <= char < 96 else char
    return bytes(result)
