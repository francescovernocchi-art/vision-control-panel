"""EventBus locale VIS•ION — senza broker esterni."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable, Optional

from utils.logger import get_logger

logger = get_logger("vision.event_bus")


class EventType(StrEnum):
    MAIL_RECEIVED = "MAIL_RECEIVED"
    MAIL_ANALYZED = "MAIL_ANALYZED"
    JOB_CREATED = "JOB_CREATED"
    JOB_STARTED = "JOB_STARTED"
    JOB_PROGRESS = "JOB_PROGRESS"
    JOB_COMPLETED = "JOB_COMPLETED"
    JOB_FAILED = "JOB_FAILED"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    DOCUMENT_CREATED = "DOCUMENT_CREATED"
    PRINT_QUEUED = "PRINT_QUEUED"
    PRINT_COMPLETED = "PRINT_COMPLETED"
    PRINT_FAILED = "PRINT_FAILED"
    PEC_PREPARED = "PEC_PREPARED"
    PEC_SENT = "PEC_SENT"
    MODULE_ONLINE = "MODULE_ONLINE"
    MODULE_OFFLINE = "MODULE_OFFLINE"
    JARVIS_STATE_CHANGED = "JARVIS_STATE_CHANGED"
    WAITING_APPROVAL = "WAITING_APPROVAL"


@dataclass
class VisionEvent:
    event_type: str
    message: str = ""
    module: str = "core"
    job_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "module": self.module,
            "job_id": self.job_id,
            "event_type": self.event_type,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


EventHandler = Callable[[VisionEvent], None]


class EventBus:
    """Bus eventi in-process, thread-safe, fan-out ai listener."""

    def __init__(self, *, history_limit: int = 500) -> None:
        self._lock = threading.RLock()
        self._handlers: dict[str, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []
        self._history: list[VisionEvent] = []
        self._history_limit = max(50, history_limit)

    def subscribe(
        self,
        event_type: str | EventType | None,
        handler: EventHandler,
    ) -> None:
        with self._lock:
            if event_type is None:
                if handler not in self._global_handlers:
                    self._global_handlers.append(handler)
                return
            key = str(event_type)
            bucket = self._handlers.setdefault(key, [])
            if handler not in bucket:
                bucket.append(handler)

    def unsubscribe(
        self,
        event_type: str | EventType | None,
        handler: EventHandler,
    ) -> None:
        with self._lock:
            if event_type is None:
                if handler in self._global_handlers:
                    self._global_handlers.remove(handler)
                return
            bucket = self._handlers.get(str(event_type), [])
            if handler in bucket:
                bucket.remove(handler)

    def publish(
        self,
        event_type: str | EventType,
        *,
        message: str = "",
        module: str = "core",
        job_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> VisionEvent:
        event = VisionEvent(
            event_type=str(event_type),
            message=message,
            module=module,
            job_id=job_id,
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit :]
            handlers = list(self._global_handlers)
            handlers.extend(self._handlers.get(event.event_type, []))
        logger.debug(
            "EVENT %s module=%s job=%s: %s",
            event.event_type,
            event.module,
            event.job_id or "-",
            event.message,
        )
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 — isolamento listener
                logger.warning("Event handler error (%s): %s", event.event_type, exc)
        return event

    def recent(self, limit: int = 50) -> list[VisionEvent]:
        with self._lock:
            return list(self._history[-max(1, limit) :])
