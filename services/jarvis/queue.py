"""Coda persistente job JARVIS (una lavorazione alla volta)."""

from __future__ import annotations

from typing import Optional

from database.models import now_iso
from services.jarvis.models import JarvisJob, MailCandidate
from services.jarvis.repository import JobRepository
from services.jarvis.states import JobStatus, JarvisState, LogLevel, NotifyEvent
from services.jarvis.notifications import NotificationService
from services.jarvis.logger import JarvisLogger


class JobQueue:
    """Accoda mail candidate; non avvia il processing (lo fa JobProcessor)."""

    def __init__(
        self,
        repo: JobRepository,
        *,
        logger: Optional[JarvisLogger] = None,
        notifications: Optional[NotificationService] = None,
    ) -> None:
        self.repo = repo
        self.logger = logger
        self.notifications = notifications

    def enqueue(
        self,
        candidate: MailCandidate,
        *,
        simulation: bool = False,
        max_attempts: int = 3,
    ) -> Optional[JarvisJob]:
        """Crea job PENDING se mail_id non già gestito. None se duplicato."""
        mail_id = (candidate.mail_id or "").strip()
        if not mail_id:
            return None
        if self.repo.mail_already_handled(mail_id):
            if self.logger:
                self.logger.log(
                    f"Mail già gestita, skip: {mail_id}",
                    level=LogLevel.INFO,
                    state=JarvisState.CONTROLLO_MAIL,
                )
            return None

        job = JarvisJob(
            mail_id=mail_id,
            mail_uid=candidate.uid,
            mail_folder=candidate.folder,
            message_id=candidate.message_id,
            subject=candidate.subject,
            sender=candidate.sender,
            received_at=candidate.received_at or now_iso(),
            order_number=candidate.order_number,
            contract_number=candidate.contract_number,
            acquisition_module=candidate.acquisition_module,
            status=JobStatus.PENDING,
            state=JarvisState.NUOVA_MAIL,
            max_attempts=max(1, int(max_attempts)),
            simulation=bool(simulation),
            created_at=now_iso(),
            last_event_at=now_iso(),
        )
        job = self.repo.create(job)
        self.repo.add_event(
            job.id or 0,
            f"Job creato — mail «{(candidate.subject or '')[:80]}»",
            level=LogLevel.INFO,
            state=JarvisState.NUOVA_MAIL,
        )
        if self.logger:
            self.logger.log(
                f"Nuova mail ENI rilevata: {(candidate.subject or '')[:70]}",
                level=LogLevel.SUCCESS,
                state=JarvisState.NUOVA_MAIL,
            )
        if self.notifications:
            self.notifications.emit(
                NotifyEvent.NEW_JOB,
                job_id=job.id,
                mail_id=mail_id,
                order_number=candidate.order_number,
                message="Nuovo job in coda",
            )
        return job

    def next_pending(self) -> Optional[JarvisJob]:
        pending = self.repo.list_pending()
        return pending[0] if pending else None

    def count_pending(self) -> int:
        return self.repo.count_pending()
