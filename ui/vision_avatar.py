"""VISION Avatar — brand android ufficiale (pseudo-3D, GLB-ready).

Official model: assets/reference/vision_android_profile_hero.png
Same android in every UI surface. States change lights/HUD / yaw only —
never a different face, helmet, or robot.
When assets/avatar/models/vision.glb arrives, swap via create_avatar_renderer().
"""

from __future__ import annotations

import logging
import math
import time
from typing import Callable, Optional

import customtkinter as ctk
from PIL import Image

from ui.avatar_renderer import (
    LEVEL_FULL,
    LEVEL_OFF,
    LEVEL_REDUCED,
    STATE_ALERT,
    STATE_IDLE,
    STATE_LISTENING,
    STATE_OFFLINE,
    STATE_PROCESSING,
    STATE_SPEAKING,
    AvatarRenderer,
    create_avatar_renderer,
)
from utils.avatar_models import (
    AVATAR_MODE_3D,
    DEFAULT_AVATAR_MODE,
    DEFAULT_AVATAR_MODEL_ID,
    normalize_avatar_mode,
    normalize_avatar_model_id,
)
from ui.theme import (
    AVATAR_DISPLAY_SIZE,
    BG,
    ERROR,
    GLOW,
    MUTED,
    PRIMARY,
    SUCCESS,
    TEXT,
    WARNING,
    font_family,
)

logger = logging.getLogger("ui.vision_avatar")

# Re-export for jarvis_avatar / callers
__all__ = [
    "VisionAvatar",
    "VisionAvatarPanel",
    "JarvisAvatar",
    "JarvisAvatarPanel",
    "LEVEL_FULL",
    "LEVEL_REDUCED",
    "LEVEL_OFF",
    "STATE_IDLE",
    "STATE_LISTENING",
    "STATE_PROCESSING",
    "STATE_SPEAKING",
    "STATE_ALERT",
    "STATE_OFFLINE",
    "map_supervisor_state",
]

_REACT_META: dict[str, tuple[float, str, str]] = {
    # event -> (yaw_target, badge, color_key)
    "ack": (0.35, "ACK", "glow"),
    "search": (-0.55, "SEARCH", "primary"),
    "download": (0.45, "DOWNLOAD", "primary"),
    "print": (0.55, "PRINT", "primary"),
    "mail": (-0.4, "MAIL", "glow"),
    "login": (0.3, "LOGIN", "glow"),
    "error": (-0.7, "ERROR", "error"),
    "success": (0.25, "OK", "success"),
}

_COLOR = {
    "glow": GLOW,
    "primary": PRIMARY,
    "error": ERROR,
    "success": SUCCESS,
}


def map_supervisor_state(raw: str) -> str:
    """Map runtime/supervisor strings → Character Bible visual state."""
    s = (raw or "").strip().upper()
    if s in ("SPEAKING", "TTS", "TALKING", "PARLANDO"):
        return STATE_SPEAKING
    if s in ("LISTENING", "LISTEN", "ASCOLTO"):
        return STATE_LISTENING
    if s in (
        "PROCESSING",
        "WORKING",
        "BUSY",
        "ANALISI",
        "DOWNLOAD",
        "STAMPA",
        "ACCESSO",
        "MAIL",
    ):
        return STATE_PROCESSING
    if s in (
        "ALERT",
        "ERROR",
        "ERRORE",
        "FAILED",
        "INTERVENTO",
        "NEEDS_ATTENTION",
        "ATTENTION",
    ):
        return STATE_ALERT
    if s in (
        "OFFLINE",
        "",
        "OFF",
        "DISABLED",
        "INACTIVE",
        "DISATTIVATO",
        "DISATTIVATA",
        "STOPPED",
    ):
        return STATE_OFFLINE
    return STATE_IDLE


class VisionAvatar(ctk.CTkFrame):
    """Unique VISION Character Bible avatar — pseudo-3D yaw + command react."""

    def __init__(
        self,
        master,
        *,
        size: int = AVATAR_DISPLAY_SIZE,
        level_provider: Optional[Callable[[], str]] = None,
        show_caption: bool = True,
        pose: str = "auto",
        renderer: Optional[AvatarRenderer] = None,
        model_id: Optional[str] = None,
        mode: Optional[str] = None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self._display = max(180, min(360, int(size)))
        self._level_provider = level_provider
        self._level = LEVEL_FULL
        self._state = STATE_IDLE
        self._raw = "OFFLINE"
        self._pose = pose
        self._t0 = time.perf_counter()
        self._job: Optional[str] = None
        self._destroyed = False
        self._static = False
        self._ctk_image = None
        self._wave_phase = 0.0
        self._model_id = normalize_avatar_model_id(model_id)
        self._mode = normalize_avatar_mode(mode)

        self._yaw = 0.0
        self._yaw_target = 0.0
        self._reaction = 0.0
        self._react_until = 0.0
        self._react_badge = ""
        self._react_color = GLOW
        self._saved_badge = ("", MUTED)

        try:
            self._renderer = renderer or create_avatar_renderer(
                self._model_id, mode=self._mode
            )
        except Exception as exc:
            logger.warning("Avatar renderer init failed: %s", exc)
            self._renderer = create_avatar_renderer(
                self._model_id, mode=self._mode
            )

        self._label = ctk.CTkLabel(self, text="", fg_color=BG)
        self._label.pack(padx=4, pady=(4, 2))

        self._caption = ctk.CTkLabel(
            self,
            text="IDLE",
            font=ctk.CTkFont(family=font_family(), size=12, weight="bold"),
            text_color=MUTED,
        )
        if show_caption:
            self._caption.pack(pady=(2, 4))

        self._badge = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family=font_family(), size=11, weight="bold"),
            text_color=WARNING,
        )
        self._badge.pack(pady=(0, 2))

        try:
            self._render(force=True)
            self._schedule()
        except Exception as exc:
            logger.warning("VisionAvatar init fallback: %s", exc)
            self._static = True
            self._label.configure(
                text="VISION",
                font=ctk.CTkFont(size=28, weight="bold"),
                text_color=PRIMARY,
                width=self._display,
                height=self._display,
            )

    def set_level(self, level: str) -> None:
        v = (level or LEVEL_FULL).strip().lower()
        if v in ("complete", "full", "completo"):
            self._level = LEVEL_FULL
        elif v in ("reduced", "ridotte", "ridotta", "low"):
            self._level = LEVEL_REDUCED
        elif v in ("off", "disattivate", "disabled", "none", "0"):
            self._level = LEVEL_OFF
        else:
            self._level = LEVEL_FULL
        self._render(force=True)
        if self._level != LEVEL_OFF and not self._static:
            self._schedule()

    def set_model(self, model_id: Optional[str]) -> None:
        """Swap avatar GLB / frame pack at runtime (Supervisor setting)."""
        mid = normalize_avatar_model_id(model_id)
        self._model_id = mid
        try:
            self._renderer = create_avatar_renderer(mid, mode=self._mode)
            self._static = False
            logger.info(
                "VisionAvatar model → %s mode=%s (%s)",
                mid,
                self._mode,
                type(self._renderer).__name__,
            )
        except Exception as exc:
            logger.warning("VisionAvatar set_model(%s) failed: %s", mid, exc)
            self._renderer = create_avatar_renderer(
                DEFAULT_AVATAR_MODEL_ID, mode=self._mode
            )
            self._model_id = DEFAULT_AVATAR_MODEL_ID
        self._render(force=True)
        if self._level != LEVEL_OFF and not self._static:
            self._schedule()

    def set_mode(self, mode: Optional[str]) -> None:
        """Switch Avatar 3D (GLB) vs Avatar PNG (Character Bible) at runtime."""
        self._mode = normalize_avatar_mode(mode)
        try:
            self._renderer = create_avatar_renderer(self._model_id, mode=self._mode)
            self._static = False
            logger.info(
                "VisionAvatar mode → %s (%s)",
                self._mode,
                type(self._renderer).__name__,
            )
        except Exception as exc:
            logger.warning("VisionAvatar set_mode(%s) failed: %s", mode, exc)
            self._mode = AVATAR_MODE_3D
            self._renderer = create_avatar_renderer(
                self._model_id, mode=DEFAULT_AVATAR_MODE
            )
        self._render(force=True)
        if self._level != LEVEL_OFF and not self._static:
            self._schedule()

    def set_renderer(self, renderer: AvatarRenderer) -> None:
        self._renderer = renderer
        self._static = False
        self._render(force=True)
        if self._level != LEVEL_OFF:
            self._schedule()

    def set_state(self, state: str, *, busy: bool = False, speaking: bool = False) -> None:
        if self._destroyed:
            return
        self._raw = (state or "").strip() or "OFFLINE"
        visual = map_supervisor_state(self._raw)
        if speaking:
            visual = STATE_SPEAKING
        elif busy and visual in (STATE_IDLE, STATE_OFFLINE):
            visual = STATE_PROCESSING
        self._state = visual
        captions = {
            STATE_IDLE: "IDLE",
            STATE_LISTENING: "IN ASCOLTO",
            STATE_PROCESSING: "IN LAVORAZIONE",
            STATE_SPEAKING: "VISION STA PARLANDO",
            STATE_ALERT: "ALERT",
            STATE_OFFLINE: "OFFLINE",
        }
        self._caption.configure(text=captions.get(visual, visual))
        if time.perf_counter() < self._react_until:
            # Keep reaction badge until burst ends
            pass
        elif visual == STATE_PROCESSING:
            self._badge.configure(text="PROCESSING", text_color=PRIMARY)
            self._saved_badge = ("PROCESSING", PRIMARY)
        elif visual == STATE_SPEAKING:
            self._badge.configure(text="SPEAKING", text_color=GLOW)
            self._saved_badge = ("SPEAKING", GLOW)
        elif visual == STATE_LISTENING:
            self._badge.configure(text="LISTENING", text_color=GLOW)
            self._saved_badge = ("LISTENING", GLOW)
        elif visual == STATE_ALERT:
            self._badge.configure(text="ALERT", text_color=ERROR)
            self._saved_badge = ("ALERT", ERROR)
        else:
            self._badge.configure(text="")
            self._saved_badge = ("", MUTED)
        self._update_idle_yaw_target()
        self._render(force=True)

    def react(self, event: str, *, intensity: float = 1.0) -> None:
        """Burst yaw + glow + badge for UI commands (search, download, …)."""
        if self._destroyed or self._level == LEVEL_OFF:
            return
        key = (event or "ack").strip().lower()
        yaw_t, badge, color_key = _REACT_META.get(key, _REACT_META["ack"])
        intensity = max(0.2, min(1.5, float(intensity)))
        self._yaw_target = max(-1.0, min(1.0, yaw_t * intensity))
        self._reaction = intensity
        self._react_until = time.perf_counter() + (1.2 + 0.5 * intensity)
        self._react_badge = badge
        self._react_color = _COLOR.get(color_key, GLOW)
        self._badge.configure(text=badge, text_color=self._react_color)
        # Trigger armature react clip when available
        try:
            side = "left" if yaw_t < 0 else "right"
            trigger = getattr(self._renderer, "trigger_react_clip", None)
            if callable(trigger):
                trigger(side)
        except Exception:
            pass
        if self._static:
            self._static = False
        self._render(force=True)
        self._schedule()

    def pause_animation(self) -> None:
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        self._static = True

    def resume_animation(self) -> None:
        self._static = False
        self._schedule()

    def _refresh_level(self) -> None:
        if not self._level_provider:
            return
        try:
            v = (self._level_provider() or LEVEL_FULL).strip().lower()
        except Exception:
            return
        if v in ("complete", "full", "completo"):
            self._level = LEVEL_FULL
        elif v in ("reduced", "ridotte", "ridotta", "low"):
            self._level = LEVEL_REDUCED
        elif v in ("off", "disattivate", "disabled", "none", "0"):
            self._level = LEVEL_OFF
        else:
            self._level = LEVEL_FULL

    def _update_idle_yaw_target(self) -> None:
        if time.perf_counter() < self._react_until:
            return
        if self._level in (LEVEL_OFF, LEVEL_REDUCED):
            self._yaw_target = 0.0
            return
        if self._state == STATE_LISTENING:
            self._yaw_target = -0.22
        elif self._state == STATE_IDLE:
            # slow wander driven in _tick
            pass
        else:
            self._yaw_target = 0.0

    def _interval_ms(self) -> int:
        if self._level == LEVEL_OFF:
            return 2000
        if time.perf_counter() < self._react_until:
            return 83  # match clip bake (~12 fps)
        # Match glb_frames clip fps (12) — avoid oversampling / stutter
        if self._level == LEVEL_FULL:
            return 83
        if self._level == LEVEL_REDUCED:
            return 200
        return 120

    def _schedule(self) -> None:
        if self._destroyed or self._static:
            return
        if self._level == LEVEL_OFF and time.perf_counter() >= self._react_until:
            return
        if self._job:
            try:
                self.after_cancel(self._job)
            except Exception:
                pass
        self._job = self.after(self._interval_ms(), self._tick)

    def _tick(self) -> None:
        self._job = None
        if self._destroyed:
            return
        try:
            if not bool(self.winfo_ismapped()):
                self._job = self.after(700, self._tick)
                return
            self._refresh_level()
            now = time.perf_counter()
            t = now - self._t0

            # Reaction decay
            if now < self._react_until:
                remain = self._react_until - now
                self._reaction = max(0.0, remain / 1.6)
            elif self._reaction > 0:
                self._reaction = 0.0
                self._update_idle_yaw_target()
                txt, col = self._saved_badge
                self._badge.configure(text=txt, text_color=col)

            # Soft yaw targets only for react / fallback turntable.
            # GlbTurntable clips already bake head motion — keep wander tiny.
            if (
                self._level == LEVEL_FULL
                and self._state == STATE_IDLE
                and now >= self._react_until
            ):
                self._yaw_target = 0.12 * math.sin(t * 0.28)
            elif (
                self._level == LEVEL_FULL
                and self._state == STATE_LISTENING
                and now >= self._react_until
            ):
                self._yaw_target = -0.08 + 0.04 * math.sin(t * 0.7)
            elif (
                self._level == LEVEL_FULL
                and self._state == STATE_SPEAKING
                and now >= self._react_until
            ):
                self._yaw_target = 0.0

            # Ease yaw toward target
            if self._level == LEVEL_FULL or now < self._react_until:
                blend = 0.18 if now < self._react_until else 0.08
                self._yaw += (self._yaw_target - self._yaw) * blend
            else:
                self._yaw *= 0.85

            if self._level == LEVEL_OFF and now >= self._react_until:
                self._render(force=True)
                return

            self._wave_phase += 0.4
            self._render()
        except Exception as exc:
            logger.warning("VisionAvatar tick: %s", exc)
            self._static = True
            return
        self._schedule()

    def _render(self, force: bool = False) -> None:
        _ = force
        self._refresh_level()
        t = time.perf_counter() - self._t0
        try:
            img = self._renderer.compose(
                state=self._state,
                yaw=self._yaw,
                t=t,
                level=self._level,
                wave_phase=self._wave_phase,
                reaction=self._reaction,
            )
        except Exception as exc:
            logger.warning("Avatar compose failed: %s", exc)
            return
        self._show(img)

    def _show(self, img) -> None:
        s = self._display
        hi = img.resize((s * 2, s * 2), Image.Resampling.LANCZOS)
        cimg = ctk.CTkImage(light_image=hi, dark_image=hi, size=(s, s))
        self._ctk_image = cimg
        self._label.configure(image=cimg, text="")


class VisionAvatarPanel(ctk.CTkFrame):
    """Supervisor tab panel — same Character Bible VisionAvatar."""

    def __init__(
        self,
        master,
        *,
        size: int = 260,
        level_provider: Optional[Callable[[], str]] = None,
        model_id: Optional[str] = None,
        mode: Optional[str] = None,
        **kwargs,
    ):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, **kwargs)
        self.avatar = VisionAvatar(
            self,
            size=size,
            level_provider=level_provider,
            show_caption=True,
            model_id=model_id,
            mode=mode,
        )
        self.avatar.pack(fill="x")
        self.online_label = ctk.CTkLabel(
            self, text="○ OFFLINE", font=ctk.CTkFont(size=13, weight="bold"), text_color=MUTED
        )
        self.online_label.pack(anchor="w", padx=8, pady=(6, 0))
        self.state_label = ctk.CTkLabel(
            self, text="Stato: OFFLINE", font=ctk.CTkFont(size=12), text_color=TEXT
        )
        self.state_label.pack(anchor="w", padx=8)
        self.meta_label = ctk.CTkLabel(
            self,
            text="Ultimo controllo: —",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            justify="left",
        )
        self.meta_label.pack(anchor="w", padx=8, pady=(0, 8))

    def set_state(self, state: str, *, busy: bool = False, speaking: bool = False) -> None:
        self.avatar.set_state(state, busy=busy, speaking=speaking)

    def set_level(self, level: str) -> None:
        self.avatar.set_level(level)

    def set_model(self, model_id: Optional[str]) -> None:
        self.avatar.set_model(model_id)

    def set_mode(self, mode: Optional[str]) -> None:
        self.avatar.set_mode(mode)

    def react(self, event: str, *, intensity: float = 1.0) -> None:
        self.avatar.react(event, intensity=intensity)

    def pause_animation(self) -> None:
        self.avatar.pause_animation()

    def resume_animation(self) -> None:
        self.avatar.resume_animation()

    def update_from_snapshot(self, snap: dict) -> None:
        active = bool(snap.get("active"))
        state = str(snap.get("state") or "OFFLINE")
        processing = bool(snap.get("processing"))
        self.avatar.set_state(state, busy=processing)
        self.online_label.configure(
            text="● ONLINE" if active else "○ OFFLINE",
            text_color=SUCCESS if active else MUTED,
        )
        self.state_label.configure(text=f"Stato: {state}")
        self.meta_label.configure(
            text=(
                f"In coda: {snap.get('pending', 0)}\n"
                f"In lavorazione: {snap.get('current_job') or '—'}"
            )
        )


# Legacy aliases — force Character Bible everywhere old names are imported
JarvisAvatar = VisionAvatar
JarvisAvatarPanel = VisionAvatarPanel
