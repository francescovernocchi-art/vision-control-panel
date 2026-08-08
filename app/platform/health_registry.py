"""HealthRegistry — stato salute componenti piattaforma."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from app.platform.descriptors import HealthSnapshot
from utils.logger import get_logger

logger = get_logger("platform.health")

VALID_STATUS = frozenset(
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


class HealthRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, HealthSnapshot] = {}

    def update(
        self,
        target_id: str,
        status: str,
        *,
        target_type: str = "module",
        ok: Optional[bool] = None,
        message: str = "",
        metadata: Optional[dict] = None,
    ) -> HealthSnapshot:
        st = str(status or "OFFLINE").upper()
        if st not in VALID_STATUS:
            st = "ERROR"
            message = message or f"status non valido: {status}"
        if ok is None:
            ok = st in ("ONLINE", "STARTING", "STOPPING", "DEGRADED")
            if st == "DEGRADED":
                ok = True
            if st in ("ERROR", "OFFLINE", "DISABLED"):
                ok = False
        snap = HealthSnapshot(
            target_id=target_id,
            target_type=target_type,
            status=st,
            ok=bool(ok),
            message=message,
            checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._items[target_id] = snap
        logger.info(
            "Health updated target=%s type=%s status=%s",
            target_id,
            target_type,
            st,
        )
        return snap

    def get(self, target_id: str) -> Optional[HealthSnapshot]:
        with self._lock:
            return self._items.get(target_id)

    def list(self) -> list[HealthSnapshot]:
        with self._lock:
            return list(self._items.values())

    def summary(self) -> dict:
        items = self.list()
        return {
            "count": len(items),
            "by_status": {
                s: sum(1 for i in items if i.status == s) for s in sorted(VALID_STATUS)
            },
            "targets": [i.to_dict() for i in items],
        }
