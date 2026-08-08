"""ModuleHealthBridge — dual-write stati modulo → HealthRegistry.

Source of truth: ModuleManager / moduli esistenti.
HealthRegistry riceve solo copia normalizzata.
"""

from __future__ import annotations

from typing import Any, Optional

from app.platform.health_registry import HealthRegistry
from utils.logger import get_logger

logger = get_logger("platform.health_bridge")

# Status runtime → status health catalog
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


def normalize_health_status(status: str) -> tuple[str, dict]:
    raw = str(status or "OFFLINE").strip().upper()
    mapped = _STATUS_MAP.get(raw, "ERROR")
    meta: dict[str, Any] = {}
    if raw == "IN_DEVELOPMENT":
        meta["module_status"] = "IN_DEVELOPMENT"
    elif raw not in _STATUS_MAP:
        meta["raw_status"] = raw
    return mapped, meta


class ModuleHealthBridge:
    def __init__(self, health: HealthRegistry) -> None:
        self.health = health
        self._attached = False
        self._manager: Any = None

    def attach(self, module_manager: Any) -> None:
        """Collega un unico listener a ModuleManager.set_status."""
        self._manager = module_manager
        if self._attached:
            return
        add = getattr(module_manager, "add_status_listener", None)
        if callable(add):
            add(self.on_module_status)
            self._attached = True
            logger.info("ModuleHealthBridge attached to ModuleManager")
        else:
            logger.warning(
                "ModuleManager senza add_status_listener — solo sync esplicito disponibile"
            )

    def attach_event_bus(self, event_bus: Any) -> None:
        """Dual-write anche da eventi MODULE_ONLINE / MODULE_OFFLINE."""
        if event_bus is None or not hasattr(event_bus, "subscribe"):
            return

        def _on_online(event: Any) -> None:
            mid = getattr(event, "module", "") or ""
            if mid and mid not in ("core", "assistant", "remote"):
                self.on_module_status(mid, "ONLINE", message=getattr(event, "message", ""))

        def _on_offline(event: Any) -> None:
            mid = getattr(event, "module", "") or ""
            if mid and mid not in ("core", "assistant", "remote"):
                self.on_module_status(mid, "OFFLINE", message=getattr(event, "message", ""))

        try:
            from app.core.event_bus import EventType

            event_bus.subscribe(EventType.MODULE_ONLINE, _on_online)
            event_bus.subscribe(EventType.MODULE_OFFLINE, _on_offline)
            logger.info("ModuleHealthBridge subscribed to EventBus module events")
        except Exception as exc:  # noqa: BLE001
            logger.warning("EventBus attach fallito: %s", exc)

    def on_module_status(
        self,
        module_id: str,
        status: str,
        *,
        message: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        if not module_id:
            return
        health_status, extra = normalize_health_status(status)
        meta = dict(metadata or {})
        meta.update(extra)
        meta["source"] = "dual_write"
        meta["source_of_truth"] = "module_manager"
        self.health.update(
            module_id,
            health_status,
            target_type="module",
            message=message or f"dual-write status={status}",
            metadata=meta,
        )

    def sync_from_manager(self, module_manager: Any = None) -> int:
        """Copia tutti gli stati correnti (non source of truth invertita)."""
        mgr = module_manager or self._manager
        if mgr is None or not hasattr(mgr, "list_modules"):
            return 0
        count = 0
        for info in mgr.list_modules():
            self.on_module_status(
                info.id,
                info.status,
                message="sync_from_manager",
                metadata={"version": getattr(info, "version", "")},
            )
            count += 1
        return count

    def sync_core_and_supervisor(
        self,
        *,
        core: Any = None,
        jarvis: Any = None,
    ) -> None:
        if core is not None:
            online = bool(getattr(core, "is_online", False))
            self.health.update(
                "core",
                "ONLINE" if online else "OFFLINE",
                target_type="core",
                message="dual-write core",
                metadata={"source": "dual_write"},
            )
        if jarvis is not None:
            active = bool(getattr(jarvis, "is_active", False))
            self.health.update(
                "supervisor",
                "ONLINE" if active or (core and getattr(core, "is_online", False)) else "OFFLINE",
                target_type="supervisor",
                message="dual-write supervisor",
                metadata={"source": "dual_write", "jarvis_active": active},
            )
        elif core is not None:
            self.health.update(
                "supervisor",
                "ONLINE" if getattr(core, "is_online", False) else "OFFLINE",
                target_type="supervisor",
                message="dual-write supervisor (no jarvis)",
                metadata={"source": "dual_write"},
            )
