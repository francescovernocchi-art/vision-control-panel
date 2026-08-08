"""NotificationService — stub eventi JARVIS (nessun Telegram/SMS)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from services.jarvis.states import NotifyEvent
from utils.logger import get_logger

logger = get_logger("jarvis.notify")

NotifyCallback = Callable[["NotifyPayload"], None]


@dataclass
class NotifyPayload:
    event: str
    job_id: Optional[int] = None
    mail_id: str = ""
    order_number: str = ""
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class NotificationService:
    """Architettura pronta per provider esterni; per ora solo listener in-process."""

    def __init__(self) -> None:
        self._listeners: list[NotifyCallback] = []
        self._history: list[NotifyPayload] = []

    def add_listener(self, cb: NotifyCallback) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)

    def remove_listener(self, cb: NotifyCallback) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    def emit(
        self,
        event: str | NotifyEvent,
        *,
        job_id: Optional[int] = None,
        mail_id: str = "",
        order_number: str = "",
        message: str = "",
        **extra: Any,
    ) -> NotifyPayload:
        payload = NotifyPayload(
            event=str(event),
            job_id=job_id,
            mail_id=mail_id,
            order_number=order_number,
            message=message,
            extra=dict(extra),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._history.append(payload)
        if len(self._history) > 200:
            self._history = self._history[-200:]
        logger.debug(
            "Notify %s job=%s ordine=%s: %s",
            payload.event,
            job_id,
            order_number,
            message,
        )
        for cb in list(self._listeners):
            try:
                cb(payload)
            except Exception:
                pass
        return payload

    def recent(self, limit: int = 50) -> list[NotifyPayload]:
        return list(self._history[-max(1, limit) :])
