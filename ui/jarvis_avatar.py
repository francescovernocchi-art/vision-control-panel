"""Compat shim — VISION Character Bible is the only avatar model.

All historical JarvisAvatar imports resolve to VisionAvatar (same android).
Do not load assets/jarvis frontal helmet frames in UI.
"""

from __future__ import annotations

from ui.vision_avatar import (  # noqa: F401
    LEVEL_FULL,
    LEVEL_OFF,
    LEVEL_REDUCED,
    STATE_ALERT,
    STATE_IDLE,
    STATE_LISTENING,
    STATE_OFFLINE,
    STATE_PROCESSING,
    STATE_SPEAKING,
    VisionAvatar,
    VisionAvatar as JarvisAvatar,
    VisionAvatarPanel,
    VisionAvatarPanel as JarvisAvatarPanel,
    map_supervisor_state,
    map_supervisor_state as map_jarvis_state,
)

__all__ = [
    "JarvisAvatar",
    "JarvisAvatarPanel",
    "VisionAvatar",
    "VisionAvatarPanel",
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
    "map_jarvis_state",
]
