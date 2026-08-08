"""Modelli dati JARVIS (job + eventi)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from services.jarvis.states import JobOutcome, JobStatus, JarvisState, LogLevel


@dataclass
class JarvisJob:
    id: Optional[int] = None
    mail_id: str = ""
    mail_uid: str = ""
    mail_folder: str = ""
    message_id: str = ""
    subject: str = ""
    sender: str = ""
    received_at: str = ""
    order_number: str = ""
    contract_number: str = ""
    acquisition_module: str = ""
    status: str = JobStatus.PENDING
    outcome: str = ""
    state: str = JarvisState.IN_ATTESA
    docs_found: int = 0
    docs_downloaded: int = 0
    docs_printed: int = 0
    printer_name: str = ""
    pdf_paths: list[str] = field(default_factory=list)
    attempts: int = 0
    max_attempts: int = 3
    error_message: str = ""
    simulation: bool = False
    created_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    last_event_at: str = ""

    @property
    def pdf_paths_json(self) -> str:
        return json.dumps(self.pdf_paths or [], ensure_ascii=False)

    @staticmethod
    def parse_pdf_paths(raw: Any) -> list[str]:
        if not raw:
            return []
        if isinstance(raw, list):
            return [str(x) for x in raw]
        try:
            data = json.loads(str(raw))
            if isinstance(data, list):
                return [str(x) for x in data]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    @property
    def duration_label(self) -> str:
        if not self.started_at or not self.finished_at:
            return "—"
        try:
            from datetime import datetime

            fmt = "%Y-%m-%d %H:%M:%S"
            a = datetime.strptime(self.started_at[:19], fmt)
            b = datetime.strptime(self.finished_at[:19], fmt)
            secs = max(0, int((b - a).total_seconds()))
            if secs < 60:
                return f"{secs}s"
            return f"{secs // 60}m {secs % 60}s"
        except Exception:
            return "—"


@dataclass
class JarvisJobEvent:
    id: Optional[int] = None
    job_id: int = 0
    timestamp: str = ""
    level: str = LogLevel.INFO
    message: str = ""
    state: str = ""


@dataclass
class JarvisSettings:
    """Impostazioni JARVIS (persistite in tabella settings)."""

    enabled: bool = False
    interval_seconds: int = 60
    autostart: bool = False
    max_retries: int = 3
    printer: str = ""
    download_folder: str = ""
    keep_pdfs: bool = True
    debug: bool = False
    simulation: bool = False


@dataclass
class MailCandidate:
    """Mail candidata ENI/MdA per la coda JARVIS."""

    mail_id: str
    uid: str = ""
    folder: str = ""
    message_id: str = ""
    subject: str = ""
    sender: str = ""
    body: str = ""
    received_at: str = ""
    order_number: str = ""
    contract_number: str = ""
    acquisition_module: str = ""
    raw_notification: Any = None
