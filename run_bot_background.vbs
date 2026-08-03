' ============================================================
'   AURA TRADING BOT - Invisible Background Launcher
' ============================================================

Set objFSO = CreateObject("Scripting.FileSystemObject")
strDirectory = objFSO.GetParentFolderName(WScript.ScriptFullName)

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = strDirectory

strCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & strDirectory & "\run_bot_background.ps1"""
WshShell.Run strCommand, 0, False
