"""Independent full-screen expectations for the native Claude launch page."""
LANDING = [
    'CLAUDE / UOS', '', 'CLAUDE CODE ON YOUR C128',
    '80-COLUMN TERMINAL + 40-COLUMN STATUS', '',
    'START THE UOS CLAUDE BRIDGE ON LINUX',
    'USING YOUR CLAUDE LOGIN AND PROJECT.', '',
    'ULTIMATE MODEM: DE00/NMI, 38400 BAUD', '',
    'RETURN: CONNECT', 'F8 OR ESC: DESKTOP', '',
    'DURING SESSION: HELP REPAINTS',
    'F8 RETURNS; ESC GOES TO CLAUDE',
]


def landing_screen(columns, error=0):
    lines = LANDING.copy()
    if error:
        lines += ['', '', 'SERIAL PORT BUSY; CLOSE OTHER SESSION' if error == 1 else
                  'SERIAL PORT UNAVAILABLE; CHECK MODEM']
    result = bytearray(b' '*(columns*25))
    for row, line in enumerate(lines):
        for col, byte in enumerate(line.encode()):
            result[row*columns+col] = byte-64 if 64 <= byte < 96 else byte
    return bytes(result)
