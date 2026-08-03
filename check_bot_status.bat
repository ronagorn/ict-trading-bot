@echo off
setlocal
echo ============================================================
echo   AURA TRADING BOT - System Status Check
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_status.ps1"

echo.
echo ============================================================
pause
