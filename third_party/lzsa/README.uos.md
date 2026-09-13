# Pinned LZSA compressor

These sources are copied without modification from
[emmanuel-marty/lzsa](https://github.com/emmanuel-marty/lzsa), commit
`15ee2dfe118eeb8f7683ca44f64821c3a61ca1e5`.

The native boot builder compiles the command-line compressor in a temporary
directory with `CC` (default `cc`). No network access or global installation is
needed. It uses raw forward LZSA2 blocks and checks each result with the separate
Python decoder in `native_lzsa.py`.

LZSA uses the zlib license; its match finder uses CC0. The bundled libdivsufsort
uses the MIT license. All license notices are retained here and in the sources.
The forward 6502 decoder in `src/native/boot-lzsa2.inc` is adapted from upstream
`asm/6502/decompress_small_v2.asm`; that file documents the uOS changes and retains
the upstream notice.
