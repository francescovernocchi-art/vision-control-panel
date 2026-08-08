"""Avatar JARVIS animato — solo presentazione UI (Pillow + after()).

Non tocca la logica del supervisore. Gli stati arrivano da set_state()
chiamato dal refresh UI esistente (_refresh_jarvis_status_ui).

Sostituire le immagini: mettere PNG in assets/jarvis/<cartella>/ come
frame_000.png, frame_001.png, … (ordinati alfabeticamente). Se la cartella
è vuota o manca, si usa jarvis_avatar_base.png + overlay procedurali.
"""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFont

import customtkinter as ctk

from ui.theme import (
    BG,
    CARD,
    ERROR,
    MUTED,
    PRIMARY,
    SUCCESS,
    TEXT,
    WARNING,
    font_family,
)
from utils.paths import brand_logo_png, resource_path

logger = logging.getLogger("ui.jarvis_avatar")

# --- Livelli animazione (persistiti come jarvis_avatar_level) -----------------
LEVEL_FULL = "full"  # Complete
LEVEL_REDUCED = "reduced"  # Ridotte
LEVEL_OFF = "off"  # Disattivate

LEVEL_LABELS = {
    LEVEL_FULL: "Complete",
    LEVEL_REDUCED: "Ridotte",
    LEVEL_OFF: "Disattivate",
}

# Stati visuali API
VIS_IDLE = "IDLE"
VIS_MAIL = "MAIL_RILEVATA"
VIS_ANALISI = "ANALISI"
VIS_ACCESSO = "ACCESSO_ENISPACE"
VIS_DOWNLOAD = "DOWNLOAD"
VIS_STAMPA = "STAMPA"
VIS_DONE = "COMPLETATO"
VIS_ERROR = "ERRORE"
VIS_INTERVENTO = "INTERVENTO_RICHIESTO"

# Cartelle asset (drop-in PNG sequences)
ASSET_FOLDERS = {
    VIS_IDLE: "jarvis_idle",
    VIS_MAIL: "jarvis_mail",
    VIS_ANALISI: "jarvis_analisi",
    VIS_ACCESSO: "jarvis_accesso",
    VIS_DOWNLOAD: "jarvis_download",
    VIS_STAMPA: "jarvis_stampa",
    VIS_DONE: "jarvis_completato",
    VIS_ERROR: "jarvis_errore",
    VIS_INTERVENTO: "jarvis_intervento",
}

# Mapping JarvisState (valori enum / stringhe UI) → stato avatar
_STATE_MAP: dict[str, str] = {
    "OFFLINE": VIS_IDLE,
    "IN ATTESA": VIS_IDLE,
    "CONTROLLO MAIL": VIS_IDLE,
    "NUOVA MAIL RILEVATA": VIS_MAIL,
    "ANALISI MAIL": VIS_ANALISI,
    "CONTRATTO RICONOSCIUTO": VIS_ANALISI,
    "ACCESSO ENISPACE": VIS_ACCESSO,
    "RICERCA DOCUMENTI": VIS_ACCESSO,
    "DOWNLOAD": VIS_DOWNLOAD,
    "PREPARAZIONE STAMPA": VIS_STAMPA,
    "STAMPA": VIS_STAMPA,
    "VERIFICA": VIS_STAMPA,
    "COMPLETATO": VIS_DONE,
    "INTERVENTO RICHIESTO": VIS_INTERVENTO,
    "ERRORE": VIS_ERROR,
    # Alias API / chiavi snakecase
    VIS_IDLE: VIS_IDLE,
    VIS_MAIL: VIS_MAIL,
    VIS_ANALISI: VIS_ANALISI,
    VIS_ACCESSO: VIS_ACCESSO,
    VIS_DOWNLOAD: VIS_DOWNLOAD,
    VIS_STAMPA: VIS_STAMPA,
    VIS_DONE: VIS_DONE,
    VIS_ERROR: VIS_ERROR,
    VIS_INTERVENTO: VIS_INTERVENTO,
}

_ACCENT = {
    VIS_IDLE: (0, 118, 192),
    VIS_MAIL: (56, 189, 248),
    VIS_ANALISI: (21, 133, 216),
    VIS_ACCESSO: (56, 189, 248),
    VIS_DOWNLOAD: (0, 150, 220),
    VIS_STAMPA: (200, 220, 240),
    VIS_DONE: (34, 197, 94),
    VIS_ERROR: (239, 68, 68),
    VIS_INTERVENTO: (245, 158, 11),
}


def map_jarvis_state(raw: str | None) -> str:
    """Converte stringa JarvisState / API in stato visuale avatar."""
    key = (raw or "").strip().upper()
    if key in _STATE_MAP:
        return _STATE_MAP[key]
    # Heuristic fallback
    if "ERRORE" in key or "ERROR" in key:
        return VIS_ERROR
    if "INTERVENTO" in key or "ATTENTION" in key:
        return VIS_INTERVENTO
    if "COMPLET" in key or "SUCCESS" in key:
        return VIS_DONE
    if "STAMP" in key or "PRINT" in key or "VERIFICA" in key:
        return VIS_STAMPA
    if "DOWNLOAD" in key:
        return VIS_DOWNLOAD
    if "ENISPACE" in key or "RICERCA" in key:
        return VIS_ACCESSO
    if "ANALISI" in key or "CONTRATTO" in key:
        return VIS_ANALISI
    if "MAIL" in key and ("NUOVA" in key or "RILEVAT" in key):
        return VIS_MAIL
    return VIS_IDLE


def jarvis_assets_dir() -> Path:
    return resource_path("assets", "jarvis")


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


class JarvisAvatar(ctk.CTkFrame):
    """Widget avatar con animazione non bloccante via after()."""

    def __init__(
        self,
        master,
        *,
        size: int = 320,
        level: str = LEVEL_FULL,
        level_provider: Optional[Callable[[], str]] = None,
        show_badge: bool = True,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", CARD)
        kwargs.setdefault("corner_radius", 12)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", PRIMARY)
        super().__init__(master, **kwargs)

        self._display_size = max(160, min(420, int(size)))
        self._level = self._normalize_level(level)
        self._level_provider = level_provider
        self._show_badge = show_badge

        self._visual = VIS_IDLE
        self._target_visual = VIS_IDLE
        self._raw_state = "OFFLINE"
        self._frame_i = 0
        self._t0 = time.perf_counter()
        self._crossfade = 0.0  # 0..1 during transition
        self._cross_from: Optional[Image.Image] = None
        self._cross_to: Optional[Image.Image] = None
        self._cross_start = 0.0
        self._cross_ms = 220
        self._mail_until = 0.0
        self._done_until = 0.0
        self._prev_before_pulse = VIS_IDLE
        self._anim_job: Optional[str] = None
        self._destroyed = False
        self._static_mode = False
        self._warned_missing = False

        self._sequences: dict[str, list[Image.Image]] = {}
        self._base: Optional[Image.Image] = None
        self._logo_chest: Optional[Image.Image] = None
        self._ctk_image: Optional[ctk.CTkImage] = None
        self._photo_ref = None

        title = ctk.CTkLabel(
            self,
            text="JARVIS",
            font=ctk.CTkFont(family=font_family(), size=13, weight="bold"),
            text_color=PRIMARY,
        )
        title.pack(pady=(10, 2))

        self._canvas_label = ctk.CTkLabel(self, text="", fg_color=BG)
        self._canvas_label.pack(padx=12, pady=4)

        self._badge = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=WARNING,
            fg_color="transparent",
            height=18,
        )
        if show_badge:
            self._badge.pack(pady=(0, 4))

        self._caption = ctk.CTkLabel(
            self,
            text="IDLE",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
        )
        self._caption.pack(pady=(0, 10))

        try:
            self._load_assets()
            self._render_frame(force=True)
            self._schedule()
        except Exception as exc:
            logger.warning("Avatar JARVIS: init fallita, placeholder statico: %s", exc)
            self._enter_static_fallback()

    # ------------------------------------------------------------------ public
    def set_state(self, state: str) -> None:
        """Aggiorna stato visuale da stringa JarvisState / API (solo UI thread)."""
        if self._destroyed:
            return
        try:
            self._refresh_level()
            raw = (state or "").strip()
            self._raw_state = raw or "OFFLINE"
            visual = map_jarvis_state(raw)

            now = time.perf_counter()
            # Pulse mail: 1–2s poi torna
            if visual == VIS_MAIL and self._visual != VIS_MAIL:
                self._prev_before_pulse = (
                    self._visual if self._visual != VIS_MAIL else VIS_IDLE
                )
                self._mail_until = now + 1.6
            # Completato: verde 1–2s poi IDLE (se supervisore resta su COMPLETATO)
            if visual == VIS_DONE and self._visual != VIS_DONE:
                self._done_until = now + 1.8

            if self._level == LEVEL_OFF:
                self._begin_transition(VIS_IDLE if visual != VIS_ERROR else VIS_ERROR)
                self._caption.configure(text=self._raw_state or VIS_IDLE)
                self._update_badge(visual)
                self._render_frame(force=True)
                return

            self._begin_transition(visual)
            self._caption.configure(text=self._raw_state or visual)
            self._update_badge(visual)
            if not self._anim_job and not self._static_mode:
                self._schedule()
        except Exception as exc:
            logger.warning("Avatar set_state fallito: %s", exc)

    def set_level(self, level: str) -> None:
        self._level = self._normalize_level(level)
        if self._level == LEVEL_OFF:
            self._stop_anim()
            self._render_frame(force=True)
        elif not self._anim_job and not self._static_mode:
            self._schedule()

    def destroy(self) -> None:  # noqa: A003
        self._destroyed = True
        self._stop_anim()
        super().destroy()

    # ------------------------------------------------------------------ assets
    def _load_assets(self) -> None:
        root = jarvis_assets_dir()
        base_path = root / "jarvis_avatar_base.png"
        if base_path.is_file():
            self._base = Image.open(base_path).convert("RGBA")
        else:
            self._base = self._procedural_base()
            try:
                root.mkdir(parents=True, exist_ok=True)
                self._base.save(base_path)
            except Exception:
                pass
            if not self._warned_missing:
                logger.warning(
                    "Avatar JARVIS: base mancante, generato placeholder in %s",
                    base_path,
                )
                self._warned_missing = True

        # Logo petto (composizione runtime se non già nel frame)
        lp = brand_logo_png()
        if lp.is_file():
            try:
                self._logo_chest = Image.open(lp).convert("RGBA")
            except Exception:
                self._logo_chest = None

        for vis, folder in ASSET_FOLDERS.items():
            frames = self._load_sequence(root / folder)
            if not frames and self._base is not None:
                frames = [self._base.copy()]
            self._sequences[vis] = frames

    def _load_sequence(self, folder: Path) -> list[Image.Image]:
        if not folder.is_dir():
            return []
        files = sorted(
            p
            for p in folder.iterdir()
            if p.suffix.lower() in (".png", ".webp", ".jpg", ".jpeg") and p.is_file()
        )
        out: list[Image.Image] = []
        for p in files:
            try:
                out.append(Image.open(p).convert("RGBA"))
            except Exception as exc:
                logger.warning("Avatar: frame non leggibile %s: %s", p.name, exc)
        return out

    def _procedural_base(self) -> Image.Image:
        """Helmet stilizzato originale (fallback senza asset)."""
        s = 512
        img = Image.new("RGBA", (s, s), (11, 18, 32, 255))
        d = ImageDraw.Draw(img)
        # Helmet silhouette
        d.ellipse([90, 40, 422, 380], fill=(180, 190, 205, 255), outline=(0, 118, 192, 255), width=3)
        d.rounded_rectangle([140, 300, 372, 470], radius=40, fill=(120, 130, 145, 255))
        # Visor
        d.rounded_rectangle([150, 160, 362, 220], radius=18, fill=(0, 40, 80, 255))
        d.rounded_rectangle([158, 168, 354, 212], radius=14, fill=(0, 180, 255, 220))
        # Crest
        d.polygon([(256, 50), (270, 160), (242, 160)], fill=(90, 100, 115, 255))
        # Chest plate
        d.rounded_rectangle([170, 380, 342, 500], radius=20, fill=(200, 208, 220, 255))
        d.ellipse([226, 410, 286, 470], outline=(0, 118, 192, 255), width=3)
        return img

    # ------------------------------------------------------------------ anim
    def _refresh_level(self) -> None:
        if self._level_provider:
            try:
                self._level = self._normalize_level(self._level_provider())
            except Exception:
                pass

    @staticmethod
    def _normalize_level(level: str | None) -> str:
        v = (level or LEVEL_FULL).strip().lower()
        if v in ("complete", "full", "completi", "completo"):
            return LEVEL_FULL
        if v in ("reduced", "ridotte", "ridotta", "low"):
            return LEVEL_REDUCED
        if v in ("off", "disattivate", "disabled", "none", "0"):
            return LEVEL_OFF
        if v in (LEVEL_FULL, LEVEL_REDUCED, LEVEL_OFF):
            return v
        return LEVEL_FULL

    def _begin_transition(self, visual: str) -> None:
        if visual == self._target_visual and self._crossfade <= 0:
            self._visual = visual
            return
        if visual == self._visual and self._crossfade <= 0:
            self._target_visual = visual
            return
        try:
            self._cross_from = self._compose_still(self._visual, self._frame_i, 0.0)
            self._cross_to = self._compose_still(visual, 0, 0.0)
            self._cross_start = time.perf_counter()
            self._crossfade = 0.01
            self._target_visual = visual
            self._frame_i = 0
        except Exception:
            self._visual = visual
            self._target_visual = visual
            self._crossfade = 0.0

    def _fps_interval_ms(self) -> int:
        if self._level == LEVEL_OFF:
            return 1000
        if self._level == LEVEL_REDUCED:
            return 80  # ~12 fps
        # Full: 20–30 fps
        busy = self._effective_visual() in (
            VIS_ANALISI,
            VIS_ACCESSO,
            VIS_DOWNLOAD,
            VIS_STAMPA,
            VIS_MAIL,
        )
        return 40 if busy else 50  # 25 / 20 fps

    def _effective_visual(self) -> str:
        now = time.perf_counter()
        if self._mail_until and now < self._mail_until:
            return VIS_MAIL
        if self._mail_until and now >= self._mail_until and self._target_visual == VIS_MAIL:
            # Torna allo stato precedente / idle se ancora "mail" solo da pulse
            return self._prev_before_pulse or VIS_IDLE
        if self._done_until and now >= self._done_until and self._target_visual == VIS_DONE:
            return VIS_IDLE
        if self._crossfade > 0:
            return self._target_visual
        return self._visual

    def _schedule(self) -> None:
        if self._destroyed or self._static_mode:
            return
        self._stop_anim()
        if self._level == LEVEL_OFF:
            return
        ms = self._fps_interval_ms()
        self._anim_job = self.after(ms, self._tick)

    def _stop_anim(self) -> None:
        if self._anim_job:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None

    def _tick(self) -> None:
        self._anim_job = None
        if self._destroyed:
            return
        try:
            self._refresh_level()
            if self._level == LEVEL_OFF:
                self._render_frame(force=True)
                return
            now = time.perf_counter()
            # Auto-end mail / completato pulses verso idle se supervisore non ha cambiato
            if self._mail_until and now >= self._mail_until:
                self._mail_until = 0.0
                if map_jarvis_state(self._raw_state) == VIS_MAIL:
                    # Mail state ancora attivo lato supervisore: resta MAIL soft
                    pass
                elif self._target_visual == VIS_MAIL:
                    self._begin_transition(self._prev_before_pulse or VIS_IDLE)
            if self._done_until and now >= self._done_until:
                self._done_until = 0.0
                if map_jarvis_state(self._raw_state) == VIS_DONE:
                    self._begin_transition(VIS_IDLE)

            if self._crossfade > 0:
                elapsed = (now - self._cross_start) * 1000.0
                t = min(1.0, elapsed / max(150.0, float(self._cross_ms)))
                self._crossfade = t
                if t >= 1.0:
                    self._visual = self._target_visual
                    self._crossfade = 0.0
                    self._cross_from = None
                    self._cross_to = None

            self._frame_i += 1
            self._render_frame()
        except Exception as exc:
            logger.warning("Avatar tick fallito, statico: %s", exc)
            self._enter_static_fallback()
            return
        self._schedule()

    def _enter_static_fallback(self) -> None:
        self._static_mode = True
        self._stop_anim()
        try:
            img = self._base or self._procedural_base()
            self._show_pil(img)
            self._caption.configure(text="AVATAR STATIC")
        except Exception:
            self._canvas_label.configure(
                text="J",
                font=ctk.CTkFont(size=48, weight="bold"),
                text_color=PRIMARY,
                width=self._display_size,
                height=self._display_size,
            )

    # ------------------------------------------------------------------ render
    def _render_frame(self, force: bool = False) -> None:
        if self._destroyed:
            return
        try:
            t = time.perf_counter() - self._t0
            if self._crossfade > 0 and self._cross_from and self._cross_to:
                a = self._cross_from
                b = self._compose_still(self._target_visual, self._frame_i, t)
                img = Image.blend(a.convert("RGBA"), b.convert("RGBA"), self._crossfade)
            else:
                vis = self._effective_visual()
                if self._crossfade <= 0:
                    self._visual = vis if vis != VIS_IDLE or self._target_visual == VIS_IDLE else self._visual
                    # Keep visual in sync when not transitioning
                    if self._mail_until <= 0 and self._done_until <= 0:
                        self._visual = self._target_visual
                img = self._compose_still(self._visual, self._frame_i, t)

            if self._level == LEVEL_OFF and not force:
                # Single static with minimal HUD
                img = self._compose_still(VIS_IDLE, 0, 0.0, hud=False)

            self._show_pil(img)
        except Exception as exc:
            logger.warning("Avatar render fallito: %s", exc)
            self._enter_static_fallback()

    def _compose_still(
        self,
        visual: str,
        frame_i: int,
        t: float,
        *,
        hud: bool = True,
    ) -> Image.Image:
        seq = self._sequences.get(visual) or self._sequences.get(VIS_IDLE) or []
        if seq:
            base = seq[frame_i % len(seq)].copy()
        elif self._base is not None:
            base = self._base.copy()
        else:
            base = self._procedural_base()

        # Ensure working size
        if base.size != (512, 512):
            base = base.resize((512, 512), Image.Resampling.LANCZOS)

        if self._level == LEVEL_OFF:
            hud = False

        reduced = self._level == LEVEL_REDUCED
        accent = _ACCENT.get(visual, _ACCENT[VIS_IDLE])

        # Subtle breathe (idle) / motion
        if hud and not reduced:
            breathe = 1.0 + 0.012 * math.sin(t * 1.4)
            if visual == VIS_IDLE:
                w = int(512 * breathe)
                scaled = base.resize((w, w), Image.Resampling.BILINEAR)
                canvas = Image.new("RGBA", (512, 512), (11, 18, 32, 255))
                off = (512 - w) // 2
                canvas.alpha_composite(scaled, (off, off))
                base = canvas
            elif visual == VIS_MAIL:
                # Nod impulse
                nod = int(6 * math.sin(min(math.pi, t * 4)))
                canvas = Image.new("RGBA", (512, 512), (11, 18, 32, 255))
                canvas.alpha_composite(base, (0, nod))
                base = canvas
            elif visual == VIS_ANALISI:
                # Gaze micro-shift
                dx = int(3 * math.sin(t * 2.2))
                dy = int(2 * math.cos(t * 1.7))
                canvas = Image.new("RGBA", (512, 512), (11, 18, 32, 255))
                canvas.alpha_composite(base, (dx, dy))
                base = canvas

        if self._logo_chest is not None and visual:
            base = self._overlay_chest_logo(base)

        if hud:
            base = self._draw_hud(base, visual, t, accent, reduced=reduced)

        # Eye pulse / accent tint
        if hud:
            base = self._eye_glow(base, visual, t, accent, reduced=reduced)

        return base

    def _overlay_chest_logo(self, img: Image.Image) -> Image.Image:
        if self._logo_chest is None:
            return img
        # Skip if frame already has composed logo area — still light overlay OK
        out = img.copy()
        lw = int(512 * 0.12)
        ratio = lw / max(1, self._logo_chest.width)
        lh = max(8, int(self._logo_chest.height * ratio))
        lg = self._logo_chest.resize((lw, lh), Image.Resampling.LANCZOS)
        bx = (512 - lw) // 2
        by = int(512 * 0.64)
        out.alpha_composite(lg, (bx, by))
        return out

    def _eye_glow(
        self,
        img: Image.Image,
        visual: str,
        t: float,
        accent: tuple[int, int, int],
        *,
        reduced: bool,
    ) -> Image.Image:
        out = img.copy()
        d = ImageDraw.Draw(out, "RGBA")
        pulse = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * (2.0 if visual == VIS_IDLE else 4.0)))
        if reduced:
            pulse = 0.55
        alpha = int(40 + 90 * pulse)
        if visual == VIS_MAIL:
            alpha = min(255, alpha + 60)
        if visual == VIS_ERROR:
            accent = (239, 68, 68)
            alpha = 140
        if visual == VIS_INTERVENTO:
            accent = (245, 158, 11)
        if visual == VIS_DONE:
            accent = (34, 197, 94)
        # Visor band approx
        y0, y1 = 168, 212
        d.rectangle([158, y0, 354, y1], fill=(*accent, alpha // 3))
        return out

    def _draw_hud(
        self,
        img: Image.Image,
        visual: str,
        t: float,
        accent: tuple[int, int, int],
        *,
        reduced: bool,
    ) -> Image.Image:
        out = img.copy()
        d = ImageDraw.Draw(out, "RGBA")
        cx, cy = 256, 256
        a = (*accent, 160 if not reduced else 90)

        # Outer rings
        speed = {
            VIS_IDLE: 0.4,
            VIS_MAIL: 1.2,
            VIS_ANALISI: 1.6,
            VIS_ACCESSO: 2.2,
            VIS_DOWNLOAD: 1.8,
            VIS_STAMPA: 1.0,
            VIS_DONE: 0.6,
            VIS_ERROR: 0.3,
            VIS_INTERVENTO: 0.2,
        }.get(visual, 0.5)
        if reduced:
            speed *= 0.4

        for i, radius in enumerate((210, 230, 248)):
            ang = (t * speed * 60 + i * 40) % 360
            bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
            d.arc(bbox, start=ang, end=ang + 70, fill=a, width=2)
            d.arc(bbox, start=ang + 180, end=ang + 230, fill=(*accent, 80), width=1)

        # Radar sweep (accesso / analisi)
        if visual in (VIS_ACCESSO, VIS_ANALISI, VIS_DOWNLOAD) and not reduced:
            sweep = (t * speed * 90) % 360
            rad = math.radians(sweep)
            x1 = cx + math.cos(rad) * 240
            y1 = cy + math.sin(rad) * 240
            d.line([(cx, cy), (x1, y1)], fill=(*accent, 100), width=2)
            # Scan lines
            for k in range(3):
                yy = int(80 + (t * 40 + k * 90) % 340)
                d.line([(80, yy), (432, yy)], fill=(*accent, 35), width=1)

        # Download data ticks
        if visual == VIS_DOWNLOAD:
            for i in range(8):
                phase = (t * 3 + i * 0.4) % 1.0
                y = int(120 + phase * 280)
                x = 60 + (i % 4) * 20
                d.rectangle([x, y, x + 10, y + 4], fill=(*accent, int(180 * (1 - phase))))

        # Print cue
        if visual == VIS_STAMPA:
            y = int(400 + 8 * math.sin(t * 5))
            d.rectangle([180, y, 332, y + 6], fill=(220, 230, 240, 160))
            d.rectangle([190, 390, 322, 420], outline=(*accent, 140), width=2)

        # Completato ring
        if visual == VIS_DONE:
            d.ellipse([200, 200, 312, 312], outline=(34, 197, 94, 200), width=3)

        # Error corners
        if visual == VIS_ERROR:
            c = (239, 68, 68, 200)
            for pts in (
                [(40, 40), (90, 40), (40, 90)],
                [(472, 40), (422, 40), (472, 90)],
                [(40, 472), (90, 472), (40, 422)],
                [(472, 472), (422, 472), (472, 422)],
            ):
                d.line(pts, fill=c, width=3)

        # Intervento badge text
        if visual == VIS_INTERVENTO:
            d.rounded_rectangle([150, 20, 362, 52], radius=6, fill=(245, 158, 11, 210))
            try:
                font = ImageFont.truetype("segoeui.ttf", 18)
            except Exception:
                font = ImageFont.load_default()
            d.text((178, 26), "INTERVENTO", fill=(15, 20, 30, 255), font=font)

        return out

    def _show_pil(self, img: Image.Image) -> None:
        s = self._display_size
        hi = img.resize((s * 2, s * 2), Image.Resampling.LANCZOS)
        cimg = ctk.CTkImage(light_image=hi, dark_image=hi, size=(s, s))
        self._ctk_image = cimg
        self._canvas_label.configure(image=cimg, text="")

    def _update_badge(self, visual: str) -> None:
        if not self._show_badge:
            return
        if visual == VIS_INTERVENTO:
            self._badge.configure(text="INTERVENTO", text_color=WARNING)
        elif visual == VIS_ERROR:
            self._badge.configure(text="ERRORE", text_color=ERROR)
        elif visual == VIS_DONE:
            self._badge.configure(text="COMPLETATO", text_color=SUCCESS)
        else:
            self._badge.configure(text="")


class JarvisAvatarPanel(ctk.CTkFrame):
    """Avatar + blocco stato supervisore (valori reali da snapshot)."""

    def __init__(
        self,
        master,
        *,
        size: int = 300,
        level: str = LEVEL_FULL,
        level_provider: Optional[Callable[[], str]] = None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)

        self.avatar = JarvisAvatar(
            self,
            size=size,
            level=level,
            level_provider=level_provider,
        )
        self.avatar.pack(fill="x", pady=(0, 8))

        status = ctk.CTkFrame(
            self,
            fg_color=CARD,
            corner_radius=10,
            border_width=1,
            border_color=PRIMARY,
        )
        status.pack(fill="x")
        ctk.CTkLabel(
            status,
            text="JARVIS SUPERVISOR",
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
            text_color=PRIMARY,
        ).pack(anchor="w", padx=12, pady=(10, 2))
        self.online_label = ctk.CTkLabel(
            status,
            text="○ OFFLINE",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=MUTED,
            anchor="w",
        )
        self.online_label.pack(fill="x", padx=12, pady=2)
        self.state_label = ctk.CTkLabel(
            status,
            text="Stato: OFFLINE",
            font=ctk.CTkFont(size=12),
            text_color=TEXT,
            anchor="w",
        )
        self.state_label.pack(fill="x", padx=12, pady=2)
        self.meta_label = ctk.CTkLabel(
            status,
            text="Ultimo controllo: —\nIn coda: 0\nIn lavorazione: —",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            anchor="w",
            justify="left",
        )
        self.meta_label.pack(fill="x", padx=12, pady=(2, 12))

    def set_state(self, state: str) -> None:
        self.avatar.set_state(state)

    def set_level(self, level: str) -> None:
        self.avatar.set_level(level)

    def update_from_snapshot(self, snap: dict) -> None:
        """Aggiorna avatar + etichette da jarvis.snapshot() (dati reali)."""
        active = bool(snap.get("active"))
        state = str(snap.get("state") or "OFFLINE")
        self.set_state(state)
        if active:
            self.online_label.configure(text="● ONLINE", text_color=SUCCESS)
        else:
            self.online_label.configure(text="○ OFFLINE", text_color=MUTED)
        self.state_label.configure(text=f"Stato: {state}")
        self.meta_label.configure(
            text=(
                f"Ultimo controllo: {snap.get('last_check', '—')}\n"
                f"Ultima lavorazione: {snap.get('last_job', '—')}\n"
                f"In coda: {snap.get('pending', 0)}\n"
                f"In lavorazione: {snap.get('current_job', '—')}"
            )
        )
