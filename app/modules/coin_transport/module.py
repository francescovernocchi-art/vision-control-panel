"""Trasporto Monete — modulo VIS•ION (IN SVILUPPO)."""

from __future__ import annotations

from typing import Any, Optional

from app.core.event_bus import EventBus, EventType
from app.core.job_manager import JobManager, VisionJob
from app.core.module_manager import ModuleInfo
from app.core.states import ModuleStatus, VisionJobStatus
from app.core.supervisor import VisionCore
from app.modules.coin_transport.workflow import (
    COIN_TRANSPORT_STEPS,
    FINAL_STATUS,
    CoinTransportWorkflow,
)
from utils.logger import get_logger

logger = get_logger("modules.coin_transport")


class CoinTransportModule:
    MODULE_ID = "coin_transport"

    def __init__(
        self,
        *,
        core: Optional[VisionCore] = None,
        event_bus: Optional[EventBus] = None,
        jobs: Optional[JobManager] = None,
        version: str = "0.1",
    ) -> None:
        self.core = core
        self.event_bus = event_bus or (core.event_bus if core else None)
        self.jobs = jobs or (core.jobs if core else None)
        self.workflow = CoinTransportWorkflow()
        self._info = ModuleInfo(
            id=self.MODULE_ID,
            name="Trasporto Monete",
            version=version,
            status=ModuleStatus.IN_DEVELOPMENT,
            description="Workflow Sala Conta → documento → PEC in approvazione",
            capabilities=[
                "mail_analysis",
                "attachment_extract",
                "activity_recognition",
                "vehicles",
                "itineraries",
                "provinces",
                "questure",
                "document_generation",
                "protocol",
                "pec_prepare",
                "approval_gate",
            ],
            metadata={"auto_send_pec": False, "final_status": FINAL_STATUS},
        )

    @property
    def info(self) -> ModuleInfo:
        return self._info

    def start(self) -> None:
        # Resta IN_DEVELOPMENT ma operativo per scheletro
        self._info.status = ModuleStatus.IN_DEVELOPMENT
        if self.event_bus:
            self.event_bus.publish(
                EventType.MODULE_ONLINE,
                message="Trasporto Monete IN SVILUPPO (scheletro attivo)",
                module=self.MODULE_ID,
            )
        logger.info("Modulo coin_transport avviato (IN_DEVELOPMENT)")

    def stop(self) -> None:
        self._info.status = ModuleStatus.DISABLED
        if self.event_bus:
            self.event_bus.publish(
                EventType.MODULE_OFFLINE,
                message="Trasporto Monete OFFLINE",
                module=self.MODULE_ID,
            )

    def create_job_from_mail(
        self,
        *,
        subject: str = "",
        source_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[VisionJob]:
        """Crea VisionJob e avanza lo scheletro fino a PEC PRONTA PER APPROVAZIONE."""
        if self.core:
            job = self.core.create_job(
                module_id=self.MODULE_ID,
                title=subject or "Trasporto Monete",
                description="Workflow Sala Conta",
                source_type="mail",
                source_id=source_id,
                metadata=metadata,
            )
            return self.run_skeleton(job)

        if not self.jobs:
            return None
        job = self.jobs.create_job(
            module_id=self.MODULE_ID,
            title=subject or "Trasporto Monete",
            description="Workflow Sala Conta",
            source_type="mail",
            source_id=source_id,
            metadata=metadata,
        )
        return self.run_skeleton(job)

    def run_skeleton(self, job: VisionJob) -> VisionJob:
        """Esegue step simulati fino allo stato finale (senza invio PEC)."""
        result = self.workflow.run(job)
        if self.jobs:
            self.jobs.update_job(result)
        if self.core:
            self.core.mark_waiting_approval(
                result,
                message=FINAL_STATUS,
            )
        elif self.event_bus:
            result.status = VisionJobStatus.WAITING_APPROVAL
            result.requires_attention = True
            result.current_step = FINAL_STATUS
            self.event_bus.publish(
                EventType.PEC_PREPARED,
                message=FINAL_STATUS,
                module=self.MODULE_ID,
                job_id=result.job_id,
                metadata={"auto_send": False, "actions": ["APRI", "MODIFICA", "APPROVA E INVIA"]},
            )
            self.event_bus.publish(
                EventType.WAITING_APPROVAL,
                message=FINAL_STATUS,
                module=self.MODULE_ID,
                job_id=result.job_id,
            )
        logger.info(
            "Coin transport job %s → %s (steps=%s)",
            result.job_id,
            FINAL_STATUS,
            len(COIN_TRANSPORT_STEPS),
        )
        return result
