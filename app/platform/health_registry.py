"""HealthRegistry — dual-write view + overall health + history."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Optional

from app.platform.descriptors import HealthReport, HealthSnapshot
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

# Componenti "required" per overall health (opzionali non forzano ERROR se OFFLINE)
REQUIRED_COMPONENTS = frozenset({"core", "enispace"})


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
            ok = st not in ("ERROR", "OFFLINE", "DISABLED")
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

    def reports(self) -> list[HealthReport]:
        return [i.to_report() for i in self.list()]

    def compute_overall_status(self) -> str:
        """
        Regole conservative (documentate):
        1. Se ``core`` è ERROR → ERROR
        2. Se ``core`` è OFFLINE → ERROR (piattaforma non operativa)
        3. Se un componente REQUIRED è ERROR → ERROR
        4. Se un REQUIRED è OFFLINE/DISABLED → ERROR
        5. Se qualsiasi componente è DEGRADED / STARTING / STOPPING → DEGRADED
        6. Se tutti ONLINE → ONLINE
        7. Altrimenti OFFLINE

        Moduli opzionali OFFLINE (es. coin_transport non avviato) non forzano ERROR
        se non sono in REQUIRED_COMPONENTS; se sono DEGRADED (IN_DEVELOPMENT) → DEGRADED.
        """
        items = {i.target_id: i for i in self.list()}
        if not items:
            return "OFFLINE"

        core = items.get("core")
        if core is not None:
            if core.status == "ERROR":
                return "ERROR"
            if core.status == "OFFLINE":
                return "ERROR"

        for req in REQUIRED_COMPONENTS:
            comp = items.get(req)
            if comp is None:
                continue
            if comp.status in ("ERROR", "OFFLINE", "DISABLED"):
                return "ERROR"

        for comp in items.values():
            if comp.status == "ERROR" and comp.target_id in REQUIRED_COMPONENTS:
                return "ERROR"

        for comp in items.values():
            if comp.status in ("DEGRADED", "STARTING", "STOPPING"):
                return "DEGRADED"

        if all(c.status == "ONLINE" for c in items.values()):
            return "ONLINE"

        # mix di ONLINE + opzionali DISABLED/OFFLINE
        if any(c.status == "ONLINE" for c in items.values()):
            if any(c.status in ("OFFLINE", "DISABLED") for c in items.values()):
                return "DEGRADED"
            return "ONLINE"
        return "OFFLINE"

    def get_health_snapshot(self) -> dict:
        reports = self.reports()
        statuses = [r.status for r in reports]
        last_updated = ""
        if reports:
            last_updated = max((r.updated_at for r in reports if r.updated_at), default="")
        return {
            "overall_status": self.compute_overall_status(),
            "components": [r.to_dict() for r in reports],
            "online_count": sum(1 for s in statuses if s == "ONLINE"),
            "degraded_count": sum(1 for s in statuses if s == "DEGRADED"),
            "error_count": sum(1 for s in statuses if s == "ERROR"),
            "offline_count": sum(1 for s in statuses if s in ("OFFLINE", "DISABLED")),
            "last_updated": last_updated,
        }

    def snapshot(self) -> list[dict]:
        """Compat: lista componenti (HealthReport dict)."""
        return [r.to_dict() for r in self.reports()]

    def summary(self) -> dict:
        hs = self.get_health_snapshot()
        return {
            "count": len(hs["components"]),
            "overall_status": hs["overall_status"],
            "by_status": {
                s: sum(1 for i in self.list() if i.status == s) for s in sorted(VALID_STATUS)
            },
            "targets": [i.to_dict() for i in self.list()],
            "snapshot": hs,
            "history_size": len(self._history),
        }
