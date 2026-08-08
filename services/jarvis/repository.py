"""Persistenza job JARVIS su SQLite (via Database)."""

from __future__ import annotations

from typing import Optional

from database.db import Database
from database.models import now_iso
from services.jarvis.models import JarvisJob, JarvisJobEvent
from services.jarvis.states import JobStatus, JarvisState, LogLevel


class JobRepository:
    """CRUD su jarvis_jobs / jarvis_job_events."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def get_by_id(self, job_id: int) -> Optional[JarvisJob]:
        return self.db.get_jarvis_job(job_id)

    def get_by_mail_id(self, mail_id: str) -> Optional[JarvisJob]:
        return self.db.get_jarvis_job_by_mail_id(mail_id)

    def list_jobs(self, *, limit: int = 200) -> list[JarvisJob]:
        return self.db.list_jarvis_jobs(limit=limit)

    def list_pending(self) -> list[JarvisJob]:
        return self.db.list_jarvis_jobs_by_status(JobStatus.PENDING)

    def list_processing(self) -> list[JarvisJob]:
        return self.db.list_jarvis_jobs_by_status(JobStatus.PROCESSING)

    def count_pending(self) -> int:
        return self.db.count_jarvis_jobs_by_status(JobStatus.PENDING)

    def create(self, job: JarvisJob) -> JarvisJob:
        return self.db.create_jarvis_job(job)

    def update(self, job: JarvisJob) -> JarvisJob:
        return self.db.update_jarvis_job(job)

    def add_event(
        self,
        job_id: int,
        message: str,
        *,
        level: str = LogLevel.INFO,
        state: str = "",
    ) -> JarvisJobEvent:
        return self.db.add_jarvis_job_event(
            job_id=job_id,
            message=message,
            level=level,
            state=state,
        )

    def list_events(self, job_id: int) -> list[JarvisJobEvent]:
        return self.db.list_jarvis_job_events(job_id)

    def mail_already_handled(self, mail_id: str) -> bool:
        """True se mail già in coda/lavorata Jarvis o già sync IMAP con successo."""
        if not mail_id:
            return False
        existing = self.get_by_mail_id(mail_id)
        if existing is not None:
            # Qualsiasi record (anche FAILED/NEEDS_ATTENTION) evita riprocessamento automatico
            return True
        # Allinea con anti-dup manuale
        if self.db.is_imap_processed(mail_id):
            return True
        return False

    def recover_interrupted_processing(self) -> list[JarvisJob]:
        """
        Job rimasti PROCESSING dopo crash → NEEDS_ATTENTION.
        NON ristampa automaticamente (regola anti-duplicazione stampe).
        """
        recovered: list[JarvisJob] = []
        for job in self.list_processing():
            job.status = JobStatus.NEEDS_ATTENTION
            job.outcome = "INTERVENTO RICHIESTO"
            job.state = JarvisState.INTERVENTO_RICHIESTO
            job.error_message = (
                "Lavorazione interrotta (riavvio applicazione). "
                "Verificare manualmente se i documenti sono già stati "
                "inviati alla coda di stampa — nessuna ristampa automatica."
            )
            job.finished_at = now_iso()
            self.update(job)
            self.add_event(
                job.id or 0,
                job.error_message,
                level=LogLevel.WARNING,
                state=job.state,
            )
            recovered.append(job)
        return recovered
