#!/usr/bin/env python3
"""Whole VIC/VDC frames through actual editor, selector and display code."""
import argparse
import hashlib
import json
from pathlib import Path

from ci_picker import Picker
from ci_editor_files import Editor
from uci_bus import ROOT


def frame(b):
    return bytes(b.bus.ram[0xa000:0xbf40]), bytes(b.bus.vdc.video[:0x1000])


def check(work):
    b = Picker(real_display=True)
    b.start(7,default=b'Wi.im-WWWW-0123456789-abcdefghijklmnop.txt')
    b.run(); b.run(0x85)
    original = frame(b)
    b.run(0xc9); b.run(0x14)
    assert frame(b) == original, 'selector filename erase differs'
    caret_x = []
    for key in (0x13, 0x1d, 0x1d, 0x9d):
        b.run(key)
        bitmap = frame(b)[0]
        xs = [x for y in range(155,165) for x in range(16,304)
              if bitmap[y//8*320+x//8*8+y%8] & (0x80 >> (x%8))]
        want = 16+8*b.value('cursor')
        assert min(xs) == want and max(xs) == want+4, (key,min(xs),max(xs),want)
        caret_x.append(want)
    picker_frame = frame(b)
    b = Editor(real_display=True)
    b.run(); b.type(b'Wi')
    original = frame(b)
    b.type(b'X'); b.run(0x14)
    assert frame(b) == original, 'editor erase differs'
    # Exact scanlines preserve both the first text line and the desktop clock.
    bitmap = original[0]
    assert all(any(bitmap[y//8*320+x//8*8+y%8] & (0x80 >> (x%8))
                   for x in range(16,70)) for y in range(34,41))
    original_doc = b.doc()
    b.run(0x85,picker=True)
    modal = frame(b)[0]
    assert all(modal[y//8*320+x//8*8+y%8] == 0
               for y in range(7,15) for x in range(16,312,8)), 'old editor title remains above selector'
    b.run(27)
    assert b.doc() == original_doc and b.ev('dirty') == 1
    final = frame(b)
    for y in list(range(33,169))+list(range(189,200)):
        for x in range(40):
            i = y//8*320+x*8+y%8
            assert final[0][i] == original[0][i], (y,x,'body/clock changed across modal return')
    assert final[1][4*80:19*80] == original[1][4*80:19*80]
    wide = Editor(real_display=True,legacy=b'\xd7'*38)
    wide.run()
    wide_frame = frame(wide)
    for y in range(33,169):
        assert wide_frame[0][y//8*320+38*8+y%8] == 0, 'wide text escaped the 36-cell text area'
        assert wide_frame[0][y//8*320+39*8+y%8] == 0x80, 'wide text overwrote the window border'
    if work:
        work.mkdir(parents=True,exist_ok=True)
        for label, data in [('picker',picker_frame),('editor',original),('cancel-return',final)]:
            for suffix, content in zip(('vic','vdc'),data):
                (work/f'{label}.{suffix}.bin').write_bytes(content)
    return dict(full_selector_erase=True, full_editor_erase=True, caret_x=caret_x,
                body_and_clock_preserved=True, document_preserved=True, old_title_erased=True,
                wide_text_keeps_border=True)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output',type=Path); args = p.parse_args()
    report = {'build': {n:hashlib.sha256((ROOT/'target'/f'{n}.prg').read_bytes()).hexdigest()
                        for n in ('uos','uos-files','uos-picker','uos-edit','uos-gfx','uos-vdc')}}
    report['checks'] = check(args.output)
    if args.output:
        (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: complete editor and selector frames, aligned caret and modal return',flush=True)


if __name__ == '__main__':
    main()
