# Claude graphical session controls

Claude now shares the suite's blue VIC bitmap, yellow focus and port-1 1351
pointer. Connect, Repaint and Desktop have icon buttons. Prev and Next expose
all 25 rows of the companion status panel through two overlapping 16-row pages.
The VDC remains an uninterrupted 80×25 terminal.

On the launch page, Tab or arrows select an enabled control; Enter or Space
activates it. Return initially activates Connect. Escape and F8 return to the
desktop. An unavailable or busy modem appears on the second panel page.

During a session, ordinary keys, Tab, arrows, Escape and F1–F7 continue to reach
the host. Help requests a repaint. **Ctrl+Help** switches keyboard focus to the
local controls: Tab/arrows select, Enter/Space activate, and Escape returns
keyboard focus to the terminal. Mouse controls work in either mode. F8 and
Desktop use the existing acknowledged shutdown; another F8 forces a return.

The frame preserves every raw host panel cell and color in the hidden text
screen and color RAM. It renders the actual live VDC glyphs, including all 256
screen codes and custom glyph updates. The full terminal is never reduced to
make room for buttons. With host panels disabled, the client displays its own
connection status. A refused bitmap display retains the text terminal and
its existing serial controls.

## Implementation and ownership

The cc65 image embeds a 64tass GUI segment beginning at `$6080`, after the native
startup at `$6020`. The build generates its static frame from
`native_claude_scene.py`, compresses it as count/value runs, and exports the
segment's vectors and state to the C client. The app owns 75 pages, including
its BSS, saved font and C stack, plus the optional 36-page bitmap at `$c000`.
The resident kernel and its 426-page heap are unchanged.

The foreground renders at most one dirty panel row per input poll after
draining the bounded receive batch. It uses the shared checked bitmap transfers
and the existing credit-controlled serial protocol. The NMI handler only
queues serial input; it never calls graphics, VDC or foreground APIs. Initial
frame rendering happens before opening the serial port.

Claude already saves all 256 programmable-key bytes. While graphics is active,
it installs the shared mouse-line filter in that owned table's unused tail,
and restores the previous KEYCHK callback before restoring the table. Its
optional Ctrl+Help decoder uses the modifier flags supplied with that scan,
so a later modifier release cannot change an enqueued key. The contract is
documented in the pinned Commodore editor sources `ed3.src` and `ed7.src`;
see [source provenance](COMMODORE-SOURCE-REFERENCE.md). Other apps emit the
same filter bytes as before. Keyboard input disarms any held mouse gesture.

Teardown closes serial input before restoring the pointer, callback, bitmap,
border, VDC font/registers, console selection, programmable keys and cc65 zero
page. Native app cleanup releases the allocations. The suite D64 contains
twelve entries and 24 free blocks; the complete mouse workflow saves the module
copy and Paint image on a separate device-9 data disk.

## Qualification

The [software qualification](validation/2026-09-13-native-claude-gui/README.md) passes. `tests/ci_native_claude_gui.py` covers
complete surfaces, keyboard and mouse actions, raw panel cells/colors/glyphs,
modifier decoding, paced serial interrupts during bitmap transfers, fallback
and teardown. `tests/ci_native_claude_iec.py --mouse --cpu-capture` exercises
real VICE mouse controls, ROM Ctrl+Help, the TCP/PTY bridge and acknowledged
shutdown. Add `--80col` for an 80-column cold boot. The full suite mouse runner
also supports `--claude-only` for the launch and unavailable-modem workflow.

This does not install a physical build. Native physical serial qualification,
an authenticated Claude session, a terminal usable on the VIC alone, native
VDC bitmap controls and the wider OS roadmap remain open.
