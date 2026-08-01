@echo off
echo ============================================================
echo   AURA TRADING BOT - Windows Power Setup
echo   ตั้งค่าระบบให้บอทรันได้ตลอด 24 ชั่วโมง
echo ============================================================
echo.

:: ต้องรันด้วยสิทธิ์ Admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] กรุณาคลิกขวาที่ไฟล์นี้ แล้วเลือก "Run as administrator"
    pause
    exit /b
)

echo [1/4] ปิดระบบ Sleep อัตโนมัติ (ทั้งเสียบปลั๊กและแบตเตอรี่)...
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
echo     OK

echo [2/4] ปิดระบบดับหน้าจออัตโนมัติ...
powercfg /change monitor-timeout-ac 0
powercfg /change monitor-timeout-dc 0
echo     OK

echo [3/4] ตั้งค่าพับฝาแล้วจอมืดแต่เครื่องยังทำงาน (Do Nothing)...
powercfg /setacvalueindex SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 5ca83367-6e45-459f-a27b-476b1d01c936 0
powercfg /setdcvalueindex SCHEME_CURRENT 4f971e89-eebd-4455-a8de-9e59040e7347 5ca83367-6e45-459f-a27b-476b1d01c936 0
powercfg /setactive SCHEME_CURRENT
echo     OK

echo [4/4] ตรวจสอบการตั้งค่าทั้งหมด...
echo.
echo ============================================================
echo   ผลการตั้งค่า:
echo   [OK] Sleep อัตโนมัติ    : ปิดแล้ว
echo   [OK] หน้าจอดับอัตโนมัติ : ปิดแล้ว
echo   [OK] พับฝา -> จอมืด     : เครื่องทำงานต่อ
echo ============================================================
echo.
echo   พร้อมรันบอทเทรดตลอด 24 ชั่วโมงได้เลยครับ!
echo   ดับเบิ้ลคลิก run_bot.bat เพื่อเริ่มต้นบอทครับ
echo.
pause
