"""Switch to RICERCA and click SYNC CASELLA / RIELABORA OGGI."""
from __future__ import annotations

import ctypes
import sys
import time
from collections import defaultdict
from ctypes import wintypes

user32 = ctypes.windll.user32
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def find_app():
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
        if "eniSpace Utility" in title:
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            targets.append(
                (hwnd, title, rect.left, rect.top, rect.right, rect.bottom)
            )
        return True

    user32.EnumWindows(EnumWindowsProc(foreach), 0)
    return targets


def click_at(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.12)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def accent_runs(img, y0=0, y1=None, tol=24):
    target = (0x0D, 0x94, 0x88)
    pixels = img.load()
    iw, ih = img.size
    if y1 is None:
        y1 = ih
    hits = []
    for y in range(max(0, y0), min(y1, ih)):
        for x in range(iw):
            p = pixels[x, y][:3]
            if (
                abs(p[0] - target[0]) < tol
                and abs(p[1] - target[1]) < tol
                and abs(p[2] - target[2]) < tol
            ):
                hits.append((x, y))
    by_x: dict[int, list[int]] = defaultdict(list)
    for x, y in hits:
        by_x[x].append(y)
    runs = []
    start = prev = None
    for x in sorted(by_x):
        if len(by_x[x]) < 6:
            if start is not None:
                runs.append((start, prev, by_x))
                start = None
            prev = None
            continue
        if start is None:
            start = x
        elif prev is not None and x - prev > 5:
            runs.append((start, prev, by_x))
            start = x
        prev = x
    if start is not None:
        runs.append((start, prev, by_x))
    solid = []
    for x0, x1, bx in runs:
        width = x1 - x0
        ys = []
        for x in range(x0, x1 + 1):
            ys.extend(bx.get(x, []))
        if not ys:
            continue
        cy = int(sum(ys) / len(ys))
        solid.append((x0, x1, (x0 + x1) // 2, cy, width))
    return hits, solid


def main() -> int:
    from PIL import ImageGrab, ImageDraw

    action = (sys.argv[1] if len(sys.argv) > 1 else "sync").lower()
    targets = find_app()
    if not targets:
        print("APP NOT FOUND")
        return 1
    hwnd, title, left, top, right, bottom = targets[0]
    print(f"app={title} rect={left},{top},{right},{bottom}")
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)

    # 1) Click RICERCA tab — typically near top-left of content
    # Tab labels are text; approximate from window: after titlebar ~40-70px
    # From probe image: tabs are under title. RICERCA is leftmost.
    img0 = ImageGrab.grab(bbox=(left, top, right, bottom))
    img0.save(r"recordings\_ui_before.png")

    # Click RICERCA roughly: left side of tab strip
    # Window may be floating; tab row ~ y=50-80 from window top in CTk
    ricerca_x = left + 70
    ricerca_y = top + 55
    print(f"click RICERCA approx {ricerca_x},{ricerca_y}")
    click_at(ricerca_x, ricerca_y)
    time.sleep(0.8)

    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    img.save(r"recordings\_ui_ricerca.png")

    # Find solid accent buttons in search toolbar band (y ~ 80-220)
    hits, solid = accent_runs(img, y0=70, y1=260)
    print("accent hits", len(hits), "solid", solid)

    # Also look for outlined teal borders for RIELABORA / SYNC region by x position
    # On RICERCA: CERCA ORDINE (solid ~160) then outlined, then SYNC (solid ~140), then RIELABORA outlined
    sync_candidates = [s for s in solid if 110 <= s[4] <= 180]
    sync_candidates.sort(key=lambda s: s[2])
    print("sync_candidates", sync_candidates)

    if action == "rielabora":
        # RIELABORA is outlined (not solid fill). Estimate right of SYNC.
        if sync_candidates:
            sync = sync_candidates[-1]
            cx = left + sync[2] + sync[4] // 2 + 80
            cy = top + sync[3]
        else:
            cx = right - 100
            cy = top + 150
        print(f"CLICK RIELABORA at {cx},{cy}")
        click_at(cx, cy)
    else:
        # Prefer rightmost solid accent in toolbar (= SYNC CASELLA; CERCA is left)
        if len(sync_candidates) >= 2:
            choice = sync_candidates[-1]
        elif sync_candidates:
            choice = sync_candidates[-1]
        else:
            print("NO sync button found, trying fallback coords")
            choice = None
        if choice:
            cx = left + choice[2]
            cy = top + choice[3]
            print(f"CLICK SYNC at {cx},{cy} w={choice[4]}")
            click_at(cx, cy)
        else:
            # Fallback relative to window width
            cx = left + int((right - left) * 0.72)
            cy = top + 150
            print(f"FALLBACK SYNC {cx},{cy}")
            click_at(cx, cy)

    time.sleep(0.5)
    img2 = ImageGrab.grab(bbox=(left, top, right, bottom))
    img2.save(r"recordings\_ui_after_click.png")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
