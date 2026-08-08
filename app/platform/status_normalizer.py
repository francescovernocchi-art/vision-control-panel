"""ModuleStatusNormalizer — mapping stati runtime → Health coerente."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Health statuses ammessi
HEALTH_STATUSES = frozenset(
    {
        "ONLINE",
        "OFFLINE",
        "DEGRADED",
        "ERROR",
        "DISABLED",
        "STARTING",
        "STOPPING",
    }
)

# Runtime / module statuses → health
_STATUS_MAP = {
    "ONLINE": "ONLINE",
    "OFFLINE": "OFFLINE",
    "DEGRADED": "DEGRADED",
    "ERROR": "ERROR",
    "DISABLED": "DISABLED",
    "STARTING": "STARTING",
    "STOPPING": "STOPPING",
    "IN_DEVELOPMENT": "DEGRADED",
}


@dataclass(frozen=True)
class NormalizedStatus:
    health_status: str
    lifecycle: str
    metadata: dict[str, Any]


class ModuleStatusNormalizer:
    """
    IN_DEVELOPMENT → health DEGRADED + metadata.lifecycle=IN_DEVELOPMENT
    Unknown → ERROR + metadata.raw_status
    """

    @staticmethod
    def normalize(status: str) -> NormalizedStatus:
        raw = str(status or "OFFLINE").strip().upper() or "OFFLINE"
        mapped = _STATUS_MAP.get(raw, "ERROR")
        meta: dict[str, Any] = {"lifecycle": raw}
        if raw == "IN_DEVELOPMENT":
            meta["module_status"] = "IN_DEVELOPMENT"
        if raw not in _STATUS_MAP:
            meta["raw_status"] = raw
        return NormalizedStatus(health_status=mapped, lifecycle=raw, metadata=meta)


def normalize_health_status(status: str) -> tuple[str, dict]:
    """Compat helper: (health_status, metadata)."""
    n = ModuleStatusNormalizer.normalize(status)
    return n.health_status, dict(n.metadata)
