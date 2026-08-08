"""JobManager globale VIS•ION — ID leggibili VISION-YYYY-NNNNNN."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.states import VisionJobStatus
from utils.logger import get_logger
from utils.paths import data_dir

logger = get_logger("vision.jobs")


@dataclass
class VisionJob:
    job_id: str
    module_id: str
    title: str = ""
    description: str = ""
    status: str = VisionJobStatus.PENDING
    progress: int = 0
    current_step: str = ""
    source_type: str = ""
    source_id: str = ""
    requires_attention: bool = False
    error_code: str = ""
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "module_id": self.module_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "progress": self.progress,
            "current_step": self.current_step,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "requires_attention": self.requires_attention,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "metadata": dict(self.metadata),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


SCHEMA = """
CREATE TABLE IF NOT EXISTS vision_jobs (
    job_id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL,
    title TEXT,
    description TEXT,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    current_step TEXT,
    source_type TEXT,
    source_id TEXT,
    requires_attention INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    seq INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vision_jobs_status ON vision_jobs(status);
CREATE INDEX IF NOT EXISTS idx_vision_jobs_module ON vision_jobs(module_id);
CREATE INDEX IF NOT EXISTS idx_vision_jobs_created ON vision_jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS vision_job_seq (
    year INTEGER PRIMARY KEY,
    last_seq INTEGER NOT NULL DEFAULT 0
);
"""


class JobManager:
    """Coda/registro globale lavorazioni VIS•ION (SQLite dedicato)."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.path = Path(db_path) if db_path else data_dir() / "vision_jobs.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def _next_id(self, conn: sqlite3.Connection) -> tuple[str, int]:
        year = datetime.now().year
        row = conn.execute(
            "SELECT last_seq FROM vision_job_seq WHERE year = ?", (year,)
        ).fetchone()
        if row:
            seq = int(row["last_seq"]) + 1
            conn.execute(
                "UPDATE vision_job_seq SET last_seq = ? WHERE year = ?",
                (seq, year),
            )
        else:
            seq = 1
            conn.execute(
                "INSERT INTO vision_job_seq(year, last_seq) VALUES (?, ?)",
                (year, seq),
            )
        job_id = f"VISION-{year}-{seq:06d}"
        return job_id, seq

    def create_job(
        self,
        *,
        module_id: str,
        title: str = "",
        description: str = "",
        source_type: str = "",
        source_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
        status: str = VisionJobStatus.PENDING,
    ) -> VisionJob:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            conn = self._connect()
            try:
                job_id, seq = self._next_id(conn)
                job = VisionJob(
                    job_id=job_id,
                    module_id=module_id,
                    title=title,
                    description=description,
                    status=str(status),
                    source_type=source_type,
                    source_id=source_id,
                    metadata=dict(metadata or {}),
                    created_at=now,
                )
                conn.execute(
                    """
                    INSERT INTO vision_jobs(
                        job_id, module_id, title, description, status, progress,
                        current_step, source_type, source_id, requires_attention,
                        error_code, error_message, metadata, created_at,
                        started_at, completed_at, seq
                    ) VALUES (?, ?, ?, ?, ?, 0, '', ?, ?, 0, '', '', ?, ?, '', '', ?)
                    """,
                    (
                        job.job_id,
                        job.module_id,
                        job.title,
                        job.description,
                        job.status,
                        job.source_type,
                        job.source_id,
                        json.dumps(job.metadata, ensure_ascii=False),
                        job.created_at,
                        seq,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        logger.info("Job creato %s module=%s", job.job_id, module_id)
        return job

    def update_job(self, job: VisionJob) -> VisionJob:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE vision_jobs SET
                        title=?, description=?, status=?, progress=?, current_step=?,
                        source_type=?, source_id=?, requires_attention=?,
                        error_code=?, error_message=?, metadata=?,
                        started_at=?, completed_at=?
                    WHERE job_id=?
                    """,
                    (
                        job.title,
                        job.description,
                        job.status,
                        int(job.progress),
                        job.current_step,
                        job.source_type,
                        job.source_id,
                        1 if job.requires_attention else 0,
                        job.error_code,
                        job.error_message,
                        json.dumps(job.metadata or {}, ensure_ascii=False),
                        job.started_at,
                        job.completed_at,
                        job.job_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return job

    def get_job(self, job_id: str) -> Optional[VisionJob]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM vision_jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
            finally:
                conn.close()
        return self._row_to_job(row) if row else None

    def list_jobs(self, *, limit: int = 100, module_id: str = "") -> list[VisionJob]:
        with self._lock:
            conn = self._connect()
            try:
                if module_id:
                    rows = conn.execute(
                        """
                        SELECT * FROM vision_jobs
                        WHERE module_id = ?
                        ORDER BY created_at DESC LIMIT ?
                        """,
                        (module_id, max(1, limit)),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT * FROM vision_jobs
                        ORDER BY created_at DESC LIMIT ?
                        """,
                        (max(1, limit),),
                    ).fetchall()
            finally:
                conn.close()
        return [self._row_to_job(r) for r in rows]

    def count_by_status(self, status: str, *, today_only: bool = False) -> int:
        day = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            conn = self._connect()
            try:
                if today_only:
                    row = conn.execute(
                        """
                        SELECT COUNT(*) AS c FROM vision_jobs
                        WHERE status = ? AND substr(created_at, 1, 10) = ?
                        """,
                        (status, day),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT COUNT(*) AS c FROM vision_jobs WHERE status = ?",
                        (status,),
                    ).fetchone()
            finally:
                conn.close()
        return int(row["c"] if row else 0)

    def kpi_today(self) -> dict[str, int]:
        day = datetime.now().strftime("%Y-%m-%d")
        with self._lock:
            conn = self._connect()
            try:
                total = conn.execute(
                    "SELECT COUNT(*) AS c FROM vision_jobs WHERE substr(created_at,1,10)=?",
                    (day,),
                ).fetchone()["c"]
                processing = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM vision_jobs
                    WHERE status IN ('PROCESSING','QUEUED') AND substr(created_at,1,10)=?
                    """,
                    (day,),
                ).fetchone()["c"]
                queued = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM vision_jobs
                    WHERE status IN ('PENDING','QUEUED') AND substr(created_at,1,10)=?
                    """,
                    (day,),
                ).fetchone()["c"]
                completed = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM vision_jobs
                    WHERE status IN ('COMPLETED','PARTIAL') AND substr(created_at,1,10)=?
                    """,
                    (day,),
                ).fetchone()["c"]
                attention = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM vision_jobs
                    WHERE status IN ('NEEDS_ATTENTION','WAITING_APPROVAL')
                      AND substr(created_at,1,10)=?
                    """,
                    (day,),
                ).fetchone()["c"]
                errors = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM vision_jobs
                    WHERE status = 'FAILED' AND substr(created_at,1,10)=?
                    """,
                    (day,),
                ).fetchone()["c"]
            finally:
                conn.close()
        return {
            "today": int(total),
            "processing": int(processing),
            "queued": int(queued),
            "completed": int(completed),
            "attention": int(attention),
            "errors": int(errors),
        }

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> VisionJob:
        meta_raw = row["metadata"] or "{}"
        try:
            meta = json.loads(meta_raw)
        except json.JSONDecodeError:
            meta = {}
        return VisionJob(
            job_id=row["job_id"],
            module_id=row["module_id"],
            title=row["title"] or "",
            description=row["description"] or "",
            status=row["status"] or VisionJobStatus.PENDING,
            progress=int(row["progress"] or 0),
            current_step=row["current_step"] or "",
            source_type=row["source_type"] or "",
            source_id=row["source_id"] or "",
            requires_attention=bool(row["requires_attention"]),
            error_code=row["error_code"] or "",
            error_message=row["error_message"] or "",
            metadata=meta if isinstance(meta, dict) else {},
            created_at=row["created_at"] or "",
            started_at=row["started_at"] or "",
            completed_at=row["completed_at"] or "",
        )
