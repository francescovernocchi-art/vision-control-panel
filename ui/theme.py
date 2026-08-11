"""Design tokens — VISION Control Panel (futuristic glass HUD)."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

# ---------------------------------------------------------------------------
# Palette — void glass + cyan HUD
# ---------------------------------------------------------------------------
BG = "#060B14"
BG_SECONDARY = "#0A1220"
SIDEBAR = "#070E1A"
CARD = "#0E1A2E"
CARD_ALT = "#122238"
BORDER = "#1B3A5C"
BORDER_SOLID = "#24507A"
BORDER_FROST = "#38BDF8"
BORDER_DIM = "#1E3A5F"
TEXT = "#F1F7FF"
MUTED = "#8BA3C1"
PRIMARY = "#1D6FE8"
ACCENT = "#38BDF8"
GLOW = "#67E8F9"
GLOW_SOFT = "#0EA5E9"
SUCCESS = "#34D399"
WARNING = "#FBBF24"
ERROR = "#FB7185"
INFO = "#38BDF8"
CONSOLE_BG = "#050D18"
ACTIVE_NAV_BG = "#0B3D91"
ACTIVE_NAV_SOFT = "#0C2748"
FOCUS_BLUE = "#38BDF8"

# Glass window — SOLO backdrop acrylic (mai alpha sulla finestra:
# testo / logo / avatar devono restare 100% opachi)
GLASS_WINDOW_ALPHA = 1.0
GLASS_ACRYLIC_ALPHA = 200
GLASS_TINT = "#061018"

# Proportions @1920
SIDEBAR_WIDTH = 310
ASSISTANT_RAIL_WIDTH = 380
HEADER_HEIGHT = 88
STATUS_FOOTER_HEIGHT = 42
ASSISTANT_WIDTH = ASSISTANT_RAIL_WIDTH
FOOTER_HEIGHT = STATUS_FOOTER_HEIGHT

# Spacing / radii — HUD soft corners
SPACE_XS = 6
SPACE_SM = 10
SPACE_MD = 16
SPACE_LG = 22
SPACE_XL = 32
RADIUS_SM = 10
RADIUS_MD = 14
RADIUS_LG = 18
BTN_HEIGHT = 44
NAV_BTN_HEIGHT = 48
MODULE_CARD_HEIGHT = 64
AVATAR_DISPLAY_SIZE = 300

APP_VERSION = "2.0-vision"

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
    "border_frost": BORDER_FROST,
    "border_dim": BORDER_DIM,
    "console": CONSOLE_BG,
    "active_nav": ACTIVE_NAV_BG,
    "assistant": CARD,
    "glow": GLOW,
    "glow_soft": GLOW_SOFT,
}

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
    # Prefer tech-forward faces when available
    for candidate in ("Segoe UI Variable", "Segoe UI", "Bahnschrift", "Inter", "Arial"):
        if not families or candidate in families:
            _FONT_FAMILY = candidate
            break
    if not _FONT_FAMILY:
        _FONT_FAMILY = "Segoe UI"
    return _FONT_FAMILY


def font(size: int = 14, weight: str = "normal") -> tuple:
    w = "bold" if weight in ("bold", "semibold") else "normal"
    return (font_family(), size, w)


def mono_font(size: int = 13) -> tuple:
    return ("Consolas", size)


def apply_treeview_style(style_name: str = "Vis.Treeview") -> str:
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
        rowheight=34,
        borderwidth=0,
        font=(font_family(), 13),
    )
    style.map(style_name, background=[("selected", ACTIVE_NAV_SOFT)])
    style.configure(
        f"{style_name}.Heading",
        background=CARD_ALT,
        foreground=GLOW,
        font=(font_family(), 12, "bold"),
        relief="flat",
    )
    return style_name
