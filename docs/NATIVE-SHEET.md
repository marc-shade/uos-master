# Native spreadsheet calculation core

The spreadsheet is in development. Its calculation core runs as compiled
6502 code in a standalone CPU harness. It is not yet a desktop application:
the blue launcher still has six apps, and the suite disk images are unchanged.
The editable grid, banked storage adapter, file workflow and desktop entry
are the next integration work. APP-SHEET remains open in the
[implementation roadmap](IMPLEMENTATION-ROADMAP.md).

## Workbook and formulas

The initial calculation model has eight columns (A–H), 32 rows and 256 cells.
Each source record contains up to 31 printable ASCII bytes followed by NUL.
The core reads records through a storage callback; it does not assume that
the entire workbook is in directly addressable RAM. The future native app
must translate keyboard/file encodings into this explicit ASCII format.

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

## Qualification and remaining application work

Run:

```sh
python3 -B tests/ci_native_sheet_engine.py --report /tmp/sheet-engine.json
```

The test needs a C compiler, cc65 and Py65. It compares host and compiled
6502 output with independent integer and workbook expectations. The host
build traps undefined behavior. Captures retain complete cell records and
actual/expected results, while the CPU fixture rejects writes outside its
assigned memory and checks its source cells and stack guard.

The [software checkpoint](validation/2026-09-14-native-sheet-engine/README.md)
records the executed inputs, compiled harness, captures and development
corrections. No VICE, native app or physical hardware claim is made here.

The remaining app work includes an editable blue VIC/VDC grid, pointer and
keyboard navigation, owned banked storage, transactional Open and verified
Save As, clipboard and undo, formatting, import/export and printing.
Decimal arithmetic, a broader formula language, larger workbooks and
geoCalc exchange also remain on the roadmap. The desktop entry should be
added with the working application and its file/lifecycle checks.
