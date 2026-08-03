Add-Type -AssemblyName System.Windows.Forms

$WorkDir = "D:\antigravity\AI-Super-trader\ict-trading-bot"

# 1. ตรวจสอบว่าบอทเปิดทำงานอยู่แล้วหรือไม่
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*bot.main*' }
if ($procs) {
    [System.Windows.Forms.MessageBox]::Show(
        "AURA Trading Bot กำลังทำงานในฉากหลังอยู่แล้วครับ!`n`nระบบจะไม่เปิดบอทซ้ำเพื่อป้องกันออเดอร์ซ้ำซ้อน`n(คุณสามารถรับการแจ้งเตือนและสั่งการผ่าน Telegram ได้เลยครับ)",
        "AURA Bot - Already Running",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    ) | Out-Null
    exit
}

# 2. ค้นหา Python executable
$pythonExe = "python"
if (Get-Command python3.13 -ErrorAction SilentlyContinue) {
    $pythonExe = "python3.13"
}

# 3. รัน Python Bot โดยตรงในฉากหลังแบบไร้หน้าต่าง CMD
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
Start-Process -FilePath $pythonExe -ArgumentList "-m", "bot.main" -WorkingDirectory $WorkDir -WindowStyle Hidden

# 4. แจ้งเตือนภาษาไทย คมชัด
[System.Windows.Forms.MessageBox]::Show(
    "AURA Super Trader Bot เริ่มทำงานในฉากหลังเรียบร้อยแล้ว!`n`nคุณสามารถรับการแจ้งเตือนการเทรดผ่าน Telegram ได้ทันที`n(หากต้องการควบคุมหรือปิดบอท ให้คลิก AURA Control Center บน Desktop)",
    "AURA Bot - Started in Background",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null
