# Native blue Editor

Build with `python3 -B build-native-desktop.py`, boot
`target/native-desktop/uos128.d64`, and open the **Editor** icon. The suite
Editor uses the desktop's blue bitmap, yellow focused buttons and port-1
1351 mouse. Closing it returns to the same desktop with Editor selected.
The VDC shows the document and text controls at the same time.

The [banked editor](NATIVE-EDITOR.md) supplies the document, search and file
operations. This is plain-text editing with 24-bit byte positions, preserved
imported bytes, transactional Open and exclusive, reopened-verified Save As.
Selection, clipboard, undo, styled pages, printing and session recovery remain
roadmap work.

## Controls

| Control | Action |
|---|---|
| Open / F1 | Enter a filename or absolute Ultimate path |
| Save As / F3 | Create a new file and compare every byte after reopening it |
| Find / Ctrl-F | Enter a literal query, with exact or ignored ASCII case |
| Replace / Ctrl-R | Enter a query and replacement, then choose One or All |
| `...` | Show New, Go To, Device and Format controls |
| New / F5 | Start an empty document after confirming unsaved changes |
| Go To / F7 in the document | Enter a hexadecimal byte offset |
| Device / F8 | Select an IEC device or Ultimate DOS context |
| Format / F6 | Cycle D64, D71, D81 and Ultimate storage |
| Tab / Enter | Move focus among enabled controls / activate the focused control |
| Browse / F7 in Open or Save As | Open the shared file picker |
| Case in a search query | Toggle exact case and ignoring ASCII letter case |
| X / Esc | Close the app or cancel the current dialog or operation |
| Ctrl-L | Redraw; explicitly retry unavailable graphics |

Moving the mouse selects a control. Press and release on the same control to
activate it; releasing outside cancels. Clicking the document places its caret
at that character or the end of the clicked line. It accounts for horizontal
scrolling and treats CRLF as one navigation unit. Clicking a field positions
its caret within the full value. Typing returns focus to the document or field.
The [existing editing keys](NATIVE-EDITOR.md) still apply.

The 16-row document view scrolls to keep the caret visible. Filename and path
clipping changes only their display: Open and Save As retain up to 255 raw
Ultimate path bytes. Dirty-document confirmation defaults to **Keep**. Save As
refuses an existing file. Cancel is polled between file chunks while opening,
writing and comparing the saved file. A cancelled save preserves the document's
name and dirty state and may leave the new partial file; it never deletes or
replaces another file.

The [shared graphical picker](NATIVE-PICKER-GUI.md) keeps the entire document
allocated and returns to the blue dialog with the chosen filename, folder and
device. Cancel preserves the original field and caret. F7 opens it because
Tab now navigates graphical controls. Find/Replace also has a visible Case
button, while Ctrl-N finds the next occurrence of the saved query.

## Storage and presentation lifetime

The suite requires ABI 1.10 and ships with the existing ABI 1.11 kernel. Its
core contains 13,126 bytes and reserves 96 bank-0 pages (`$6000..$bfff`) for
code, persistent state and one checked module window at `$9346`.
`EDPICK.PRG` contains 11,448 bytes; `EDFIND.PRG` contains the search engine and
graphical renderer in 11,357 bytes. Peak core plus picker is 24,574 bytes; core plus graphics is 24,483 bytes.
Both modules bind to this core's checksum and load from the original app's
source device/context and directory, even after changing the document device.
For USB, install all three matching files together.

The optional VIC surface reserves 36 pages at `$c000..$e3ff`. Document chunks
span both banks in 4 KiB allocations. A 66,057-byte document fits in seventeen
chunks with the graphical view active; available capacity depends on heap
fragmentation, other allocations and temporary Open storage. The kernel and
426-page heap are unchanged. REU and disk-backed documents are not implemented.

Keyboard ownership, the surface descriptor, document state, fields and query
remain in the core while picker and graphics replace one another. A missing or
invalid graphics module, or another owner's surface reservation, leaves both
text consoles usable. Ctrl-L retries after the cause is resolved. A picker
that retains a cursor or cache after failed cleanup keeps its module loaded;
new file operations wait for an explicit Browse retry. An uncertain module
source close similarly retains ownership until checked cleanup succeeds.

Ordinary edits repaint changed glyph cells and the old/new caret. Search
calls the renderer within its existing module invocation. Readiness is cleared
before entering a checked module call, including idle pointer polling. Closing
or replacing the graphical view restores the display and sprites before
releasing its allocation. Controlled app exit restores the original ROM key
definitions and input state.

The diagnostic disk built by `build-native.py` keeps the earlier ABI 1.7
text editor: 79 pages, a 12,443-byte core and separate 2,090-byte search module.
Its PRG bytes are unchanged. Use the module files from the same build as each
editor; suite and diagnostic modules are not interchangeable.

## Qualification

The [frozen software qualification](validation/2026-09-13-native-editor-gui/README.md) passes CPU, full
mouse/keyboard VICE, large-document disk and serial workflows with independent
rebuilds. This build has not been installed or qualified on the physical C128. Tests execute the real app, kernel and modules
in CPU models and VICE, check complete bitmap/VDC surfaces and VIC palette
pixels, compare large saved files independently, and verify cleanup before
returning to the desktop.
