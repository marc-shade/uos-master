#!/usr/bin/env python3
"""Offline archive audit and separate AST/integer oracle for retained cases."""
import ast
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
EMPTY, NUMBER, TEXT, SYNTAX, REFERENCE, DIVZERO, OVERFLOW, VALUE, CYCLE, DEPTH, IO = range(11)
LO, HI = -(2**31), 2**31-1
sys.setrecursionlimit(8192)


class CellError(Exception):
    pass


def checked(value):
    if not LO <= value <= HI:
        raise CellError(OVERFLOW)
    return value


def reference(name):
    match = re.fullmatch(r'([A-Z]+)([0-9]+)', name)
    if not match:
        raise CellError(SYNTAX)
    column, row = match.groups()
    if len(column) != 1 or not 'A' <= column <= 'H' or row[0] == '0' or not 1 <= int(row) <= 32:
        raise CellError(REFERENCE)
    return (int(row)-1)*8+ord(column)-65


def grammar(node):
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return
    if isinstance(node, ast.Name):
        reference(node.id)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        count = 0
        while isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            count += 1
            node = node.operand
        if count > 8:
            raise CellError(DEPTH)
        grammar(node)
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        grammar(node.left); grammar(node.right)
        return
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'RANGE':
        if len(node.args) != 2 or node.keywords:
            raise CellError(SYNTAX)
        for argument in node.args:
            if not isinstance(argument, ast.Constant) or type(argument.value) is not str:
                raise CellError(SYNTAX)
            reference(argument.value)
        return
    raise CellError(SYNTAX)


def parse(text):
    text = re.sub(r'\bSUM\s*\(\s*([A-Z]+[0-9]+)\s*:\s*([A-Z]+[0-9]+)\s*\)',
                  lambda m: 'RANGE("'+m[1]+'","'+m[2]+'")', text.upper())
    nested = 0
    for char in text:
        if char == '(':
            nested += 1
            if nested > 8:
                raise CellError(DEPTH)
        elif char == ')':
            nested -= 1
    try:
        node = ast.parse(text.strip(), mode='eval').body
    except SyntaxError:
        raise CellError(SYNTAX)
    grammar(node)
    return node


def oracle(data):
    cache, active = {}, set()

    def value(index, in_sum=False):
        type_, result = cell(index)
        if type_ == NUMBER:
            return result
        if type_ == EMPTY or (type_ == TEXT and in_sum):
            return 0
        raise CellError(VALUE if type_ == TEXT else type_)

    def expression(node):
        if isinstance(node, ast.Constant):
            return checked(node.value)
        if isinstance(node, ast.Name):
            return value(reference(node.id))
        if isinstance(node, ast.UnaryOp):
            sign = 1
            while isinstance(node, ast.UnaryOp):
                if isinstance(node.op, ast.USub):
                    sign = -sign
                node = node.operand
            if isinstance(node, ast.Constant):
                return checked(sign*node.value)
            return checked(sign*expression(node))
        if isinstance(node, ast.Call):
            a, b = (reference(arg.value) for arg in node.args)
            x0, x1 = sorted((a % 8, b % 8)); y0, y1 = sorted((a//8, b//8))
            result = 0
            for y in range(y0, y1+1):
                for x in range(x0, x1+1):
                    result = checked(result+value(y*8+x, True))
            return result
        a = expression(node.left); b = expression(node.right)
        if isinstance(node.op, ast.Add): return checked(a+b)
        if isinstance(node.op, ast.Sub): return checked(a-b)
        if isinstance(node.op, ast.Mult): return checked(a*b)
        if b == 0: raise CellError(DIVZERO)
        return checked((abs(a)//abs(b)) * (-1 if (a < 0) != (b < 0) else 1))

    def cell(index):
        if index in cache:
            return cache[index]
        if index in active:
            raise CellError(CYCLE)
        active.add(index)
        try:
            raw = data[index*32:index*32+32]
            if b'\0' not in raw:
                raise CellError(SYNTAX)
            raw = raw.split(b'\0')[0]
            if any(c < 32 or c > 126 for c in raw):
                raise CellError(SYNTAX)
            text = raw.decode('ascii').strip(' ')
            if not text:
                result = (EMPTY, 0)
            elif text.startswith("'"):
                result = (TEXT, 0)
            elif text.startswith('='):
                result = (NUMBER, expression(parse(text[1:])))
            elif re.fullmatch(r'[+-]?[0-9]+', text):
                result = (NUMBER, checked(int(text)))
            else:
                result = (TEXT, 0)
        except CellError as error:
            result = (error.args[0], 0)
        active.remove(index)
        cache[index] = result
        return result

    return [cell(index) for index in range(256)]


def archive(name):
    with tarfile.open(ROOT/name, 'r:gz') as tar:
        result = {}
        for member in tar:
            assert member.isfile() and not member.name.startswith('/') and '..' not in Path(member.name).parts
            assert member.name not in result
            result[member.name] = tar.extractfile(member).read()
        return result


def main():
    for line in (ROOT/'SHA256SUMS').read_text().splitlines():
        sha, name = line.split('  ', 1)
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == sha, name
    report = json.loads((ROOT/'test-report.json').read_text())
    assert report['passed'] and report['standalone_engine'] and not report['app_or_hardware_qualification']
    inputs = archive('inputs.tar.gz'); artifacts = archive('artifacts.tar.gz')
    for name, sha in report['inputs'].items():
        assert hashlib.sha256(inputs[name]).hexdigest() == sha, name
    for name, sha in report['artifacts'].items():
        assert hashlib.sha256(artifacts[name]).hexdigest() == sha, name
    changes = json.loads((ROOT/'changes.json').read_text())
    assert set(changes) == set(inputs)
    for name, item in changes.items():
        assert hashlib.sha256(inputs[name]).hexdigest() == item['after']
    rebuild = json.loads((ROOT/'rebuild.json').read_text())
    assert rebuild['passed'] and rebuild['standalone_prg_identical']
    assert hashlib.sha256(artifacts['engine.prg']).hexdigest() == rebuild['sha256']
    assert artifacts['engine.prg'][:2] == b'\0\x60'
    symbols = {line.split()[2].lstrip('.'):int(line.split()[1], 16)
               for line in artifacts['engine.lbl'].decode().splitlines()}
    assert symbols['__CSTACK_RUN__'] + symbols['__CSTACK_SIZE__'] == report['runtime_end'] <= 0xc000
    assert symbols['__CSTACK_SIZE__'] == 1024 and report['c_stack_guard_preserved']
    assert report['c_stack_bytes_written'] < 1024-32
    counts = dict(Host=0, Native=0); numeric_cells = 0
    with gzip.open(ROOT/'captures.jsonl.gz', 'rt') as stream:
        for line in stream:
            capture = json.loads(line); data = bytes.fromhex(capture['data'])
            assert len(data) == 8192
            if capture['fault'] < 256:
                assert capture['status'] == IO and capture['reads'] == capture['fault']+1
                want = [(IO, 0)]*256
            else:
                assert capture['status'] == 0
                want = oracle(data)
            actual = [tuple(pair) for pair in capture['results']]
            expected = [tuple(pair) for pair in capture['expected']]
            assert len(actual) == len(expected) == 256
            assert actual == want == expected, (capture['label'], [(i, a, w) for i, (a, w) in enumerate(zip(actual, want)) if a != w][:4])
            numeric_cells += sum(type_ == NUMBER for type_, _ in want)
            counts[capture['implementation']] += 1
    assert counts == dict(Host=217, Native=23), counts
    print(json.dumps(dict(passed=True, sealed_files=len((ROOT/'SHA256SUMS').read_text().splitlines()),
                          independent_ast_oracle_boards=counts, cells_checked=sum(counts.values())*256,
                          numeric_results=numeric_cells, executable_rebuild_identical=True)))


if __name__ == '__main__':
    main()
