$WshShell = New-Object -comObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$IconPath = "D:\antigravity\AI-Super-trader\ict-trading-bot\aura_logo.ico"
$WorkDir = "D:\antigravity\AI-Super-trader\ict-trading-bot"

# 1. ลบ Shortcut เก่า/ที่ซ้ำซ้อนทิ้งให้หมด
$OldShortcuts = @(
    "$DesktopPath\AURA Trading Bot.lnk",
    "$DesktopPath\AURA Trading Bot (Console).lnk",
    "$DesktopPath\AURA Bot (Check Status).lnk",
    "$DesktopPath\AURA Bot (Stop Background).lnk",
    "$DesktopPath\AURA Trading Dashboard.lnk"
)

foreach ($file in $OldShortcuts) {
    if (Test-Path $file) {
        Remove-Item -Path $file -Force
        Write-Host "[REMOVED] Removed redundant shortcut: $file"
    }
}

# 2. สร้าง 2 Icon หลักที่จำเป็นที่สุดบน Desktop

# Icon 1: ปุ่มกดรันบอทฉากหลังทันที
$BgShortcut = $WshShell.CreateShortcut("$DesktopPath\AURA Bot (Start Background).lnk")
$BgShortcut.TargetPath = "$WorkDir\run_bot_background.vbs"
$BgShortcut.WorkingDirectory = $WorkDir
$BgShortcut.Description = "Start AURA Trading Bot invisibly in Background"
$BgShortcut.IconLocation = $IconPath
$BgShortcut.Save()
Write-Host "[CREATED] Created: AURA Bot (Start Background).lnk"

# Icon 2: ศูนย์รวมเมนูควบคุม (เช็คสถานะ, ปิดบอท, เปิด Dashboard, เปิด Console)
$ControlShortcut = $WshShell.CreateShortcut("$DesktopPath\AURA Control Center.lnk")
$ControlShortcut.TargetPath = "$WorkDir\aura_control.bat"
$ControlShortcut.WorkingDirectory = $WorkDir
$ControlShortcut.Description = "AURA Bot All-in-One Control Center"
$ControlShortcut.IconLocation = $IconPath
$ControlShortcut.Save()
Write-Host "[CREATED] Created: AURA Control Center.lnk"

Write-Host "✅ Cleaned up Desktop shortcuts! Keeping only 2 essential icons."
