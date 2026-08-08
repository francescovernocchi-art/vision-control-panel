"""ModuleHealthBridge — dual-write stati modulo → HealthRegistry."""

from __future__ import annotations

from typing import Any, Optional

from app.platform.health_registry import HealthRegistry
from app.platform.status_normalizer import normalize_health_status
from utils.logger import get_logger

# re-export per compat test / import storici
__all__ = ["ModuleHealthBridge", "normalize_health_status"]

logger = get_logger("platform.health_bridge")


class ModuleHealthBridge:
    def __init__(self, health: HealthRegistry) -> None:
        self.health = health
        self._attached = False
        self._manager: Any = None

    def attach(self, module_manager: Any) -> None:
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
                "ModuleManager senza add_status_listener — solo sync esplicito"
            )

    def attach_event_bus(self, event_bus: Any) -> None:
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
                metadata={"source": "dual_write", "lifecycle": "ONLINE" if online else "OFFLINE"},
            )
        if jarvis is not None:
            active = bool(getattr(jarvis, "is_active", False))
            st = "ONLINE" if active or (core and getattr(core, "is_online", False)) else "OFFLINE"
            self.health.update(
                "supervisor",
                st,
                target_type="supervisor",
                message="dual-write supervisor",
                metadata={"source": "dual_write", "jarvis_active": active, "lifecycle": st},
            )
        elif core is not None:
            st = "ONLINE" if getattr(core, "is_online", False) else "OFFLINE"
            self.health.update(
                "supervisor",
                st,
                target_type="supervisor",
                message="dual-write supervisor (no jarvis)",
                metadata={"source": "dual_write", "lifecycle": st},
            )
