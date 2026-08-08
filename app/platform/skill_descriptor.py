"""SkillDescriptor — descrizione skill (catalogo, non runtime)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillDescriptor:
    id: str
    name: str
    description: str = ""
    version: str = "0.0.0"
    module_id: str = ""
    category: str = "general"
    enabled: bool = True
    commands: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    required_core_version: str = ""
    icon: str = ""
    visibility: str = "public"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "module_id": self.module_id,
            "category": self.category,
            "enabled": self.enabled,
            "commands": list(self.commands),
            "events": list(self.events),
            "permissions": list(self.permissions),
            "dependencies": list(self.dependencies),
            "required_core_version": self.required_core_version,
            "icon": self.icon,
            "visibility": self.visibility,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillDescriptor":
        return cls(
            id=str(data.get("id") or "").strip(),
            name=str(data.get("name") or "").strip(),
            description=str(data.get("description") or ""),
            version=str(data.get("version") or "0.0.0"),
            module_id=str(data.get("module_id") or "").strip(),
            category=str(data.get("category") or "general"),
            enabled=bool(data.get("enabled", True)),
            commands=[str(x) for x in (data.get("commands") or [])],
            events=[str(x) for x in (data.get("events") or [])],
            permissions=[str(x) for x in (data.get("permissions") or [])],
            dependencies=[str(x) for x in (data.get("dependencies") or [])],
            required_core_version=str(data.get("required_core_version") or ""),
            icon=str(data.get("icon") or ""),
            visibility=str(data.get("visibility") or "public"),
            metadata=dict(data.get("metadata") or {}),
        )
