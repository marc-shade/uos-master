"""Independent expected character cells for the native Ultimate panel."""
TITLE = ['UOS ULTIMATE', '', 'I INFO  D DRIVES  N NETWORK  T CLOCK', '']
FOOTER = ['', 'R REFRESH   ESC DESKTOP', 'LEFT/RIGHT: TARGET OR INTERFACE']


def panel_screen(columns, body):
    lines = TITLE+body+FOOTER
    assert columns in (40, 80) and len(lines) <= 25
    result = bytearray(b' '*(columns*25))
    for row, line in enumerate(lines):
        assert len(line) < 40, line
        for col, byte in enumerate(line.encode('ascii')):
            result[row*columns+col] = byte-64 if 64 <= byte < 96 else byte
    return bytes(result)
