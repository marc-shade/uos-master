# Native Sheet

Sheet is the seventh native desktop app. Press **S** in the blue launcher,
or select **Sheet** with the keyboard or a port-1 1351 mouse. The app presents
an editable spreadsheet on the VIC and through the shared VDC display service.
Its first workbook supports eight columns, 32 rows, text and checked integer
formulas. APP-SHEET remains open in the [completion roadmap](IMPLEMENTATION-ROADMAP.md).

Build the complete D64/D81 suite with `python3 -B build-native-desktop.py`.
`python3 -B build-native-sheet.py` builds the standalone app. Keep
`VDSVC.PRG` beside `SHEET` when copying the app to another disk or Ultimate
folder. The app uses the checked native loader for either source.

## Desktop controls

| Control | Action |
|---|---|
| Arrows / Tab | Move between cells; the four-column, twelve-row viewport follows the selection |
| Home | Return to A1 |
| Ctrl-Z / Ctrl-R | Undo / redo the last cell edit or Clear |
| Enter / F7 / Edit | Edit the selected cell's existing source |
| Printable key | Start a replacement cell entry |
| Enter while editing | Commit and recalculate the workbook |
| Escape while editing | Cancel the draft and retain the old cell |
| Del / Clear | Empty the selected cell and recalculate |
| F1 / New | Create an empty workbook, with dirty-workbook confirmation |
| F3 / Open | Open a USHT workbook, with dirty-workbook confirmation |
| F5 / Save | Save As a new file and verify its complete readback |
| Escape / Back | Return to the desktop; unsaved work requires confirmation |
| Ctrl-L | Retry the VDC service after a clean refusal or retained display failure |

Mouse clicks select visible cells and activate toolbar controls. Field editing
uses the shared native field service: Left/Right, Home, Ctrl-E, Del, Ctrl-D,
Insert and Ctrl-U. The cell field accepts 31 ASCII characters. PETSCII letter
keys are translated at the cell-input boundary; workbook records remain ASCII.
The complete selected source and number are shown above and below the grid.
Numbers too wide for a cell show `########` in the grid, retaining the complete
value below. The VDC currently mirrors the four-column viewport; a denser
native-width grid remains work.

Open and Save As accept a typed filename or absolute Ultimate path. In that
dialog, **F1** cycles D64/D71/D81/Ultimate and **F3** cycles IEC devices 8–30
or Ultimate DOS contexts 1/2. Enter confirms; Escape or Back cancels. IEC names
are limited to 16 bytes and use SEQ files; Ultimate paths can reach 255 bytes.
This initial dialog does not yet use the shared directory picker.

Undo/Redo exchanges the complete source of one cell and recalculates the
workbook, returning the selection to that cell. Unchanged edits preserve the
history. A new edit replaces it; successful New/Open clears it. Save As keeps
history available. Undo and Redo conservatively mark the workbook unsaved,
even if its bytes match an earlier saved version. History is unavailable while
a cell field or file dialog is open. Multi-step and range history remain work.

## Workbook files and ownership

A workbook owns 32 bank-1 pages (8 KiB), accessed through checked handles.
New and Open allocate a second workbook, validate and calculate it, and only
then replace the current one. Failed allocation, malformed input, reads or
staged calculation preserve the original source and dirty flag. Failed writes
to a live cell mark its storage uncertain and refuse further edits or Save As;
New/Open can replace it. A failed close keeps its handle for an explicit retry.
The app never frees its display owners while VDC restoration is incomplete.

USHT version 1 is exactly 8,208 bytes, without a PRG load address:

| Offset | Bytes | Meaning |
|---|---|---|
| 0 | 4 | ASCII `USHT` |
| 4 | 4 | Version 1, columns 8, rows 32, record bytes 32 |
| 8 | 2 | Payload length 8192, little endian |
| 10 | 2 | CRC16-CCITT of the payload, initial 65535, little endian |
| 12 | 4 | Reserved zero bytes |
| 16 | 8192 | Row-major cell records, A1 through H32 |

Each record contains printable ASCII, one NUL, then zero padding to 32 bytes.
Open rejects unsupported headers, bad CRC, malformed records, truncation and
trailing bytes. Save As creates exclusively, closes, reopens and compares the
header and every cell before reporting success. Cancellation and errors keep
the workbook; a newly created partial file is retained. Transfers poll for
Escape and mouse Back at record boundaries and show progress.

The current app reserves 94 pages for code, state and the C stack, plus its
36-page VIC surface and the 39-page VDC component. With the 32-page workbook,
RAM-backed 16/64 KiB VDC snapshots leave 161/153 managed pages free. The calculated budget for a supported
REU-backed display snapshot leaves 225 (not yet tested with Sheet); staged Open/New need 32 additional
pages. Source cells currently stay in main banked RAM.

## Workbook and formulas

The initial calculation model has eight columns (A–H), 32 rows and 256 cells.
Each source record contains up to 31 printable ASCII bytes followed by NUL.
The core reads records through a storage callback; it does not assume that
the entire workbook is in directly addressable RAM. The native app translates keyboard letters into this explicit ASCII format.

Empty cells and cells containing only spaces are empty. A whole signed
decimal value is a number. Other non-formula input is text; a leading
apostrophe forces text. Leading and trailing spaces around numbers are
accepted. Text and formulas remain in source storage; calculation does not
rewrite them.

Formulas begin with `=` and support:

- Signed 32-bit integers, `+`, `-`, `*`, `/`, unary signs and parentheses.
- Normal multiplication/division precedence and left-to-right evaluation
  within each precedence level. Division truncates toward zero.
- Case-insensitive references such as `A1` or `h32`.
- A single rectangular range per `SUM`, such as `=SUM(A1:B12)`.
  Reversed endpoints describe the same rectangle. Empty and text cells in
  the range are ignored; directly referencing text produces a value error.
- Full recalculation after source edits, forward references, error
  propagation and detection of cycles, including cycles inside a range.

Values range from −2,147,483,648 through 2,147,483,647. Each arithmetic step
and running SUM must fit that range. Division by zero and overflow produce
cell errors. There is no floating-point, decimal, currency, date or time
type yet; for example, `1.25` is currently text. SUM lists, other functions,
multiple sheets, absolute references and formula rewriting on cell moves
are not implemented.

Parentheses may nest eight levels. Each unary-sign sequence may contain
eight signs; its combined sign applies to the following literal or primary
expression. Leading-zero row numbers and references outside A1:H32 are
rejected. Unterminated, non-ASCII and control-byte records produce syntax
errors without reading beyond the cell buffer.

## Calculation API and memory

`src/native/sheet/engine.h` exposes `sh_recalculate`, the result arrays and
an integer formatter. The app provides `sh_read_cell(index, out)`, which
copies exactly one 32-byte record and returns zero on success. The storage
adapter must keep the workbook stable throughout the call. The calculation
core is synchronous, is not reentrant and does not poll input.

Results distinguish empty, number and text cells from syntax, reference,
division, overflow, value, cycle, expression-depth and storage errors.
Non-number result values are zero. A read failure invalidates all results
with the storage-error type and returns `SH_IO`. A successful retry
recalculates from the current source; no old dependency state is reused.

Cell dependencies use an explicit stack that can hold every cell. Formula
parsing uses a separate bounded C stack, so a 256-cell reference chain does
not create 256 nested parser calls. A range containing unresolved cells is
revisited as those cells become available; a dependency-heavy SUM can take
more work than a simple formula. The core has no cancellation or timed
hardware responsiveness claim yet.

The standalone linker reserves 1 KiB for the C stack and rejects a runtime
extent beyond `$c000`. Its source-cell region is read-only to the engine.
These are harness constraints, not qualification of a native app's memory
ownership, display cleanup or file handling.

## Qualification and remaining work

Run the standalone engine or the loaded app checks (Py65 is required):

```sh
python3 -B tests/ci_native_sheet_engine.py --report /tmp/sheet-engine.json
python3 -B tests/ci_native_sheet.py --case core --report /tmp/sheet-core.json
python3 -B tests/ci_native_sheet.py --case files --report /tmp/sheet-files.json
python3 -B tests/ci_native_sheet_iec.py --80col --vdc64
```

The test needs a C compiler, cc65 and Py65. It compares host and compiled
6502 output with independent integer and workbook expectations. The host
build traps undefined behavior. Captures retain complete cell records and
actual/expected results, while the CPU fixture rejects writes outside its
assigned memory and checks its source cells and stack guard.

The [software checkpoint](validation/2026-09-14-native-sheet-engine/README.md)
records the executed inputs, compiled harness, captures and development
corrections. No VICE, native app or physical hardware claim is made here.

The [desktop checkpoint](validation/2026-09-14-native-sheet-desktop/README.md)
records the native app's software qualification separately from that engine
checkpoint. The [Undo/Redo checkpoint](validation/2026-09-15-native-sheet-undo/README.md)
covers the subsequent one-cell history feature. Physical C128/Ultimate testing
is still required.

Remaining work includes the shared file picker, clipboard, multi-step/range undo, formatting,
CSV and geoCalc exchange, decimal arithmetic, more functions, larger/multiple
sheets, printing and session recovery. Recalculation is synchronous; background
recalculation and cancellation of long dependency chains remain open. The
initial working app does not complete spreadsheet or GEOS/Wheels parity.
