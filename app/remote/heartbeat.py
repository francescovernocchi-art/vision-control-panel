"""Heartbeat outbound — aggiorna last_seen_at sul backend."""

from __future__ import annotations

from typing import Any, Callable, Optional

from app.remote.models import DeviceIdentity, DeviceStatus, now_iso
from app.remote.remote_log import remote_log


class HeartbeatService:
    def __init__(
        self,
        *,
        identity: DeviceIdentity,
        backend: Any,
        snapshot_provider: Optional[Callable[[], dict[str, Any]]] = None,
    ) -> None:
        self.identity = identity
        self.backend = backend
        self.snapshot_provider = snapshot_provider

    def refresh_identity(self, status: str = DeviceStatus.ONLINE) -> DeviceIdentity:
        snap = self.snapshot_provider() if self.snapshot_provider else {}
        modules = snap.get("modules") or self.identity.modules
        current = ""
        for job in snap.get("current_jobs") or []:
            if isinstance(job, dict) and job.get("job_id"):
                current = str(job["job_id"])
                break
        if not current:
            for j in (snap.get("jobs_processing") or []):
                current = str(j)
                break
        self.identity.status = status
        self.identity.last_seen_at = now_iso()
        self.identity.modules = list(modules)
        self.identity.current_job_id = current or self.identity.current_job_id
        if snap.get("platform_version"):
            self.identity.platform_version = str(snap.get("platform_version") or "")
        return self.identity

    def send(self, status: str = DeviceStatus.ONLINE) -> bool:
        identity = self.refresh_identity(status=status)
        try:
            self.backend.heartbeat(identity)
            remote_log.info(
                "Heartbeat sent device=%s status=%s",
                identity.device_id,
                identity.status,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("Heartbeat failed: %s", exc)
            return False
