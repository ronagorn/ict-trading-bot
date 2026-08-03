$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path -Path $startupFolder -ChildPath "AURA_Bot_AutoStart.lnk"
$targetPath = "D:\antigravity\AI-Super-trader\ict-trading-bot\run_bot_background.vbs"

$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = "D:\antigravity\AI-Super-trader\ict-trading-bot"
$shortcut.Description = "AURA Super Trader Automatic Background Startup"
$shortcut.Save()

Write-Host "✅ Created shortcut in Windows Startup folder:" $shortcutPath
