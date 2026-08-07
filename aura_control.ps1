# Set Console output encoding to UTF-8
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$host.UI.RawUI.WindowTitle = "AURA Super Trader - Control Center"

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

function Show-Menu {
    Clear-Host
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "   🤖 AURA SUPER TRADER BOT - Control Center" -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   [1] Start Bot in Background - Run Hidden (รันฉากหลัง)" -ForegroundColor White
    Write-Host "   [2] Check Bot Status and Memory (เช็คสถานะระบบ)" -ForegroundColor White
    Write-Host "   [3] Stop Background Bot (หยุดบอทฉากหลัง)" -ForegroundColor White
    Write-Host "   [4] Start Bot in Console Mode (เปิดหน้าต่างดำสแกนกราฟสด)" -ForegroundColor Green
    Write-Host "   [5] Open Web Dashboard (เปิดเว็บแดชบอร์ด)" -ForegroundColor Green
    Write-Host "   [6] Restart Bot and XM MT5 (Re-open fresh)" -ForegroundColor Yellow
    Write-Host "   [7] Show / Unhide XM MT5 Window (แสดงหน้าต่าง XM MT5)" -ForegroundColor Cyan
    Write-Host "   [8] Hide XM MT5 Window (ซ่อนหน้าต่าง XM MT5 ลงฉากหลัง)" -ForegroundColor DarkGray
    Write-Host "   [0] Exit (ออกจากเมนู)" -ForegroundColor Red
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
}

do {
    Show-Menu
    $choice = Read-Host "Select Menu [0-8]"
    Write-Host ""

    switch ($choice) {
        "1" {
            Write-Host "🚀 Starting bot in background..." -ForegroundColor Green
            Start-Process -FilePath "wscript.exe" -ArgumentList "`"$ScriptDir\run_bot_background.vbs`""
            Start-Sleep -Seconds 2
        }
        "2" {
            & "$ScriptDir\check_status.ps1"
            Write-Host ""
            Read-Host "Press Enter to return to menu..."
        }
        "3" {
            & "$ScriptDir\stop_bot.ps1"
            Start-Sleep -Seconds 2
        }
        "4" {
            Write-Host "🖥️ Launching Bot in Console Mode..." -ForegroundColor Green
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$ScriptDir\run_bot.bat`""
            Start-Sleep -Seconds 2
        }
        "5" {
            Write-Host "🌐 Launching Web Dashboard..." -ForegroundColor Green
            Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$ScriptDir\run_dashboard.bat`""
            Start-Sleep -Seconds 2
        }
        "6" {
            Write-Host "🔄 Restarting Bot process..." -ForegroundColor Yellow
            & "$ScriptDir\stop_bot.ps1" | Out-Null
            Start-Sleep -Seconds 2
            Write-Host "🚀 Starting fresh background instance..." -ForegroundColor Green
            Start-Process -FilePath "wscript.exe" -ArgumentList "`"$ScriptDir\run_bot_background.vbs`""
            Start-Sleep -Seconds 2
        }
        "7" {
            Write-Host "👁️ Restoring XM MT5 Window..." -ForegroundColor Cyan
            python -c "from bot.mt5_client import MT5Client; client = MT5Client(); client.show_window()"
            Write-Host "✅ [OK] MT5 Window unhidden and restored to Taskbar." -ForegroundColor Green
            Start-Sleep -Seconds 2
        }
        "8" {
            Write-Host "🙈 Hiding XM MT5 Window..." -ForegroundColor DarkGray
            python -c "from bot.mt5_client import MT5Client; client = MT5Client(); client.hide_window()"
            Write-Host "✅ [OK] MT5 Window hidden from Taskbar." -ForegroundColor Green
            Start-Sleep -Seconds 2
        }
        "0" {
            Write-Host "Exiting Control Center. Goodbye!" -ForegroundColor Gray
            break
        }
        default {
            Write-Host "❌ Invalid choice. Please select 0 to 8." -ForegroundColor Red
            Start-Sleep -Seconds 1
        }
    }
} while ($choice -ne "0")
