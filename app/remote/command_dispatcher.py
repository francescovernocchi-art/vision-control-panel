"""CommandDispatcher — inoltra a VisionCore / moduli; policy remota status_only."""

from __future__ import annotations

from typing import Any, Optional

from app.core.supervisor import VisionCore
from app.remote.models import (
    IMPLEMENTED_COMMANDS,
    STUB_COMMANDS,
    CommandType,
    RemoteCommand,
    is_remote_command_allowed,
)
from app.remote.remote_log import remote_log
from app.remote.status_service import RemoteStatusService


class CommandDispatcher:
    def __init__(
        self,
        core: VisionCore,
        *,
        status_service: Optional[RemoteStatusService] = None,
        remote_execution_policy: str = "status_only",
    ) -> None:
        self.core = core
        self.status_service = status_service or RemoteStatusService(core)
        self.remote_execution_policy = remote_execution_policy or "status_only"

    def dispatch(self, command: RemoteCommand) -> dict[str, Any]:
        ctype = command.command_type

        # Policy di fase: solo GET_STATUS dai comandi remoti (non path locali)
        if not is_remote_command_allowed(
            ctype, policy=self.remote_execution_policy
        ):
            remote_log.info(
                "Remote command rejected by policy=%s type=%s",
                self.remote_execution_policy,
                ctype,
            )
            return {
                "ok": False,
                "code": "REMOTE_OPERATION_NOT_ENABLED",
                "message": (
                    f"{ctype} non autorizzato in modalità "
                    f"{self.remote_execution_policy} (solo GET_STATUS remoto)"
                ),
            }

        if ctype in STUB_COMMANDS:
            return {
                "ok": False,
                "code": "NOT_IMPLEMENTED",
                "message": f"{ctype} ricevuto e validato — workflow non ancora autorizzato",
            }
        if ctype not in IMPLEMENTED_COMMANDS:
            return {
                "ok": False,
                "code": "NOT_WHITELISTED",
                "message": f"Comando non eseguibile: {ctype}",
            }
        if ctype == CommandType.GET_STATUS:
            return self._get_status()
        if ctype == CommandType.CHECK_ENISPACE_MAIL:
            return self._check_enispace_mail(command)
        if ctype == CommandType.RETRY_JOB:
            return self._retry_job(command)
        if ctype == CommandType.PAUSE_MODULE:
            return self._pause_module(command)
        if ctype == CommandType.RESUME_MODULE:
            return self._resume_module(command)
        return {"ok": False, "code": "NOT_IMPLEMENTED", "message": ctype}

    def _get_status(self) -> dict[str, Any]:
        return self.status_service.build_status()

    def _check_enispace_mail(self, command: RemoteCommand) -> dict[str, Any]:
        """Delega al modulo eniSpace — nessuna logica eniSpace qui."""
        mod = self.core.modules.get("enispace")
        if mod is None:
            return {"ok": False, "code": "MODULE_MISSING", "message": "eniSpace non registrato"}
        if not hasattr(mod, "check_mail_now"):
            return {
                "ok": False,
                "code": "NO_HANDLER",
                "message": "eniSpace.check_mail_now non disponibile",
            }
        dry_run = bool(command.params.get("dry_run"))
        remote_log.info("Dispatch CHECK_ENISPACE_MAIL dry_run=%s", dry_run)
        result = mod.check_mail_now(dry_run=dry_run)
        if not isinstance(result, dict):
            result = {"ok": True, "result": result}
        job_id = str(result.get("vision_job_id") or "")
        if job_id:
            job = self.core.jobs.get_job(job_id)
            if job:
                result["job"] = {
                    "job_id": job.job_id,
                    "module_id": job.module_id,
                    "title": job.title,
                    "status": job.status,
                    "progress": job.progress,
                    "current_step": job.current_step,
                }
        return result

    def _retry_job(self, command: RemoteCommand) -> dict[str, Any]:
        job_id = str(
            command.params.get("job_id") or command.params.get("jarvis_job_id") or ""
        ).strip()
        mod = self.core.modules.get("enispace")
        if mod and hasattr(mod, "retry_job"):
            return mod.retry_job(job_id)
        return {
            "ok": False,
            "code": "NOT_IMPLEMENTED",
            "message": "retry_job non disponibile sul modulo eniSpace",
        }

    def _pause_module(self, command: RemoteCommand) -> dict[str, Any]:
        module_id = str(command.params.get("module_id") or "").strip()
        mod = self.core.modules.get(module_id)
        if not mod:
            return {"ok": False, "code": "MODULE_MISSING", "message": module_id}
        if hasattr(mod, "pause"):
            mod.pause()
        else:
            try:
                mod.stop()
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "code": "PAUSE_FAILED", "message": str(exc)}
            self.core.modules.set_status(module_id, "DISABLED")
        return {"ok": True, "module_id": module_id, "status": "DISABLED"}

    def _resume_module(self, command: RemoteCommand) -> dict[str, Any]:
        module_id = str(command.params.get("module_id") or "").strip()
        mod = self.core.modules.get(module_id)
        if not mod:
            return {"ok": False, "code": "MODULE_MISSING", "message": module_id}
        if hasattr(mod, "resume"):
            mod.resume()
        else:
            try:
                mod.start()
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "code": "RESUME_FAILED", "message": str(exc)}
            self.core.modules.set_status(module_id, getattr(mod.info, "status", "ONLINE"))
        return {
            "ok": True,
            "module_id": module_id,
            "status": getattr(mod.info, "status", "ONLINE"),
        }
