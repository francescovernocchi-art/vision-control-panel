"""Remote status DTO — risposta serializzabile GET_STATUS (no secret / no oggetti Python)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional


def _iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class RemoteModuleStatus:
    module_id: str
    display_name: str
    version: str
    status: str
    health: str
    enabled: bool
    current_job: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "display_name": self.display_name,
            "version": self.version,
            "status": self.status,
            "health": self.health,
            "enabled": self.enabled,
            "current_job": self.current_job,
        }


@dataclass(frozen=True)
class RemoteSkillStatus:
    skill_id: str
    name: str
    enabled: bool
    module_id: str
    version: str
    category: str
    health: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RemoteServiceStatus:
    service_id: str
    available: bool
    health: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RemoteWarningStatus:
    code: str
    severity: str
    component: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RemoteAgentStatus:
    status: str
    connected_backend: str
    remote_mode: str
    last_heartbeat: str
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RemoteStatusResponse:
    """Risposta GET_STATUS — JSON-safe, non sensibile."""

    api_version: str = "v1"
    contract_version: str = "1.0.0"
    device_id: str = ""
    device_name: str = ""
    agent_version: str = ""
    vision_version: str = ""
    platform_version: str = ""
    timestamp: str = ""
    core_status: str = "UNKNOWN"
    supervisor_status: str = "UNKNOWN"
    overall_health: str = "UNKNOWN"
    current_job: Optional[dict[str, Any]] = None
    queue_size: int = 0
    modules: tuple[RemoteModuleStatus, ...] = ()
    skills: tuple[RemoteSkillStatus, ...] = ()
    services: tuple[RemoteServiceStatus, ...] = ()
    warnings: tuple[RemoteWarningStatus, ...] = ()
    remote_control_enabled: bool = False
    agent: Optional[RemoteAgentStatus] = None
    partial: bool = False
    missing_sections: tuple[str, ...] = ()
    ok: bool = True
    # compat leggera con GET_STATUS precedente (test / consumer interni)
    vision_core: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "api_version": self.api_version,
            "contract_version": self.contract_version,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "agent_version": self.agent_version,
            "vision_version": self.vision_version,
            "platform_version": self.platform_version,
            "timestamp": self.timestamp or _iso_now(),
            "core_status": self.core_status,
            "supervisor_status": self.supervisor_status,
            "overall_health": self.overall_health,
            "current_job": dict(self.current_job) if self.current_job else None,
            "queue_size": int(self.queue_size),
            "modules": [m.to_dict() for m in self.modules],
            "skills": [s.to_dict() for s in self.skills],
            "services": [s.to_dict() for s in self.services],
            "warnings": [w.to_dict() for w in self.warnings],
            "remote_control_enabled": bool(self.remote_control_enabled),
            "agent": self.agent.to_dict() if self.agent else None,
            "partial": bool(self.partial),
            "missing_sections": list(self.missing_sections),
            "vision_core": dict(self.vision_core) if self.vision_core else None,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)
