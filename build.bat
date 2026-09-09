@echo off
setlocal
cd /d "%~dp0"
if not exist target mkdir target
set "uos_modules=uos uos-gfx uos-vdc uos-drv1351 uos-sprites uos-reu uos-net uos-files uos-desktop uos-settings uos-fmgr uos-shell uos-edit uos-calc uos-ultimate uos-copy"
for %%m in (%uos_modules%) do (
    64tass -a "src/%%m.asm" -o "target/%%m.prg" -L "target/%%m.lst"
    if errorlevel 1 exit /b 1
)
c1541 -format "ultos,sh" d64 "target/ultos.d64"
if errorlevel 1 exit /b 1
for %%m in (%uos_modules%) do (
    c1541 -attach "target/ultos.d64" -write "target/%%m.prg" "%%m"
    if errorlevel 1 exit /b 1
)
endlocal
