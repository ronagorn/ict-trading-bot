@echo off
title AURA Super Trader - Control Center
cd /d "%~dp0"

:menu
cls
echo ============================================================
echo   AURA SUPER TRADER BOT - Control Center
echo ============================================================
echo.
echo   [1] Start Bot in Background - Run Hidden
echo   [2] Check Bot Status and Memory
echo   [3] Stop Background Bot
echo   [4] Start Bot in Console Mode
echo   [5] Open Web Dashboard
echo   [6] Restart Bot and XM MT5 (Re-open fresh)
echo   [0] Exit
echo.
echo ============================================================
set /p choice="Select Menu [0-6]: "

if "%choice%"=="1" (
    wscript.exe "%~dp0run_bot_background.vbs"
    timeout /t 2 >nul
    goto menu
)
if "%choice%"=="2" (
    call "%~dp0check_bot_status.bat"
    goto menu
)
if "%choice%"=="3" (
    call "%~dp0stop_bot.bat"
    goto menu
)
if "%choice%"=="4" (
    start "" "%~dp0run_bot.bat"
    goto menu
)
if "%choice%"=="5" (
    start "" "%~dp0run_dashboard.bat"
    goto menu
)
if "%choice%"=="6" (
    echo Stopping existing process...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_bot.ps1" >nul 2>&1
    timeout /t 2 >nul
    echo Starting fresh background instance...
    wscript.exe "%~dp0run_bot_background.vbs"
    timeout /t 2 >nul
    goto menu
)
if "%choice%"=="0" exit /b

echo Invalid choice.
timeout /t 1 >nul
goto menu
