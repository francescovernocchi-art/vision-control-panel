"""Remote status DTO — risposta serializzabile GET_STATUS (no secret / no oggetti Python)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
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
class RemoteEniSpaceRuntimeStatus:
    """
    Phase 3D — EniSpace / legacy supervisor observability (read-only).
    Separate from Vision Core ``current_job`` / ``queue_size``.
    Never exposes legacy product name "JARVIS" in API output.
    """

    status: str = "UNKNOWN"  # IDLE|PROCESSING|DEGRADED|OFFLINE|UNKNOWN
    active: Optional[bool] = None
    pending_jobs: Optional[int] = None
    current_job: Optional[dict[str, Any]] = None
    last_job: Optional[dict[str, Any]] = None
    last_mail_check: Optional[str] = None
    last_error: Optional[str] = None
    available: bool = True
    # Internal state label from legacy supervisor (Italian UI states), not product branding
    detail_state: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "available": bool(self.available),
        }
        if self.active is not None:
            payload["active"] = bool(self.active)
        if self.pending_jobs is not None:
            payload["pending_jobs"] = int(self.pending_jobs)
        if self.current_job is not None:
            payload["current_job"] = dict(self.current_job)
        else:
            payload["current_job"] = None
        if self.last_job is not None:
            payload["last_job"] = dict(self.last_job)
        else:
            payload["last_job"] = None
        if self.last_mail_check is not None:
            payload["last_mail_check"] = self.last_mail_check
        else:
            payload["last_mail_check"] = None
        if self.last_error is not None:
            payload["last_error"] = self.last_error
        else:
            payload["last_error"] = None
        if self.detail_state is not None:
            payload["detail_state"] = self.detail_state
        return payload


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
    # Phase 3D — additive EniSpace runtime (optional; consumers ignore if unknown)
    enispace_runtime: Optional[RemoteEniSpaceRuntimeStatus] = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
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
        if self.enispace_runtime is not None:
            payload["enispace_runtime"] = self.enispace_runtime.to_dict()
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)
