"""Click SYNC CASELLA on the running VIS | eniSpace Utility window."""
from __future__ import annotations

import ctypes
import time
from collections import defaultdict
from ctypes import wintypes

user32 = ctypes.windll.user32

EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def find_app_windows():
    targets = []

    def foreach(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if "eniSpace Utility" in title or title.startswith("VIS |"):
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            targets.append(
                (hwnd, title, rect.left, rect.top, rect.right, rect.bottom)
            )
        return True

    user32.EnumWindows(EnumWindowsProc(foreach), 0)
    return targets


def click_at(x: int, y: int) -> None:
    user32.SetCursorPos(x, y)
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def main() -> int:
    from PIL import ImageGrab

    targets = find_app_windows()
    print("windows:", targets)
    if not targets:
        return 1

    hwnd, title, left, top, right, bottom = targets[0]
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)

    w, h = right - left, bottom - top
    print(f"rect={left},{top},{right},{bottom} size={w}x{h}")

    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    img.save(r"recordings\_ui_probe.png")
    target = (0x0D, 0x94, 0x88)
    pixels = img.load()
    iw, ih = img.size
    hits = []
    for y in range(60, min(240, ih)):
        for x in range(0, iw):
            p = pixels[x, y][:3]
            if (
                abs(p[0] - target[0]) < 22
                and abs(p[1] - target[1]) < 22
                and abs(p[2] - target[2]) < 22
            ):
                hits.append((x, y))
    print("accent hits", len(hits))

    if hits:
        by_x: dict[int, list[int]] = defaultdict(list)
        for x, y in hits:
            by_x[x].append(y)
        runs = []
        start = None
        prev = None
        for x in sorted(by_x):
            if len(by_x[x]) < 8:
                if start is not None:
                    runs.append((start, prev))
                    start = None
                prev = None
                continue
            if start is None:
                start = x
            elif prev is not None and x - prev > 5:
                runs.append((start, prev))
                start = x
            prev = x
        if start is not None:
            runs.append((start, prev))
        print("accent runs:", runs)

        solid = []
        for x0, x1 in runs:
            width = x1 - x0
            if 90 <= width <= 200:
                ys = []
                for x in range(x0, x1 + 1):
                    ys.extend(by_x.get(x, []))
                if not ys:
                    continue
                cy = int(sum(ys) / len(ys))
                solid.append((x0, x1, (x0 + x1) // 2, cy, width))
        print("solid candidates:", solid)
        if solid:
            solid.sort(key=lambda s: s[2])
            # Rightmost solid teal button in the top toolbar is SYNC CASELLA
            # (CERCA ORDINE is left, SYNC is further right).
            choice = solid[-1]
            cx = left + choice[2]
            cy = top + choice[3]
            print(f"CLICKING at {cx},{cy} width={choice[4]}")
            click_at(cx, cy)
            print("clicked")
            return 0

    # Fallback: from right edge — RIELABORA(150)+gap+SYNC center
    cx = right - 24 - 150 - 8 - 70
    cy = top + 140
    print(f"FALLBACK click {cx},{cy}")
    click_at(cx, cy)
    print("clicked fallback")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
