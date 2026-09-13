# Native graphical Calculator

The Calculator on both native desktop suite disks uses the desktop's blue
bitmap, yellow focused buttons and port-1 1351 pointer. It has a numeric
keypad, arithmetic operators, Delete, Clear, history paging, Save and Close.
The existing 80-column text view remains usable with the same arithmetic and
history shortcuts. Returning from Calculator reloads the blue desktop.

Use digits, `+ - * /`, Enter or `=`, Delete and C as before. Tab or arrows
move button focus; Space presses that button. Mouse movement focuses a button;
press and release on the same button activates it. A stationary pointer leaves
keyboard focus alone. Dragging to another button cancels the press.

S or Save opens the filename dialog. Type a name, use the existing cursor and
editing keys, then Enter or the Save button. Tab selects Save or Cancel; Enter
confirms that choice. Escape or Cancel returns to Calculator. Saving retains
the existing exclusive-create and reopen/compare verification; an existing
file is preserved and a failed write keeps its failure status. N/B and the
Older/Newer buttons page through the 32 retained results.

This remains an unsigned 16-bit integer calculator with immediate operation
evaluation, overflow and division-by-zero reporting. Scientific/decimal modes,
history import, persistent sessions and a graphical VDC interface remain in
the roadmap. The window is fixed; desktop window management is still open.

## Memory and shared controls

The suite Calculator uses 37 app pages, a two-page history in bank 1 and the
existing 36-page VIC surface at bank 0 `$c000..$e3ff`, leaving 351 of the 426
managed pages free. Display and mouse ownership end before app exit or a
history failure. An occupied surface or unsupported display configuration
releases any temporary surface and runs the original controls on both text
consoles. The standalone diagnostic disk retains the original 16-page text
Calculator; its program bytes are unchanged.

`src/native/input/pointer.inc` is now shared by Desktop and Calculator. The
caller supplies its surface selector, hit-test callback and control count;
events distinguish focus from activation. Each caller handles its own app or
dialog actions. The qualified sampling delay, reconnect baseline and exact
sprite/CIA/BASIC-hook restoration remain in the driver.

`src/native/graphics/buttons.inc` supplies rectangular hit testing and focus
colors on the bound surface. Callers provide the selected index and a static
table of fewer than 32 on-screen rectangles. Focus painting requires edges on
8-pixel cell boundaries. Dialogs restrict the active index interval, so covered
calculator controls cannot receive clicks. The graphics scene interpreters
are shared as well; each application retains its own layout tables.

The builder generates Calculator's scenes and hit rectangles from
`native_calc_scene.py`, which also contains the independent bitmap oracle.
Neither resident kernel grows and no persistent desktop allocation is added.

## Verification

The [graphical Calculator qualification](validation/2026-09-12-native-calc-gui/README.md)
records assembled arithmetic, mouse gestures, complete bitmaps, text mirrors,
save/cancel/failure behavior and cleanup. VICE exercises actual host mouse and
ROM keyboard input in both boot modes, saves a history file, compares all app
files on the disk and operates all five suite apps. Physical C128 testing and
deployment of this revision remain pending.

```sh
python3 -B build-native-desktop.py
python3 -B tests/ci_native_calc_gui.py --report /tmp/calculator-gui.json
python3 -B tests/ci_native_pointer.py --report /tmp/pointer.json
python3 -B tests/ci_native_pointer_iec.py
python3 -B tests/ci_native_pointer_iec.py --80col
```

The CPU suites require the existing py65 environment. The VICE workflows use
private disk copies and X displays and perform no physical-machine I/O.
