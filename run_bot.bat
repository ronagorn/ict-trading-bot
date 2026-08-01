@echo off
echo Starting ICT Trading Bot...
cd /d "%~dp0"
set PYTHONPATH=%cd%
python -m bot.main
pause
