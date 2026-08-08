"""PlatformContext — accesso unico a registri/servizi/config/versione."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.platform.capability_registry import CapabilityRegistry
from app.platform.health_registry import HealthRegistry
from app.platform.service_registry import ServiceRegistry
from app.platform.skill_registry import SkillRegistry


@dataclass
class PlatformContext:
    capability: CapabilityRegistry
    health: HealthRegistry
    services: ServiceRegistry
    skills: SkillRegistry = field(default_factory=SkillRegistry)
    version: str = "2.0-vision"
    platform_version: str = "0.2.0-skills-health"
    config: dict[str, Any] = field(default_factory=dict)
    core: Any = None
    health_bridge: Any = None
    last_consistency: Any = None

    def get_service(self, service_id: str) -> Optional[Any]:
        return self.services.get(service_id)

    def get_platform_snapshot(self) -> dict[str, Any]:
        """Snapshot completo piattaforma (nessun consumer operativo in questa fase)."""
        core_h = self.health.get("core")
        return {
            "platform_version": self.platform_version,
            "vision_version": self.version,
            "core_health": core_h.to_dict() if core_h else None,
            "services": self.services.list_ids(),
            "modules": [m.to_dict() for m in self.capability.list_modules()],
            "skills": [s.to_dict() for s in self.skills.list_skills()],
            "capabilities": {
                "commands": [c.to_dict() for c in self.capability.list_commands()],
                "events": [e.to_dict() for e in self.capability.list_events()],
            },
            "health": self.health.snapshot(),
            "consistency": (
                self.last_consistency.to_dict()
                if self.last_consistency is not None
                else None
            ),
        }

    # alias retrocompatibile
    def snapshot(self) -> dict[str, Any]:
        return self.get_platform_snapshot()

    def supervisor_readonly_view(self) -> dict[str, Any]:
        """
        Predisposizione read-only per futuro Supervisor.
        NON usato da UI/avatar in questa fase.
        """
        return {
            "skills": [s.to_dict() for s in self.skills.list_skills()],
            "enabled_skills": [s.to_dict() for s in self.skills.get_enabled_skills()],
            "health": self.health.snapshot(),
            "capabilities": {
                "modules": [m.to_dict() for m in self.capability.list_modules()],
                "commands": [c.id for c in self.capability.list_commands()],
            },
        }
