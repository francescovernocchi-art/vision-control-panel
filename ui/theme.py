"""Design tokens VIS | eniSpace Utility — solo grafica."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

# ---------------------------------------------------------------------------
# Palette (spec)
# ---------------------------------------------------------------------------
BG = "#0B1220"
BG_SECONDARY = "#101A2B"
SIDEBAR = "#0A1020"
CARD = "#111C2E"
CARD_ALT = "#162235"
BORDER = "#FFFFFF14"  # ~rgba(255,255,255,0.08) approx for solid widgets
BORDER_SOLID = "#1E2A3D"
TEXT = "#F3F6FA"
MUTED = "#9DA9BA"
PRIMARY = "#0076C0"
ACCENT = "#1585D8"
SUCCESS = "#22C55E"
WARNING = "#F59E0B"
ERROR = "#EF4444"
INFO = "#38BDF8"
CONSOLE_BG = "#08101D"
ACTIVE_NAV_BG = "#0E1A2E"
FOCUS_BLUE = "#1585D8"

# Backward-compatible COLORS dict (keys used across the codebase)
COLORS = {
    "bg": BG,
    "bg_secondary": BG_SECONDARY,
    "sidebar": SIDEBAR,
    "panel": CARD,
    "panel_alt": CARD_ALT,
    "card": CARD,
    "card_alt": CARD_ALT,
    "accent": PRIMARY,
    "accent_hover": ACCENT,
    "primary": PRIMARY,
    "danger": ERROR,
    "success": SUCCESS,
    "warning": WARNING,
    "info": INFO,
    "text": TEXT,
    "muted": MUTED,
    "input": CONSOLE_BG,
    "border": BORDER_SOLID,
    "border_subtle": BORDER,
    "console": CONSOLE_BG,
    "active_nav": ACTIVE_NAV_BG,
}

# Spacing / radii
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
RADIUS_SM = 6
RADIUS_MD = 8
RADIUS_LG = 10
BTN_HEIGHT = 40
SIDEBAR_WIDTH = 236
HEADER_HEIGHT = 56
APP_VERSION = "1.0"

# Font families (Inter if present, else Segoe UI)
_FONT_FAMILY: Optional[str] = None


def font_family() -> str:
    global _FONT_FAMILY
    if _FONT_FAMILY:
        return _FONT_FAMILY
    try:
        root = tk._default_root  # noqa: SLF001
        families = set(root.tk.call("font", "families")) if root else set()
    except Exception:
        families = set()
    for candidate in ("Inter", "Segoe UI", "Arial"):
        if not families or candidate in families:
            _FONT_FAMILY = candidate
            break
    if not _FONT_FAMILY:
        _FONT_FAMILY = "Segoe UI"
    return _FONT_FAMILY


def font(size: int = 13, weight: str = "normal") -> tuple:
    """Tuple font for tk widgets."""
    w = "bold" if weight in ("bold", "semibold") else "normal"
    return (font_family(), size, w)


def mono_font(size: int = 12) -> tuple:
    return ("Consolas", size)


def apply_treeview_style(style_name: str = "Vis.Treeview") -> str:
    """Configure a modern dark Treeview style; returns style name."""
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        style_name,
        background=CARD,
        foreground=TEXT,
        fieldbackground=CARD,
        rowheight=30,
        borderwidth=0,
        font=font(11),
    )
    style.configure(
        f"{style_name}.Heading",
        background=CARD_ALT,
        foreground=MUTED,
        relief="flat",
        font=font(11, "bold"),
        borderwidth=0,
    )
    style.map(
        style_name,
        background=[("selected", PRIMARY), ("!selected", CARD)],
        foreground=[("selected", TEXT)],
    )
    style.layout(style_name, style.layout("Treeview"))
    return style_name
