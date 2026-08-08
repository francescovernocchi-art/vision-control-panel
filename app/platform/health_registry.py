"""HealthRegistry — stato salute componenti piattaforma (+ history in-memory)."""

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
    def __init__(self, *, history_limit: int = 50) -> None:
        self._lock = threading.RLock()
        self._items: dict[str, HealthSnapshot] = {}
        self._history: list[dict] = []
        self._history_limit = max(10, int(history_limit))

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
            if st in ("ERROR", "OFFLINE", "DISABLED"):
                ok = False
            else:
                ok = True
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
            prev = self._items.get(target_id)
            self._items[target_id] = snap
            if prev is None or prev.status != snap.status or prev.message != snap.message:
                self._history.append(
                    {
                        "target_id": target_id,
                        "from": prev.status if prev else None,
                        "to": snap.status,
                        "at": snap.checked_at,
                        "message": snap.message,
                    }
                )
                if len(self._history) > self._history_limit:
                    self._history = self._history[-self._history_limit :]
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

    def history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._history[-max(1, limit) :])

    def snapshot(self) -> list[dict]:
        """Snapshot globale componenti (dual-write view)."""
        out = []
        for item in self.list():
            d = item.to_dict()
            out.append(
                {
                    "component_id": d["target_id"],
                    "status": d["status"],
                    "ok": d["ok"],
                    "message": d["message"],
                    "updated_at": d["checked_at"],
                    "target_type": d["target_type"],
                    "metadata": d["metadata"],
                }
            )
        return out

    def summary(self) -> dict:
        items = self.list()
        return {
            "count": len(items),
            "by_status": {
                s: sum(1 for i in items if i.status == s) for s in sorted(VALID_STATUS)
            },
            "targets": [i.to_dict() for i in items],
            "snapshot": self.snapshot(),
            "history_size": len(self._history),
        }
