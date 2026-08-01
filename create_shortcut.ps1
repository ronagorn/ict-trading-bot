$WshShell = New-Object -comObject WScript.Shell
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$Shortcut = $WshShell.CreateShortcut("$DesktopPath\AURA ICT Bot.lnk")
$Shortcut.TargetPath = "D:\antigravity\AI-Super-trader\ict-trading-bot\run_bot.bat"
$Shortcut.WorkingDirectory = "D:\antigravity\AI-Super-trader\ict-trading-bot"
$Shortcut.IconLocation = "D:\antigravity\AI-Super-trader\ict-trading-bot\bot_icon.ico"
$Shortcut.Save()
