"""Icone geometriche leggere (Pillow) — stile Lucide, senza emoji."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional, Tuple

from PIL import Image, ImageDraw, ImageTk

import customtkinter as ctk

from ui.theme import MUTED, PRIMARY
from utils.paths import brand_logo_ico, brand_logo_png


Color = Tuple[int, int, int, int]

# Keep PhotoImage refs alive for wm_iconphoto
_ICON_PHOTO_REFS: list[Any] = []


def _hex(h: str, alpha: int = 255) -> Color:
    h = h.lstrip("#")
    if len(h) == 8:
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4, 6))  # type: ignore
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, alpha)


def _new(size: int) -> Image.Image:
    return Image.new("RGBA", (size, size), (0, 0, 0, 0))


def _line(draw: ImageDraw.ImageDraw, pts, color: Color, width: int = 2) -> None:
    draw.line(pts, fill=color, width=width, joint="curve")


@lru_cache(maxsize=64)
def _draw_icon(name: str, size: int, color_hex: str) -> Image.Image:
    img = _new(size)
    d = ImageDraw.Draw(img)
    c = _hex(color_hex)
    m = size * 0.18
    s = size - m

    if name == "dashboard":
        gap = size * 0.08
        d.rounded_rectangle([m, m, size * 0.48, size * 0.48], radius=3, outline=c, width=2)
        d.rounded_rectangle([size * 0.52 + gap * 0.2, m, s, size * 0.38], radius=3, outline=c, width=2)
        d.rounded_rectangle([m, size * 0.52, size * 0.38, s], radius=3, outline=c, width=2)
        d.rounded_rectangle([size * 0.48, size * 0.45, s, s], radius=3, outline=c, width=2)
    elif name == "search":
        d.ellipse([m, m, size * 0.62, size * 0.62], outline=c, width=2)
        _line(d, [(size * 0.55, size * 0.55), (s, s)], c, 2)
    elif name == "mail":
        d.rounded_rectangle([m, m + 2, s, s - 2], radius=3, outline=c, width=2)
        _line(d, [(m, m + 4), (size / 2, size * 0.55), (s, m + 4)], c, 2)
    elif name == "docs":
        d.rounded_rectangle([m + 2, m, s - 2, s], radius=3, outline=c, width=2)
        _line(d, [(m + 6, size * 0.35), (s - 6, size * 0.35)], c, 2)
        _line(d, [(m + 6, size * 0.5), (s - 6, size * 0.5)], c, 2)
        _line(d, [(m + 6, size * 0.65), (size * 0.6, size * 0.65)], c, 2)
    elif name == "print":
        d.rectangle([size * 0.3, m, size * 0.7, size * 0.4], outline=c, width=2)
        d.rounded_rectangle([m, size * 0.35, s, size * 0.72], radius=3, outline=c, width=2)
        d.rectangle([size * 0.32, size * 0.62, size * 0.68, s], outline=c, width=2)
    elif name == "jarvis":
        # Geometric J — original, non-Marvel
        _line(d, [(size * 0.55, m), (size * 0.55, size * 0.68)], c, 3)
        d.arc([m + 2, size * 0.38, size * 0.55, s - 2], start=0, end=180, fill=c, width=3)
        d.ellipse([size * 0.48, m + 2, size * 0.62, m + size * 0.14], fill=c)
    elif name == "history":
        d.ellipse([m, m, s, s], outline=c, width=2)
        _line(d, [(size / 2, size / 2), (size / 2, m + 6)], c, 2)
        _line(d, [(size / 2, size / 2), (s - 6, size / 2)], c, 2)
    elif name == "settings":
        cx = cy = size / 2
        r = size * 0.22
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=c, width=2)
        for angle in range(0, 360, 60):
            import math

            rad = math.radians(angle)
            x0 = cx + math.cos(rad) * (r + 2)
            y0 = cy + math.sin(rad) * (r + 2)
            x1 = cx + math.cos(rad) * (size * 0.42)
            y1 = cy + math.sin(rad) * (size * 0.42)
            _line(d, [(x0, y0), (x1, y1)], c, 3)
    elif name == "user":
        d.ellipse([size * 0.32, m, size * 0.68, size * 0.48], outline=c, width=2)
        d.arc([m + 2, size * 0.42, s - 2, s + 4], start=200, end=340, fill=c, width=2)
    elif name == "check":
        _line(d, [(m + 2, size * 0.52), (size * 0.42, s - 4), (s - 2, m + 4)], c, 3)
    elif name == "alert":
        d.polygon(
            [(size / 2, m), (s - 2, s - 2), (m + 2, s - 2)],
            outline=c,
        )
        d.ellipse([size * 0.45, size * 0.42, size * 0.55, size * 0.52], fill=c)
        d.rectangle([size * 0.46, size * 0.58, size * 0.54, size * 0.78], fill=c)
    elif name == "info":
        d.ellipse([m, m, s, s], outline=c, width=2)
        d.ellipse([size * 0.45, size * 0.28, size * 0.55, size * 0.38], fill=c)
        d.rectangle([size * 0.46, size * 0.45, size * 0.54, size * 0.72], fill=c)
    else:
        d.ellipse([m, m, s, s], outline=c, width=2)

    return img


def ctk_icon(
    name: str,
    size: int = 18,
    color: str = MUTED,
) -> ctk.CTkImage:
    img = _draw_icon(name, size * 2, color)  # 2x for crispness
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


def jarvis_mark(size: int = 36, color: str = PRIMARY) -> ctk.CTkImage:
    """Larger geometric J for supervisor card."""
    return ctk_icon("jarvis", size=size, color=color)


def _load_brand_rgba() -> Optional[Image.Image]:
    path = brand_logo_png()
    if not path.is_file():
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def brand_logo_image(height: int = 56) -> Optional[ctk.CTkImage]:
    """Logo ufficiale VIS ridimensionato preservando proporzioni (sidebar ~48–64px)."""
    src = _load_brand_rgba()
    if src is None:
        return None
    h = max(24, int(height))
    w = max(24, int(round(src.width * (h / src.height))))
    # 2x source for crisp CTkImage scaling
    hi = src.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=hi, dark_image=hi, size=(w, h))


def apply_app_icon(window: Any) -> bool:
    """Imposta icona finestra (.ico + PhotoImage). Ritorna True se applicata."""
    ico = brand_logo_ico()
    png = brand_logo_png()
    ok = False
    if ico.is_file():
        try:
            window.iconbitmap(default=str(ico))
            ok = True
        except Exception:
            try:
                window.iconbitmap(str(ico))
                ok = True
            except Exception:
                pass
    if png.is_file():
        try:
            src = Image.open(png).convert("RGBA")
            side = 64
            ratio = min(side / src.width, side / src.height)
            size = (
                max(16, int(src.width * ratio)),
                max(16, int(src.height * ratio)),
            )
            thumb = src.resize(size, Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(thumb)
            _ICON_PHOTO_REFS.append(photo)
            window.wm_iconphoto(True, photo)
            ok = True
        except Exception:
            pass
    return ok
