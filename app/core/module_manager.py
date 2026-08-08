"""ModuleManager — registro moduli VIS•ION."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from app.core.states import ModuleStatus
from utils.logger import get_logger

logger = get_logger("vision.modules")


@dataclass
class ModuleInfo:
    id: str
    name: str
    version: str
    status: str = ModuleStatus.OFFLINE
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Observer minimo: intercetta assegnazioni dirette a ``status``
        (es. modulo._info.status = ONLINE) senza richiedere set_status().
        ModuleManager resta source of truth; listener fa dual-write Health.
        """
        if name == "status":
            had = "status" in self.__dict__
            old = self.__dict__.get("status")
            object.__setattr__(self, name, value)
            listener = self.__dict__.get("_status_listener")
            if had and listener is not None and str(old) != str(value):
                try:
                    listener(self.__dict__.get("id", ""), str(value))
                except Exception:
                    pass
            return
        object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "status": self.status,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "metadata": dict(self.metadata),
        }


class VisionModule(Protocol):
    """Contratto minimo di un modulo VIS•ION."""

    @property
    def info(self) -> ModuleInfo: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


class ModuleManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._modules: dict[str, VisionModule] = {}
        self._infos: dict[str, ModuleInfo] = {}
        self._status_listeners: list[Any] = []

    def add_status_listener(self, callback: Any) -> None:
        """Listener opzionale per dual-write Health (platform layer)."""
        if callback not in self._status_listeners:
            self._status_listeners.append(callback)

    def remove_status_listener(self, callback: Any) -> None:
        if callback in self._status_listeners:
            self._status_listeners.remove(callback)

    def register(self, module: VisionModule) -> ModuleInfo:
        info = module.info
        with self._lock:
            self._modules[info.id] = module
            self._infos[info.id] = info
            # Abilita watch su assegnazioni dirette info.status = ...
            object.__setattr__(
                info,
                "_status_listener",
                self._make_status_listener(info.id),
            )
        logger.info("Modulo registrato: %s (%s) v%s", info.name, info.id, info.version)
        self._notify_status(info.id, info.status)
        return info

    def _make_status_listener(self, module_id: str):
        def _cb(_mid: str, status: str) -> None:
            self._notify_status(module_id, status)

        return _cb

    def unregister(self, module_id: str) -> None:
        with self._lock:
            info = self._infos.pop(module_id, None)
            self._modules.pop(module_id, None)
            if info is not None:
                try:
                    object.__setattr__(info, "_status_listener", None)
                except Exception:
                    pass

    def get(self, module_id: str) -> Optional[VisionModule]:
        with self._lock:
            return self._modules.get(module_id)

    def get_info(self, module_id: str) -> Optional[ModuleInfo]:
        with self._lock:
            info = self._infos.get(module_id)
            return ModuleInfo(**info.to_dict()) if info else None

    def list_modules(self) -> list[ModuleInfo]:
        with self._lock:
            return [ModuleInfo(**i.to_dict()) for i in self._infos.values()]

    def set_status(self, module_id: str, status: str | ModuleStatus) -> None:
        """Aggiorna status SoT; il watch su ModuleInfo notifica i listener."""
        with self._lock:
            info = self._infos.get(module_id)
            if not info:
                return
            # Assegnazione → __setattr__ → listener → dual-write
            # Evita doppia notifica: listener già chiama _notify_status
            info.status = str(status)

    def _notify_status(self, module_id: str, status: str) -> None:
        for cb in list(self._status_listeners):
            try:
                cb(module_id, status)
            except Exception as exc:  # noqa: BLE001 — dual-write non deve rompere runtime
                logger.warning("status listener error (%s): %s", module_id, exc)

    def start_all(self) -> None:
        with self._lock:
            items = list(self._modules.items())
        for module_id, module in items:
            try:
                module.start()
                self.set_status(module_id, ModuleStatus.ONLINE)
            except Exception as exc:  # noqa: BLE001 — isolamento moduli
                logger.error("Avvio modulo %s fallito: %s", module_id, exc)
                self.set_status(module_id, ModuleStatus.ERROR)

    def stop_all(self) -> None:
        with self._lock:
            items = list(self._modules.items())
        for module_id, module in items:
            try:
                module.stop()
                self.set_status(module_id, ModuleStatus.OFFLINE)
            except Exception as exc:  # noqa: BLE001
                logger.error("Stop modulo %s fallito: %s", module_id, exc)
