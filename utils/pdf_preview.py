"""Anteprima prima pagina PDF (PyMuPDF + Pillow) per la UI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from utils.logger import get_logger

logger = get_logger("pdf_preview")


def render_pdf_thumbnail(
    path: Path | str,
    *,
    max_width: int = 140,
    max_height: int = 160,
) -> Optional[Tuple[object, tuple[int, int]]]:
    """Rende la prima pagina come immagine PIL.

    Returns:
        (PIL.Image.Image, (w, h)) oppure None se dipendenza/file assenti.
    """
    pdf = Path(path)
    if not pdf.is_file():
        return None
    try:
        import fitz  # PyMuPDF
        from PIL import Image
    except ImportError:
        logger.debug("PyMuPDF/Pillow non disponibili: skip thumbnail PDF.")
        return None

    try:
        doc = fitz.open(str(pdf))
        try:
            if doc.page_count < 1:
                return None
            page = doc.load_page(0)
            # Scala per rientrare nel box anteprima
            rect = page.rect
            if rect.width <= 0 or rect.height <= 0:
                return None
            zoom = min(max_width / rect.width, max_height / rect.height, 1.5)
            zoom = max(0.2, zoom)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            return img, (img.width, img.height)
        finally:
            doc.close()
    except Exception as exc:
        logger.debug("Thumbnail PDF fallita (%s): %s", pdf.name, exc)
        return None
