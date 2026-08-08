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
    platform_version: str = "0.3.0-services-health"
    config: dict[str, Any] = field(default_factory=dict)
    core: Any = None
    health_bridge: Any = None
    last_consistency: Any = None
    last_diagnostics: Any = None

    # --- soft-DI / read-only helpers ---

    def get_service(self, service_id: str) -> Optional[Any]:
        return self.services.get(service_id)

    def get_skill(self, skill_id: str) -> Optional[Any]:
        return self.skills.get_skill(skill_id)

    def get_health(self, target_id: str) -> Optional[Any]:
        return self.health.get(target_id)

    def get_capability(self, module_id: str) -> Optional[Any]:
        return self.capability.get_module(module_id)

    def get_platform_snapshot(self) -> dict[str, Any]:
        """Snapshot piattaforma v2 (nessun consumer operativo obbligatorio)."""
        health_snap = self.health.get_health_snapshot()
        return {
            "platform_version": self.platform_version,
            "vision_version": self.version,
            "overall_health": health_snap.get("overall_status"),
            "components_health": health_snap,
            "services": [d.to_dict() for d in self.services.list_descriptors()],
            "skills": [s.to_dict() for s in self.skills.list_skills()],
            "capabilities": {
                "modules": [m.to_dict() for m in self.capability.list_modules()],
                "commands": [c.to_dict() for c in self.capability.list_commands()],
                "events": [e.to_dict() for e in self.capability.list_events()],
            },
            "modules": [m.to_dict() for m in self.capability.list_modules()],
            "consistency": (
                self.last_consistency.to_dict()
                if self.last_consistency is not None
                else None
            ),
            # compat campi precedenti
            "health": self.health.snapshot(),
            "core_health": (
                self.health.get("core").to_dict() if self.health.get("core") else None
            ),
        }

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
            "health": self.health.get_health_snapshot(),
            "services": [d.to_dict() for d in self.services.list_descriptors()],
            "capabilities": {
                "modules": [m.to_dict() for m in self.capability.list_modules()],
                "commands": [c.id for c in self.capability.list_commands()],
            },
        }
