@echo off
title MT5 Tick Data Engine Launcher
cd /d "%~dp0"
echo ===================================================
echo   Launching MT5 Tick Data Engine ^& Backtester
echo ===================================================
python run_tick_engine.py
pause
