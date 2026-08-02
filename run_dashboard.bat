@echo off
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
cd /d "%~dp0"
echo ============================================================
echo   📈 Starting AURA Trading Dashboard...
echo ============================================================

:: ตรวจสอบ Python 3.13 ก่อน
where python3.13 >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python3.13
    goto :found_python
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=python
    goto :found_python
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    set PY_CMD=py -3.13
    goto :found_python
)

echo ❌ ไม่พบ Python ในเครื่อง!
pause
exit /b

:found_python
echo [INFO] Using Python: %PY_CMD%

:: ติดตั้ง dependencies (ซ่อน WARNING ที่ไม่จำเป็น)
%PY_CMD% -m pip install -q --no-warn-script-location -r requirements.txt

echo [INFO] Starting Streamlit Dashboard on http://localhost:8501
echo [INFO] กด Ctrl+C เพื่อปิด Dashboard

:: รัน Streamlit จาก path ที่ถูกต้อง
%PY_CMD% -m streamlit run dashboard\app.py --server.port 8501 --server.headless false

pause
