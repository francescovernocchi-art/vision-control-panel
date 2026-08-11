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

    @staticmethod
    def _italian_command_message(
        event_type: str, message: str, metadata: Optional[dict[str, Any]]
    ) -> str:
        """Human-readable Italian lines for PWA agent_messages feed."""
        raw = (message or "").strip()
        meta = metadata or {}
        ctype = str(meta.get("command_type") or raw).upper()
        labels = {
            "WAKE_SUPERVISOR": "Sveglia Supervisor",
            "DEACTIVATE_SUPERVISOR": "Disattiva Supervisor",
            "GET_STATUS": "Stato Agent",
        }
        label = labels.get(ctype, raw or ctype or "comando")
        if event_type == "COMMAND_RECEIVED":
            return f"Comando ricevuto: {label}"
        if event_type == "COMMAND_STARTED":
            return f"Esecuzione: {label}"
        if event_type == "COMMAND_COMPLETED":
            if ctype == "WAKE_SUPERVISOR":
                return "Supervisor attivato (WAKE)"
            if ctype == "DEACTIVATE_SUPERVISOR":
                return "Supervisor disattivato"
            if ctype == "GET_STATUS":
                return "GET_STATUS completato"
            return f"Completato: {label}"
        if event_type == "COMMAND_FAILED":
            detail = str(meta.get("message") or meta.get("code") or raw or "errore")
            return f"Fallito: {label} — {detail}"[:500]
        return raw or event_type

    def publish_command_event(
        self,
        event_type: str,
        *,
        command_id: str,
        message: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        meta = dict(metadata or {})
        # Preserve command_type when message is the type code.
        if message and "command_type" not in meta and message.isupper() and "_" in message:
            meta.setdefault("command_type", message)
        text = self._italian_command_message(event_type, message, meta)
        remote_event = RemoteEvent(
            event_type=event_type,
            message=text,
            module="remote",
            command_id=command_id,
            device_id=self.device_id,
            metadata=meta,
        )
        try:
            self.backend.publish_event(remote_event)
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("command event sync failed: %s", exc)
