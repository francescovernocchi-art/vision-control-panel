"""Validazione comandi remoti — whitelist + target + scadenza + schema params."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from app.remote.models import (
    COMMAND_WHITELIST,
    CommandStatus,
    CommandType,
    RemoteCommand,
)
from app.remote.security import sanitize_params


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""
    command: Optional[RemoteCommand] = None


def _parse_ts(value: str) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    text = str(value).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19] if len(text) >= 19 else text, fmt)
        except ValueError:
            continue
    return None


def validate_command(
    raw: RemoteCommand | dict[str, Any],
    *,
    device_id: str,
    already_handled: bool = False,
) -> ValidationResult:
    if isinstance(raw, dict):
        cmd = RemoteCommand(
            command_id=str(raw.get("command_id") or "").strip(),
            command_type=str(raw.get("command_type") or "").strip(),
            target_device_id=str(raw.get("target_device_id") or "").strip(),
            status=str(raw.get("status") or CommandStatus.PENDING),
            params=sanitize_params(raw.get("params") or {}),
            created_at=str(raw.get("created_at") or ""),
            expires_at=str(raw.get("expires_at") or ""),
            source=str(raw.get("source") or "backend"),
        )
    else:
        cmd = raw
        cmd.params = sanitize_params(cmd.params)

    if not cmd.command_id:
        return ValidationResult(False, "command_id mancante")
    if already_handled:
        return ValidationResult(False, "comando già gestito (idempotenza)", cmd)
    if cmd.status != CommandStatus.PENDING:
        return ValidationResult(False, f"stato non PENDING ({cmd.status})", cmd)
    if cmd.command_type not in COMMAND_WHITELIST:
        return ValidationResult(False, f"command_type non in whitelist: {cmd.command_type}", cmd)
    if cmd.target_device_id != device_id:
        return ValidationResult(
            False,
            f"target_device_id mismatch ({cmd.target_device_id} != {device_id})",
            cmd,
        )

    expires = _parse_ts(cmd.expires_at)
    if expires and datetime.now() > expires:
        return ValidationResult(False, "comando scaduto (expires_at)", cmd)

    # Schema parametri minimi per tipo
    schema_err = _validate_params_schema(cmd.command_type, cmd.params)
    if schema_err:
        return ValidationResult(False, schema_err, cmd)

    return ValidationResult(True, "ok", cmd)


def _validate_params_schema(command_type: str, params: dict[str, Any]) -> str:
    if command_type == CommandType.RETRY_JOB:
        job_id = str(params.get("job_id") or params.get("jarvis_job_id") or "").strip()
        if not job_id:
            return "RETRY_JOB richiede params.job_id"
    if command_type in (CommandType.PAUSE_MODULE, CommandType.RESUME_MODULE):
        module_id = str(params.get("module_id") or "").strip()
        if not module_id:
            return f"{command_type} richiede params.module_id"
        if module_id not in ("enispace", "coin_transport"):
            return f"module_id non consentito: {module_id}"
    if command_type in (CommandType.APPROVE_JOB, CommandType.REJECT_JOB):
        job_id = str(params.get("job_id") or "").strip()
        if not job_id:
            return f"{command_type} richiede params.job_id"
    return ""
