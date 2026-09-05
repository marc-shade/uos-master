#!/usr/bin/env bash
# Boot uOS in C64 mode under x128 (VICE) headless with BOTH the VIC-II 40-col
# and the VDC 80-col displays, and screenshot them at intervals — so the
# 80-column output can be verified without eyes on the real second monitor.
#
#   -go64      x128 boots straight into C64 mode (uOS is a C64-mode OS); the
#              8563 VDC is still emulated and rendered in its own window.
#   Both VICE toplevels land at the same spot on a WM-less Xvfb root, so the
#   root capture may overlap them; each window is ALSO captured by id.
#
# Usage: vdc_emu.sh [out_dir] [timeout_s]
set -u
UOS="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$UOS/vdc-emu-out}"; TIMEOUT="${2:-90}"
mkdir -p "$OUT"
DISP=:94
export __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json
export DISPLAY=$DISP
rm -f /tmp/.X11-unix/X94
Xvfb $DISP -screen 0 1600x700x24 >/dev/null 2>&1 & XV=$!
for i in $(seq 1 20); do xdpyinfo -display "$DISP" >/dev/null 2>&1 && break; sleep 0.25; done
EMU=""
trap '[ -n "$EMU" ] && kill $EMU 2>/dev/null; kill $XV 2>/dev/null' EXIT

x128 -default -go64 \
    -autostart "$UOS/target/ultos.d64" \
    -drive8true -drive8type 1541 \
    -sounddev dummy -jamaction 0 -warp \
    >"$OUT/vice.log" 2>&1 &
EMU=$!

capture() {
    local tag=$1 n=0
    magick import -display $DISP -window root "$OUT/root-${tag}.png" 2>/dev/null
    for wid in $(xwininfo -display $DISP -root -tree 2>/dev/null \
                 | grep -iE "vice" | grep -oE "^ *0x[0-9a-f]+" | tr -d ' ' | head -4); do
        n=$((n+1))
        magick import -display $DISP -window "$wid" "$OUT/win${n}-${tag}.png" 2>/dev/null
    done
    echo "captured ${tag}: root + ${n} VICE window(s)"
}

last=0
for t in 20 40 60 90 120; do
    [ $t -le $TIMEOUT ] || break
    sleep $(( t - last )); last=$t
    kill -0 $EMU 2>/dev/null || { echo "x128 died"; tail -5 "$OUT/vice.log"; break; }
    capture "${t}s"
done
echo "windows on the Xvfb root at exit:"
xwininfo -display $DISP -root -tree 2>/dev/null | grep -iE "vice" | head
