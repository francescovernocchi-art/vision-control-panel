"""Avatar renderers — Pseudo3D (single plate + perspective); GLB stub later.

IMPORTANT: do NOT use vision_pose_*.png — those are character-bible sheets
(multi-panel labels), not turntable frames. They cause ghosting/overlap.
"""

from __future__ import annotations

import logging
import math
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from utils.paths import (
    vision_avatar_bible_dir,
    vision_avatar_glb_frames_dir,
    vision_avatar_model_glb,
    vision_avatar_profile_png,
    vision_istituto_logo_backdrop_png,
)
from utils.avatar_models import (
    avatar_model_frames_dir,
    normalize_avatar_model_id,
    resolve_avatar_preview_png,
    uses_shared_meshy_frames,
)

logger = logging.getLogger("ui.avatar_renderer")

STATE_IDLE = "IDLE"
STATE_LISTENING = "LISTENING"
STATE_PROCESSING = "PROCESSING"
STATE_SPEAKING = "SPEAKING"
STATE_ALERT = "ALERT"
STATE_OFFLINE = "OFFLINE"

LEVEL_FULL = "full"
LEVEL_REDUCED = "reduced"
LEVEL_OFF = "off"

_STATE_FILES = {
    STATE_IDLE: "vision_state_idle.png",
    STATE_LISTENING: "vision_state_listening.png",
    STATE_PROCESSING: "vision_state_processing.png",
    STATE_SPEAKING: "vision_state_speaking.png",
    STATE_ALERT: "vision_state_alert.png",
    STATE_OFFLINE: "vision_state_offline.png",
}

Point = Tuple[float, float]

# Flat void used by older stage fills — knocked out so logo peeks behind
_VOID_RGB = (13, 17, 23)
_istituto_logo_cache: Optional[Image.Image] = None
_istituto_layer_cache: dict[tuple, object] = {}


def normalize_square(img: Image.Image, side: int = 512) -> Image.Image:
    # Transparent stage so Istituto logo backdrop can sit behind the bust
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ratio = min(side / img.width, side / img.height) * 0.98
    nw = max(1, int(img.width * ratio))
    nh = max(1, int(img.height * ratio))
    scaled = img.resize((nw, nh), Image.Resampling.LANCZOS)
    ox, oy = (side - nw) // 2, (side - nh) // 2
    canvas.alpha_composite(scaled, (ox, oy))
    return canvas


def fit_opaque_to_square(
    img: Image.Image,
    side: int = 512,
    *,
    target_fill: float = 0.90,
    alpha_threshold: int = 12,
) -> Image.Image:
    """Crop letterboxing and scale opaque subject toward Meshy-like frame fill.

    Used for still-model previews that often arrive with large empty margins.
    Does not clip the subject: scales so the larger bbox side hits ``target_fill``.
    """
    rgba = img.convert("RGBA")
    alpha = rgba.split()[-1]
    bbox = alpha.point(lambda v: 255 if v > alpha_threshold else 0).getbbox()
    if not bbox:
        return normalize_square(rgba, side)

    cropped = rgba.crop(bbox)
    bw, bh = cropped.size
    target = max(8, min(side, int(side * float(target_fill))))
    ratio = target / max(bw, bh)
    nw = max(1, int(bw * ratio))
    nh = max(1, int(bh * ratio))
    # Guard: never exceed canvas
    if nw > side or nh > side:
        shrink = min(side / nw, side / nh)
        nw = max(1, int(nw * shrink))
        nh = max(1, int(nh * shrink))
    scaled = cropped.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ox, oy = (side - nw) // 2, (side - nh) // 2
    canvas.alpha_composite(scaled, (ox, oy))
    return canvas


# Still-plate models (no Meshy clip pack) — fill + composite scale overrides.
# Meshy glb_frames already fill ~0.82–0.88 of the plate; still previews were ~0.55–0.79.
_STILL_PLATE_FILL: dict[str, float] = {
    "vision_avatar_cyborg_source": 0.94,
    "vision_futuristic": 0.94,
    "vision_avatar_rigged_v1": 0.92,
}
_STILL_SUBJECT_SCALE: dict[str, float] = {
    "vision_avatar_cyborg_source": 1.06,
    "vision_futuristic": 1.06,
    "vision_avatar_rigged_v1": 1.04,
}
_STILL_DEFAULT_FILL = 0.90
_STILL_DEFAULT_SUBJECT_SCALE = 1.02


def placeholder(side: int = 512) -> Image.Image:
    img = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([140, 80, 370, 340], fill=(230, 232, 235, 255))
    d.ellipse([200, 160, 240, 200], fill=(0, 182, 255, 255))
    d.ellipse([270, 160, 310, 200], fill=(0, 182, 255, 255))
    d.ellipse([210, 360, 300, 450], outline=(0, 182, 255, 255), width=4)
    return img


def _eye_glow_score(img: Image.Image) -> float:
    """Fraction of bright cyan/blue pixels in the upper-face band (lower ⇒ closed lids)."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    # Bust plates: eyes sit roughly in the upper-middle third
    y0, y1 = int(h * 0.28), int(h * 0.42)
    x0, x1 = int(w * 0.30), int(w * 0.70)
    if y1 <= y0 or x1 <= x0:
        return 1.0
    try:
        import numpy as np

        arr = np.asarray(rgba)
        roi = arr[y0:y1, x0:x1, :3].astype("int16")
        cyan = (
            (roi[..., 2] > 140)
            & (roi[..., 1] > 90)
            & (roi[..., 2] > roi[..., 0] + 20)
        )
        return float(cyan.mean())
    except Exception:
        # Pillow fallback: sample a coarse grid
        px = rgba.load()
        hits = total = 0
        step = max(1, (x1 - x0) // 32)
        for y in range(y0, y1, step):
            for x in range(x0, x1, step):
                r, g, b, a = px[x, y]
                total += 1
                if a > 8 and b > 140 and g > 90 and b > r + 20:
                    hits += 1
        return hits / max(1, total)


def _pick_closed_eye_frame(frames: Sequence[Image.Image]) -> Optional[Image.Image]:
    """Return the idle-clip frame with the clearest blink-closed eyes, if any."""
    if not frames:
        return None
    scores = [_eye_glow_score(fr) for fr in frames]
    best_i = min(range(len(scores)), key=lambda i: scores[i])
    best = scores[best_i]
    # Robust against packs with no blink: require a clear dip vs median
    ordered = sorted(scores)
    median = ordered[len(ordered) // 2]
    if median <= 1e-6:
        return frames[best_i].copy()
    if best <= median * 0.55 or (median - best) >= 0.008:
        return frames[best_i].copy()
    return None


def _suppress_closed_lid_cyan(
    img: Image.Image,
    *,
    strength: float = 0.92,
) -> Image.Image:
    """Neutralize baked cyan emissive that bleeds through closed eyelids.

    Runtime overlay fix for sprite packs: blink/offline frames often keep
    eye-glow under the lids. Desaturates cyan only inside periocular ellipses
    — does not invent new lids or touch neck/armor LEDs.
    """
    rgba = img.convert("RGBA")
    w, h = rgba.size
    y0, y1 = int(h * 0.26), int(h * 0.42)
    if y1 <= y0:
        return rgba
    try:
        import numpy as np

        arr = np.asarray(rgba).astype(np.float32).copy()
        yy, xx = np.ogrid[:h, :w]
        mask = np.zeros((h, w), dtype=bool)
        for x_a, x_b in (
            (int(w * 0.32), int(w * 0.48)),
            (int(w * 0.52), int(w * 0.68)),
        ):
            cx = (x_a + x_b) / 2.0
            cy = (y0 + y1) / 2.0
            rx = max(1.0, (x_b - x_a) / 2.0 * 1.15)
            ry = max(1.0, (y1 - y0) / 2.0 * 1.1)
            mask |= ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1.0

        r = arr[..., 0]
        g = arr[..., 1]
        b = arr[..., 2]
        a = arr[..., 3]
        cyan = (
            mask
            & (a > 8)
            & (b > r + 10)
            & (b > 85)
            & (g > 50)
        )
        if not bool(cyan.any()):
            return rgba

        excess = np.clip((b - r - 10) / 80.0, 0.0, 1.0)
        s = float(max(0.0, min(1.0, strength))) * excess
        target_g = r * 0.72 + g * 0.18
        target_b = r * 0.62 + b * 0.10
        arr[..., 1] = np.where(cyan, g * (1.0 - s) + target_g * s, g)
        arr[..., 2] = np.where(cyan, b * (1.0 - s) + target_b * s, b)
        return Image.fromarray(np.clip(arr, 0, 255).astype("uint8"), "RGBA")
    except Exception:
        # Pillow fallback: darken blue channel in a coarse eye band
        out = rgba.copy()
        px = out.load()
        for y in range(y0, y1, 1):
            for x in range(int(w * 0.32), int(w * 0.68)):
                r, g, b, a = px[x, y]
                if a <= 8 or b <= r + 10 or b <= 85:
                    continue
                # skip far from eye centers
                left = abs(x / w - 0.40)
                right = abs(x / w - 0.60)
                if min(left, right) > 0.10:
                    continue
                excess = min(1.0, (b - r - 10) / 80.0) * strength
                tg = int(r * 0.72 + g * 0.18)
                tb = int(r * 0.62 + b * 0.10)
                px[x, y] = (
                    r,
                    int(g * (1 - excess) + tg * excess),
                    int(b * (1 - excess) + tb * excess),
                    a,
                )
        return out


def _maybe_suppress_lid_cyan(
    img: Image.Image,
    *,
    open_glow_ref: Optional[float] = None,
    force: bool = False,
) -> Image.Image:
    """Apply lid cyan kill when eyes look closed (or force for offline still)."""
    if force:
        return _suppress_closed_lid_cyan(img)
    score = _eye_glow_score(img)
    if open_glow_ref is not None and open_glow_ref > 1e-6:
        if score <= open_glow_ref * 0.60:
            return _suppress_closed_lid_cyan(img)
    elif score < 0.015:
        return _suppress_closed_lid_cyan(img)
    return img

def _find_coeffs(source: Sequence[Point], dest: Sequence[Point]):
    """Perspective coeffs: map dest → source (PIL PERSPECTIVE convention)."""
    aug = []
    for (u, v), (x, y) in zip(source, dest):
        aug.append([x, y, 1, 0, 0, 0, -u * x, -u * y, u])
        aug.append([0, 0, 0, x, y, 1, -v * x, -v * y, v])
    n = 8
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        div = aug[col][col] or 1e-12
        for j in range(col, n + 1):
            aug[col][j] /= div
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            for j in range(col, n + 1):
                aug[r][j] -= factor * aug[col][j]
    return [aug[i][n] for i in range(n)]


def perspective_yaw(
    img: Image.Image,
    yaw: float,
    pitch: float = 0.0,
    *,
    strength: float = 0.14,
) -> Image.Image:
    """Single-image 3D card: foreshorten far side, no second plate."""
    yaw = max(-1.0, min(1.0, float(yaw)))
    pitch = max(-1.0, min(1.0, float(pitch)))
    if abs(yaw) < 0.01 and abs(pitch) < 0.01:
        return img.copy()

    w, h = img.size
    inset = strength * abs(yaw) * h * 0.55
    pull = strength * abs(yaw) * w * 0.35
    p_in = strength * abs(pitch) * w * 0.25

    if yaw >= 0:
        dest = [
            (pull, inset + p_in),
            (w - 1, -inset * 0.15 + p_in * 0.3),
            (w - 1, h - 1 + inset * 0.15 - p_in * 0.3),
            (pull, h - 1 - inset - p_in),
        ]
    else:
        dest = [
            (0, -inset * 0.15 + p_in * 0.3),
            (w - 1 - pull, inset + p_in),
            (w - 1 - pull, h - 1 - inset - p_in),
            (0, h - 1 + inset * 0.15 - p_in * 0.3),
        ]

    src = [(0.0, 0.0), (float(w - 1), 0.0), (float(w - 1), float(h - 1)), (0.0, float(h - 1))]
    try:
        coeffs = _find_coeffs(src, dest)
        out = img.transform(
            (w, h),
            Image.Transform.PERSPECTIVE,
            coeffs,
            resample=Image.Resampling.BICUBIC,
            fillcolor=(0, 0, 0, 0),
        )
        return out
    except Exception as exc:
        logger.warning("perspective_yaw failed: %s", exc)
        return img.copy()


def lighting_ramp(img: Image.Image, yaw: float) -> Image.Image:
    """Key light from the near side — cheap depth shading."""
    if abs(yaw) < 0.05:
        return img
    w, h = img.size
    ramp = Image.new("L", (w, h))
    px = ramp.load()
    for x in range(w):
        t = x / max(1, w - 1)
        if yaw >= 0:
            v = int(210 + 45 * t)
        else:
            v = int(255 - 45 * t)
        v = max(160, min(255, v))
        for y in range(h):
            px[x, y] = v
    ramp = ramp.filter(ImageFilter.GaussianBlur(radius=8))
    rgb = img.convert("RGB")
    dark = Image.new("RGB", (w, h), (8, 12, 18))
    mixed = Image.composite(rgb, Image.blend(rgb, dark, 0.35), ramp)
    out = Image.new("RGBA", (w, h))
    out.paste(mixed, (0, 0))
    if img.mode == "RGBA":
        out.putalpha(img.split()[-1])
    return out


def _load_istituto_logo() -> Optional[Image.Image]:
    global _istituto_logo_cache
    if _istituto_logo_cache is not None:
        return _istituto_logo_cache
    path = vision_istituto_logo_backdrop_png()
    if not path.is_file():
        logger.warning("Istituto logo backdrop missing: %s", path)
        return None
    try:
        _istituto_logo_cache = Image.open(path).convert("RGBA")
    except Exception as exc:
        logger.warning("Failed to load istituto logo: %s", exc)
        return None
    return _istituto_logo_cache


def _knockout_flat_void(img: Image.Image, *, tol: int = 14) -> Image.Image:
    """Restore transparency on flat void fills so the logo can sit behind the bust."""
    rgba = img.convert("RGBA")
    try:
        import numpy as np

        arr = np.asarray(rgba)
        alpha = arr[..., 3]
        if float((alpha == 0).mean()) > 0.12:
            return rgba
        arr = arr.copy()
        rgb = arr[..., :3].astype(np.int16)
        vr, vg, vb = _VOID_RGB
        near_void = (
            (np.abs(rgb[..., 0] - vr) <= tol)
            & (np.abs(rgb[..., 1] - vg) <= tol)
            & (np.abs(rgb[..., 2] - vb) <= tol)
            & (arr[..., 3] > 8)
        )
        near_black = (rgb.sum(axis=-1) <= 18) & (arr[..., 3] > 200)
        arr[..., 3] = np.where(near_void | near_black, 0, arr[..., 3])
        return Image.fromarray(arr, "RGBA")
    except Exception:
        return rgba


def _istituto_logo_layers(
    side: int, reduced: bool
) -> Optional[tuple[Image.Image, Image.Image, tuple[int, int]]]:
    key = ("logo", side, bool(reduced))
    cached = _istituto_layer_cache.get(key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    logo = _load_istituto_logo()
    if logo is None:
        return None

    scale = int(side * (1.18 if not reduced else 1.10))
    ox = (side - scale) // 2
    oy = (side - scale) // 2 - int(side * 0.02)
    base = logo.resize((scale, scale), Image.Resampling.LANCZOS)
    soft = base.filter(ImageFilter.GaussianBlur(radius=2.2 if not reduced else 1.4))
    r, g, b, a = soft.split()
    bloom_rgb = Image.merge(
        "RGB",
        (
            r.point(lambda v: int(v * 0.12)),
            g.point(lambda v: int(v * 0.55)),
            b.point(lambda v: min(255, int(v * 1.45))),
        ),
    ).convert("RGBA")
    bloom_rgb.putalpha(a)
    bloom = bloom_rgb.filter(ImageFilter.GaussianBlur(radius=16 if not reduced else 10))
    layers = (soft, bloom, (ox, oy))
    _istituto_layer_cache[key] = layers
    return layers


def build_istituto_backdrop(
    side: int = 512,
    *,
    t: float = 0.0,
    level: str = LEVEL_FULL,
) -> Image.Image:
    """Dark atmospheric stage with VIS Istituto emblem + electric-blue bloom."""
    reduced = level == LEVEL_REDUCED
    off = level == LEVEL_OFF
    bucket = "off" if off else ("reduced" if reduced else "full")
    pair_key = ("stage_pair", side, bucket)
    pair = _istituto_layer_cache.get(pair_key)
    if pair is None:
        lo = _build_istituto_backdrop_static(side, level=level, pulse=0.0)
        hi = _build_istituto_backdrop_static(side, level=level, pulse=1.0)
        pair = (lo, hi)
        _istituto_layer_cache[pair_key] = pair
    lo, hi = pair  # type: ignore[misc]
    if off:
        return lo.copy()
    pulse = 0.5 + 0.5 * math.sin(t * (2 * math.pi / 4.2))
    if reduced:
        pulse *= 0.45
    return Image.blend(lo, hi, pulse)


def _build_istituto_backdrop_static(
    side: int,
    *,
    level: str,
    pulse: float,
) -> Image.Image:
    reduced = level == LEVEL_REDUCED
    off = level == LEVEL_OFF
    canvas = Image.new("RGBA", (side, side), (6, 11, 20, 255))

    atmos_key = ("atmos", side)
    atmos = _istituto_layer_cache.get(atmos_key)
    if atmos is None:
        atmos = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        ad = ImageDraw.Draw(atmos)
        cx = cy = side // 2
        for i, alpha in ((int(side * 0.72), 28), (int(side * 0.48), 40), (int(side * 0.28), 22)):
            ad.ellipse(
                [cx - i, cy - i - 12, cx + i, cy + i - 12],
                fill=(12, 36, 68, alpha),
            )
        atmos = atmos.filter(ImageFilter.GaussianBlur(radius=max(12, side // 28)))
        _istituto_layer_cache[atmos_key] = atmos
    canvas.alpha_composite(atmos)  # type: ignore[arg-type]

    layers = _istituto_logo_layers(side, reduced)
    if layers is not None:
        soft, bloom, (ox, oy) = layers
        opacity = 0.22 if off else (0.28 if reduced else (0.34 + 0.08 * pulse))
        r, g, b, a = soft.split()
        canvas.alpha_composite(
            Image.merge("RGBA", (r, g, b, a.point(lambda v, o=opacity: int(v * o)))),
            (ox, oy),
        )
        bloom_opacity = 0.2 if off else ((0.42 + 0.28 * pulse) * (0.75 if reduced else 1.0))
        br, bg, bb, ba = bloom.split()
        canvas.alpha_composite(
            Image.merge(
                "RGBA",
                (br, bg, bb, ba.point(lambda v, o=bloom_opacity: int(v * o))),
            ),
            (ox, oy),
        )

    spill_key = ("spill", side)
    spill_base = _istituto_layer_cache.get(spill_key)
    if spill_base is None:
        spill_base = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        sd = ImageDraw.Draw(spill_base)
        sd.ellipse(
            [int(side * 0.12), int(side * 0.22), int(side * 0.88), int(side * 0.78)],
            fill=(0, 150, 220, 90),
        )
        sd.ellipse(
            [int(side * 0.28), int(side * 0.30), int(side * 0.72), int(side * 0.62)],
            fill=(56, 189, 248, 50),
        )
        spill_base = spill_base.filter(ImageFilter.GaussianBlur(radius=max(28, side // 14)))
        _istituto_layer_cache[spill_key] = spill_base
    spill_mul = 0.2 if off else ((0.42 + 0.35 * pulse) * (0.7 if reduced else 1.0))
    sr, sg, sb, sa = spill_base.split()  # type: ignore[union-attr]
    canvas.alpha_composite(
        Image.merge("RGBA", (sr, sg, sb, sa.point(lambda v, m=spill_mul: int(v * m))))
    )

    vig_key = ("vig", side)
    vig = _istituto_layer_cache.get(vig_key)
    if vig is None:
        vig = Image.new("L", (side, side), 0)
        vd = ImageDraw.Draw(vig)
        vd.ellipse(
            [int(side * 0.06), int(side * 0.04), int(side * 0.94), int(side * 0.96)],
            fill=255,
        )
        vig = vig.filter(ImageFilter.GaussianBlur(radius=max(20, side // 18)))
        _istituto_layer_cache[vig_key] = vig
    dark = Image.new("RGB", (side, side), (4, 8, 14))
    rgb = canvas.convert("RGB")
    mixed = Image.composite(rgb, Image.blend(rgb, dark, 0.55), vig)  # type: ignore[arg-type]
    out = Image.new("RGBA", (side, side))
    out.paste(mixed, (0, 0))
    out.putalpha(255)
    return out


def finalize_with_istituto_backdrop(
    img: Image.Image,
    *,
    t: float,
    level: str,
    subject_scale: Optional[float] = None,
) -> Image.Image:
    """Place avatar in front of Istituto logo stage; preserve face clarity."""
    side = max(img.size)
    if img.size[0] != side or img.size[1] != side:
        img = normalize_square(img.convert("RGBA"), side)

    stage = build_istituto_backdrop(side, t=t, level=level)
    subject = _knockout_flat_void(img)

    # Framing scale — keep emblem readable behind without shrinking face too much
    if subject_scale is None:
        subject_scale = 0.93 if level != LEVEL_REDUCED else 0.95
        if level == LEVEL_OFF:
            subject_scale = 0.96
    else:
        subject_scale = float(subject_scale)
        if level == LEVEL_REDUCED:
            subject_scale = min(subject_scale, max(subject_scale * 0.98, 0.95))
    # Cap so we do not blow past the panel (logo still peeks at edges)
    subject_scale = max(0.85, min(1.12, subject_scale))
    sw = max(1, int(side * subject_scale))
    scaled = subject.resize((sw, sw), Image.Resampling.BILINEAR)
    ox = (side - sw) // 2
    oy = (side - sw) // 2 - int(side * 0.01)

    shadow_key = ("shadow", side)
    shadow = _istituto_layer_cache.get(shadow_key)
    if shadow is None:
        shadow = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.ellipse(
            [int(side * 0.28), int(side * 0.82), int(side * 0.72), int(side * 0.94)],
            fill=(0, 0, 0, 80),
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14))
        _istituto_layer_cache[shadow_key] = shadow
    stage.alpha_composite(shadow)  # type: ignore[arg-type]
    stage.alpha_composite(scaled, (ox, oy))
    # Shoulder light spill lives in the backdrop (behind subject) — no per-frame rim blur
    _ = t
    return stage



class AvatarRenderer(ABC):
    """Swap point: Pseudo3D now, GLB later — same compose contract."""

    @abstractmethod
    def compose(
        self,
        *,
        state: str,
        yaw: float,
        t: float,
        level: str,
        wave_phase: float,
        reaction: float,
    ) -> Image.Image:
        raise NotImplementedError


class Pseudo3DRenderer(AvatarRenderer):
    """One clean state plate + perspective / lighting / breath — no pose sheets."""

    def __init__(self, bible_dir: Optional[Path] = None) -> None:
        self._root = bible_dir or vision_avatar_bible_dir()
        self._states: dict[str, Image.Image] = {}
        self._load()

    def _load(self) -> None:
        for state, fname in _STATE_FILES.items():
            path = self._root / fname
            if path.is_file():
                self._states[state] = normalize_square(Image.open(path).convert("RGBA"))
            else:
                logger.warning("Character Bible frame missing: %s", path)

        if STATE_IDLE not in self._states:
            fb = vision_avatar_profile_png()
            if fb.is_file():
                self._states[STATE_IDLE] = normalize_square(Image.open(fb).convert("RGBA"))
            else:
                self._states[STATE_IDLE] = placeholder()

        for st in (
            STATE_LISTENING,
            STATE_PROCESSING,
            STATE_SPEAKING,
            STATE_ALERT,
            STATE_OFFLINE,
        ):
            if st not in self._states:
                self._states[st] = self._states[STATE_IDLE].copy()

    def _base(self, state: str) -> Image.Image:
        return (self._states.get(state) or self._states[STATE_IDLE]).copy()

    def compose(
        self,
        *,
        state: str,
        yaw: float,
        t: float,
        level: str,
        wave_phase: float,
        reaction: float,
    ) -> Image.Image:
        reduced = level == LEVEL_REDUCED
        off = level == LEVEL_OFF
        # Supervisor off / animations off → held offline plate (closed / dim eyes)
        visual = STATE_OFFLINE if (off or state == STATE_OFFLINE) else state
        img = self._base(visual)

        # Brightness by state (same face — illumination only)
        boost = 1.0
        if visual == STATE_LISTENING:
            boost = 1.06 + 0.025 * math.sin(t * 2.5)
        elif visual == STATE_PROCESSING:
            boost = 1.08 + 0.04 * math.sin(t * 2.2)
        elif visual == STATE_SPEAKING:
            boost = 1.10 + 0.05 * math.sin(t * 5.0)
        elif visual == STATE_ALERT:
            boost = 1.04 + 0.04 * math.sin(t * 6.0)
        elif visual == STATE_IDLE and not reduced:
            boost = 1.0 + 0.02 * math.sin(t * (2 * math.pi / 3.2))
        elif visual == STATE_OFFLINE:
            boost = 0.82
        if reaction > 0.05 and visual != STATE_OFFLINE:
            boost += 0.05 * reaction
        if boost != 1.0:
            img = ImageEnhance.Brightness(img).enhance(boost)

        # Pseudo-3D: perspective + key light (full motion only)
        pitch = 0.0
        if not off and not reduced and visual != STATE_OFFLINE:
            pitch = 0.08 * math.sin(t * 0.55)
            if visual == STATE_LISTENING:
                pitch += 0.06
            if reaction > 0.05:
                pitch += 0.1 * reaction * math.sin(t * 7)
            strength = 0.22 + 0.12 * reaction
            img = perspective_yaw(img, yaw, pitch, strength=strength)
            img = lighting_ramp(img, yaw)

        # Breathing scale + micro drift (≤ ~3°)
        if (
            not off
            and not reduced
            and visual not in (STATE_ALERT, STATE_OFFLINE)
        ):
            phase = t * (2 * math.pi / 3.0) + 0.2 * math.sin(t * 0.41)
            amp = 0.008 if visual == STATE_IDLE else 0.005
            drift_x = int(2 * math.sin(phase * 0.9) + yaw * 3)
            drift_y = int(2 * math.cos(phase * 0.75))
            if reaction > 0.1:
                amp += 0.004 * reaction
            scale = 1.0 + amp * math.sin(phase)
            w = int(512 * scale)
            scaled = img.resize((w, w), Image.Resampling.BILINEAR)
            canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            # Soft contact shadow under bust for depth
            shadow = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            sd = ImageDraw.Draw(shadow)
            sd.ellipse([150, 430, 362, 490], fill=(0, 0, 0, 70))
            shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14))
            canvas.alpha_composite(shadow, (0, 0))
            ox = (512 - w) // 2 + drift_x
            oy = (512 - w) // 2 + drift_y
            canvas.alpha_composite(scaled, (ox, oy))
            img = canvas
        elif visual == STATE_ALERT and not off and not reduced:
            nudge = int(1 * math.sin(t * 8))
            canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            canvas.alpha_composite(img, (nudge, 0))
            img = canvas

        # Soft eye/core bloom — never composite cyan over closed lids / offline
        if not off and visual != STATE_OFFLINE:
            if _eye_glow_score(img) >= 0.015:
                img = _apply_png_eye_glow(
                    img,
                    state=visual,
                    t=t,
                    reaction=reaction,
                    reduced=reduced,
                )
            else:
                img = _suppress_closed_lid_cyan(img)
        elif visual == STATE_OFFLINE or off:
            img = _suppress_closed_lid_cyan(img)

        if visual == STATE_SPEAKING and not off:
            d = ImageDraw.Draw(img)
            bar_rgb = _png_eye_color(visual, t)
            base_y = 455
            for i in range(16):
                amp = 6 + 14 * abs(math.sin(wave_phase + i * 0.5))
                x = 170 + i * 12
                d.rectangle(
                    [x, base_y - amp, x + 5, base_y + 2],
                    fill=(*bar_rgb, 200),
                )

        return finalize_with_istituto_backdrop(img, t=t, level=level)


def _png_eye_color(state: str, t: float) -> tuple[int, int, int]:
    """Eye / core glow RGB by action state (navy–cyan brand; amber process; red alert)."""
    if state == STATE_ALERT:
        # Red/orange warning pulse
        pulse = 0.5 + 0.5 * abs(math.sin(t * 7.0))
        return (int(220 + 35 * pulse), int(40 + 30 * pulse), int(20 + 10 * pulse))
    if state == STATE_PROCESSING:
        # Cyan → amber tech (avoid purple-slop)
        u = 0.5 + 0.5 * math.sin(t * 2.4)
        return (
            int(0 + 255 * u),
            int(182 - 40 * u),
            int(255 - 215 * u),
        )
    if state == STATE_SPEAKING:
        # Stronger electric blue
        pulse = 0.55 + 0.45 * abs(math.sin(t * 6.0))
        return (int(20 * (1 - pulse)), int(120 + 80 * pulse), 255)
    if state == STATE_LISTENING:
        # Brighter attentive cyan
        pulse = 0.5 + 0.5 * math.sin(t * 2.5)
        return (0, int(200 + 40 * pulse), 255)
    if state == STATE_OFFLINE:
        return (90, 110, 130)
    # IDLE — calm cyan/blue
    breath = 0.5 + 0.5 * math.sin(t * (2 * math.pi / 3.2))
    return (0, int(160 + 40 * breath), int(220 + 25 * breath))


def _apply_png_eye_glow(
    img: Image.Image,
    *,
    state: str,
    t: float,
    reaction: float,
    reduced: bool,
) -> Image.Image:
    """Non-destructive eye + chest-core glow overlay for Character Bible plates."""
    pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * (2 * math.pi / 3.1)))
    if reduced:
        pulse = 0.4
    if state == STATE_SPEAKING:
        pulse = 0.55 + 0.45 * abs(math.sin(t * 6.0))
    elif state == STATE_LISTENING:
        pulse = 0.45 + 0.4 * (0.5 + 0.5 * math.sin(t * 2.8))
    elif state == STATE_PROCESSING:
        pulse = 0.5 + 0.45 * abs(math.sin(t * 3.2))
    elif state == STATE_ALERT:
        pulse = 0.6 + 0.4 * abs(math.sin(t * 7.0))
    if reaction > 0.05:
        pulse = min(1.0, pulse + 0.35 * reaction)

    glow_rgb = _png_eye_color(state, t)
    glow = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    alpha = int(22 + 48 * pulse)
    # Eye regions (stable on bible bust plates)
    gd.ellipse([200, 150, 250, 200], fill=(*glow_rgb, alpha))
    gd.ellipse([270, 150, 320, 200], fill=(*glow_rgb, alpha))
    # Inner hot spots for readable color shift
    hot = int(min(200, alpha + 40))
    gd.ellipse([214, 164, 236, 186], fill=(*glow_rgb, hot))
    gd.ellipse([284, 164, 306, 186], fill=(*glow_rgb, hot))
    core_a = int(alpha * (1.3 if state == STATE_PROCESSING else 1.05))
    gd.ellipse([220, 320, 300, 400], fill=(*glow_rgb, min(160, core_a)))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=12 if state != STATE_ALERT else 10))
    base = img if img.mode == "RGBA" else img.convert("RGBA")
    return Image.alpha_composite(base, glow)


def _alive_face_overlay(
    img: Image.Image,
    *,
    state: str,
    t: float,
    wave_phase: float,
    reduced: bool,
) -> Image.Image:
    """Legacy Pseudo3D-only micro-motion. Disabled for GLB clips.

    Meshy bake already includes blink / mouth / emission. Hardcoded eye lids,
    cyan glow blobs, and mouth ROI stretch mis-land on 3/4 busts and look broken.
    """
    _ = (state, t, wave_phase, reduced)
    return img


class GlbTurntableRenderer(AvatarRenderer):
    """Hero Meshy GLB via yaw turntable + armature animation clips.

    Also plays per-model sprite packs under ``model_frames/<id>/`` using the
    same clip state map. Manifest ``clips`` may list relative paths (Meshy
    legacy) or compact ``{ "frames": N, "loop": true }`` with files at
    ``clips/<name>/00.png``.
    """

    def __init__(self, frames_dir: Optional[Path] = None) -> None:
        self._root = frames_dir or vision_avatar_glb_frames_dir()
        self._yaw: list[tuple[float, Image.Image]] = []
        self._states: dict[str, Image.Image] = {}
        self._clips: dict[str, dict] = {}
        self._offline_still: Optional[Image.Image] = None
        self._idle_open_glow: Optional[float] = None
        self._react_clip: Optional[str] = None
        self._react_t0: float = 0.0
        self._clip_state: Optional[str] = None
        self._clip_t0: float = 0.0
        self._default_fps: float = 12.0
        self._load()

    @staticmethod
    def _numbered_frame_paths(clip_dir: Path, count: Optional[int] = None) -> list[Path]:
        """Contiguous zero-padded PNGs: 00.png, 01.png, … (no gaps)."""
        if not clip_dir.is_dir():
            return []
        paths: list[Path] = []
        i = 0
        while True:
            if count is not None and i >= count:
                break
            found: Optional[Path] = None
            for pad in (2, 3, 4):
                candidate = clip_dir / f"{i:0{pad}d}.png"
                if candidate.is_file():
                    found = candidate
                    break
            if found is None:
                break
            paths.append(found)
            i += 1
        return paths

    def _load_clip_frames(
        self,
        clip_name: str,
        meta: dict,
        *,
        default_fps: float,
    ) -> Optional[dict]:
        frames: list[Image.Image] = []
        frames_meta = meta.get("frames")
        if isinstance(frames_meta, list):
            for rel in frames_meta:
                path = self._root / str(rel)
                if path.is_file():
                    frames.append(normalize_square(Image.open(path).convert("RGBA"), 512))
        else:
            count = int(frames_meta) if isinstance(frames_meta, int) else None
            clip_dir = self._root / "clips" / clip_name
            for path in self._numbered_frame_paths(clip_dir, count):
                frames.append(normalize_square(Image.open(path).convert("RGBA"), 512))
        if not frames:
            return None
        fps = float(meta.get("fps") or default_fps)
        return {
            "fps": fps,
            "loop": bool(meta.get("loop", True)),
            "frames": frames,
        }

    def _load(self) -> None:
        manifest_path = self._root / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"Missing turntable manifest: {manifest_path}")
        import json

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        size_raw = data.get("size")
        if isinstance(size_raw, (list, tuple)) and size_raw:
            # Authoring size is informational; playback normalizes to 512
            pass
        self._default_fps = float(
            data.get("fps")
            or (data.get("animation") or {}).get("fps")
            or 12
        )
        for entry in data.get("yaw_frames") or []:
            path = self._root / entry["file"]
            if path.is_file():
                img = Image.open(path).convert("RGBA")
                self._yaw.append((float(entry["yaw"]), normalize_square(img, 512)))
        self._yaw.sort(key=lambda x: x[0])
        for entry in data.get("state_frames") or []:
            path = self._root / entry["file"]
            st = str(entry.get("state") or "").upper()
            if path.is_file() and st:
                self._states[st] = normalize_square(Image.open(path).convert("RGBA"), 512)
        # Animation clips (armature-baked or authored sprite sequences)
        clips_data = data.get("clips") or {}
        for clip_name, meta in clips_data.items():
            if not isinstance(meta, dict):
                continue
            loaded = self._load_clip_frames(
                clip_name, meta, default_fps=self._default_fps
            )
            if loaded:
                self._clips[clip_name] = loaded
        # Discover clip folders present on disk but omitted from manifest
        clips_root = self._root / "clips"
        if clips_root.is_dir():
            for child in sorted(clips_root.iterdir()):
                if not child.is_dir() or child.name in self._clips:
                    continue
                loaded = self._load_clip_frames(
                    child.name,
                    {"frames": None, "loop": child.name not in ("react_left", "react_right")},
                    default_fps=self._default_fps,
                )
                if loaded:
                    self._clips[child.name] = loaded
        if not self._yaw and not self._clips:
            raise RuntimeError("No yaw frames or clips loaded")
        if not self._yaw and self._clips.get("idle"):
            # synthesize single yaw from idle mid frame
            mid = self._clips["idle"]["frames"][0]
            self._yaw = [(0.0, mid.copy())]
        if STATE_IDLE not in self._states and self._yaw:
            self._states[STATE_IDLE] = self._yaw[len(self._yaw) // 2][1].copy()
        # Prefer idle / preview still as state plate fallback for sprite-only packs
        if STATE_IDLE not in self._states:
            preview = self._root / "preview.png"
            if preview.is_file():
                self._states[STATE_IDLE] = normalize_square(
                    Image.open(preview).convert("RGBA"), 512
                )
            elif self._clips.get("idle"):
                self._states[STATE_IDLE] = self._clips["idle"]["frames"][0].copy()
        self._offline_still = self._resolve_offline_still()
        idle_frames = (self._clips.get("idle") or {}).get("frames") or []
        if idle_frames:
            scores = [_eye_glow_score(fr) for fr in idle_frames]
            self._idle_open_glow = sorted(scores)[len(scores) // 2]
        elif STATE_IDLE in self._states:
            self._idle_open_glow = _eye_glow_score(self._states[STATE_IDLE])

    def _resolve_offline_still(self) -> Image.Image:
        """Held closed-eyes (or dimmest) plate for OFFLINE / LEVEL_OFF — not a blink loop."""
        # 1) Dedicated offline clip — prefer blink-closed frame inside it
        offline_clip = self._clips.get("offline")
        if offline_clip and offline_clip.get("frames"):
            frames = offline_clip["frames"]
            closed = _pick_closed_eye_frame(frames)
            still = closed or frames[len(frames) // 2].copy()
            logger.info("Offline still from clips/offline (%d frames)", len(frames))
            return _suppress_closed_lid_cyan(still)

        idle_frames = (self._clips.get("idle") or {}).get("frames") or []
        idle_ref = idle_frames[0] if idle_frames else self._states.get(STATE_IDLE)

        # 2) Manifest state_offline plate when eyes are darker than idle
        plate = self._states.get(STATE_OFFLINE)
        if plate is not None:
            if idle_ref is None:
                return _suppress_closed_lid_cyan(plate.copy())
            if _eye_glow_score(plate) <= _eye_glow_score(idle_ref) * 0.75:
                logger.info("Offline still from state_offline plate")
                return _suppress_closed_lid_cyan(plate.copy())

        # 3) Mid-blink frame from idle (e.g. vision_futuristic idle/10.png)
        if idle_frames:
            closed = _pick_closed_eye_frame(idle_frames)
            if closed is not None:
                logger.info("Offline still from idle blink-closed frame")
                return _suppress_closed_lid_cyan(closed)

        # 4) Fallback: dimmest available plate (may still show open eyes if bake has no blink)
        if plate is not None:
            return _suppress_closed_lid_cyan(plate.copy())
        if idle_ref is not None:
            return _suppress_closed_lid_cyan(idle_ref.copy())
        if self._yaw:
            return _suppress_closed_lid_cyan(self._yaw[len(self._yaw) // 2][1].copy())
        return placeholder(512)

    def trigger_react_clip(self, side: str = "left") -> None:
        import time as _time

        name = "react_left" if side.startswith("l") else "react_right"
        if name in self._clips:
            self._react_clip = name
            self._react_t0 = _time.perf_counter()

    def _clip_image(self, name: str, t: float) -> Optional[Image.Image]:
        clip = self._clips.get(name)
        if not clip:
            return None
        frames: list[Image.Image] = clip["frames"]
        fps = clip["fps"]
        n = len(frames)
        if n == 0:
            return None
        idx_f = t * fps
        if clip["loop"]:
            idx = int(idx_f) % n
        else:
            idx = min(n - 1, max(0, int(idx_f)))
            if idx >= n - 1:
                # one-shot finished
                if name == self._react_clip:
                    self._react_clip = None
        return frames[idx].copy()

    def _blend_yaw(self, yaw: float) -> Image.Image:
        yaw = max(-1.0, min(1.0, float(yaw)))
        frames = self._yaw
        if not frames:
            idle = self._clips.get("idle")
            if idle and idle["frames"]:
                return idle["frames"][0].copy()
            return Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        if yaw <= frames[0][0]:
            return frames[0][1].copy()
        if yaw >= frames[-1][0]:
            return frames[-1][1].copy()
        for i in range(len(frames) - 1):
            y0, im0 = frames[i]
            y1, im1 = frames[i + 1]
            if y0 <= yaw <= y1:
                span = y1 - y0
                u = 0.0 if span < 1e-6 else (yaw - y0) / span
                if u <= 0.02:
                    return im0.copy()
                if u >= 0.98:
                    return im1.copy()
                return Image.blend(im0, im1, u)
        return frames[-1][1].copy()

    def compose(
        self,
        *,
        state: str,
        yaw: float,
        t: float,
        level: str,
        wave_phase: float,
        reaction: float,
    ) -> Image.Image:
        import time as _time

        reduced = level == LEVEL_REDUCED
        off = level == LEVEL_OFF
        deactivated = off or state == STATE_OFFLINE

        # Supervisor / animations off: hold closed-eyes still (no blink reopen)
        if deactivated:
            img = (self._offline_still or self._states.get(STATE_IDLE) or placeholder(512)).copy()
            img = _suppress_closed_lid_cyan(img)
            img = ImageEnhance.Brightness(img).enhance(0.85)
            canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            canvas.alpha_composite(img, (0, 0))
            _ = (yaw, wave_phase, reaction, reduced)
            return finalize_with_istituto_backdrop(canvas, t=t, level=level)

        # One-shot react clip overrides briefly
        img: Optional[Image.Image] = None
        if self._react_clip and not reduced:
            img = self._clip_image(self._react_clip, _time.perf_counter() - self._react_t0)

        clip_map = {
            STATE_IDLE: "idle",
            STATE_LISTENING: "listening",
            STATE_SPEAKING: "speaking",
            STATE_PROCESSING: "processing",
            STATE_ALERT: "alert",
        }
        if img is None and level == LEVEL_FULL:
            clip_name = clip_map.get(state)
            if clip_name:
                # Restart clip timeline on state change so loops don't start mid-cycle
                if self._clip_state != state:
                    self._clip_state = state
                    self._clip_t0 = _time.perf_counter()
                elapsed = _time.perf_counter() - self._clip_t0
                img = self._clip_image(clip_name, elapsed)
                # Partial packs: missing state → idle clip
                if img is None and clip_name != "idle":
                    img = self._clip_image("idle", elapsed)
            else:
                self._clip_state = None
        else:
            if img is None:
                self._clip_state = None

        playing_clip = img is not None
        if img is None:
            # Fallback: yaw turntable + state plate (no clip available)
            img = self._blend_yaw(yaw)
            plate = self._states.get(state) or self._states.get(STATE_IDLE)
            if plate is not None and state != STATE_IDLE:
                mix = 0.22 if state in (STATE_LISTENING, STATE_PROCESSING) else 0.18
                if state == STATE_SPEAKING:
                    mix = 0.28
                if state == STATE_ALERT:
                    mix = 0.2
                img = Image.blend(img, plate, mix)
        # Do NOT blend yaw turntable over bone clips — different camera angles
        # ghost (same failure mode as rejected pose-sheet blending).

        # Blink / closed-lid frames: kill baked cyan under lids (no emissive overlay)
        img = _maybe_suppress_lid_cyan(img, open_glow_ref=self._idle_open_glow)
        boost = 1.0
        if state == STATE_LISTENING:
            boost = 1.02 + 0.015 * math.sin(t * 2.5)
        elif state == STATE_PROCESSING:
            boost = 1.03 + 0.02 * math.sin(t * 2.2)
        elif state == STATE_SPEAKING:
            boost = 1.03 + 0.025 * math.sin(t * 5.0)
        elif state == STATE_ALERT:
            boost = 1.02 + 0.025 * math.sin(t * 6.0)
        if reaction > 0.05:
            boost += 0.02 * reaction
        if boost != 1.0:
            img = ImageEnhance.Brightness(img).enhance(boost)

        # Keep clip frames stable: no breath/scale when armature clip is playing
        if playing_clip or reduced or state == STATE_ALERT:
            canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            canvas.alpha_composite(img, (0, 0))
            img = canvas
        else:
            phase = t * (2 * math.pi / 3.0)
            amp = 0.003
            drift_x = int(1 * math.sin(phase * 0.9))
            drift_y = int(1 * math.cos(phase * 0.75))
            scale = 1.0 + amp * math.sin(phase)
            w = int(512 * scale)
            scaled = img.resize((w, w), Image.Resampling.BILINEAR)
            canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            ox = (512 - w) // 2 + drift_x
            oy = (512 - w) // 2 + drift_y
            canvas.alpha_composite(scaled, (ox, oy))
            img = canvas

        # No HUD waveform bars / face overlays on Meshy clips — baked motion only
        _ = wave_phase
        return finalize_with_istituto_backdrop(img, t=t, level=level)


class GlbRenderer(GlbTurntableRenderer):
    """Alias — live GLB viewport can replace turntable later."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or vision_avatar_model_glb()
        super().__init__()


class StillPlateRenderer(AvatarRenderer):
    """Single preview plate for models without a full clip/turntable pack.

    Applies light perspective yaw + Istituto backdrop so switching models is
    visibly different even before animation clips exist.
    """

    def __init__(self, plate: Path, *, model_id: str = "") -> None:
        self.model_id = model_id or plate.stem
        self._plate_path = Path(plate)
        if not self._plate_path.is_file():
            raise FileNotFoundError(f"Avatar preview missing: {self._plate_path}")
        fill = _STILL_PLATE_FILL.get(self.model_id, _STILL_DEFAULT_FILL)
        self._subject_scale = _STILL_SUBJECT_SCALE.get(
            self.model_id, _STILL_DEFAULT_SUBJECT_SCALE
        )
        # Content-aware fit removes Blender letterboxing so still models
        # read at hero size comparable to Meshy plates.
        self._plate = fit_opaque_to_square(
            Image.open(self._plate_path).convert("RGBA"),
            512,
            target_fill=fill,
        )

    def compose(
        self,
        *,
        state: str,
        yaw: float,
        t: float,
        level: str,
        wave_phase: float,
        reaction: float,
    ) -> Image.Image:
        _ = wave_phase
        reduced = level == LEVEL_REDUCED
        off = level == LEVEL_OFF
        img = self._plate.copy()

        boost = 1.0
        if state == STATE_LISTENING:
            boost = 1.04 + 0.02 * math.sin(t * 2.5)
        elif state == STATE_PROCESSING:
            boost = 1.05 + 0.025 * math.sin(t * 2.2)
        elif state == STATE_SPEAKING:
            boost = 1.06 + 0.03 * math.sin(t * 5.0)
        elif state == STATE_ALERT:
            boost = 1.03 + 0.03 * math.sin(t * 6.0)
        elif state == STATE_OFFLINE or off:
            boost = 0.85
        if reaction > 0.05:
            boost += 0.03 * reaction
        if boost != 1.0:
            img = ImageEnhance.Brightness(img).enhance(boost)

        if not off and not reduced:
            pitch = 0.06 * math.sin(t * 0.55)
            if state == STATE_LISTENING:
                pitch += 0.05
            strength = 0.18 + 0.1 * reaction
            img = perspective_yaw(img, yaw if not off else 0.0, pitch, strength=strength)
            img = lighting_ramp(img, yaw)

        if not off and not reduced and state != STATE_ALERT:
            phase = t * (2 * math.pi / 3.0)
            amp = 0.006
            scale = 1.0 + amp * math.sin(phase)
            w = int(512 * scale)
            scaled = img.resize((w, w), Image.Resampling.BILINEAR)
            canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            ox = (512 - w) // 2
            oy = (512 - w) // 2
            canvas.alpha_composite(scaled, (ox, oy))
            img = canvas

        return finalize_with_istituto_backdrop(
            img, t=t, level=level, subject_scale=self._subject_scale
        )


def create_avatar_renderer(
    model_id: Optional[str] = None,
    *,
    mode: Optional[str] = None,
) -> AvatarRenderer:
    """Build renderer for Supervisor avatar mode + selected GLB/sprite pack.

    ``mode``:
      - ``png`` → Character Bible state plates with per-state eye glow
      - ``3d`` (default) → sprite clip pack / still plate / Pseudo3D fallback

    Preference in 3D mode:
      1. Per-model pack ``model_frames/<id>/`` (clips + manifest)
      2. Meshy legacy ``glb_frames/`` for Meshy model ids
      3. Still ``preview.png``
      4. Pseudo3D fallback
    """
    from utils.avatar_models import (
        AVATAR_MODE_PNG,
        avatar_model_glb_path,
        model_has_sprite_pack,
        normalize_avatar_mode,
        resolve_sprite_pack_dir,
    )

    if normalize_avatar_mode(mode) == AVATAR_MODE_PNG:
        logger.info("Using Pseudo3DRenderer (avatar PNG mode)")
        return Pseudo3DRenderer()

    mid = normalize_avatar_model_id(model_id)

    # Prefer per-model sprite pack over shared Meshy glb_frames
    if model_has_sprite_pack(mid):
        pack = avatar_model_frames_dir(mid)
        try:
            logger.info("Using GlbTurntableRenderer for %s from %s", mid, pack)
            return GlbTurntableRenderer(pack)
        except Exception as exc:
            logger.warning("Per-model sprite pack failed for %s (%s)", mid, exc)

    # Shared Meshy animation pack (legacy path for vision_avatar_v1)
    if uses_shared_meshy_frames(mid):
        frames = vision_avatar_glb_frames_dir()
        if (frames / "manifest.json").is_file():
            try:
                logger.info("Using GlbTurntableRenderer (%s) from %s", mid, frames)
                return GlbTurntableRenderer(frames)
            except Exception as exc:
                logger.warning("GlbTurntableRenderer failed (%s); falling back", exc)

    # Any other resolved pack path (defensive)
    pack = resolve_sprite_pack_dir(mid)
    if pack is not None and pack != vision_avatar_glb_frames_dir():
        try:
            logger.info("Using GlbTurntableRenderer for %s from %s", mid, pack)
            return GlbTurntableRenderer(pack)
        except Exception as exc:
            logger.warning("Sprite pack failed for %s (%s)", mid, exc)

    preview = resolve_avatar_preview_png(mid)
    if preview is not None:
        try:
            logger.info("Using StillPlateRenderer for %s (%s)", mid, preview)
            return StillPlateRenderer(preview, model_id=mid)
        except Exception as exc:
            logger.warning("StillPlateRenderer failed for %s (%s)", mid, exc)

    glb = avatar_model_glb_path(mid)
    if glb.is_file():
        logger.info(
            "Model %s present at %s but no preview/frames yet — Pseudo3D fallback",
            mid,
            glb,
        )
    else:
        logger.info("Model %s unavailable — Pseudo3D fallback", mid)
    return Pseudo3DRenderer()
