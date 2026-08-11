"""Effetto vetro / acrylic per finestre VISION (solo Windows).

IMPORTANTE: non usare attributes(-alpha) sulla finestra —
rende trasparenti anche testo, logo e avatar.
Il vetro è solo backdrop (acrylic/mica) dietro pannelli opachi.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any


# Win11 DWM
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWA_MICA_EFFECT = 1029  # legacy
DWMSBT_TRANSIENTWINDOW = 3  # Acrylic

# Win10 SetWindowCompositionAttribute
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
WCA_ACCENT_POLICY = 19


class _ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(_ACCENT_POLICY)),
        ("SizeOfData", ctypes.c_size_t),
    ]


class _MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def _hwnd_for(widget: Any) -> int:
    try:
        widget.update_idletasks()
    except Exception:
        pass
    try:
        wid = int(widget.winfo_id())
    except Exception:
        return 0
    try:
        parent = int(ctypes.windll.user32.GetParent(wid))
        return parent or wid
    except Exception:
        return wid


def _abgr(alpha: int, hex_rgb: str) -> int:
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        h = "061018"
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    a = max(0, min(255, int(alpha)))
    return (a << 24) | (b << 16) | (g << 8) | r


def _set_dwm_attr(hwnd: int, attr: int, value: int) -> bool:
    try:
        v = ctypes.c_int(value)
        hr = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(attr),
            ctypes.byref(v),
            ctypes.sizeof(v),
        )
        return int(hr) == 0
    except Exception:
        return False


def _apply_win11_acrylic(hwnd: int) -> bool:
    _set_dwm_attr(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
    if _set_dwm_attr(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW):
        return True
    return _set_dwm_attr(hwnd, DWMWA_MICA_EFFECT, 1)


def _apply_win10_acrylic(hwnd: int, *, tint: str = "#061018", alpha: int = 200) -> bool:
    try:
        accent = _ACCENT_POLICY()
        accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags = 2
        accent.GradientColor = _abgr(alpha, tint)
        accent.AnimationId = 0
        data = _WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = WCA_ACCENT_POLICY
        data.Data = ctypes.pointer(accent)
        data.SizeOfData = ctypes.sizeof(accent)
        fn = ctypes.windll.user32.SetWindowCompositionAttribute
        fn.argtypes = [wintypes.HWND, ctypes.POINTER(_WINDOWCOMPOSITIONATTRIBDATA)]
        fn.restype = wintypes.BOOL
        return bool(fn(wintypes.HWND(hwnd), ctypes.byref(data)))
    except Exception:
        try:
            accent = _ACCENT_POLICY()
            accent.AccentState = ACCENT_ENABLE_BLURBEHIND
            accent.AccentFlags = 2
            accent.GradientColor = _abgr(alpha, tint)
            data = _WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = WCA_ACCENT_POLICY
            data.Data = ctypes.pointer(accent)
            data.SizeOfData = ctypes.sizeof(accent)
            return bool(
                ctypes.windll.user32.SetWindowCompositionAttribute(
                    wintypes.HWND(hwnd), ctypes.byref(data)
                )
            )
        except Exception:
            return False


def apply_window_glass(
    window: Any,
    *,
    alpha: float = 1.0,
    tint: str = "#061018",
    acrylic_alpha: int = 200,
) -> bool:
    """
    Vetro solo sul backdrop Windows (acrylic/mica).
    NON applica -alpha alla finestra: testo/logo/avatar restano opachi.
    """
    # Forza opaco: eventuale alpha residuo da sessioni precedenti
    try:
        window.attributes("-alpha", 1.0)
    except Exception:
        pass

    if sys.platform != "win32":
        return True

    hwnd = _hwnd_for(window)
    if not hwnd:
        return False

    applied = False
    if _apply_win11_acrylic(hwnd):
        applied = True
    if _apply_win10_acrylic(hwnd, tint=tint, alpha=acrylic_alpha):
        applied = True
    return applied


def schedule_window_glass(window: Any, *, delay_ms: int = 80, **kwargs: Any) -> None:
    """Applica il vetro dopo il map della finestra (hwnd valido)."""

    def _run(attempt: int = 0) -> None:
        ok = apply_window_glass(window, **kwargs)
        if not ok and attempt < 5:
            try:
                window.after(120, lambda: _run(attempt + 1))
            except Exception:
                pass

    try:
        window.after(max(0, int(delay_ms)), lambda: _run(0))
    except Exception:
        apply_window_glass(window, **kwargs)
