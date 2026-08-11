"""VISION avatar model discovery and display labels.
Scans ``assets/avatar/models/*.glb`` (non-recursive) and
``assets/avatar/model_frames/<id>/`` sprite packs; maps stems to
human-readable names for Supervisor settings.
"""
from __future__ import annotations
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional
from utils.paths import resource_path, vision_avatar_glb_frames_dir
logger = logging.getLogger("utils.avatar_models")
# Canonical default — Meshy optimized + pre-rendered glb_frames pack
DEFAULT_AVATAR_MODEL_ID = "vision_avatar_v1"
# UI mode: GLB-based 3D pack/still vs Character Bible PNG plates
AVATAR_MODE_3D = "3d"
AVATAR_MODE_PNG = "png"
DEFAULT_AVATAR_MODE = AVATAR_MODE_3D
# Prefer these labels when the file exists; unknown stems get a title-cased name.
_KNOWN_LABELS: dict[str, str] = {
    "vision_avatar_v1": "VISION Meshy v1",
    "vision": "VISION Meshy v1",
    "vision_avatar_cyborg_source": "Cyborg futuristic",
    "vision_futuristic": "VISION Futuristic",
    "vision_avatar_rigged_v1": "VISION Rigged v1",
}
# Models that use the shared Meshy turntable/clip pack under glb_frames/
_MESHY_FRAME_PACK_IDS = frozenset({"vision_avatar_v1", "vision", "meshy", "default"})
# Complete sprite pack states (partial packs OK — missing clips fall back)
REQUIRED_SPRITE_CLIP_STATES = ("idle", "listening", "speaking", "processing", "alert")
OPTIONAL_SPRITE_CLIP_STATES = ("react_left", "react_right")
DEFAULT_SPRITE_FPS = 16
_SAFE_STEM_RE = re.compile(r"[^a-zA-Z0-9_-]+")

def avatar_models_dir() -> Path:
    return resource_path("assets", "avatar", "models")

def avatar_model_frames_root() -> Path:
    return resource_path("assets", "avatar", "model_frames")

def avatar_model_frames_dir(model_id: str) -> Path:
    """Per-model still/clip frames (not the shared Meshy glb_frames pack)."""
    mid = (model_id or DEFAULT_AVATAR_MODEL_ID).strip()
    return avatar_model_frames_root() / mid

def normalize_avatar_model_id(raw: Optional[str]) -> str:
    mid = (raw or DEFAULT_AVATAR_MODEL_ID).strip()
    if not mid or mid.lower() in ("default", "meshy"):
        return DEFAULT_AVATAR_MODEL_ID
    if mid.lower() in ("vision",):
        return DEFAULT_AVATAR_MODEL_ID
    # Accept bare filename
    if mid.lower().endswith(".glb"):
        mid = Path(mid).stem
    return mid

def normalize_avatar_mode(raw: Optional[str]) -> str:
    text = (raw or DEFAULT_AVATAR_MODE).strip().lower()
    if text in ("png", "2d", "bible", "plates", "character"):
        return AVATAR_MODE_PNG
    if text in ("3d", "glb", "model", "mesh"):
        return AVATAR_MODE_3D
    return DEFAULT_AVATAR_MODE

def avatar_mode_label(mode: Optional[str]) -> str:
    if normalize_avatar_mode(mode) == AVATAR_MODE_PNG:
        return "Avatar PNG"
    return "Avatar 3D (GLB)"

def avatar_mode_from_label(label: str) -> str:
    text = (label or "").strip().lower()
    if "png" in text:
        return AVATAR_MODE_PNG
    return AVATAR_MODE_3D

def _humanize_stem(stem: str) -> str:
    known = _KNOWN_LABELS.get(stem)
    if known:
        return known
    text = stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(p.capitalize() for p in text.split()) or stem

def is_valid_sprite_pack(root: Path | str) -> bool:
    """True when ``root`` has ``manifest.json`` + ``clips/`` with at least one PNG."""
    base = Path(root)
    if not base.is_dir():
        return False
    if not (base / "manifest.json").is_file():
        return False
    clips = base / "clips"
    if not clips.is_dir():
        return False
    return any(clips.glob("*/*.png"))


def model_has_sprite_pack(model_id: str) -> bool:
    """Per-model animated pack under ``model_frames/<id>/`` (not Meshy legacy)."""
    mid = normalize_avatar_model_id(model_id)
    return is_valid_sprite_pack(avatar_model_frames_dir(mid))


def model_is_animated(model_id: str) -> bool:
    """True if a clip pack is available (per-model or Meshy ``glb_frames`` legacy)."""
    return resolve_sprite_pack_dir(model_id) is not None


def resolve_sprite_pack_dir(model_id: str) -> Optional[Path]:
    """Directory with playable clips for ``model_id``.

    Preference:
      1. ``assets/avatar/model_frames/<id>/`` when clips + manifest exist
      2. Legacy Meshy pack ``assets/avatar/glb_frames/`` for Meshy ids
    """
    mid = normalize_avatar_model_id(model_id)
    pack = avatar_model_frames_dir(mid)
    if is_valid_sprite_pack(pack):
        return pack
    if uses_shared_meshy_frames(mid):
        legacy = vision_avatar_glb_frames_dir()
        if is_valid_sprite_pack(legacy) or (legacy / "manifest.json").is_file():
            # Meshy manifest may list clip paths even if helper is strict
            if (legacy / "clips").is_dir() and (legacy / "manifest.json").is_file():
                return legacy
    return None


def list_avatar_models() -> list[tuple[str, str]]:
    """Return ``[(model_id, label), ...]`` for GLBs and sprite-only packs.

    Scans ``models/*.glb`` (non-recursive, skips ``meshy_raw/``) and
    ``model_frames/<id>/`` packs with ``clips/`` + ``manifest.json``.
    Stable order: known ids first, then alphabetical.
    """
    root = avatar_models_dir()
    found: dict[str, str] = {}
    if root.is_dir():
        for path in sorted(root.glob("*.glb")):
            if not path.is_file():
                continue
            stem = path.stem
            found[stem] = _humanize_stem(stem)
    frames_root = avatar_model_frames_root()
    if frames_root.is_dir():
        for child in sorted(frames_root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if not is_valid_sprite_pack(child):
                continue
            stem = child.name
            found.setdefault(stem, _humanize_stem(stem))
    # Ensure default id appears even if file briefly missing (UI still usable)
    if DEFAULT_AVATAR_MODEL_ID not in found:
        found[DEFAULT_AVATAR_MODEL_ID] = _KNOWN_LABELS[DEFAULT_AVATAR_MODEL_ID]
    preferred = [
        DEFAULT_AVATAR_MODEL_ID,
        "vision_futuristic",
        "vision_avatar_cyborg_source",
        "vision_avatar_rigged_v1",
    ]
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for mid in preferred:
        if mid in found:
            ordered.append((mid, found[mid]))
            seen.add(mid)
    for mid in sorted(found.keys()):
        if mid not in seen:
            ordered.append((mid, found[mid]))
            seen.add(mid)
    return ordered

def avatar_model_label(model_id: str) -> str:
    mid = normalize_avatar_model_id(model_id)
    for mid_i, label in list_avatar_models():
        if mid_i == mid:
            return label
    return _humanize_stem(mid)

def avatar_model_id_from_label(label: str) -> str:
    text = (label or "").strip()
    for mid, lab in list_avatar_models():
        if lab == text or mid == text:
            return mid
    return DEFAULT_AVATAR_MODEL_ID

def avatar_model_glb_path(model_id: str) -> Path:
    mid = normalize_avatar_model_id(model_id)
    primary = avatar_models_dir() / f"{mid}.glb"
    if primary.is_file():
        return primary
    if mid == DEFAULT_AVATAR_MODEL_ID:
        legacy = avatar_models_dir() / "vision.glb"
        if legacy.is_file():
            return legacy
    return primary

def uses_shared_meshy_frames(model_id: str) -> bool:
    return normalize_avatar_model_id(model_id) in _MESHY_FRAME_PACK_IDS

def resolve_avatar_preview_png(model_id: str) -> Optional[Path]:
    """Best available still for a non-Meshy (or fallback) model."""
    mid = normalize_avatar_model_id(model_id)
    candidates = [
        avatar_model_frames_dir(mid) / "preview.png",
        avatar_model_frames_dir(mid) / "state_idle.png",
        avatar_models_dir() / f"{mid}_preview.png",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None

def sanitize_avatar_model_stem(name: str) -> str:
    """Safe filesystem stem for imported GLBs (no overwrite of Meshy default)."""
    stem = Path(name or "").stem.strip()
    stem = _SAFE_STEM_RE.sub("_", stem).strip("_-").lower()
    if not stem:
        stem = "avatar_custom"
    # Avoid clobbering canonical Meshy / known pack ids accidentally
    reserved = {
        "vision_avatar_v1",
        "vision",
        "vision_avatar_rigged_v1",
        "meshy",
        "default",
    }
    if stem in reserved:
        stem = f"{stem}_import"
    return stem[:80]

def _unique_model_stem(preferred: str) -> str:
    base = sanitize_avatar_model_stem(preferred)
    root = avatar_models_dir()
    candidate = base
    n = 2
    while (root / f"{candidate}.glb").is_file():
        candidate = f"{base}_{n}"
        n += 1
    return candidate

def _write_placeholder_preview(model_id: str) -> Path:
    """Simple labeled placeholder when Blender preview is unavailable."""
    from PIL import Image, ImageDraw
    out_dir = avatar_model_frames_dir(model_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "preview.png"
    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([96, 64, 416, 384], fill=(28, 36, 48, 255), outline=(0, 182, 255, 220), width=3)
    d.ellipse([190, 170, 230, 210], fill=(0, 182, 255, 255))
    d.ellipse([282, 170, 322, 210], fill=(0, 182, 255, 255))
    label = _humanize_stem(model_id)[:28]
    d.text((256, 430), label, fill=(180, 200, 220, 255), anchor="mm")
    img.save(out)
    return out

def try_render_avatar_preview(model_id: str, *, timeout_s: float = 180.0) -> Optional[Path]:
    """Headless Blender still → model_frames/<id>/preview.png; None on failure."""
    mid = normalize_avatar_model_id(model_id)
    glb = avatar_model_glb_path(mid)
    if not glb.is_file():
        return None
    blender = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
    script = resource_path("tools", "blender_avatar", "render_model_preview.py")
    if not blender.is_file() or not script.is_file():
        logger.info("Blender preview unavailable for %s — using placeholder", mid)
        return _write_placeholder_preview(mid)
    try:
        proc = subprocess.run(
            [
                str(blender),
                "--background",
                "--python",
                str(script),
                "--",
                "--model",
                mid,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        preview = resolve_avatar_preview_png(mid)
        if proc.returncode == 0 and preview is not None:
            return preview
        logger.warning(
            "Blender preview failed for %s (code=%s): %s",
            mid,
            proc.returncode,
            (proc.stderr or proc.stdout or "")[-400:],
        )
    except Exception as exc:
        logger.warning("Blender preview error for %s: %s", mid, exc)
    existing = resolve_avatar_preview_png(mid)
    if existing is not None:
        return existing
    return _write_placeholder_preview(mid)

def import_avatar_glb(
    source: Path | str,
    *,
    render_preview: bool = False,
) -> tuple[str, Path]:
    """Copy a user-selected ``.glb`` into ``assets/avatar/models/``.

    Returns ``(model_id, dest_path)``. Does not overwrite Meshy/rigged sources
    unless the sanitized stem already differs; collisions get a numeric suffix.
    Never overwrites ``vision_avatar_v1.glb`` / ``vision_avatar_rigged_v1.glb``.

    By default writes a placeholder preview (fast UI). Pass ``render_preview=True``
    to run Blender headless (slow) synchronously.
    """
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(f"GLB non trovato: {src}")
    if src.suffix.lower() != ".glb":
        raise ValueError("Selezionare un file .glb")
    root = avatar_models_dir()
    root.mkdir(parents=True, exist_ok=True)
    stem = _unique_model_stem(src.stem)
    dest = root / f"{stem}.glb"
    # Extra guard: never clobber protected models even if stem logic changes
    protected = {
        root / "vision_avatar_v1.glb",
        root / "vision_avatar_rigged_v1.glb",
    }
    if dest.resolve() in {p.resolve() for p in protected if p.exists()}:
        stem = _unique_model_stem(f"{src.stem}_custom")
        dest = root / f"{stem}.glb"
    shutil.copy2(src, dest)
    logger.info("Imported avatar GLB → %s", dest)
    try:
        if render_preview:
            try_render_avatar_preview(stem)
        else:
            _write_placeholder_preview(stem)
    except Exception as exc:
        logger.warning("Preview generation after import failed: %s", exc)
        try:
            _write_placeholder_preview(stem)
        except Exception:
            pass
    return stem, dest


def sanitize_sprite_pack_stem(name: str) -> str:
    """Safe ``model_id`` for sprite packs — may match an existing GLB stem."""
    stem = Path(name or "").stem.strip()
    stem = _SAFE_STEM_RE.sub("_", stem).strip("_-").lower()
    if not stem:
        stem = "avatar_sprite"
    return stem[:80]


def _count_clip_frames(clip_dir: Path) -> int:
    """Count contiguous zero-padded PNG frames starting at ``00.png``."""
    if not clip_dir.is_dir():
        return 0
    n = 0
    while True:
        found = False
        for pad in (2, 3, 4):
            if (clip_dir / f"{n:0{pad}d}.png").is_file():
                found = True
                break
        if not found:
            break
        n += 1
    return n


def build_sprite_manifest(
    model_id: str,
    pack_root: Path,
    *,
    fps: int = DEFAULT_SPRITE_FPS,
    size: tuple[int, int] = (1024, 1024),
) -> dict[str, Any]:
    """Build compact manifest from on-disk ``clips/<state>/NN.png`` layout."""
    clips_meta: dict[str, Any] = {}
    clips_root = pack_root / "clips"
    known = list(REQUIRED_SPRITE_CLIP_STATES) + list(OPTIONAL_SPRITE_CLIP_STATES)
    discovered: list[str] = []
    if clips_root.is_dir():
        for child in sorted(clips_root.iterdir()):
            if child.is_dir() and child.name not in known:
                discovered.append(child.name)
    for name in known + discovered:
        count = _count_clip_frames(clips_root / name)
        if count <= 0:
            continue
        loop = name not in OPTIONAL_SPRITE_CLIP_STATES
        clips_meta[name] = {"frames": count, "loop": loop}
    return {
        "model_id": model_id,
        "fps": int(fps),
        "size": [int(size[0]), int(size[1])],
        "clips": clips_meta,
    }


def write_sprite_manifest(pack_root: Path, data: dict[str, Any]) -> Path:
    path = pack_root / "manifest.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def import_avatar_sprite_pack(
    source: Path | str,
    *,
    model_id: Optional[str] = None,
) -> tuple[str, Path]:
    """Copy a sprite pack folder into ``assets/avatar/model_frames/<id>/``.

    Source must contain ``clips/`` with PNG sequences. ``manifest.json`` is
    optional — generated from frame counts when missing. No GLB required
    (sprite-only models appear in the Supervisor dropdown).

    Never writes into ``assets/avatar/glb_frames/`` (Meshy legacy pack).
    """
    src = Path(source)
    if not src.is_dir():
        raise FileNotFoundError(f"Cartella pack non trovata: {src}")
    clips_src = src / "clips"
    if not clips_src.is_dir():
        raise ValueError(
            "La cartella deve contenere clips/ (es. clips/idle/00.png). "
            "Vedi assets/avatar/model_frames/SPRITE_PACK_SPEC.md"
        )
    if not any(clips_src.glob("*/*.png")):
        raise ValueError("Nessun frame PNG trovato sotto clips/<stato>/")

    mid = (model_id or "").strip()
    manifest_src = src / "manifest.json"
    if not mid and manifest_src.is_file():
        try:
            data = json.loads(manifest_src.read_text(encoding="utf-8"))
            mid = str(data.get("model_id") or "").strip()
        except Exception:
            mid = ""
    if not mid:
        mid = src.name
    mid = sanitize_sprite_pack_stem(mid)
    if mid in ("glb_frames", "bible", "reference"):
        mid = f"avatar_{mid}"

    dest = avatar_model_frames_dir(mid)
    dest.mkdir(parents=True, exist_ok=True)

    # Copy clips (merge/overwrite frames for this model_id)
    clips_dest = dest / "clips"
    clips_dest.mkdir(parents=True, exist_ok=True)
    for state_dir in clips_src.iterdir():
        if not state_dir.is_dir():
            continue
        target = clips_dest / state_dir.name
        target.mkdir(parents=True, exist_ok=True)
        for png in state_dir.glob("*.png"):
            shutil.copy2(png, target / png.name)

    preview_src = src / "preview.png"
    if preview_src.is_file():
        shutil.copy2(preview_src, dest / "preview.png")
    elif not (dest / "preview.png").is_file():
        # Use first idle frame as preview when available
        idle0 = clips_dest / "idle" / "00.png"
        if idle0.is_file():
            shutil.copy2(idle0, dest / "preview.png")

    if manifest_src.is_file():
        shutil.copy2(manifest_src, dest / "manifest.json")
        # Ensure model_id matches destination folder
        try:
            data = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
            data["model_id"] = mid
            if "fps" not in data:
                data["fps"] = DEFAULT_SPRITE_FPS
            if "clips" not in data or not data["clips"]:
                data = build_sprite_manifest(
                    mid, dest, fps=int(data.get("fps") or DEFAULT_SPRITE_FPS)
                )
            write_sprite_manifest(dest, data)
        except Exception as exc:
            logger.warning("Sprite manifest normalize failed: %s — regenerating", exc)
            write_sprite_manifest(dest, build_sprite_manifest(mid, dest))
    else:
        write_sprite_manifest(dest, build_sprite_manifest(mid, dest))

    if not is_valid_sprite_pack(dest):
        raise RuntimeError(f"Pack sprite non valido dopo import: {dest}")
    logger.info("Imported avatar sprite pack → %s", dest)
    return mid, dest
