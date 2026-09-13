"""Desktop layout data and an independent per-pixel surface oracle."""
from src.native.graphics.font import font

OPS = [(0, (16, 27, 304, 28), 1)]
for top in (32, 56, 80, 104, 128):
    OPS.extend([(0, (16, top, 304, top+20), 1),
                (0, (17, top+1, 303, top+19), 0)])
# Calculator, document, folder, cartridge and terminal silhouettes.
OPS.extend([(0, (24, 34, 48, 50), 1), (0, (26, 36, 46, 41), 0)])
for y in (43, 47):
    for x in (27, 34, 41):
        OPS.append((0, (x, y, x+4, y+2), 0))
OPS.extend([(0, (27, 58, 46, 74), 1), (0, (28, 59, 45, 73), 0)])
for y in (61, 65, 69): OPS.append((0, (31, y, 42, y+1), 1))
OPS.extend([(0, (24, 87, 48, 98), 1), (0, (24, 83, 35, 88), 1),
            (0, (26, 89, 46, 96), 0)])
OPS.extend([(0, (24, 107, 48, 119), 1), (0, (26, 109, 46, 117), 0),
            (0, (28, 119, 44, 122), 1), (0, (40, 111, 44, 114), 1)])
OPS.extend([(0, (24, 131, 48, 145), 1), (0, (26, 133, 46, 143), 0),
            (0, (28, 135, 30, 137), 1), (0, (30, 137, 32, 139), 1),
            (0, (28, 139, 30, 141), 1), (0, (35, 140, 42, 141), 1)])
TEXT = [(16, 8, 1, b'uOS 128'), (184, 8, 1, b'Desktop')]
for top, name, description in [
    (32, b'Calculator', b'Numbers and saved history'),
    (56, b'Text editor', b'Documents on disk and USB'),
    (80, b'Files', b'Drives, USB folders, apps'),
    (104, b'Ultimate', b'Drives, network and clock'),
    (128, b'Claude', b'Claude Code terminal'),
]:
    TEXT.extend([(64, top+2, 1, name), (64, top+11, 1, description)])
TEXT.extend([(8, 176, 1, b'Mouse clicks open  C/E/F/U/A open'),
             (8, 188, 1, b'Arrows/Tab/Enter   Esc workspace')])


# Two single-color sprites: white interior (0) over black outline (1).
# Each ASCII pixel is independently translated into the VIC's 24x21 format.
POINTER = [
    'B', 'BB', 'BWB', 'BWWB', 'BWWWB', 'BWWWWB', 'BWWWWWB',
    'BWWWWWWB', 'BWWWWWWWB', 'BWWWWBBBBB', 'BWWBWWB',
    'BWB BWWB', 'BB  BWWB', 'B    BWWB', '     BWWB', '      BB',
]


def pointer_shape():
    output = bytearray()
    for ink in ('W', 'B'):
        for y in range(21):
            row = POINTER[y] if y < len(POINTER) else ''
            bits = sum(1 << (23-x) for x, pixel in enumerate(row) if pixel == ink)
            output.extend(bits.to_bytes(3, 'big'))
        output.append(0)
    return bytes(output)


def surface(selected=0, error=0):
    assert 0 <= selected < 5 and 0 <= error <= 255
    data = bytearray(bytes(8192) + b'\x16' * 1024)
    for mode, (x0, y0, x1, y1), value in OPS:
        assert mode == 0 and value in (0, 1)
        for y in range(max(0, y0), min(200, y1)):
            for x in range(max(0, x0), min(320, x1)):
                at = y//8*320 + x//8*8 + y%8
                mask = 128 >> (x%8)
                if value: data[at] |= mask
                else: data[at] &= mask ^ 255
    labels = TEXT + ([(8, 164, 1, f'App could not open: {error:02X}'.encode())] if error else [])
    glyphs = font()
    for x0, y0, pen, label in labels:
        assert pen == 1
        for column, code in enumerate(label):
            for dy, row in enumerate(glyphs[(code-32)*8:][:8]):
                for dx in range(8):
                    x, y = x0+column*8+dx, y0+dy
                    if 0 <= x < 320 and 0 <= y < 200 and row & (128 >> dx):
                        data[y//8*320+x//8*8+y%8] |= 128 >> (x%8)
    for index, top in enumerate((4, 7, 10, 13, 16)):
        for y in range(top, top+3):
            for x in range(2, 38):
                data[8192+y*40+x] = 0x07 if index == selected else 0x1b
    data[8000:8128] = pointer_shape()
    data[9208:9210] = bytes([0x7d, 0x7e])
    return bytes(data)


def console(columns, selected=0, error=0, fallback=False):
    lines = ['UOS DESKTOP', '']
    for index, (name, description) in enumerate([
        ('C  CALCULATOR', 'NUMBERS AND SAVED HISTORY'),
        ('E  TEXT EDITOR', 'DOCUMENTS ON DISK AND USB'),
        ('F  FILES', 'DRIVES, USB FOLDERS AND APPS'),
        ('U  ULTIMATE', 'DRIVES, NETWORK AND CLOCK'),
        ('A  CLAUDE', 'CLAUDE CODE TERMINAL'),
    ]):
        lines.extend([('>' if selected == index else ' ') + ' ' + name, '    '+description, ''])
    lines.extend(['ARROWS/TAB SELECT. ENTER OPENS.', 'C/E/F/U/A OPEN APPS. ESC WORKSPACE.', ''])
    # Assembly prints no newline after the error value unless the fallback follows.
    lines.append(f'APP COULD NOT OPEN: {error:02X}' if error else '')
    if fallback:
        lines.extend(['GRAPHICS UNAVAILABLE.', 'TEXT CONTROLS REMAIN ACTIVE.'])
    result = bytearray(b' ' * (columns*25))
    for y, line in enumerate(lines):
        for x, char in enumerate(line.encode()):
            result[y*columns+x] = char-64 if 64 <= char < 96 else char
    return bytes(result)


def write_assembly(directory):
    """Generate the assembler's static commands from the reviewed layout."""
    shape = pointer_shape()
    (directory/'pointer-shape.inc').write_text('\n'.join(
        '        .byte '+','.join('$%02x'%v for v in shape[i:i+16])
        for i in range(0, len(shape), 16))+'\n')
    scene = [f'scene_commands_count={len(OPS)}']
    for mode, rect, value in OPS:
        scene.extend(['        .sint '+','.join(map(str, rect)), f'        .byte {mode},{value}'])
    (directory/'scene-commands.inc').write_text('\n'.join(scene)+'\n')
    text = [f'text_commands_count={len(TEXT)}']
    for x, y, pen, label in TEXT:
        text.extend([f'        .word {x},{y}', f'        .byte {pen},{len(label)}',
                     '        .byte '+','.join(map(str, label))])
    (directory/'text-commands.inc').write_text('\n'.join(text)+'\n')
