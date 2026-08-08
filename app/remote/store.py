"""Store locale idempotenza comandi remoti (SQLite dedicato)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from app.remote.models import CommandStatus, RemoteCommand, now_iso
from utils.paths import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS remote_commands (
    command_id TEXT PRIMARY KEY,
    command_type TEXT NOT NULL,
    target_device_id TEXT NOT NULL,
    status TEXT NOT NULL,
    params TEXT,
    created_at TEXT,
    expires_at TEXT,
    acknowledged_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    result TEXT,
    error TEXT,
    source TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_remote_cmd_status ON remote_commands(status);
"""

TERMINAL = frozenset(
    {
        CommandStatus.COMPLETED,
        CommandStatus.FAILED,
        CommandStatus.REJECTED,
    }
)
SEEN = frozenset(
    {
        CommandStatus.ACKNOWLEDGED,
        CommandStatus.EXECUTING,
        CommandStatus.COMPLETED,
        CommandStatus.FAILED,
        CommandStatus.REJECTED,
    }
)


class CommandStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else data_dir() / "vision_remote.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(SCHEMA)
                conn.commit()
            finally:
                conn.close()

    def get(self, command_id: str) -> Optional[RemoteCommand]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM remote_commands WHERE command_id = ?",
                    (command_id,),
                ).fetchone()
            finally:
                conn.close()
        return self._row(row) if row else None

    def already_handled(self, command_id: str) -> bool:
        existing = self.get(command_id)
        return bool(existing and existing.status in SEEN)

    def is_terminal(self, command_id: str) -> bool:
        existing = self.get(command_id)
        return bool(existing and existing.status in TERMINAL)

    def upsert(self, cmd: RemoteCommand) -> RemoteCommand:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO remote_commands(
                        command_id, command_type, target_device_id, status, params,
                        created_at, expires_at, acknowledged_at, started_at, finished_at,
                        result, error, source, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(command_id) DO UPDATE SET
                        status=excluded.status,
                        params=excluded.params,
                        acknowledged_at=excluded.acknowledged_at,
                        started_at=excluded.started_at,
                        finished_at=excluded.finished_at,
                        result=excluded.result,
                        error=excluded.error,
                        updated_at=excluded.updated_at
                    """,
                    (
                        cmd.command_id,
                        cmd.command_type,
                        cmd.target_device_id,
                        cmd.status,
                        json.dumps(cmd.params or {}, ensure_ascii=False),
                        cmd.created_at,
                        cmd.expires_at,
                        cmd.acknowledged_at,
                        cmd.started_at,
                        cmd.finished_at,
                        json.dumps(cmd.result or {}, ensure_ascii=False),
                        cmd.error,
                        cmd.source,
                        now_iso(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return cmd

    def list_recent(self, limit: int = 50) -> list[RemoteCommand]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM remote_commands
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (max(1, limit),),
                ).fetchall()
            finally:
                conn.close()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> RemoteCommand:
        def _json(raw: Any) -> dict:
            if not raw:
                return {}
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}

        return RemoteCommand(
            command_id=row["command_id"],
            command_type=row["command_type"],
            target_device_id=row["target_device_id"],
            status=row["status"],
            params=_json(row["params"]),
            created_at=row["created_at"] or "",
            expires_at=row["expires_at"] or "",
            acknowledged_at=row["acknowledged_at"] or "",
            started_at=row["started_at"] or "",
            finished_at=row["finished_at"] or "",
            result=_json(row["result"]),
            error=row["error"] or "",
            source=row["source"] or "",
        )
