@echo off
setlocal EnableDelayedExpansion
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
echo ============================================================
echo   🚀 Starting AURA Super Trader Bot...
echo ============================================================

:: ตรวจสอบ Python 3.13 ก่อน (ชัดเจนที่สุด)
where python3.13 >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python3.13
    goto :found_python
)

:: ตรวจสอบ python (ใช้ python ที่ติดตั้ง packages ไว้ใน 3.13)
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    set PY_CANDIDATE=%%i
    %%i --version 2>&1 | findstr /C:"3.13" >nul
    if !errorlevel! equ 0 (
        set PY_CMD=%%i
        goto :found_python
    )
)

:: fallback: ใช้ py launcher ที่เจอก่อน
where py >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=py -3.13
    goto :found_python
)

:: fallback สุดท้าย: ใช้ python ที่เจอ
where python >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :found_python
)

echo ❌ ไม่พบ Python ในเครื่อง!
echo กรุณาติดตั้ง Python จาก https://python.org แล้วติ๊กถูก "Add Python to PATH"
pause
exit /b

:found_python
echo [INFO] Using Python: %PY_CMD%

:: ติดตั้ง dependencies อัตโนมัติ (ซ่อน WARNING ที่ไม่จำเป็น)
%PY_CMD% -m pip install -q --no-warn-script-location -r requirements.txt

:: รันบอท
%PY_CMD% -m bot.main

pause
