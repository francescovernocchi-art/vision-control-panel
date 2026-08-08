"""Sincronizzazione eventi VisionCore → backend (senza dati sensibili)."""

from __future__ import annotations

from typing import Any, Optional

from app.core.event_bus import VisionEvent
from app.remote.models import (
    NOTIFY_EVENT_TYPES,
    SYNC_EVENT_TYPES,
    RemoteEvent,
)
from app.remote.remote_log import remote_log


class EventSync:
    def __init__(self, *, backend: Any, device_id: str) -> None:
        self.backend = backend
        self.device_id = device_id
        self._seen: set[str] = set()

    def on_core_event(self, event: VisionEvent) -> None:
        et = str(event.event_type)
        if et not in SYNC_EVENT_TYPES:
            # mappa alcuni tipi EventBus esistenti
            if et not in {
                "JOB_CREATED",
                "JOB_STARTED",
                "JOB_PROGRESS",
                "JOB_COMPLETED",
                "JOB_FAILED",
                "NEEDS_ATTENTION",
                "MAIL_RECEIVED",
                "MAIL_ANALYZED",
                "MODULE_ONLINE",
                "MODULE_OFFLINE",
                "PRINT_QUEUED",
                "PRINT_COMPLETED",
                "PRINT_FAILED",
                "WAITING_APPROVAL",
                "DOCUMENT_CREATED",
                "PEC_PREPARED",
            }:
                return
        if event.event_id in self._seen:
            return
        self._seen.add(event.event_id)
        if len(self._seen) > 2000:
            self._seen = set(list(self._seen)[-1000:])

        # Strip metadata sensibile
        meta = {
            k: v
            for k, v in (event.metadata or {}).items()
            if k.lower()
            not in {
                "password",
                "token",
                "secret",
                "cookie",
                "authorization",
                "credentials",
            }
        }
        remote_event = RemoteEvent(
            event_type=et,
            message=event.message,
            module=event.module,
            job_id=event.job_id,
            metadata=meta,
            event_id=event.event_id,
            timestamp=event.timestamp,
            device_id=self.device_id,
        )
        try:
            self.backend.publish_event(remote_event)
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("publish_event failed: %s", exc)
            return

        if et in NOTIFY_EVENT_TYPES:
            try:
                self.backend.create_notification(
                    event_type=et,
                    message=event.message,
                    job_id=event.job_id,
                    device_id=self.device_id,
                    metadata={"module": event.module},
                )
            except Exception as exc:  # noqa: BLE001
                remote_log.warning("create_notification failed: %s", exc)

    def publish_command_event(
        self,
        event_type: str,
        *,
        command_id: str,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        remote_event = RemoteEvent(
            event_type=event_type,
            message=message,
            module="remote",
            command_id=command_id,
            device_id=self.device_id,
            metadata=dict(metadata or {}),
        )
        try:
            self.backend.publish_event(remote_event)
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("command event sync failed: %s", exc)
