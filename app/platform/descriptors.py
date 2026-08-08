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
    """Storage interno HealthRegistry (compat)."""

    target_id: str
    status: str
    target_type: str = "module"
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

    def to_report(self, *, source: str = "dual_write") -> "HealthReport":
        return HealthReport(
            component_id=self.target_id,
            component_type=self.target_type,
            status=self.status,
            ok=self.ok,
            message=self.message,
            updated_at=self.checked_at,
            source=str((self.metadata or {}).get("source") or source),
            metadata=dict(self.metadata),
        )


@dataclass
class HealthReport:
    """Schema standard Health (export / snapshot)."""

    component_id: str
    component_type: str  # core | module | supervisor | service | agent
    status: str
    ok: bool = True
    message: str = ""
    updated_at: str = ""
    source: str = "dual_write"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_type": self.component_type,
            "status": self.status,
            "ok": self.ok,
            "message": self.message,
            "updated_at": self.updated_at,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass
class ServiceDescriptor:
    service_id: str
    display_name: str = ""
    version: str = "1.0"
    lifetime: str = "singleton"  # singleton | transient | external
    required: bool = False
    health_managed: bool = False
    available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_id": self.service_id,
            "display_name": self.display_name or self.service_id,
            "version": self.version,
            "lifetime": self.lifetime,
            "required": self.required,
            "health_managed": self.health_managed,
            "available": self.available,
            "metadata": dict(self.metadata),
        }
