"""Modelli Remote Agent — contratti stabili, indipendenti dallo schema SQL cloud."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional


class DeviceStatus(StrEnum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"  # determinato dal backend/PWA via last_seen_at
    DISABLED = "DISABLED"


class CommandStatus(StrEnum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class CommandType(StrEnum):
    GET_STATUS = "GET_STATUS"
    WAKE_SUPERVISOR = "WAKE_SUPERVISOR"
    DEACTIVATE_SUPERVISOR = "DEACTIVATE_SUPERVISOR"
    CHECK_ENISPACE_MAIL = "CHECK_ENISPACE_MAIL"
    RETRY_JOB = "RETRY_JOB"
    PAUSE_MODULE = "PAUSE_MODULE"
    RESUME_MODULE = "RESUME_MODULE"
    PREPARE_COIN_TRANSPORT = "PREPARE_COIN_TRANSPORT"
    APPROVE_JOB = "APPROVE_JOB"
    REJECT_JOB = "REJECT_JOB"


COMMAND_WHITELIST: frozenset[str] = frozenset(c.value for c in CommandType)

IMPLEMENTED_COMMANDS: frozenset[str] = frozenset(
    {
        CommandType.GET_STATUS,
        CommandType.WAKE_SUPERVISOR,
        CommandType.DEACTIVATE_SUPERVISOR,
        CommandType.CHECK_ENISPACE_MAIL,
        CommandType.RETRY_JOB,
        CommandType.PAUSE_MODULE,
        CommandType.RESUME_MODULE,
    }
)

STUB_COMMANDS: frozenset[str] = frozenset(
    {
        CommandType.PREPARE_COIN_TRANSPORT,
        CommandType.APPROVE_JOB,
        CommandType.REJECT_JOB,
    }
)

# Policy di fase thin channel: status + lifecycle Supervisor (non job orchestration)
REMOTE_EXECUTION_POLICY_STATUS_ONLY = "status_only"
REMOTE_EXECUTION_POLICY_FULL = "full"
DEFAULT_REMOTE_EXECUTION_POLICY = REMOTE_EXECUTION_POLICY_STATUS_ONLY

REMOTE_STATUS_ONLY_ALLOWED: frozenset[str] = frozenset(
    {
        CommandType.GET_STATUS,
        CommandType.WAKE_SUPERVISOR,
        CommandType.DEACTIVATE_SUPERVISOR,
    }
)


def is_remote_command_allowed(command_type: str, *, policy: str) -> bool:
    """True se il comando remoto è consentito dalla policy di fase."""
    pol = (policy or DEFAULT_REMOTE_EXECUTION_POLICY).strip().lower()
    if pol == REMOTE_EXECUTION_POLICY_FULL:
        return True
    # status_only = canale sottile Control Panel ↔ Agent
    return str(command_type) in REMOTE_STATUS_ONLY_ALLOWED


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class RemoteCommand:
    command_id: str
    command_type: str
    target_device_id: str
    status: str = CommandStatus.PENDING
    params: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    expires_at: str = ""
    acknowledged_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    source: str = "backend"

    @classmethod
    def create(
        cls,
        *,
        command_type: str,
        target_device_id: str,
        params: Optional[dict[str, Any]] = None,
        command_id: str = "",
        expires_at: str = "",
        source: str = "backend",
    ) -> "RemoteCommand":
        return cls(
            command_id=command_id or str(uuid.uuid4()),
            command_type=str(command_type),
            target_device_id=target_device_id,
            params=dict(params or {}),
            created_at=now_iso(),
            expires_at=expires_at,
            source=source,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type,
            "target_device_id": self.target_device_id,
            "status": self.status,
            "params": dict(self.params),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "acknowledged_at": self.acknowledged_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": dict(self.result),
            "error": self.error,
            "source": self.source,
        }


@dataclass
class DeviceIdentity:
    device_id: str
    device_name: str
    agent_version: str
    vision_version: str
    hostname: str
    status: str = DeviceStatus.DISABLED
    last_seen_at: str = ""
    current_job_id: str = ""
    modules: list[dict[str, Any]] = field(default_factory=list)
    platform_version: str = ""

    def to_heartbeat(self) -> dict[str, Any]:
        """Heartbeat leggero — non full GET_STATUS."""
        modules_summary = []
        for m in self.modules or []:
            if not isinstance(m, dict):
                continue
            modules_summary.append(
                {
                    "module_id": m.get("module_id") or m.get("id") or "",
                    "status": m.get("status") or m.get("health") or "",
                    "health": m.get("health") or m.get("status") or "",
                }
            )
        ts = self.last_seen_at or now_iso()
        return {
            "device_id": self.device_id,
            "status": self.status,
            "agent_version": self.agent_version,
            "vision_version": self.vision_version,
            "platform_version": self.platform_version or "",
            "current_job_id": self.current_job_id or "",
            "modules": modules_summary,
            "timestamp": ts,
            # campi legacy compat backend mock
            "device_name": self.device_name,
            "hostname": self.hostname,
            "last_seen_at": ts,
        }


@dataclass
class RemoteEvent:
    event_type: str
    message: str = ""
    module: str = "remote"
    job_id: str = ""
    command_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = ""
    timestamp: str = ""
    device_id: str = ""

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "device_id": self.device_id,
            "module": self.module,
            "job_id": self.job_id,
            "command_id": self.command_id,
            "event_type": self.event_type,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


SYNC_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "COMMAND_RECEIVED",
        "COMMAND_STARTED",
        "COMMAND_COMPLETED",
        "COMMAND_FAILED",
        "MAIL_RECEIVED",
        "MAIL_ANALYZED",
        "JOB_CREATED",
        "JOB_STARTED",
        "JOB_PROGRESS",
        "JOB_COMPLETED",
        "JOB_FAILED",
        "DOWNLOAD_STARTED",
        "DOWNLOAD_COMPLETED",
        "PRINT_STARTED",
        "PRINT_COMPLETED",
        "PRINT_FAILED",
        "NEEDS_ATTENTION",
        "MODULE_ONLINE",
        "MODULE_OFFLINE",
        "WAITING_APPROVAL",
        "DEVICE_DEGRADED",
    }
)

NOTIFY_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "JOB_COMPLETED",
        "JOB_FAILED",
        "NEEDS_ATTENTION",
        "DEVICE_DEGRADED",
        "WAITING_APPROVAL",
    }
)
