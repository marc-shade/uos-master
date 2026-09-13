"""Deterministic bounded RLE container for the disk's native BASIC boot file."""
import binascii
import os
import subprocess
from pathlib import Path


def pack(data):
    out = bytearray()
    at = 0
    while at < len(data):
        run = 1
        while at+run < len(data) and data[at+run] == data[at] and run < 130:
            run += 1
        if run >= 3:
            out += bytes([0x80+run-3, data[at]])
            at += run
        else:
            first = at
            at += run
            while at < len(data) and at-first < 127:
                if data[at:at+3] == data[at:at+1]*3:
                    break
                at += 1
            out.append(at-first)
            out += data[first:at]
    out.append(0)
    return bytes(out)


def unpack(data, length):
    out = bytearray()
    at = 0
    while at < len(data):
        code = data[at]; at += 1
        if code == 0:
            if at != len(data) or len(out) != length:
                raise ValueError('wrong boot stream length')
            return bytes(out)
        count = code-125 if code >= 128 else code
        needed = 1 if code >= 128 else count
        if at+needed > len(data) or len(out)+count > length:
            raise ValueError('boot stream exceeds its input or output bounds')
        out += data[at:at+1]*count if code >= 128 else data[at:at+count]
        at += needed
    raise ValueError('unterminated boot stream')


def build(root, out):
    root, out = Path(root), Path(out)
    raw = (out/'uos128.prg').read_bytes()
    assert raw[:2] == b'\x01\x1c'
    data = raw[2:]
    packed = pack(data)
    assert unpack(packed, len(data)) == data
    payload = out/'uos128-packed.bin'
    payload.write_bytes(packed)
    try:
        subprocess.run(['64tass', '-a', '-B',
                        '-D', f'BOOT_PACKED_FILE="{os.path.relpath(payload, root/"src/native")}"',
                        '-D', f'BOOT_LENGTH={len(packed)}',
                        '-D', f'BOOT_END={0x1c01+len(data)}',
                        '-D', f'BOOT_EXPECTED_CRC={binascii.crc_hqx(data,0xffff)}',
                        str(root/'src/native/boot-unpack.asm'),
                        '-o', str(out/'uos128-boot.prg'),
                        '-l', str(out/'uos128-boot.sym'),
                        '-L', str(out/'uos128-boot.lst')], check=True)
    finally:
        payload.unlink()
    return dict(codec='rle1-crc16', unpacked_bytes=len(data), packed_bytes=len(packed),
                boot_file='uos128-boot.prg', decoder_start=0x1300, scratch_start=0x6000)
