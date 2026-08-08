Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;
using System.Text;
public static class MT5Debug {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsDelegate f, IntPtr lp);
    public delegate bool EnumWindowsDelegate(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder s, int max);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex);
    [DllImport("user32.dll")] public static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);
    public static string ScanAndShow(int targetPid) {
        var lines = new List<string>();
        int total = 0;
        EnumWindows((hwnd, lp) => {
            total++;
            uint pid;
            GetWindowThreadProcessId(hwnd, out pid);
            bool vis = IsWindowVisible(hwnd);
            var title = new StringBuilder(256);
            GetWindowText(hwnd, title, 256);
            if ((int)pid == targetPid) {
                IntPtr exStyle = GetWindowLongPtr(hwnd, -20);
                long newStyle = (exStyle.ToInt64() & ~0x80L) | 0x40000L;
                SetWindowLongPtr(hwnd, -20, new IntPtr(newStyle));
                ShowWindow(hwnd, 9);
                BringWindowToTop(hwnd);
                SetForegroundWindow(hwnd);
                lines.Add("[MT5] hwnd=" + hwnd.ToInt64().ToString("X") + " pid=" + pid + " vis=" + vis + " title=" + title.ToString() + " -> RESTORED");
            }
            return true;
        }, IntPtr.Zero);
        lines.Insert(0, "Total windows enumerated: " + total);
        return string.Join("\n", lines);
    }
}
"@

$pid28312 = (Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'terminal64.exe' }).ProcessId
Write-Host "terminal64 PID: $pid28312"
if ($pid28312) {
    $result = [MT5Debug]::ScanAndShow([int]$pid28312)
    Write-Host $result
} else {
    Write-Host "terminal64 not running"
}
