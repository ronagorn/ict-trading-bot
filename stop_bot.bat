@echo off
setlocal
echo ============================================================
echo   Stopping AURA Trading Bot Background Process...
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_bot.ps1"

echo.
echo ============================================================
pause
