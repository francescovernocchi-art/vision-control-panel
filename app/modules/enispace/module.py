"""Modulo ENISPACE — wrappa la logica esistente senza riscriverla."""

from __future__ import annotations

from typing import Any, Optional

from app.core.event_bus import EventBus, EventType
from app.core.module_manager import ModuleInfo
from app.core.states import ModuleStatus
from utils.logger import get_logger

logger = get_logger("modules.enispace")


class EniSpaceModule:
    """
    Adapter: espone eniSpace / JARVIS Supervisor come modulo VIS•ION.
    La logica operativa resta in services/* (MailWatcher, BatchService, ecc.).
    """

    MODULE_ID = "enispace"

    def __init__(
        self,
        *,
        event_bus: Optional[EventBus] = None,
        jarvis: Any = None,
        version: str = "1.0",
    ) -> None:
        self.event_bus = event_bus
        self.jarvis = jarvis
        self._info = ModuleInfo(
            id=self.MODULE_ID,
            name="eniSpace Automation",
            version=version,
            status=ModuleStatus.OFFLINE,
            description="Automazione mail ENI/MdA, ricerca eniSpace, download e stampa",
            capabilities=[
                "mail_watch",
                "enispace_login",
                "document_download",
                "print_queue",
                "jarvis_supervisor",
                "anti_duplication",
                "retry",
                "history",
            ],
        )
        self._bridge_wired = False

    @property
    def info(self) -> ModuleInfo:
        return self._info

    def bind_jarvis(self, jarvis: Any) -> None:
        self.jarvis = jarvis
        self._wire_jarvis_bridge()

    def check_mail_now(self, *, dry_run: bool = False) -> dict:
        """
        Entry point remoto/locale: un controllo mail via JARVIS esistente.
        dry_run=True → nessun accesso IMAP (test automatici).
        """
        if dry_run:
            logger.info("check_mail_now dry_run (nessun IMAP)")
            if self.event_bus:
                self.event_bus.publish(
                    EventType.MAIL_ANALYZED,
                    message="CHECK_ENISPACE_MAIL dry_run",
                    module=self.MODULE_ID,
                    metadata={"dry_run": True},
                )
            return {
                "ok": True,
                "dry_run": True,
                "message": "dry_run — nessun accesso mail/eniSpace",
                "module_id": self.MODULE_ID,
            }
        if not self.jarvis:
            return {
                "ok": False,
                "code": "JARVIS_NOT_BOUND",
                "message": "JARVIS non collegato al modulo eniSpace",
            }
        if not hasattr(self.jarvis, "run_mail_check_once"):
            return {
                "ok": False,
                "code": "NO_HANDLER",
                "message": "JarvisSupervisor.run_mail_check_once assente",
            }
        if self.event_bus:
            self.event_bus.publish(
                EventType.MAIL_RECEIVED,
                message="CHECK_ENISPACE_MAIL richiesto",
                module=self.MODULE_ID,
            )
        try:
            result = self.jarvis.run_mail_check_once()
            if not isinstance(result, dict):
                result = {"ok": True, "result": result}
            result.setdefault("ok", True)
            result["module_id"] = self.MODULE_ID
            return result
        except Exception as exc:  # noqa: BLE001
            logger.error("check_mail_now failed: %s", exc)
            return {"ok": False, "code": "CHECK_FAILED", "message": str(exc)}

    def retry_job(self, job_id: str) -> dict:
        """Retry minimo: job JARVIS FAILED/NEEDS_ATTENTION → PENDING."""
        if not self.jarvis or not hasattr(self.jarvis, "db"):
            return {"ok": False, "code": "JARVIS_NOT_BOUND", "message": "JARVIS assente"}
        try:
            jid = int(str(job_id).replace("JARVIS-", "").strip())
        except ValueError:
            return {
                "ok": False,
                "code": "BAD_JOB_ID",
                "message": f"job_id non valido: {job_id}",
            }
        try:
            from services.jarvis.states import JobStatus

            job = self.jarvis.db.get_jarvis_job(jid)
            if not job:
                return {
                    "ok": False,
                    "code": "NOT_FOUND",
                    "message": f"job {jid} non trovato",
                }
            if job.status not in (
                JobStatus.FAILED,
                JobStatus.NEEDS_ATTENTION,
                "FAILED",
                "NEEDS_ATTENTION",
            ):
                return {
                    "ok": False,
                    "code": "NOT_RETRYABLE",
                    "message": f"stato {job.status} non ritentabile",
                }
            job.status = JobStatus.PENDING
            job.error_message = ""
            self.jarvis.db.update_jarvis_job(job)
            return {"ok": True, "jarvis_job_id": jid, "status": "PENDING"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "code": "RETRY_FAILED", "message": str(exc)}

    def start(self) -> None:
        self._info.status = ModuleStatus.ONLINE
        self._wire_jarvis_bridge()
        if self.event_bus:
            self.event_bus.publish(
                EventType.MODULE_ONLINE,
                message="eniSpace Automation ONLINE",
                module=self.MODULE_ID,
            )
        logger.info("Modulo eniSpace ONLINE")

    def stop(self) -> None:
        self._info.status = ModuleStatus.OFFLINE
        if self.event_bus:
            self.event_bus.publish(
                EventType.MODULE_OFFLINE,
                message="eniSpace Automation OFFLINE",
                module=self.MODULE_ID,
            )
        logger.info("Modulo eniSpace OFFLINE")

    def _wire_jarvis_bridge(self) -> None:
        """Collega notifiche JARVIS esistenti all'EventBus globale."""
        if self._bridge_wired or not self.jarvis or not self.event_bus:
            return
        try:
            notifications = getattr(self.jarvis, "notifications", None)
            if notifications and hasattr(notifications, "add_listener"):
                notifications.add_listener(self._on_jarvis_notify)
                self._bridge_wired = True
                logger.info("Bridge JARVIS → EventBus attivo")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bridge JARVIS non collegato: %s", exc)

    def _on_jarvis_notify(self, payload: Any) -> None:
        if not self.event_bus:
            return
        event_name = str(getattr(payload, "event", "") or "")
        mapping = {
            "JOB_COMPLETED": EventType.JOB_COMPLETED,
            "JOB_FAILED": EventType.JOB_FAILED,
            "NEEDS_ATTENTION": EventType.NEEDS_ATTENTION,
            "NEW_JOB": EventType.JOB_CREATED,
        }
        et = mapping.get(event_name)
        if not et:
            return
        job_id = getattr(payload, "job_id", None)
        self.event_bus.publish(
            et,
            message=str(getattr(payload, "message", "") or event_name),
            module=self.MODULE_ID,
            job_id=f"JARVIS-{job_id}" if job_id else "",
            metadata={
                "mail_id": getattr(payload, "mail_id", ""),
                "order_number": getattr(payload, "order_number", ""),
                "legacy_jarvis": True,
            },
        )
