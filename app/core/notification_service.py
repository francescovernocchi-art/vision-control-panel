"""NotificationService centrale VIS•ION (provider esterni futuri)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

from app.core.event_bus import EventBus, EventType, VisionEvent
from utils.logger import get_logger

logger = get_logger("vision.notify")

NotifyCallback = Callable[["VisionNotifyPayload"], None]


@dataclass
class VisionNotifyPayload:
    event: str
    job_id: str = ""
    module: str = ""
    message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


class VisionNotificationService:
    """Interfaccia notifiche centralizzata — nessun provider esterno obbligatorio."""

    SUPPORTED = (
        EventType.JOB_COMPLETED,
        EventType.JOB_FAILED,
        EventType.NEEDS_ATTENTION,
        EventType.WAITING_APPROVAL,
    )

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._listeners: list[NotifyCallback] = []
        self._history: list[VisionNotifyPayload] = []
        self.event_bus = event_bus
        if event_bus:
            for et in self.SUPPORTED:
                event_bus.subscribe(et, self._on_bus_event)

    def add_listener(self, cb: NotifyCallback) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)

    def remove_listener(self, cb: NotifyCallback) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    def emit(
        self,
        event: str | EventType,
        *,
        job_id: str = "",
        module: str = "",
        message: str = "",
        **extra: Any,
    ) -> VisionNotifyPayload:
        payload = VisionNotifyPayload(
            event=str(event),
            job_id=job_id,
            module=module,
            message=message,
            extra=dict(extra),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._history.append(payload)
        if len(self._history) > 200:
            self._history = self._history[-200:]
        logger.info(
            "NOTIFY %s module=%s job=%s: %s",
            payload.event,
            module or "-",
            job_id or "-",
            message,
        )
        for cb in list(self._listeners):
            try:
                cb(payload)
            except Exception:
                pass
        return payload

    def _on_bus_event(self, event: VisionEvent) -> None:
        # Solo ascolto bus → notifiche UI (niente re-publish)
        self.emit(
            event.event_type,
            job_id=event.job_id,
            module=event.module,
            message=event.message,
            **event.metadata,
        )

    def recent(self, limit: int = 50) -> list[VisionNotifyPayload]:
        return list(self._history[-max(1, limit) :])
