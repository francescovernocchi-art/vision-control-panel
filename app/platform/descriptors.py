"""Descriptor del Platform Layer (catalogo, non runtime operativo)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ModuleDescriptor:
    id: str
    display_name: str
    version: str
    status: str = "OFFLINE"
    commands: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "version": self.version,
            "status": self.status,
            "commands": list(self.commands),
            "events": list(self.events),
            "permissions": list(self.permissions),
            "dependencies": list(self.dependencies),
            "metadata": dict(self.metadata),
        }


@dataclass
class CommandDescriptor:
    id: str
    display_name: str
    description: str = ""
    module: str = ""
    permission: str = ""
    implemented: bool = False
    deprecated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "description": self.description,
            "module": self.module,
            "permission": self.permission,
            "implemented": self.implemented,
            "deprecated": self.deprecated,
        }


@dataclass
class EventDescriptor:
    event: str
    severity: str = "INFO"
    module: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "severity": self.severity,
            "module": self.module,
            "description": self.description,
        }


@dataclass
class HealthSnapshot:
    target_id: str
    status: str
    target_type: str = "module"  # module | core | supervisor | service
    ok: bool = True
    message: str = ""
    checked_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_type": self.target_type,
            "status": self.status,
            "ok": self.ok,
            "message": self.message,
            "checked_at": self.checked_at,
            "metadata": dict(self.metadata),
        }
