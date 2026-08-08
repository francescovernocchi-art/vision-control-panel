"""VisionRemoteAgent — adattatore outbound verso backend/PWA."""

from __future__ import annotations

import socket
import threading
import time
from typing import Any, Callable, Optional

from app.core.supervisor import VisionCore
from app.remote.client import create_backend
from app.remote.command_dispatcher import CommandDispatcher
from app.remote.command_validator import validate_command
from app.remote.config import RemoteConfig
from app.remote.event_sync import EventSync
from app.remote.heartbeat import HeartbeatService
from app.remote.models import (
    CommandStatus,
    DeviceIdentity,
    DeviceStatus,
    RemoteCommand,
    now_iso,
)
from app.remote.remote_log import remote_log
from app.remote.store import CommandStore

StatusListener = Callable[[str], None]

_BACKOFF = (2, 5, 10, 30, 60)


class VisionRemoteAgent:
    """
    Adattatore remoto:
    - HTTPS/WSS solo in uscita (quando backend reale disponibile)
    - kill switch locale VISION_REMOTE_ENABLED
    - non blocca UI / moduli
    """

    def __init__(
        self,
        core: VisionCore,
        config: Optional[RemoteConfig] = None,
        *,
        backend: Any = None,
        store: Optional[CommandStore] = None,
    ) -> None:
        self.core = core
        self.config = config or RemoteConfig.load()
        self.store = store or CommandStore()
        self.backend = backend or create_backend(self.config)
        self.dispatcher = CommandDispatcher(core)
        self.identity = DeviceIdentity(
            device_id=self.config.device_id,
            device_name=self.config.device_name,
            agent_version=self.config.agent_version,
            vision_version=self.config.vision_version,
            hostname=socket.gethostname(),
            status=DeviceStatus.DISABLED,
            modules=[],
        )
        self.events = EventSync(backend=self.backend, device_id=self.config.device_id)
        self.heartbeat = HeartbeatService(
            identity=self.identity,
            backend=self.backend,
            snapshot_provider=self._snapshot_for_heartbeat,
        )

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._enabled = False
        self._running = False
        self._status = DeviceStatus.DISABLED
        self._backoff_idx = 0
        self._listeners: list[StatusListener] = []
        self._bus_wired = False

    # ------------------------------------------------------------------ properties
    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def status(self) -> str:
        return self._status

    @property
    def is_running(self) -> bool:
        return self._running

    def add_status_listener(self, cb: StatusListener) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)

    def _set_status(self, status: str) -> None:
        self._status = status
        self.identity.status = status
        for cb in list(self._listeners):
            try:
                cb(status)
            except Exception:
                pass

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> bool:
        """Avvia solo se kill switch locale ON."""
        self.config = RemoteConfig.load()
        if not self.config.enabled:
            self._enabled = False
            self._set_status(DeviceStatus.DISABLED)
            remote_log.info(
                "Remote Agent DISABLED (VISION_REMOTE_ENABLED=false) device=%s",
                self.config.device_id,
            )
            return False

        with self._lock:
            if self._running and self._thread and self._thread.is_alive():
                return True
            self._enabled = True
            self._stop.clear()
            self._running = True
            self._wire_event_bus()
            self._thread = threading.Thread(
                target=self._loop, name="vision-remote-agent", daemon=True
            )
            self._thread.start()

        remote_log.info("Remote Agent started")
        remote_log.info("Device %s (%s)", self.config.device_id, self.config.device_name)
        return True

    def stop(self) -> None:
        with self._lock:
            self._stop.set()
            self._running = False
            self._enabled = False
        self._set_status(DeviceStatus.DISABLED)
        try:
            self.backend.disconnect()
        except Exception:
            pass
        remote_log.info("Remote Agent stopped")

    def set_enabled(self, enabled: bool) -> None:
        """Kill switch runtime (UI locale)."""
        # Aggiorna env di processo per coerenza con reload
        import os

        os.environ["VISION_REMOTE_ENABLED"] = "true" if enabled else "false"
        self.config.enabled = enabled
        if enabled:
            self.start()
        else:
            self.stop()

    def _wire_event_bus(self) -> None:
        if self._bus_wired:
            return
        try:
            self.core.event_bus.subscribe(None, self.events.on_core_event)
            self._bus_wired = True
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("Event bus wire failed: %s", exc)

    # ------------------------------------------------------------------ loop
    def _loop(self) -> None:
        connected = False
        last_heartbeat = 0.0
        while not self._stop.is_set() and self._enabled:
            try:
                if not connected:
                    self.backend.connect()
                    connected = True
                    self._backoff_idx = 0
                    self._set_status(DeviceStatus.ONLINE)
                    remote_log.info("Backend connected (mode=%s)", self.config.mode)
                    last_heartbeat = 0.0

                now = time.monotonic()
                if now - last_heartbeat >= float(self.config.heartbeat_seconds):
                    ok = self.heartbeat.send(status=DeviceStatus.ONLINE)
                    last_heartbeat = now
                    if not ok:
                        self._set_status(DeviceStatus.DEGRADED)
                        raise RuntimeError("heartbeat failed")
                    if self._status != DeviceStatus.ONLINE:
                        self._set_status(DeviceStatus.ONLINE)

                # poll + realtime futuro condividono handle_command (idempotente)
                self._poll_and_execute()

                if self._stop.wait(timeout=float(self.config.command_poll_seconds)):
                    break
            except Exception as exc:  # noqa: BLE001
                connected = False
                self._set_status(DeviceStatus.DEGRADED)
                remote_log.warning("Remote loop error: %s", exc)
                try:
                    self.backend.create_notification(
                        event_type="DEVICE_DEGRADED",
                        message=str(exc),
                        device_id=self.config.device_id,
                    )
                except Exception:
                    pass
                try:
                    self.backend.disconnect()
                except Exception:
                    pass
                delay = _BACKOFF[min(self._backoff_idx, len(_BACKOFF) - 1)]
                self._backoff_idx = min(self._backoff_idx + 1, len(_BACKOFF) - 1)
                remote_log.info("Reconnect backoff %ss", delay)
                if self._stop.wait(timeout=float(delay)):
                    break

        self._set_status(DeviceStatus.DISABLED)
        self._running = False

    def _snapshot_for_heartbeat(self) -> dict[str, Any]:
        snap = self.core.snapshot()
        jobs = [
            j.to_dict()
            for j in self.core.jobs.list_jobs(limit=10)
            if j.status in ("PROCESSING", "QUEUED", "PENDING")
        ]
        snap["current_jobs"] = jobs
        return snap

    # ------------------------------------------------------------------ commands
    def _poll_and_execute(self) -> None:
        try:
            commands = self.backend.fetch_commands(self.config.device_id)
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("fetch_commands failed: %s", exc)
            raise
        for raw in commands:
            try:
                self.handle_command(raw)
            except Exception as exc:  # noqa: BLE001
                remote_log.error("handle_command error: %s", exc)

    def handle_command(self, raw: RemoteCommand | dict[str, Any]) -> RemoteCommand:
        """Entry point unico (poll / mock inject / futuro realtime)."""
        command_id = ""
        if isinstance(raw, RemoteCommand):
            command_id = raw.command_id
        elif isinstance(raw, dict):
            command_id = str(raw.get("command_id") or "")

        already = self.store.already_handled(command_id) if command_id else False
        result = validate_command(
            raw, device_id=self.config.device_id, already_handled=already
        )
        if not result.ok or not result.command:
            cmd = result.command or RemoteCommand(
                command_id=command_id or "unknown",
                command_type="UNKNOWN",
                target_device_id=self.config.device_id,
            )
            cmd.status = CommandStatus.REJECTED
            cmd.error = result.reason
            cmd.finished_at = now_iso()
            self.store.upsert(cmd)
            try:
                self.backend.update_command(cmd)
            except Exception:
                pass
            remote_log.warning(
                "Command rejected id=%s reason=%s", cmd.command_id, result.reason
            )
            self.events.publish_command_event(
                "COMMAND_FAILED",
                command_id=cmd.command_id,
                message=result.reason,
                metadata={"rejected": True},
            )
            return cmd

        cmd = result.command
        remote_log.info("Command received %s id=%s", cmd.command_type, cmd.command_id)
        self.events.publish_command_event(
            "COMMAND_RECEIVED",
            command_id=cmd.command_id,
            message=cmd.command_type,
        )

        # ACK
        cmd.status = CommandStatus.ACKNOWLEDGED
        cmd.acknowledged_at = now_iso()
        self.store.upsert(cmd)
        try:
            self.backend.acknowledge_command(cmd)
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("acknowledge failed: %s", exc)
        remote_log.info("Command acknowledged id=%s", cmd.command_id)

        # EXECUTING
        cmd.status = CommandStatus.EXECUTING
        cmd.started_at = now_iso()
        self.store.upsert(cmd)
        try:
            self.backend.update_command(cmd)
        except Exception:
            pass
        remote_log.info("Command executing id=%s type=%s", cmd.command_id, cmd.command_type)
        self.events.publish_command_event(
            "COMMAND_STARTED",
            command_id=cmd.command_id,
            message=cmd.command_type,
        )

        try:
            payload = self.dispatcher.dispatch(cmd)
            ok = bool(payload.get("ok", True))
            if payload.get("code") == "NOT_IMPLEMENTED":
                # validato ma non operativo — COMPLETED con flag, non azione pericolosa
                cmd.status = CommandStatus.COMPLETED
                cmd.result = payload
                cmd.finished_at = now_iso()
                self.store.upsert(cmd)
                self.backend.update_command(cmd)
                remote_log.info(
                    "Command completed (NOT_IMPLEMENTED) id=%s", cmd.command_id
                )
                self.events.publish_command_event(
                    "COMMAND_COMPLETED",
                    command_id=cmd.command_id,
                    message="NOT_IMPLEMENTED",
                    metadata=payload,
                )
                return cmd

            if not ok and payload.get("code") not in (None, ""):
                cmd.status = CommandStatus.FAILED
                cmd.result = payload
                cmd.error = str(payload.get("message") or payload.get("code") or "failed")
                cmd.finished_at = now_iso()
                self.store.upsert(cmd)
                self.backend.update_command(cmd)
                remote_log.error("Command failed id=%s: %s", cmd.command_id, cmd.error)
                self.events.publish_command_event(
                    "COMMAND_FAILED",
                    command_id=cmd.command_id,
                    message=cmd.error,
                    metadata=payload,
                )
                return cmd

            cmd.status = CommandStatus.COMPLETED
            cmd.result = payload
            cmd.finished_at = now_iso()
            self.store.upsert(cmd)
            self.backend.update_command(cmd)
            # sync job se presente
            job = payload.get("job")
            if isinstance(job, dict):
                try:
                    job_out = dict(job)
                    job_out["device_id"] = self.config.device_id
                    self.backend.sync_job(job_out)
                except Exception:
                    pass
            remote_log.info("Command completed id=%s", cmd.command_id)
            self.events.publish_command_event(
                "COMMAND_COMPLETED",
                command_id=cmd.command_id,
                message=cmd.command_type,
                metadata={"ok": True},
            )
            return cmd
        except Exception as exc:  # noqa: BLE001
            cmd.status = CommandStatus.FAILED
            cmd.error = str(exc)
            cmd.finished_at = now_iso()
            self.store.upsert(cmd)
            try:
                self.backend.update_command(cmd)
            except Exception:
                pass
            remote_log.error("Command failed id=%s: %s", cmd.command_id, exc)
            self.events.publish_command_event(
                "COMMAND_FAILED",
                command_id=cmd.command_id,
                message=str(exc),
            )
            return cmd

    # ------------------------------------------------------------------ mock helpers
    def inject_mock_command(self, command: RemoteCommand) -> RemoteCommand:
        """Solo modalità mock / test."""
        if hasattr(self.backend, "enqueue_command"):
            self.backend.enqueue_command(command)
        return self.handle_command(command)
