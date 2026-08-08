"""HealthMonitor — stato CORE e moduli."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from app.core.module_manager import ModuleManager
from app.core.states import ModuleStatus


@dataclass
class HealthSnapshot:
    core_online: bool = True
    assistant_online: bool = False
    assistant_state: str = "OFFLINE"
    modules: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = ""


class HealthMonitor:
    def __init__(self, modules: ModuleManager) -> None:
        self.modules = modules
        self.core_online = True
        self.assistant_online = False
        self.assistant_state = "OFFLINE"

    def set_assistant(self, *, online: bool, state: str = "") -> None:
        self.assistant_online = online
        if state:
            self.assistant_state = state

    def snapshot(self) -> HealthSnapshot:
        mods = []
        for info in self.modules.list_modules():
            mods.append(
                {
                    "id": info.id,
                    "name": info.name,
                    "status": info.status,
                    "version": info.version,
                }
            )
        return HealthSnapshot(
            core_online=self.core_online,
            assistant_online=self.assistant_online,
            assistant_state=self.assistant_state,
            modules=mods,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def module_online_count(self) -> int:
        return sum(
            1
            for m in self.modules.list_modules()
            if m.status in (ModuleStatus.ONLINE, ModuleStatus.IN_DEVELOPMENT)
        )
