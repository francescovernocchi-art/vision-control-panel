"""Caricamento brand SVG (sfondo trasparente) → CTkImage via PyMuPDF/Pillow."""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

import customtkinter as ctk


def render_svg_rgba(path: Path, *, dpi: int = 192) -> Optional[Image.Image]:
    """Rasterizza SVG in RGBA (alpha preservato)."""
    if not path.is_file():
        return None
    try:
        import pymupdf
    except Exception:
        return None
    try:
        data = path.read_bytes()
        doc = pymupdf.open(stream=data, filetype="svg")
        try:
            page = doc[0]
            pix = page.get_pixmap(alpha=True, dpi=max(72, int(dpi)))
            mode = "RGBA" if pix.n >= 4 else "RGB"
            img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            return img
        finally:
            doc.close()
    except Exception:
        try:
            # fallback path-based open
            doc = pymupdf.open(path)
            try:
                page = doc[0]
                pix = page.get_pixmap(alpha=True, dpi=max(72, int(dpi)))
                mode = "RGBA" if pix.n >= 4 else "RGB"
                img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                return img
            finally:
                doc.close()
        except Exception:
            return None


@lru_cache(maxsize=32)
def _cached_svg_rgba(path_str: str, dpi: int) -> Optional[Image.Image]:
    img = render_svg_rgba(Path(path_str), dpi=dpi)
    if img is None:
        return None
    # cache copy — callers may resize
    return img.copy()


def load_brand_rgba(
    *,
    svg: Optional[Path] = None,
    png_fallback: Optional[Path] = None,
    dpi: int = 192,
) -> Optional[Image.Image]:
    if svg is not None and svg.is_file():
        img = _cached_svg_rgba(str(svg.resolve()), int(dpi))
        if img is not None:
            return img.copy()
    if png_fallback is not None and png_fallback.is_file():
        try:
            return Image.open(png_fallback).convert("RGBA")
        except Exception:
            return None
    return None


def ctk_image_from_rgba(
    src: Image.Image,
    *,
    height: int,
    max_width: Optional[int] = None,
) -> ctk.CTkImage:
    h = max(16, int(height))
    w = max(16, int(round(src.width * (h / max(1, src.height)))))
    if max_width is not None and w > max_width:
        w = int(max_width)
        h = max(16, int(round(src.height * (w / max(1, src.width)))))
    hi = src.resize((max(1, w * 2), max(1, h * 2)), Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=hi, dark_image=hi, size=(w, h))
