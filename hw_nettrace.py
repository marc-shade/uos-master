#!/usr/bin/env python3
"""Run probes/nettrace.bin on the real C128 through the tick vector and
decode the SNTP step log it leaves at $6000 (see the probe source)."""
import importlib.util, os, struct, sys, time
from importlib.machinery import SourceFileLoader
_l = SourceFileLoader("cbm", "/home/marc/.claude/skills/commodore-basic/bin/cbm")
cbm = importlib.util.module_from_spec(importlib.util.spec_from_loader("cbm", _l)); _l.exec_module(cbm)
UOS = os.path.dirname(os.path.abspath(__file__))
TICK_VEC, TRAMP, LOG = 0x033C, 0x7F00, 0x6000
code = bytearray(open(os.path.join(UOS, "probes/nettrace.bin"), "rb").read()[2:])
i = code.index(bytes([0xa9, 0x00, 0x8d, 0x3c, 0x03])); j = code.index(bytes([0xa9, 0x00, 0x8d, 0x3d, 0x03]))
import argparse, re
ap = argparse.ArgumentParser()
ap.add_argument("--host", default="pool.ntp.org"); ap.add_argument("--port", type=int, default=123)
ap.add_argument("--proto", default="udp"); ap.add_argument("--req", default="ntp", help="ntp | dns | hex bytes")
a = ap.parse_args()
lst = open(os.path.join(UOS, "probes/nettrace.lst"), "rb").read().decode("latin-1")
sym = lambda n: int(re.search(r"^[.>]([0-9a-f]{4})\s+(?:(?:[0-9a-f]{2} ?)+\s+)?%s:" % n, lst, re.M).group(1), 16) - TRAMP
if a.req == "ntp":
    req = b"\x23" + bytes(47)
elif a.req == "dns":     # A query for pool.ntp.org, RD set
    req = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + b"\x04pool\x03ntp\x03org\x00\x00\x01\x00\x01"
else:
    req = bytes.fromhex(a.req)
code[sym("proto")] = 7 if a.proto == "tcp" else 8
code[sym("portL")], code[sym("portH")] = a.port & 0xff, a.port >> 8
code[sym("reqlen")] = len(req)
h = a.host.encode() + b"\x00"; code[sym("host"):sym("host") + len(h)] = h
code[sym("req"):sym("req") + len(req)] = req
print(f"probe: {a.proto} {a.host}:{a.port} req {len(req)} B")
u = cbm.Ultimate()
vec = u.read_mem(TICK_VEC, 2)
assert vec != b"\x00\x00", "desktop not live"
code[i + 1], code[j + 1] = vec[0], vec[1]
def wr(addr, data):                     # the Ultimate client caps a write at 128 bytes
    for k in range(0, len(data), 128):
        u.write_mem(addr + k, bytes(data[k:k + 128]))
wr(LOG, bytes(256))
wr(TRAMP, code)
u.write_mem(TICK_VEC, struct.pack("<H", TRAMP))
t0 = time.time()
for _ in range(60):
    time.sleep(2)
    if u.read_mem(LOG + 0xff, 1) == b"\xa5":
        break
else:
    sys.exit(f"probe never finished (vec={u.read_mem(TICK_VEC, 2).hex()})")
print(f"probe done after {time.time() - t0:.0f}s")
m = u.read_mem(LOG, 256)
z = lambda b: b.split(b"\x00")[0].decode("latin-1")
print(f"open: A={m[0]:#04x} C={m[1]} status={z(m[2:0x22])!r}")
print(f"write: A={m[0x40]:#04x} status={z(m[0x41:0x60])!r}")
print(f"read: tries={m[0x80]} final A={m[0x81]} status={z(m[0x82:0xa2])!r}")
ln = m[0xc0] | m[0xc1] << 8
print(f"NET_LEN={ln} payload={m[0xc2:0xc2+48].hex()} close A={m[0xf8]:#04x}")
if a.req == "ntp" and ln == 48:
    secs = struct.unpack(">I", m[0xc2 + 40:0xc2 + 44])[0] - 2208988800
    print("NTP transmit timestamp:", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(secs)), "UTC")
