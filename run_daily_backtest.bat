@echo off
chcp 65001 > NUL
title AURA Daily Backtest Summary

echo ============================================================
echo   📊 AURA SUPER TRADER - DAILY BACKTEST REPORT GENERATOR
echo ============================================================
echo.
python "%~dp0run_daily_backtest.py"
echo.
echo ============================================================
echo   Done! Report sent to Telegram. Press any key to exit.
echo ============================================================
pause > nul
