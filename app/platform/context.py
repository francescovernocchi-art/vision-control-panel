"""PlatformContext — accesso unico a registri/servizi/config/versione."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.platform.capability_registry import CapabilityRegistry
from app.platform.health_registry import HealthRegistry
from app.platform.service_registry import ServiceRegistry


@dataclass
class PlatformContext:
    capability: CapabilityRegistry
    health: HealthRegistry
    services: ServiceRegistry
    version: str = "2.0-vision"
    platform_version: str = "0.1.0-foundation"
    config: dict[str, Any] = field(default_factory=dict)
    core: Any = None

    def get_service(self, service_id: str) -> Optional[Any]:
        return self.services.get(service_id)

    def snapshot(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "platform_version": self.platform_version,
            "modules": [m.to_dict() for m in self.capability.list_modules()],
            "commands": [c.to_dict() for c in self.capability.list_commands()],
            "events": [e.to_dict() for e in self.capability.list_events()],
            "services": self.services.list_ids(),
            "health": self.health.summary(),
            "config_keys": sorted(self.config.keys()),
        }
