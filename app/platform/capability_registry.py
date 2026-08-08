"""CapabilityRegistry — catalogo moduli/comandi/eventi (nessun load dinamico)."""

from __future__ import annotations

import threading
from typing import Optional

from app.platform.descriptors import (
    CommandDescriptor,
    EventDescriptor,
    ModuleDescriptor,
)
from utils.logger import get_logger

logger = get_logger("platform.capability")


class CapabilityRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._modules: dict[str, ModuleDescriptor] = {}
        self._commands: dict[str, CommandDescriptor] = {}
        self._events: dict[str, EventDescriptor] = {}

    def register_module(self, descriptor: ModuleDescriptor) -> None:
        with self._lock:
            self._modules[descriptor.id] = descriptor
        logger.info(
            "Module registered id=%s version=%s status=%s",
            descriptor.id,
            descriptor.version,
            descriptor.status,
        )
        logger.info("Capability registered module=%s", descriptor.id)

    def register_command(self, descriptor: CommandDescriptor) -> None:
        with self._lock:
            self._commands[descriptor.id] = descriptor
        logger.info(
            "Capability registered command=%s module=%s implemented=%s",
            descriptor.id,
            descriptor.module,
            descriptor.implemented,
        )

    def register_event(self, descriptor: EventDescriptor) -> None:
        key = f"{descriptor.module}:{descriptor.event}" if descriptor.module else descriptor.event
        with self._lock:
            self._events[key] = descriptor
        logger.info(
            "Capability registered event=%s module=%s",
            descriptor.event,
            descriptor.module or "-",
        )

    def get_module(self, module_id: str) -> Optional[ModuleDescriptor]:
        with self._lock:
            return self._modules.get(module_id)

    def list_modules(self) -> list[ModuleDescriptor]:
        with self._lock:
            return list(self._modules.values())

    def get_command(self, command_id: str) -> Optional[CommandDescriptor]:
        with self._lock:
            return self._commands.get(command_id)

    def list_commands(self, *, module_id: str = "") -> list[CommandDescriptor]:
        with self._lock:
            cmds = list(self._commands.values())
        if module_id:
            return [c for c in cmds if c.module == module_id]
        return cmds

    def list_events(self, *, module_id: str = "") -> list[EventDescriptor]:
        with self._lock:
            evs = list(self._events.values())
        if module_id:
            return [e for e in evs if e.module == module_id]
        return evs

    def supports_command(self, module_id: str, command_id: str) -> bool:
        mod = self.get_module(module_id)
        if not mod:
            return False
        return command_id in mod.commands
