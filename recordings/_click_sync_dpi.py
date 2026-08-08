"""DPI-aware: focus app, open RICERCA, click SYNC CASELLA, confirm Yes."""
from __future__ import annotations

import ctypes
import sys
import time
from collections import defaultdict
from ctypes import wintypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def enum_titles(substr: str):
    out = []

    def foreach(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if substr.lower() in title.lower():
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append((hwnd, title, r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumWindows(EnumWindowsProc(foreach), 0)
    return out


def click_at(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.1)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def accent_solid(img, y0, y1, min_w=100, max_w=220, tol=28):
    target = (0x0D, 0x94, 0x88)
    pixels = img.load()
    iw, ih = img.size
    by_x: dict[int, list[int]] = defaultdict(list)
    for y in range(max(0, y0), min(y1, ih)):
        for x in range(iw):
            p = pixels[x, y][:3]
            if (
                abs(p[0] - target[0]) < tol
                and abs(p[1] - target[1]) < tol
                and abs(p[2] - target[2]) < tol
            ):
                by_x[x].append(y)
    runs = []
    start = prev = None
    for x in sorted(by_x):
        if len(by_x[x]) < 8:
            if start is not None:
                runs.append((start, prev))
                start = None
            prev = None
            continue
        if start is None:
            start = x
        elif prev is not None and x - prev > 4:
            runs.append((start, prev))
            start = x
        prev = x
    if start is not None:
        runs.append((start, prev))
    solid = []
    for x0, x1 in runs:
        width = x1 - x0
        if not (min_w <= width <= max_w):
            continue
        ys = []
        for x in range(x0, x1 + 1):
            ys.extend(by_x.get(x, []))
        cy = int(sum(ys) / len(ys))
        solid.append((x0, x1, (x0 + x1) // 2, cy, width))
    return solid


def dismiss_dialogs() -> bool:
    """Click Sì / OK on any tk messagebox related to sync."""
    clicked = False
    for substr in ("Sync casella", "Rielabora", "Casella IMAP", "Occupato", "VIS |"):
        wins = enum_titles(substr)
        for hwnd, title, l, t, r, b in wins:
            if title == "VIS | eniSpace Utility":
                continue
            # Typical Yes/No dialog: Sì is leftish button near bottom
            w, h = r - l, b - t
            if w < 120 or h < 80 or w > 900:
                continue
            print(f"dialog: {title!r} {w}x{h} @ {l},{t}")
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.2)
            # Try 'Sì' roughly center-left bottom
            click_at(l + int(w * 0.38), t + int(h * 0.72))
            time.sleep(0.3)
            clicked = True
    return clicked


def main() -> int:
    from PIL import ImageGrab

    action = (sys.argv[1] if len(sys.argv) > 1 else "sync").lower()
    apps = [w for w in enum_titles("eniSpace Utility") if w[1].startswith("VIS |")]
    if not apps:
        print("APP NOT FOUND")
        return 1
    hwnd, title, left, top, right, bottom = apps[0]
    print(f"app rect={left},{top},{right},{bottom} size={right-left}x{bottom-top}")
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)

    # Close any leftover dialogs first (Enter / Escape)
    dismiss_dialogs()
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)

    img0 = ImageGrab.grab(bbox=(left, top, right, bottom))
    img0.save(r"recordings\_dpi_app.png")
    print("saved _dpi_app.png", img0.size)

    # Click RICERCA tab (leftmost tab under title)
    # CTk title bar ~32, tabs around y=40-60
    click_at(left + 55, top + 48)
    time.sleep(0.7)

    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    img.save(r"recordings\_dpi_ricerca.png")
    solid = accent_solid(img, 90, 280)
    print("solid accent buttons:", solid)

    # CERCA ORDINE left solid, SYNC CASELLA right solid in same row
    toolbar = [s for s in solid if 100 <= s[3] <= 250]
    toolbar.sort(key=lambda s: s[2])
    print("toolbar:", toolbar)

    if action == "rielabora":
        # outlined button to the right of SYNC
        if toolbar:
            sync = toolbar[-1]
            cx = left + sync[2] + sync[4] // 2 + 90
            cy = top + sync[3]
        else:
            cx, cy = right - 90, top + 160
        print(f"click RIELABORA {cx},{cy}")
        click_at(cx, cy)
    else:
        if len(toolbar) >= 2:
            choice = toolbar[-1]  # SYNC
        elif toolbar:
            choice = toolbar[0]
        else:
            choice = None
        if choice:
            cx, cy = left + choice[2], top + choice[3]
            print(f"click SYNC {cx},{cy} w={choice[4]}")
            click_at(cx, cy)
        else:
            # relative fallback: buttons packed after entry; SYNC near 70-80% width
            cx = left + int((right - left) * 0.78)
            cy = top + 155
            print(f"fallback SYNC {cx},{cy}")
            click_at(cx, cy)

    time.sleep(0.8)
    # Confirm askyesno
    for _ in range(5):
        if dismiss_dialogs():
            break
        # Also try pressing Enter / Y for default Yes
        time.sleep(0.3)
    else:
        # Send Enter to focused dialog
        VK_RETURN = 0x0D
        user32.keybd_event(VK_RETURN, 0, 0, 0)
        user32.keybd_event(VK_RETURN, 0, 2, 0)
        print("sent Enter")

    time.sleep(0.5)
    img2 = ImageGrab.grab(bbox=(left, top, right, bottom))
    img2.save(r"recordings\_dpi_after.png")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
