$botProcs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*bot.main*' }
$mt5Procs = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'terminal64.exe' -or $_.CommandLine -like '*terminal64*' }

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " 🤖 PYTHON TRADING BOT STATUS:" -ForegroundColor Yellow
if ($botProcs) {
    Write-Host "   STATUS: 🟢 RUNNING (บอทกำลังทำงานในฉากหลัง)" -ForegroundColor Green
    foreach ($p in $botProcs) {
        $procObj = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
        if ($procObj) {
            $mem = [math]::Round($procObj.WorkingSet64 / 1MB, 2)
            Write-Host ("   - Process ID (PID) : " + $p.ProcessId)
            Write-Host ("   - Memory Usage (RAM): " + $mem + " MB")
        }
    }
} else {
    Write-Host "   STATUS: 🔴 STOPPED (บอทไม่ได้เปิดทำงานอยู่)" -ForegroundColor Red
}

Write-Host ""
Write-Host " 📈 XM MT5 TERMINAL STATUS:" -ForegroundColor Yellow
if ($mt5Procs) {
    Write-Host "   STATUS: 🟢 RUNNING (โปรแกรม XM MT5 กำลังเปิดอยู่)" -ForegroundColor Green
    foreach ($p in $mt5Procs) {
        $procObj = Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue
        if ($procObj) {
            $mem = [math]::Round($procObj.WorkingSet64 / 1MB, 2)
            Write-Host ("   - Process ID (PID) : " + $p.ProcessId)
            Write-Host ("   - Memory Usage (RAM): " + $mem + " MB")
        }
    }
} else {
    Write-Host "   STATUS: 🔴 STOPPED (โปรแกรม XM MT5 ไม่ได้เปิดอยู่)" -ForegroundColor Red
}
Write-Host "============================================================" -ForegroundColor Cyan
