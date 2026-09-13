"""Offline LZSA2 packing with a pinned compressor and a bounded Python decoder."""
import atexit
from functools import lru_cache
import os
from pathlib import Path
import shlex
import subprocess
import tempfile


@lru_cache(maxsize=1)
def compressor():
    source = Path(__file__).resolve().parent/'third_party/lzsa/src'
    temporary = tempfile.TemporaryDirectory(prefix='uos-lzsa-compiler-')
    atexit.register(temporary.cleanup)
    binary = Path(temporary.name)/'lzsa'
    files = sorted(source.glob('*.c')) + sorted((source/'libdivsufsort/lib').glob('*.c'))
    command = shlex.split(os.environ.get('CC', 'cc'))
    subprocess.run(command + ['-O2', '-I'+str(source),
                   '-I'+str(source/'libdivsufsort/include'),
                   *map(str, files), '-o', str(binary)], check=True)
    return binary


def pack(data):
    if not 1 <= len(data) <= 65535:
        raise ValueError('a raw boot block must contain 1..65535 bytes')
    with tempfile.TemporaryDirectory(prefix='uos-lzsa-block-') as temporary:
        source, target = Path(temporary)/'input', Path(temporary)/'output'
        source.write_bytes(data)
        subprocess.run([str(compressor()), '-r', '-f2', str(source), str(target)],
                       check=True, capture_output=True)
        result = target.read_bytes()
    if unpack(result, len(data)) != data:
        raise ValueError('LZSA2 round trip differs from the input')
    return result


def unpack(data, length):
    """Decode one raw forward block; never read or copy beyond its bounds."""
    if not 0 <= length <= 65535:
        raise ValueError('invalid decoded length')
    at, pending, previous = 0, None, None
    out = bytearray()

    def byte():
        nonlocal at
        if at >= len(data):
            raise ValueError('truncated LZSA2 input')
        value = data[at]
        at += 1
        return value

    def nibble():
        nonlocal pending
        if pending is not None:
            value, pending = pending, None
            return value
        value = byte()
        pending = value & 15
        return value >> 4

    def count(value, short, base, end=False):
        if value < short:
            return value + base
        value += nibble() + base
        if value < short + 15 + base:
            return value
        extra = byte()
        value += extra
        if value < 256:
            return value
        if end and value == 256:
            return None
        if value != 257:
            raise ValueError('invalid LZSA2 extended length')
        value = byte() | byte() << 8
        if value == 0:
            raise ValueError('zero LZSA2 extended length')
        return value

    while True:
        token = byte()
        literals = count((token >> 3) & 3, 3, 0)
        if at + literals > len(data) or len(out) + literals > length:
            raise ValueError('LZSA2 literals exceed input or output')
        out += data[at:at+literals]
        at += literals
        kind = token >> 5
        z = (~kind) & 1
        if kind < 2:
            offset = (0xffe0 | nibble() << 1 | z) - 65536
        elif kind < 4:
            offset = (0xfe00 | z << 8 | byte()) - 65536
        elif kind < 6:
            high = nibble()
            offset = (0xe000 | high << 9 | z << 8 | byte()) - 65536 - 512
        elif kind == 6:
            offset = (byte() << 8 | byte()) - 65536
        else:
            offset = previous
        matches = count(token & 7, 7, 2, end=True)
        if matches is None:
            if at != len(data) or len(out) != length:
                raise ValueError('wrong LZSA2 input or output length')
            return bytes(out)
        if offset is None or not -len(out) <= offset < 0 or len(out)+matches > length:
            raise ValueError('LZSA2 match exceeds decoded output')
        previous = offset
        for _ in range(matches):
            out.append(out[len(out)+offset])
