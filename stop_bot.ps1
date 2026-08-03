$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*bot.main*' }
if ($procs) {
    foreach ($p in $procs) {
        Stop-Process -Id $p.ProcessId -Force
        Write-Host ("[OK] Stopped AURA Bot Process (PID: " + $p.ProcessId + ")") -ForegroundColor Green
    }
} else {
    Write-Host "[INFO] ไม่พบการทำงานของ AURA Bot ในระบบ (Bot is not running)" -ForegroundColor Yellow
}
