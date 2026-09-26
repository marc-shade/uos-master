"""Independent expectation of the GEM desktop (docs/GEM-DESKTOP.md)."""
import native_aes_scene as scene

MENU = b'Desk:About uOS...;File:Open^O|-|Close^W;Options:Launcher^L'
ICONS = [(2, b'Boot', 0), (6, b'Drive 9', 0), (20, b'Trash', 1)]
DESK, ICON_SELECTED, PAPER, SELECTED = 0x16, 0x61, 0x61, 0x16
ART = [
    [0x7ffffffe, 0x40000002, 0x40000002, 0x47ffffe2, 0x40000002, 0x40000002, 0x40000002, 0x40000002,
     0x40000002, 0x40000002, 0x40000002, 0x4000001a, 0x4000001a, 0x40000002, 0x7ffffffe, 0],
    [0x000ff000, 0x3ffffffc, 0x3ffffffc, 0x10000008] + [0x12492488]*9 + [0x10000008, 0x1ffffff8, 0],
]
KIND = (scene.WK['NAME'] | scene.WK['CLOSER'] | scene.WK['FULLER'] | scene.WK['MOVER'] |
        scene.WK['SIZER'] | scene.WK['UP'] | scene.WK['DN'] | scene.WK['VSLIDE'])
TYPES = [b'DEL', b'SEQ', b'PRG', b'USR', b'REL']


def draw_icons(s, selected=None):
    for index, (y, label, art) in enumerate(ICONS):
        for g in range(8):
            column, half = g & 3, g >> 2
            rows = [(ART[art][half*8+r] >> (24-8*column)) & 255 for r in range(8)]
            s.glyph(34+column, y+half, rows)
        s.colors(34, y, 38, y+2, ICON_SELECTED if selected == index else DESK)
        s.rect(31*8, (y+2)*8, 320, (y+2)*8+8, 0)
        s.text(288-len(label)*4, (y+2)*8, label)


def desktop(selected=None):
    s = scene.Surface(bytes(8192)+bytes([DESK])*1024)
    draw_icons(s, selected)
    return scene.menu_draw(bytes(s.data), MENU)[0]


def row_text(entry):
    name = bytes(32 if c == 0xa0 or (c & 0x7f) < 32 else c & 0x7f for c in entry['name'].ljust(16, b'\xa0'))
    blocks = str(entry['blocks']).rjust(4).encode()
    return name+b' '+TYPES[entry['type'] if entry['type'] < 5 else 0]+b' '+blocks


def listing(entries, window):
    """content callback: rows from window['top'], selection inverted."""
    def draw(s, win, g):
        s.clip = (g['wx']*8, g['wy']*8, (g['wx']+g['ww'])*8, (g['wy']+g['wh'])*8)
        for i in range(g['wh']):
            n = window['top']+i
            if n >= len(entries):
                break
            s.text(g['wx']*8, (g['wy']+i)*8, row_text(entries[n]))
            if n == window.get('selected'):
                s.colors(g['wx'], g['wy']+i, g['wx']+g['ww'], g['wy']+i+1, SELECTED)
        s.clip = (0, 0, 320, 200)
    return draw


def slider(count, wh, top):
    size = 255 if count <= wh else wh*255//count
    most = max(0, count-wh)
    return size, (0 if most == 0 else top*255//most)


def picture(windows, entries_of, selected_icon=None):
    """windows: list (bottom->top) of dicts id/x/y/w/h/title/top/selected/entries."""
    base = desktop(selected_icon)
    out = []
    for w in windows:
        g = scene.geometry(dict(kind=KIND, **{k: w[k] for k in ('x', 'y', 'w', 'h')}))
        size, pos = slider(len(entries_of[w['id']]), g['wh'], w['top'])
        out.append(dict(id=w['id'], kind=KIND, x=w['x'], y=w['y'], w=w['w'], h=w['h'],
                        title=w['title'], vsize=size, vpos=pos))
    fills = {w['id']: (0, PAPER) for w in windows}
    def content(s, win, g):
        w = next(v for v in windows if v['id'] == win['id'])
        listing(entries_of[w['id']], w)(s, win, g)
    return scene.windows_draw(out, fills, base=base, content=content, markers=False)
