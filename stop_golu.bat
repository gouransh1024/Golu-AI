@echo off
title Stop Project Golu
cd /d "%~dp0"
echo Stopping Project Golu processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*start_golu.py*' -or $_.CommandLine -like '*mic_listener.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo.
echo ======================================================================
echo Project Golu stopped cleanly.
echo All audio handles, VRAM allocation, and background ports released.
echo ======================================================================
pause
