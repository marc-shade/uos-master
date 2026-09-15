/* Native uOS spreadsheet calculation core, GPL v3.
 * All arithmetic is signed 32-bit integer arithmetic with checked bounds.
 * Cell dependencies use an explicit 256-cell stack, never the CPU stack.
 */
#include "engine.h"
#include <string.h>

#define SH_MAX INT32_C(2147483647)
#define SH_MIN (-SH_MAX - 1)
#define SH_PENDING 255

int32_t sh_values[SH_CELLS];
uint8_t sh_types[SH_CELLS];
static uint8_t seen[SH_CELLS];
static uint8_t cells[SH_CELLS];
static char source[SH_CELL_SIZE];
static uint8_t position, depth, error, dependency;

static uint8_t upper(uint8_t c)
{
    /* Explicit ASCII: cc65's c128 target maps letter literals to PETSCII. */
    return c >= 0x61 && c <= 0x7a ? c - 0x20 : c;
}

static uint8_t digit(uint8_t c)
{
    return c >= '0' && c <= '9';
}

static uint8_t letter(uint8_t c)
{
    c = upper(c);
    return c >= 0x41 && c <= 0x5a;
}

static void spaces(void)
{
    while (source[position] == ' ') ++position;
}

static void fail(uint8_t code)
{
    /* Complete grammar checks even while a dependency is being resolved.
     * Invalid syntax/references must not become spurious dependency cycles. */
    if ((code == SH_SYNTAX || code == SH_REFERENCE || code == SH_DEPTH) &&
        error != SH_SYNTAX && error != SH_REFERENCE && error != SH_DEPTH) {
        error = code;
        return;
    }
    if (!error) error = code;
}

static uint32_t magnitude(int32_t value)
{
    return value < 0 ? (uint32_t)(-(value + 1)) + 1 : (uint32_t)value;
}

static int32_t signed_value(uint32_t value, uint8_t negative)
{
    if (!negative) return (int32_t)value;
    if (value == UINT32_C(2147483648)) return SH_MIN;
    return -(int32_t)value;
}

static int32_t number(uint8_t negative)
{
    uint32_t value = 0;
    uint8_t c;
    while (digit(source[position])) {
        c = source[position++] - '0';
        if (value > UINT32_C(214748364) ||
            (value == UINT32_C(214748364) && c > (negative ? 8 : 7))) {
            fail(SH_OVERFLOW);
            while (digit(source[position])) ++position;
            return 0;
        }
        value = value * 10 + c;
    }
    return signed_value(value, negative);
}

static int32_t arithmetic(int32_t a, int32_t b, uint8_t op)
{
    uint32_t x, y, limit;
    uint8_t negative;
    if (error) return 0;
    switch (op) {
    case '+':
        if ((b > 0 && a > SH_MAX - b) || (b < 0 && a < SH_MIN - b)) break;
        return a + b;
    case '-':
        if ((b > 0 && a < SH_MIN + b) || (b < 0 && a > SH_MAX + b)) break;
        return a - b;
    case '*':
        x = magnitude(a); y = magnitude(b);
        negative = (a < 0) != (b < 0);
        limit = negative ? UINT32_C(2147483648) : UINT32_C(2147483647);
        if (y && x > limit / y) break;
        return signed_value(x * y, negative);
    default: /* '/' */
        if (!b) { fail(SH_DIVZERO); return 0; }
        if (a == SH_MIN && b == -1) break;
        return a / b;
    }
    fail(SH_OVERFLOW);
    return 0;
}

/* Consume an entire reference even when it is outside the workbook. */
static uint8_t reference(void)
{
    uint8_t column, invalid = 0, first;
    uint16_t row = 0;
    spaces();
    if (!letter(source[position])) { fail(SH_SYNTAX); return 0; }
    column = upper(source[position++]) - 0x41;
    while (letter(source[position])) { ++position; invalid = 1; }
    first = source[position];
    if (!digit(first)) { fail(SH_SYNTAX); return 0; }
    while (digit(source[position])) {
        if (row <= SH_ROWS) row = row * 10 + source[position] - '0';
        ++position;
    }
    if (invalid || column >= SH_COLUMNS || first == '0' || row < 1 || row > SH_ROWS) {
        fail(SH_REFERENCE);
        return 0;
    }
    return (uint8_t)((row - 1) * SH_COLUMNS + column);
}

static int32_t cell_value(uint8_t index, uint8_t in_sum)
{
    if (error) return 0;
    if (!seen[index]) {
        dependency = index;
        error = SH_PENDING;
        return 0;
    }
    if (seen[index] == 1) { fail(SH_CYCLE); return 0; }
    switch (sh_types[index]) {
    case SH_EMPTY: return 0;
    case SH_NUMBER: return sh_values[index];
    case SH_TEXT:
        if (!in_sum) fail(SH_VALUE);
        return 0;
    default:
        fail(sh_types[index]);
        return 0;
    }
}

static int32_t expression(void);

/* Aggregates accept one rectangle, ignoring empty/text cells. All resolve
 * dependencies and propagate cell errors, including COUNT. Empty sets give 0. */
static int32_t aggregate(uint8_t function)
{
    uint8_t first, last, x, y, x0, x1, y0, y1, swap, index, found = 0;
    int32_t value = 0, item;
    spaces();
    if (source[position] != '(') { fail(SH_SYNTAX); return 0; }
    ++position;
    first = reference(); spaces();
    if (source[position] != ':') { fail(SH_SYNTAX); return 0; }
    ++position;
    last = reference(); spaces();
    if (source[position] != ')') { fail(SH_SYNTAX); return 0; }
    ++position;
    if (error) return 0;
    x0 = first % SH_COLUMNS; y0 = first / SH_COLUMNS;
    x1 = last % SH_COLUMNS; y1 = last / SH_COLUMNS;
    if (x0 > x1) { swap = x0; x0 = x1; x1 = swap; }
    if (y0 > y1) { swap = y0; y0 = y1; y1 = swap; }
    for (y = y0; y <= y1; ++y) {
        for (x = x0; x <= x1; ++x) {
            index = y * SH_COLUMNS + x;
            item = cell_value(index, 1);
            if (error) return 0;
            if (sh_types[index] != SH_NUMBER) continue;
            if (function == 0) value = arithmetic(value, item, '+');
            else if (function == 3) ++value;
            else if (!found || (function == 1 ? item < value : item > value)) value = item;
            found = 1;
            if (error) return 0;
        }
    }
    return value;
}

static int32_t primary(void)
{
    int32_t value;
    uint8_t start, index;
    spaces();
    if (digit(source[position])) return number(0);
    if (source[position] == '(') {
        if (depth == SH_EXPRESSION_DEPTH) { fail(SH_DEPTH); return 0; }
        ++depth; ++position;
        value = expression();
        --depth; spaces();
        if (source[position] != ')') fail(SH_SYNTAX);
        else ++position;
        return value;
    }
    if (letter(source[position])) {
        start = position;
        while (letter(source[position])) ++position;
        if (position - start == 3 && upper(source[start]) == 0x53 &&
            upper(source[start+1]) == 0x55 && upper(source[start+2]) == 0x4d) return aggregate(0);
        if (position - start == 3 && upper(source[start]) == 0x4d) {
            if (upper(source[start+1]) == 0x49 && upper(source[start+2]) == 0x4e) return aggregate(1);
            if (upper(source[start+1]) == 0x41 && upper(source[start+2]) == 0x58) return aggregate(2);
        }
        if (position - start == 5 && upper(source[start]) == 0x43 &&
            upper(source[start+1]) == 0x4f && upper(source[start+2]) == 0x55 &&
            upper(source[start+3]) == 0x4e && upper(source[start+4]) == 0x54) return aggregate(3);
        position = start;
        index = reference();
        return cell_value(index, 0);
    }
    fail(SH_SYNTAX);
    return 0;
}

static int32_t unary(void)
{
    uint8_t negative = 0, signs = 0;
    int32_t value;
    spaces();
    while (source[position] == '+' || source[position] == '-') {
        if (++signs > SH_EXPRESSION_DEPTH) { fail(SH_DEPTH); return 0; }
        if (source[position] == '-') negative ^= 1;
        ++position; spaces();
    }
    if (digit(source[position])) return number(negative);
    value = primary();
    if (!negative || error) return value;
    if (value == SH_MIN) { fail(SH_OVERFLOW); return 0; }
    return -value;
}

static int32_t product(void)
{
    int32_t value = unary(), rhs;
    uint8_t op;
    spaces();
    while (source[position] == '*' || source[position] == '/') {
        op = source[position++];
        rhs = unary();
        value = arithmetic(value, rhs, op);
        spaces();
    }
    return value;
}

static int32_t expression(void)
{
    int32_t value = product(), rhs;
    uint8_t op;
    spaces();
    while (source[position] == '+' || source[position] == '-') {
        op = source[position++];
        rhs = product();
        value = arithmetic(value, rhs, op);
        spaces();
    }
    return value;
}

static uint8_t evaluate(uint8_t index, int32_t *value)
{
    uint8_t i, negative = 0, start;
    if (sh_read_cell(index, source)) return SH_IO;
    /* Never let a malformed record move the parser beyond its own buffer. */
    for (i = 0; i < SH_CELL_SIZE; ++i) {
        if (!source[i]) break;
        if ((uint8_t)source[i] < 32 || (uint8_t)source[i] > 126) return SH_SYNTAX;
    }
    if (i == SH_CELL_SIZE) return SH_SYNTAX;
    position = depth = error = 0;
    spaces();
    if (!source[position]) return SH_EMPTY;
    if (source[position] == '\'') return SH_TEXT;
    if (source[position] == '=') {
        ++position;
        *value = expression();
        spaces();
        if (source[position]) fail(SH_SYNTAX);
        return error ? error : SH_NUMBER;
    }
    if (source[position] == '-' || source[position] == '+') {
        negative = source[position] == '-'; ++position;
    }
    start = position;
    while (digit(source[position])) ++position;
    if (position == start) return SH_TEXT;
    spaces();
    if (source[position]) return SH_TEXT;
    position = start;
    *value = number(negative);
    return error ? error : SH_NUMBER;
}

uint8_t sh_recalculate(void)
{
    uint16_t next, level;
    uint8_t index, type;
    int32_t value;
    memset(seen, 0, sizeof(seen));
    memset(sh_values, 0, sizeof(sh_values));
    memset(sh_types, SH_EMPTY, sizeof(sh_types));
    for (next = 0; next < SH_CELLS; ++next) {
        if (seen[next]) continue;
        level = 1; cells[0] = (uint8_t)next; seen[next] = 1;
        while (level) {
            index = cells[level - 1]; value = 0;
            type = evaluate(index, &value);
            if (type == SH_IO) {
                memset(sh_values, 0, sizeof(sh_values));
                memset(sh_types, SH_IO, sizeof(sh_types));
                return SH_IO;
            }
            if (type == SH_PENDING) {
                /* An unseen cell implies at most 255 cells already stacked. */
                if (level < SH_CELLS) {
                    cells[level++] = dependency; seen[dependency] = 1;
                    continue;
                }
                type = SH_DEPTH;
            }
            sh_types[index] = type;
            sh_values[index] = type == SH_NUMBER ? value : 0;
            seen[index] = 2; --level;
        }
    }
    return 0;
}

void sh_format_number(int32_t value, char *out)
{
    char reverse[10];
    uint8_t count = 0;
    uint32_t number = magnitude(value);
    if (value < 0) *out++ = '-';
    do {
        reverse[count++] = '0' + (uint8_t)(number % 10);
        number /= 10;
    } while (number);
    while (count) *out++ = reverse[--count];
    *out = 0;
}
