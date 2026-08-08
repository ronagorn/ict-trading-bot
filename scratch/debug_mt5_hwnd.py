import ctypes, subprocess

out = subprocess.check_output('tasklist /FI "IMAGENAME eq terminal64.exe" /FO CSV /NH', shell=True, text=True)
pids = set()
for line in out.strip().splitlines():
    parts = line.split('","')
    if len(parts) >= 2:
        try:
            pids.add(int(parts[1].replace('"', '')))
        except:
            pass
print('Target PIDs:', pids)

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_size_t, ctypes.c_size_t)
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_size_t, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong

found = []
count = [0]

def cb(hwnd, lparam):
    count[0] += 1
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value in pids:
        found.append((hwnd, pid.value))
        print(f'  Found MT5 window! hwnd={hwnd:#x} pid={pid.value}')
    return True

# CRITICAL: store reference to prevent garbage collection during EnumWindows
_cb_ref = EnumWindowsProc(cb)
ret = user32.EnumWindows(_cb_ref, 0)
print(f'EnumWindows return: {ret}, total callbacks fired: {count[0]}')
print(f'MT5 windows found: {len(found)}')

# Now try to show them
if found:
    GWL_EXSTYLE = -20
    WS_EX_APPWINDOW = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    user32.GetWindowLongW.argtypes = [ctypes.c_size_t, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [ctypes.c_size_t, ctypes.c_int, ctypes.c_long]
    user32.ShowWindow.argtypes = [ctypes.c_size_t, ctypes.c_int]
    user32.BringWindowToTop.argtypes = [ctypes.c_size_t]
    user32.SetForegroundWindow.argtypes = [ctypes.c_size_t]
    for hwnd, pid in found:
        ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        new_ex = (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex)
        r = user32.ShowWindow(hwnd, 9)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        print(f'ShowWindow({hwnd:#x}) = {r}')
    print('Done! MT5 window should be visible now.')
else:
    print('No MT5 windows found by EnumWindows.')
