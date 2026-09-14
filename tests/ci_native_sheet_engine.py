#!/usr/bin/env python3
"""Compare host and compiled 6502 calculations with integer/workbook oracles.

This is a standalone engine test, not a native-app, VICE or hardware test.
"""
import argparse
import ctypes
import gzip
import hashlib
import json
import random
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMPTY, NUMBER, TEXT, SYNTAX, REFERENCE, DIVZERO, OVERFLOW, VALUE, CYCLE, DEPTH, IO = range(11)
LO, HI = -(2**31), 2**31-1
CAPTURES = None


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def arithmetic(a, b, operator):
    if operator == '/' and not b:
        return DIVZERO, 0
    value = {'+': lambda: a+b, '-': lambda: a-b, '*': lambda: a*b,
             '/': lambda: (abs(a)//abs(b)) * (-1 if (a < 0) != (b < 0) else 1)}[operator]()
    return (NUMBER, value) if LO <= value <= HI else (OVERFLOW, 0)


def cell_name(index):
    return chr(65+index % 8)+str(index//8+1)


def payload(cells):
    result = bytearray(8192)
    for index, value in enumerate(cells):
        value = value.encode('ascii') if isinstance(value, str) else value
        assert len(value) <= 32
        result[index*32:index*32+len(value)] = value
    return bytes(result)


class Host:
    def __init__(self, path):
        self.lib = ctypes.CDLL(str(path))
        self.cells = (ctypes.c_uint8 * 8192).in_dll(self.lib, 'sh_test_cells')
        self.values = (ctypes.c_int32 * 256).in_dll(self.lib, 'sh_values')
        self.types = (ctypes.c_uint8 * 256).in_dll(self.lib, 'sh_types')
        self.fail = ctypes.c_uint16.in_dll(self.lib, 'sh_test_fail_index')
        self.reads = ctypes.c_uint16.in_dll(self.lib, 'sh_test_reads')
        self.lib.sh_recalculate.restype = ctypes.c_uint8
        self.lib.sh_format_number.argtypes = [ctypes.c_int32, ctypes.c_void_p]

    def run(self, data, fault=65535):
        self.cells[:] = data
        self.fail.value = fault
        self.reads.value = 0
        status = self.lib.sh_recalculate()
        assert bytes(self.cells) == data
        return status, list(zip(self.types, self.values)), self.reads.value

    def format(self, number):
        buffer = ctypes.create_string_buffer(b'Z'*14, 14)
        self.lib.sh_format_number(number, ctypes.byref(buffer, 1))
        assert buffer.raw[:1] == buffer.raw[-1:] == b'Z'
        return buffer.raw[1:-1].split(b'\0')[0].decode()


class CheckedRAM(list):
    def __init__(self, bss, stack, end):
        super().__init__([0]*65536)
        self.bss, self.stack, self.end = bss, stack, end
        self.lowest_stack = end

    def __setitem__(self, address, value):
        assert isinstance(address, int), address
        assert (2 <= address < 0x1c or 0x100 <= address < 0x200 or
                self.bss <= address < self.end), ('write outside owned test memory', hex(address))
        if self.stack <= address < self.end:
            self.lowest_stack = min(self.lowest_stack, address)
        super().__setitem__(address, value)

    def inject(self, address, data):
        list.__setitem__(self, slice(address, address+len(data)), data)


class Native:
    def __init__(self, path, labels):
        from py65.devices.mpu6502 import MPU
        self.symbols = {}
        for line in labels.read_text().splitlines():
            _, address, name = line.split()
            self.symbols[name.lstrip('.')] = int(address, 16)
        self.stack = self.symbols['__CSTACK_RUN__']
        self.end = self.stack + self.symbols['__CSTACK_SIZE__']
        self.ram = CheckedRAM(self.symbols['__BSS_RUN__'], self.stack, self.end)
        image = path.read_bytes()
        self.ram.inject(int.from_bytes(image[:2], 'little'), image[2:])
        self.cpu = MPU(memory=self.ram)
        self.steps = self.worst = self.calls = 0
        self.call('start')
        self.ram.inject(self.stack, b'\xa5'*32)

    def call(self, name):
        cpu = self.cpu
        cpu.pc = self.symbols[name]
        cpu.sp = 0xef
        cpu.stPushWord(0x2ff)
        for steps in range(60000000):
            cpu.step()
            if cpu.pc == 0x300:
                assert cpu.sp == 0xef, ('unbalanced CPU stack', name, cpu.sp)
                self.steps += steps+1
                self.worst = max(self.worst, steps+1)
                self.calls += 1
                return cpu.a
        raise AssertionError(('engine did not return', name, hex(cpu.pc)))

    def run(self, data, fault=65535):
        self.ram.inject(0x4000, data)
        self.ram.inject(self.symbols['_sh_test_fail_index'], fault.to_bytes(2, 'little'))
        self.ram.inject(self.symbols['_sh_test_reads'], b'\0\0')
        status = self.call('_sh_recalculate')
        assert bytes(self.ram[0x4000:0x6000]) == data
        assert bytes(self.ram[self.stack:self.stack+32]) == b'\xa5'*32, 'C stack crossed guard'
        values = self.symbols['_sh_values']; types = self.symbols['_sh_types']
        results = [(self.ram[types+i], int.from_bytes(self.ram[values+i*4:values+i*4+4],
                                                     'little', signed=True)) for i in range(256)]
        reads = self.symbols['_sh_test_reads']
        return status, results, int.from_bytes(self.ram[reads:reads+2], 'little')

    def format(self, number):
        self.ram.inject(self.symbols['_sh_test_number'], number.to_bytes(4, 'little', signed=True))
        self.call('_sh_test_format')
        start = self.symbols['_sh_test_formatted']
        return bytes(self.ram[start:start+12]).split(b'\0')[0].decode()


def build(directory, native):
    src = ROOT/'src/native/sheet/engine.c'
    test = ROOT/'tests/native_sheet_engine'
    subprocess.run(['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-Wpedantic',
                    '-fsanitize=undefined', '-fsanitize-undefined-trap-on-error', '-shared', '-fPIC',
                    str(src), str(test/'harness.c'), '-o', str(directory/'engine.so')], check=True)
    if native:
        for name, path in [('engine', src), ('harness', test/'harness.c'), ('startup', test/'startup.s')]:
            subprocess.run(['cl65', '-t', 'c128', '-O', '-g', '-c', '-o',
                            str(directory/f'{name}.o'), str(path)], check=True)
        subprocess.run(['ld65', '-C', str(test/'link.cfg'), '-m', str(directory/'engine.map'),
                        '-Ln', str(directory/'engine.lbl'), '-o', str(directory/'engine.prg'),
                        *(str(directory/f'{n}.o') for n in ('startup', 'engine', 'harness')), 'c128.lib'], check=True)


def scalar_cases(random_count):
    cases = [('', EMPTY, 0), (' ', EMPTY, 0), ('budget', TEXT, 0), ("'123", TEXT, 0),
             ("'=A1", TEXT, 0), ('1.25', TEXT, 0), ('12x', TEXT, 0), ('+ 12', TEXT, 0),
             (' +12 ', NUMBER, 12), (' -0 ', NUMBER, 0), (str(LO), NUMBER, LO),
             (str(HI), NUMBER, HI), (str(LO-1), OVERFLOW, 0), (str(HI+1), OVERFLOW, 0),
             ('9'*31, OVERFLOW, 0), ('='+'9'*30, OVERFLOW, 0), ('x'*31, TEXT, 0),
             (b'x'*32, SYNTAX, 0), ('=2+3*4', NUMBER, 14), ('=(2+3)*4', NUMBER, 20),
             ('=20/3/2', NUMBER, 3), ('=20-3-2', NUMBER, 15), ('= -7 / 3', NUMBER, -2),
             ('=7/-3', NUMBER, -2), ('=-7/-3', NUMBER, 2), ('=2--3', NUMBER, 5),
             ('=-2147483648', NUMBER, LO), ('=--2147483648', OVERFLOW, 0),
             ('=-(-2147483648)', OVERFLOW, 0), ('=--(-2147483648)', NUMBER, LO),
             ('='+'('*8+'1'+')'*8, NUMBER, 1), ('='+'('*9+'1'+')'*9, DEPTH, 0),
             ('='+'-'*8+'1', NUMBER, 1), ('='+'-'*9+'1', DEPTH, 0),
             ('=((((1+2)*3)-4)/5)+6', NUMBER, 7)]
    for text in ('=', '=1+', '=()', '=1 2', '=1.5', '=2**3', '=1//2', '=1(2)', '=1)',
                 '=SUM()', '=SUM(A1)', '=SUM(1:2)', '=SUM(A1:A2', '=SUM(A1,A2)',
                 '=AVG(A1:A2)', '=A', '="text"', '=2^3'):
        cases.append((text, SYNTAX, 0))
    for text in ('=A0', '=A01', '=A33', '=I1', '=AA1', '=Z255', '=H9999999999999999', '=SUM(A1:I1)'):
        cases.append((text, REFERENCE, 0))
    for byte in range(1, 256):
        if byte < 32 or byte > 126:
            cases.append((bytes([byte]), SYNTAX, 0))
    bounds = [LO, LO+1, -65536, -46341, -46340, -32768, -2, -1, 0, 1, 2,
              32767, 46340, 46341, 65535, 65536, HI-1, HI]
    for a in bounds:
        for b in bounds:
            for op in '+-*/':
                type_, value = arithmetic(a, b, op)
                cases.append((f'={a}{op}{b}', type_, value))
    rng = random.Random(0x1285)
    for _ in range(random_count):
        a, b = (rng.randint(LO, HI) for _ in range(2))
        op = rng.choice('+-*/')
        type_, value = arithmetic(a, b, op)
        cases.append((f'={a}{op}{b}', type_, value))
    return cases


def workbook_cases():
    cells = ['']*256; want = [(EMPTY, 0)]*256
    entries = {0:('120', NUMBER, 120), 1:('35', NUMBER, 35), 2:('=A1-B1', NUMBER, 85),
               3:('=C1*2', NUMBER, 170), 5:('=E1+7', NUMBER, 7), 8:('label', TEXT, 0),
               9:("'12", TEXT, 0), 10:('=SUM(A1:B2)', NUMBER, 155),
               11:('=sum(b2:a1)', NUMBER, 155), 12:('=A2+1', VALUE, 0),
               14:('=sUm(b2:A1)', NUMBER, 155),
               13:('=E2+1', VALUE, 0), 16:('=SUM(A1:H2)', VALUE, 0),
               18:('=h32', NUMBER, 7), 24:('=B4', CYCLE, 0), 25:('=C4', CYCLE, 0),
               26:('=A4', CYCLE, 0), 27:('=A4+1', CYCLE, 0),
               32:('=A5+', SYNTAX, 0), 33:('=A5', SYNTAX, 0),
               40:('=1/0', DIVZERO, 0), 41:('=A6', DIVZERO, 0),
               42:('=SUM(A6:B6)', DIVZERO, 0), 247:('=SUM(A31:H31)', CYCLE, 0),
               255:('7', NUMBER, 7)}
    for index, (text, type_, value) in entries.items():
        cells[index] = text; want[index] = (type_, value)
    yield 'mixed workbook', cells, want, None
    cells[0] = '200'; want[0] = (NUMBER, 200); want[2] = (NUMBER, 165); want[3] = (NUMBER, 330)
    want[10] = want[11] = want[14] = (NUMBER, 235)
    yield 'edit and recalculate', cells, want, None
    cells[0] = ''; want[0] = (EMPTY, 0); want[2] = (NUMBER, -35); want[3] = (NUMBER, -70)
    want[10] = want[11] = want[14] = (NUMBER, 35)
    yield 'clear and recalculate', cells, want, None
    cells = [f'={cell_name(i+1)}+1' for i in range(255)]+['1']
    yield '256-cell forward dependency chain', cells, [(NUMBER, 256-i) for i in range(256)], 511
    cells = ['1']+[f'={cell_name(i-1)}+1' for i in range(1, 256)]
    yield '256-cell backward dependency chain', cells, [(NUMBER, i+1) for i in range(256)], 256
    cells = [f'={cell_name(i+1)}' for i in range(255)]+['=A1']
    yield '256-cell cycle', cells, [(CYCLE, 0)]*256, 511
    cells = ['']*256; want = [(EMPTY, 0)]*256
    cells[7] = '1'; want[7] = (NUMBER, 1)
    for row in range(1, 32):
        cells[row*8+7] = f'=SUM(A1:H{row})'; want[row*8+7] = (NUMBER, 2**(row-1))
    yield 'rectangular range recalculation', cells, want, 256
    cells[7] = '2'; want[7] = (NUMBER, 2)
    for row in range(1, 32):
        want[row*8+7] = (NUMBER, 2**row) if row < 31 else (OVERFLOW, 0)
    yield 'SUM overflow', cells, want, 256
    cells = ['1']*256; want = [(NUMBER, 1)]*256
    cells[0] = '=SUM(A2:H32)'; want[0] = (NUMBER, 248)
    yield 'SUM with 248 forward dependencies', cells, want, 504


def check(implementation, cells, want, label, reads=None, fault=65535):
    data = payload(cells)
    got_status, got, got_reads = implementation.run(data, fault)
    if CAPTURES is not None:
        CAPTURES.write((json.dumps(dict(implementation=type(implementation).__name__, label=label,
                                      data=data.hex(), results=got, expected=want, status=got_status,
                                      reads=got_reads, fault=fault), separators=(',', ':'))+'\n').encode())
    expected_status = IO if fault < 256 else 0
    assert got_status == expected_status, (label, got_status, expected_status)
    for index, (actual, expected) in enumerate(zip(got, want)):
        assert actual == expected, (label, cell_name(index), cells[index], actual, expected)
    if reads is not None:
        assert got_reads == reads, (label, got_reads, reads)
    return got_reads


def main():
    global CAPTURES
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--host-only', action='store_true')
    args = parser.parse_args()
    directory = Path(tempfile.mkdtemp(prefix='sheet-engine-', dir=args.report.parent))
    report = dict(passed=False, build_directory=str(directory), tests=[], native_boards=0,
                  host_boards=0, standalone_engine=True, app_or_hardware_qualification=False)
    capture_path = args.report.with_suffix('.captures.jsonl.gz')
    capture_file = capture_path.open('xb')
    CAPTURES = gzip.GzipFile(filename='', mode='wb', fileobj=capture_file, mtime=0)
    try:
        build(directory, not args.host_only)
        host = Host(directory/'engine.so')
        native = None if args.host_only else Native(directory/'engine.prg', directory/'engine.lbl')
        cases = scalar_cases(50000)
        for name, implementation, selected in [('host', host, cases), ('6502', native, cases[:2048])]:
            if implementation is None:
                continue
            for start in range(0, len(selected), 256):
                chunk = selected[start:start+256]
                cells = [case[0] for case in chunk]+['']*(256-len(chunk))
                want = [(case[1], case[2]) for case in chunk]+[(EMPTY, 0)]*(256-len(chunk))
                check(implementation, cells, want, f'{name} scalar batch {start//256}')
                report['native_boards' if name == '6502' else 'host_boards'] += 1
            report[name+'_scalar_cases'] = len(selected)
            print(f'PASS {name}: {len(selected)} scalar cases', flush=True)
        for label, cells, want, reads in workbook_cases():
            check(host, cells, want, label, reads)
            if native:
                check(native, cells, want, label, reads)
            report['tests'].append(label)
            print('PASS '+label, flush=True)
        for fault in (0, 127, 255):
            for implementation in (host, native):
                if implementation is None:
                    continue
                check(implementation, ['123']*256, [(IO, 0)]*256, f'storage fault {fault}', fault=fault)
                check(implementation, ['7']*256, [(NUMBER, 7)]*256, 'storage retry', reads=256)
            report['tests'].append(f'storage failure at {fault} and full retry')
        rng = random.Random(0x128)
        numbers = [LO, HI, -1, 0, 1, -10, 10]+[rng.randint(LO, HI) for _ in range(121)]
        for number in numbers:
            assert host.format(number) == str(number)
            if native:
                assert native.format(number) == str(number)
        report['formatted_numbers'] = len(numbers)
        report['format_cases'] = numbers
        if native:
            report.update(native_instructions=native.steps, native_calls=native.calls,
                          worst_call_instructions=native.worst,
                          c_stack_bytes_written=native.end-native.ram.lowest_stack,
                          c_stack_bytes_reserved=native.end-native.stack,
                          c_stack_guard_preserved=True, source_cells_unchanged=True,
                          native_image_bytes=(directory/'engine.prg').stat().st_size,
                          engine_bss_bytes=native.symbols['__BSS_SIZE__'],
                          runtime_end=native.end)
        inputs = ['src/native/sheet/engine.c', 'src/native/sheet/engine.h', 'tests/ci_native_sheet_engine.py']
        inputs += [str(path.relative_to(ROOT)) for path in sorted((ROOT/'tests/native_sheet_engine').iterdir())]
        report['inputs'] = {path: digest(ROOT/path) for path in inputs}
        report['artifacts'] = {path.name:digest(path) for path in sorted(directory.iterdir())}
        report['passed'] = True
        print('PASS spreadsheet engine: checked integer arithmetic, references, ranges, cycles, bounded stacks and storage recovery', flush=True)
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        CAPTURES.close(); capture_file.close(); CAPTURES = None
        report['captures'] = dict(path=str(capture_path), sha256=digest(capture_path))
        args.report.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
