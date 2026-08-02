$WshShell = New-Object -comObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$IconPath = "D:\antigravity\AI-Super-trader\ict-trading-bot\aura_logo.ico"

# 1. Shortcut สำหรับ Trading Bot
$BotShortcut = $WshShell.CreateShortcut("$DesktopPath\AURA Trading Bot.lnk")
$BotShortcut.TargetPath = "D:\antigravity\AI-Super-trader\ict-trading-bot\run_bot.bat"
$BotShortcut.WorkingDirectory = "D:\antigravity\AI-Super-trader\ict-trading-bot"
$BotShortcut.Description = "AURA Super Trader Bot v2.0 (Futuristic AI Trading Engine)"
$BotShortcut.IconLocation = $IconPath
$BotShortcut.Save()

# 2. Shortcut สำหรับ Trading Dashboard
$DashShortcut = $WshShell.CreateShortcut("$DesktopPath\AURA Trading Dashboard.lnk")
$DashShortcut.TargetPath = "D:\antigravity\AI-Super-trader\ict-trading-bot\run_dashboard.bat"
$DashShortcut.WorkingDirectory = "D:\antigravity\AI-Super-trader\ict-trading-bot"
$DashShortcut.Description = "AURA Super Trader Analytics Dashboard"
$DashShortcut.IconLocation = $IconPath
$DashShortcut.Save()

Write-Host "✅ Created Desktop Shortcuts with AI Logo Successfully!"
