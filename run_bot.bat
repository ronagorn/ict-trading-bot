@echo off
setlocal EnableDelayedExpansion
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
echo ============================================================
echo   Starting AURA Super Trader Bot...
echo ============================================================
echo.

:: Check Python 3.13
where python3.13 >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python3.13
    goto :found_python
)

for /f "tokens=*" %%i in ('where python 2^>nul') do (
    set PY_CANDIDATE=%%i
    %%i --version 2>&1 | findstr /C:"3.13" >nul
    if !errorlevel! equ 0 (
        set PY_CMD=%%i
        goto :found_python
    )
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=py -3.13
    goto :found_python
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :found_python
)

echo Python 3.13 not found!
pause
exit /b

:found_python
echo [INFO] Using Python: %PY_CMD%

%PY_CMD% -m pip install -q --no-warn-script-location -r requirements.txt

%PY_CMD% -m bot.main

pause
