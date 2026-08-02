$WshShell = New-Object -comObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")

# 1. Shortcut สำหรับ Trading Bot
$BotShortcut = $WshShell.CreateShortcut("$DesktopPath\AURA Trading Bot.lnk")
$BotShortcut.TargetPath = "D:\antigravity\AI-Super-trader\ict-trading-bot\run_bot.bat"
$BotShortcut.WorkingDirectory = "D:\antigravity\AI-Super-trader\ict-trading-bot"
$BotShortcut.Description = "AURA Super Trader Bot v2.0 (Auto Trading Engine)"
$BotShortcut.IconLocation = "shell32.dll, 13" # Rocket/Lightning icon
$BotShortcut.Save()

# 2. Shortcut สำหรับ Trading Dashboard
$DashShortcut = $WshShell.CreateShortcut("$DesktopPath\AURA Trading Dashboard.lnk")
$DashShortcut.TargetPath = "D:\antigravity\AI-Super-trader\ict-trading-bot\run_dashboard.bat"
$DashShortcut.WorkingDirectory = "D:\antigravity\AI-Super-trader\ict-trading-bot"
$DashShortcut.Description = "AURA Super Trader Analytics Dashboard"
$DashShortcut.IconLocation = "shell32.dll, 14" # Graph/Chart icon
$DashShortcut.Save()

Write-Host "✅ Created Desktop Shortcuts Successfully!"
