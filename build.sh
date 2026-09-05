#!/usr/bin/env bash
# Linux build for UltOS — replaces build.bat (Windows-only).
# Assembles 7 PRGs with 64tass, packs them into target/ultos.d64 with c1541.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p target
rm -f target/*.bin target/*.prg target/ultos.d64

for m in uos uos-gfx uos-vdc uos-drv1351 uos-sprites uos-reu uos-desktop uos-settings uos-fmgr uos-shell; do
    echo "== 64tass $m =="
    64tass -a "src/${m}.asm" -o "target/${m}.prg" -L "target/${m}.lst"
done

c1541 -format "ultos,sh" d64 target/ultos.d64 >/dev/null 2>&1
for m in uos uos-gfx uos-vdc uos-drv1351 uos-sprites uos-reu uos-desktop uos-settings uos-fmgr uos-shell; do
    c1541 -attach target/ultos.d64 -write "target/${m}.prg" "$m" >/dev/null 2>&1
done
echo "== done =="
ls -la target/*.d64 target/*.prg