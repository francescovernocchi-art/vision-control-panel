"""Interfaccia RemoteBackend — adapter cloud senza accoppiamento stretto."""

from __future__ import annotations

from typing import Any, Optional, Protocol

from app.remote.models import DeviceIdentity, RemoteCommand, RemoteEvent


class RemoteBackend(Protocol):
    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def health_check(self) -> bool: ...

    def heartbeat(self, identity: DeviceIdentity) -> None: ...

    def fetch_commands(self, device_id: str) -> list[RemoteCommand]: ...

    def acknowledge_command(self, command: RemoteCommand) -> None: ...

    def update_command(self, command: RemoteCommand) -> None: ...

    def sync_job(self, job: dict[str, Any]) -> None: ...

    def publish_event(self, event: RemoteEvent) -> None: ...

    def create_notification(
        self,
        *,
        event_type: str,
        message: str,
        job_id: str = "",
        device_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None: ...
