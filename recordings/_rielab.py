"""Close dialogs, click RIELABORA OGGI, confirm Yes."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
WM_CLOSE = 0x0010


def click(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.1)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def wins():
    out = []

    def foreach(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        t = buf.value
        if not t:
            return True
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        if any(
            k in t
            for k in ("eniSpace Utility", "Rielabora", "Sync", "Occupato", "Casella")
        ):
            out.append((hwnd, t, r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumWindows(EnumWindowsProc(foreach), 0)
    return out


def main() -> int:
    for hwnd, t, *_ in wins():
        if t != "VIS | eniSpace Utility":
            print("close", t)
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    time.sleep(0.5)

    apps = [w for w in wins() if w[1].startswith("VIS |")]
    if not apps:
        print("APP MISSING")
        return 1
    hwnd, t, left, top, right, bottom = apps[0]
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    click(left + 55, top + 48)  # RICERCA
    time.sleep(0.6)
    click(left + 994, top + 217)  # RIELABORA OGGI
    print("clicked RIELABORA")
    time.sleep(1.0)

    for hwnd, t, l2, top2, r2, b2 in wins():
        if "Rielabora" in t:
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.2)
            w, h = r2 - l2, b2 - top2
            click(l2 + int(w * 0.32), top2 + int(h * 0.78))
            time.sleep(0.1)
            user32.keybd_event(0x0D, 0, 0, 0)
            user32.keybd_event(0x0D, 0, 2, 0)
            print("confirmed", t)
            return 0
    print("NO CONFIRM DIALOG")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
