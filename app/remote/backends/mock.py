"""Backend mock — test locali senza cloud."""

from __future__ import annotations

import threading
from typing import Any, Optional

from app.remote.models import DeviceIdentity, RemoteCommand, RemoteEvent, now_iso


class MockRemoteBackend:
    """In-memory backend per modalità mock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.connected = False
        self.heartbeats: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self.jobs: list[dict[str, Any]] = []
        self.commands: dict[str, RemoteCommand] = {}
        self.command_updates: list[dict[str, Any]] = []

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def health_check(self) -> bool:
        return self.connected

    def heartbeat(self, identity: DeviceIdentity) -> None:
        payload = identity.to_heartbeat()
        payload["received_at"] = now_iso()
        with self._lock:
            self.heartbeats.append(payload)
            if len(self.heartbeats) > 200:
                self.heartbeats = self.heartbeats[-200:]

    def enqueue_command(self, command: RemoteCommand) -> RemoteCommand:
        with self._lock:
            self.commands[command.command_id] = command
        return command

    def fetch_commands(self, device_id: str) -> list[RemoteCommand]:
        with self._lock:
            pending = [
                c
                for c in self.commands.values()
                if c.target_device_id == device_id and c.status == "PENDING"
            ]
        return list(pending)

    def acknowledge_command(self, command: RemoteCommand) -> None:
        self.update_command(command)

    def update_command(self, command: RemoteCommand) -> None:
        with self._lock:
            self.commands[command.command_id] = command
            self.command_updates.append(command.to_dict())

    def sync_job(self, job: dict[str, Any]) -> None:
        with self._lock:
            self.jobs.append(dict(job))
            if len(self.jobs) > 200:
                self.jobs = self.jobs[-200:]

    def publish_event(self, event: RemoteEvent) -> None:
        with self._lock:
            self.events.append(event.to_dict())
            if len(self.events) > 500:
                self.events = self.events[-500:]

    def create_notification(
        self,
        *,
        event_type: str,
        message: str,
        job_id: str = "",
        device_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self.notifications.append(
                {
                    "event_type": event_type,
                    "message": message,
                    "job_id": job_id,
                    "device_id": device_id,
                    "metadata": dict(metadata or {}),
                    "at": now_iso(),
                }
            )
