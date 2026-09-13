# Native graphical Files

The suite Files app uses the same blue VIC bitmap, yellow focus and port-1
1351 mouse as the desktop, Calculator, Paint and Ultimate. Open it with the
Files icon or **F** on the desktop. The VDC retains its text view and names the
currently focused control. Both suite disks include this interface.

## Controls

Click a file row to select it, then Open, View or Copy. A keyboard selection
followed by Enter opens the selected folder, app or byte viewer. Up/Down select
rows, N/B change pages, R refreshes, D edits the IEC device and F changes the
format. In Ultimate mode, G edits the directory path, P opens the parent and
F1 changes DOS context. L edits an absolute Ultimate application path.

**Tab** cycles enabled buttons and fields; **Enter** activates the focused
control. Fields support the shared caret, insertion, deletion, Home/Ctrl-E and
Ctrl-U controls. Clicking inside a field places its caret in the visible text.
Long names retain every byte and show clipping markers; display truncation
never changes the path used for file I/O.

Copy proposes the selected source name. Edit it or press **F7** / Browse to
choose a destination using the [shared graphical picker](NATIVE-PICKER-GUI.md). The blue dialog returns
with the source and edited destination intact. F1 edits device/DOS, F3 changes
format and F5 changes the destination IEC type. Copy creates a new file,
closes and reopens both streams, and compares all bytes before reporting success.
Cancel is available during copy and verification. Failed writes are never
replayed, and partial new files remain available for inspection.

The byte viewer shows 128 bytes per page. Next or Enter advances and Esc returns
to the file list. Esc from the list returns to the blue desktop. An unavailable
graphics module or occupied bitmap range leaves text controls usable; Refresh
retries graphics. The text fallback also accepts Tab for the destination picker.

## Memory and module lifetime

Files declares 96 bank-0 app pages, with a resident core followed by one checked
module window at `$92b6`, following a 12,982-byte core. `fsview.prg` contains graphics, font, controls and pointer code;
`fspick.prg` contains the 11,446-byte destination picker. The two modules alternate. Both
are bound to the exact core checksum and loaded from the original app's device,
format and folder, even after the data destination changes.

The core retains browser/copy state, raw source and destination paths, transfer
buffers, descriptors and keyboard ownership. Picker cursors and caches must
close before their module can be replaced. An uncertain module-source close
also blocks new file operations until cleanup succeeds. The app restores the
original keyboard callback, function-key table and display/pointer state on exit.

The graphical surface uses 36 pages at `$c000..$e3ff`. The IEC browser cache uses
37 bank-1 pages; Ultimate and picker caches are allocated as needed. Ordinary
field edits update changed glyph cells and the old/new caret. Pointer polling
enters the module only while a new or unfinished sample needs attention; the
app publishes readiness after the complete module call returns.

No kernel code or ABI change is required. The app requires ABI 1.10 and ships
with the current ABI 1.11 suite. All 426 managed pages remain available after
app and workspace allocations are released.

## Current scope

The [frozen software qualification](validation/2026-09-13-native-files-gui/README.md) retains the CPU, full
mouse/keyboard VICE, copy, serial and independent rebuild results. This build
has not been installed or qualified on the physical C128. The shared picker
now has a [graphical implementation](NATIVE-PICKER-GUI.md), and the VDC remains
a text companion. Rename/delete, sorting, multi-selection,
directory copying, media identity, interrupted-copy recovery, REL/VLIR and
zero-byte IEC creation remain backend or file-manager work.

Ultimate paths may contain 255 bytes in total; each created path component is
limited to 127 bytes by the supported firmware contract. Existing files are
never replaced by Copy. See [file behavior](NATIVE-BROWSER.md#copying-from-the-suite-files-app)
and [owned file services](NATIVE-FILES.md) for the retained transport limits.
