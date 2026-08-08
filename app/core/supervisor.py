"""VisionCore — coordinatore centrale (senza logica di dominio moduli)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from app.core.event_bus import EventBus, EventType, VisionEvent
from app.core.health_monitor import HealthMonitor, HealthSnapshot
from app.core.job_manager import JobManager, VisionJob
from app.core.mail_router import MailHints, MailRouteDecision, MailRouter
from app.core.module_manager import ModuleInfo, ModuleManager, VisionModule
from app.core.notification_service import VisionNotificationService
from app.core.states import AssistantState, ModuleStatus, VisionJobStatus
from utils.logger import get_logger
from utils.paths import ASSISTANT_NAME, PRODUCT_NAME

logger = get_logger("vision.core")

AssistantStateListener = Callable[[str], None]


class VisionCore:
    """
    Cuore di VIS•ION:
    - conosce moduli e stato ONLINE/OFFLINE
    - riceve/emette eventi
    - gestisce coda globale VisionJob
    - aggiorna stato assistente (JARVIS)
    - NON contiene logica eniSpace / Trasporto Monete
    """

    def __init__(self) -> None:
        self.product_name = PRODUCT_NAME
        self.assistant_name = ASSISTANT_NAME
        self.event_bus = EventBus()
        self.modules = ModuleManager()
        self.jobs = JobManager()
        self.mail_router = MailRouter()
        self.notifications = VisionNotificationService(self.event_bus)
        self.health = HealthMonitor(self.modules)
        self.assistant_state = AssistantState.IDLE
        self._assistant_listeners: list[AssistantStateListener] = []
        self._started = False
        self.started_at = ""

        # Bridge eventi → stato avatar globale
        self.event_bus.subscribe(None, self._on_any_event)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.health.core_online = True
        self.set_assistant_state(AssistantState.IDLE, online=True)
        logger.info("%s CORE ONLINE — assistente=%s", self.product_name, self.assistant_name)
        self.event_bus.publish(
            EventType.MODULE_ONLINE,
            message=f"{self.product_name} Core avviato",
            module="core",
        )

    def stop(self) -> None:
        try:
            self.modules.stop_all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Stop moduli: %s", exc)
        self.health.core_online = False
        self.set_assistant_state(AssistantState.OFFLINE, online=False)
        self._started = False
        logger.info("%s CORE OFFLINE", self.product_name)

    @property
    def is_online(self) -> bool:
        return self._started and self.health.core_online

    # ------------------------------------------------------------------ modules
    def register_module(self, module: VisionModule) -> ModuleInfo:
        info = self.modules.register(module)
        status = info.status
        if status in (ModuleStatus.ONLINE, ModuleStatus.IN_DEVELOPMENT):
            self.event_bus.publish(
                EventType.MODULE_ONLINE,
                message=f"Modulo {info.name} registrato ({status})",
                module=info.id,
            )
        return info

    def list_modules(self) -> list[ModuleInfo]:
        return self.modules.list_modules()

    # ------------------------------------------------------------------ jobs
    def create_job(
        self,
        *,
        module_id: str,
        title: str = "",
        description: str = "",
        source_type: str = "",
        source_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> VisionJob:
        job = self.jobs.create_job(
            module_id=module_id,
            title=title,
            description=description,
            source_type=source_type,
            source_id=source_id,
            metadata=metadata,
            status=VisionJobStatus.QUEUED,
        )
        self.event_bus.publish(
            EventType.JOB_CREATED,
            message=title or f"Job {job.job_id}",
            module=module_id,
            job_id=job.job_id,
            metadata={"source_id": source_id, "source_type": source_type},
        )
        return job

    def mark_job_started(self, job: VisionJob, step: str = "") -> VisionJob:
        job.status = VisionJobStatus.PROCESSING
        job.started_at = job.started_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        job.current_step = step or job.current_step
        self.jobs.update_job(job)
        self.event_bus.publish(
            EventType.JOB_STARTED,
            message=step or f"Avvio {job.job_id}",
            module=job.module_id,
            job_id=job.job_id,
        )
        self.set_assistant_state(AssistantState.PROCESSING)
        return job

    def mark_job_progress(
        self, job: VisionJob, *, progress: int, step: str = "", message: str = ""
    ) -> VisionJob:
        job.progress = max(0, min(100, int(progress)))
        if step:
            job.current_step = step
        self.jobs.update_job(job)
        self.event_bus.publish(
            EventType.JOB_PROGRESS,
            message=message or step or f"{job.progress}%",
            module=job.module_id,
            job_id=job.job_id,
            metadata={"progress": job.progress, "step": job.current_step},
        )
        return job

    def mark_job_completed(self, job: VisionJob, message: str = "") -> VisionJob:
        job.status = VisionJobStatus.COMPLETED
        job.progress = 100
        job.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        job.requires_attention = False
        self.jobs.update_job(job)
        self.event_bus.publish(
            EventType.JOB_COMPLETED,
            message=message or f"Completato {job.job_id}",
            module=job.module_id,
            job_id=job.job_id,
        )
        self.set_assistant_state(AssistantState.SUCCESS)
        return job

    def mark_job_failed(self, job: VisionJob, message: str = "", code: str = "") -> VisionJob:
        job.status = VisionJobStatus.FAILED
        job.error_message = message
        job.error_code = code
        job.completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.jobs.update_job(job)
        self.event_bus.publish(
            EventType.JOB_FAILED,
            message=message or f"Fallito {job.job_id}",
            module=job.module_id,
            job_id=job.job_id,
            metadata={"error_code": code},
        )
        self.set_assistant_state(AssistantState.ERROR)
        return job

    def mark_job_needs_attention(self, job: VisionJob, message: str = "") -> VisionJob:
        job.status = VisionJobStatus.NEEDS_ATTENTION
        job.requires_attention = True
        job.error_message = message
        self.jobs.update_job(job)
        self.event_bus.publish(
            EventType.NEEDS_ATTENTION,
            message=message or f"Intervento richiesto {job.job_id}",
            module=job.module_id,
            job_id=job.job_id,
        )
        self.set_assistant_state(AssistantState.NEEDS_ATTENTION)
        return job

    def mark_waiting_approval(self, job: VisionJob, message: str = "") -> VisionJob:
        job.status = VisionJobStatus.WAITING_APPROVAL
        job.requires_attention = True
        job.current_step = "PEC_PRONTA_PER_APPROVAZIONE"
        self.jobs.update_job(job)
        self.event_bus.publish(
            EventType.WAITING_APPROVAL,
            message=message or "PEC pronta per approvazione",
            module=job.module_id,
            job_id=job.job_id,
        )
        self.set_assistant_state(AssistantState.NEEDS_ATTENTION)
        return job

    # ------------------------------------------------------------------ mail
    def route_mail(self, mail: MailHints) -> MailRouteDecision:
        decision = self.mail_router.route(mail)
        self.event_bus.publish(
            EventType.MAIL_RECEIVED,
            message=mail.subject or "Mail ricevuta",
            module=decision.module_id or "core",
            metadata={
                "action": decision.action,
                "rule_id": decision.rule_id,
                "reason": decision.reason,
                "sender": mail.sender,
            },
        )
        if decision.action == "ROUTE":
            self.set_assistant_state(AssistantState.MAIL_RECEIVED)
        elif decision.action == "NEEDS_CLASSIFICATION":
            self.set_assistant_state(AssistantState.NEEDS_ATTENTION)
        return decision

    # ------------------------------------------------------------------ assistant
    def add_assistant_listener(self, cb: AssistantStateListener) -> None:
        if cb not in self._assistant_listeners:
            self._assistant_listeners.append(cb)

    def set_assistant_state(self, state: str | AssistantState, *, online: bool = True) -> None:
        new_state = str(state)
        self.assistant_state = new_state  # type: ignore[assignment]
        self.health.set_assistant(online=online, state=new_state)
        self.event_bus.publish(
            EventType.JARVIS_STATE_CHANGED,
            message=f"{self.assistant_name} → {new_state}",
            module="assistant",
            metadata={"state": new_state, "online": online},
        )
        for cb in list(self._assistant_listeners):
            try:
                cb(new_state)
            except Exception:
                pass

    def _on_any_event(self, event: VisionEvent) -> None:
        # Mapping soft eventi → analisi
        if event.event_type == EventType.MAIL_ANALYZED:
            self.set_assistant_state(AssistantState.ANALYSIS)

    # ------------------------------------------------------------------ status
    def snapshot(self) -> dict[str, Any]:
        health: HealthSnapshot = self.health.snapshot()
        return {
            "product": self.product_name,
            "assistant": self.assistant_name,
            "core_online": health.core_online,
            "assistant_online": health.assistant_online,
            "assistant_state": health.assistant_state,
            "modules": health.modules,
            "kpi": self.jobs.kpi_today(),
            "started_at": self.started_at,
            "timestamp": health.timestamp,
        }
