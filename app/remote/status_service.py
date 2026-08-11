"""RemoteStatusService — costruisce GET_STATUS da SupervisorPlatformView (read-only)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from app.remote.remote_log import remote_log
from app.remote.status_models import (
    RemoteAgentStatus,
    RemoteEniSpaceRuntimeStatus,
    RemoteModuleStatus,
    RemoteServiceStatus,
    RemoteSkillStatus,
    RemoteStatusResponse,
    RemoteWarningStatus,
    _iso_now,
)

# Warning da non ripetere quando è proprio l'Agent a rispondere
_SELF_AGENT_WARNINGS = frozenset({"AGENT_UNAVAILABLE"})

_MODULE_DISPLAY = {
    "enispace": "eniSpace Automation",
    "coin_transport": "Trasporto Monete",
    "core": "VIS•ION Core",
    "supervisor": "VIS•ION Supervisor",
}


class RemoteStatusService:
    """
    Flusso:
      SupervisorPlatformView → RemoteStatusResponse
      fallback PlatformContext snapshot → legacy core.snapshot()
    Mai crash; preferisce partial=true.
    """

    def __init__(
        self,
        core: Any = None,
        *,
        config: Any = None,
        agent: Any = None,
    ) -> None:
        self.core = core
        self.config = config
        self.agent = agent

    def build_status(self) -> dict[str, Any]:
        try:
            resp = self.build_response()
            return resp.to_dict()
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("RemoteStatusService build_status failed: %s", exc)
            return self._attach_enispace_runtime(
                RemoteStatusResponse(
                    ok=True,
                    core_status="DEGRADED",
                    supervisor_status="UNKNOWN",
                    overall_health="DEGRADED",
                    partial=True,
                    missing_sections=("skills", "services", "modules", "warnings"),
                    timestamp=_iso_now(),
                    device_id=self._device_id(),
                    device_name=self._device_name(),
                    agent_version=self._agent_version(),
                    vision_version=self._vision_version(),
                    platform_version="unavailable",
                    remote_control_enabled=self._remote_enabled(),
                    agent=self._agent_status_dto(last_error=str(exc)[:200]),
                    vision_core={"online": False, "error": "status_build_failed"},
                )
            ).to_dict()

    def build_response(self) -> RemoteStatusResponse:
        missing: list[str] = []
        # 1) SupervisorPlatformView
        snap = self._try_supervisor_snapshot()
        source = "supervisor_view" if snap is not None else None

        # 2) PlatformContext snapshot
        platform_snap = None
        if snap is None:
            platform_snap = self._try_platform_snapshot()
            if platform_snap is not None:
                source = "platform_snapshot"

        # 3) legacy core.snapshot
        legacy = None
        if snap is None and platform_snap is None:
            legacy = self._try_legacy_snapshot()
            if legacy is not None:
                source = "legacy"
            else:
                source = "none"
                missing.extend(["skills", "services", "modules", "warnings"])

        if source == "supervisor_view":
            return self._attach_enispace_runtime(self._from_supervisor(snap, missing))
        if source == "platform_snapshot":
            return self._attach_enispace_runtime(self._from_platform(platform_snap, missing))
        if source == "legacy":
            return self._attach_enispace_runtime(self._from_legacy(legacy, missing))
        return self._attach_enispace_runtime(
            RemoteStatusResponse(
                ok=True,
                device_id=self._device_id(),
                device_name=self._device_name(),
                agent_version=self._agent_version(),
                vision_version=self._vision_version(),
                platform_version="unavailable",
                timestamp=_iso_now(),
                core_status="DEGRADED",
                supervisor_status="UNKNOWN",
                overall_health="DEGRADED",
                partial=True,
                missing_sections=tuple(missing) or ("skills", "services", "modules"),
                remote_control_enabled=self._remote_enabled(),
                agent=self._agent_status_dto(),
                vision_core={"online": False},
            )
        )

    def build_heartbeat_summary(self) -> dict[str, Any]:
        """Payload leggero per heartbeat — non full GET_STATUS."""
        try:
            resp = self.build_response()
            modules_summary = [
                {
                    "module_id": m.module_id,
                    "status": m.status,
                    "health": m.health,
                }
                for m in resp.modules
                if m.module_id in ("enispace", "coin_transport", "core")
            ]
            job_id = ""
            if resp.current_job and isinstance(resp.current_job, dict):
                job_id = str(resp.current_job.get("job_id") or "")
            return {
                "device_id": resp.device_id,
                "status": self._agent_runtime_status(),
                "agent_version": resp.agent_version,
                "vision_version": resp.vision_version,
                "platform_version": resp.platform_version,
                "current_job_id": job_id,
                "modules": modules_summary,
                "timestamp": resp.timestamp or _iso_now(),
            }
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("heartbeat summary failed: %s", exc)
            return {
                "device_id": self._device_id(),
                "status": "DEGRADED",
                "agent_version": self._agent_version(),
                "vision_version": self._vision_version(),
                "platform_version": "unavailable",
                "current_job_id": "",
                "modules": [],
                "timestamp": _iso_now(),
            }

    def _attach_enispace_runtime(self, resp: RemoteStatusResponse) -> RemoteStatusResponse:
        """Phase 3D: attach additive ``enispace_runtime`` (backward compatible, read-only)."""
        missing = list(resp.missing_sections)
        warnings = list(resp.warnings)
        try:
            runtime = self._build_enispace_runtime()
        except Exception as exc:  # noqa: BLE001
            remote_log.debug("enispace_runtime section skipped: %s", exc)
            runtime = RemoteEniSpaceRuntimeStatus(
                status="UNKNOWN",
                available=False,
                last_error="enispace_runtime_unavailable",
            )
            if "enispace_runtime" not in missing:
                missing.append("enispace_runtime")
            warnings.append(
                RemoteWarningStatus(
                    code="ENISPACE_RUNTIME_UNAVAILABLE",
                    severity="warning",
                    component="enispace",
                    message="EniSpace runtime observability unavailable",
                )
            )
            return replace(
                resp,
                enispace_runtime=runtime,
                partial=True,
                missing_sections=tuple(dict.fromkeys(missing)),
                warnings=tuple(warnings),
            )

        if runtime.available is False and "enispace_runtime" not in missing:
            missing.append("enispace_runtime")
            return replace(
                resp,
                enispace_runtime=runtime,
                partial=True if missing else resp.partial,
                missing_sections=tuple(dict.fromkeys(missing)),
            )
        return replace(resp, enispace_runtime=runtime)

    def _build_enispace_runtime(self) -> RemoteEniSpaceRuntimeStatus:
        """
        Read-only EniSpace / legacy supervisor snapshot.
        Dual-job: never merges into Vision Core current_job / queue_size.
        No mail/process/print/download side effects.
        """
        worker = self._resolve_enispace_worker()
        if worker is None:
            return RemoteEniSpaceRuntimeStatus(
                status="UNKNOWN",
                available=False,
                active=None,
                pending_jobs=None,
                current_job=None,
                last_job=None,
                last_mail_check=None,
                last_error=None,
            )

        active = bool(getattr(worker, "is_active", False))
        processing = bool(getattr(worker, "is_processing", False))
        detail_state = str(getattr(worker, "state", "") or "") or None

        pending: Optional[int]
        try:
            pc = getattr(worker, "pending_count", None)
            if callable(pc):
                pending = int(pc())
            elif pc is None:
                pending = None
            else:
                pending = int(pc)
        except Exception:
            pending = None

        last_check_raw = getattr(worker, "last_check", None)
        last_mail_check: Optional[str]
        if last_check_raw in (None, "", "—"):
            last_mail_check = None
        else:
            last_mail_check = str(last_check_raw)

        current_job = self._sanitize_enispace_job(getattr(worker, "current_job", None))

        last_summary = getattr(worker, "last_job_summary", None)
        last_job: Optional[dict[str, Any]]
        if last_summary in (None, "", "—"):
            last_job = None
        else:
            last_job = {"summary": str(last_summary)[:240]}

        last_error: Optional[str] = None
        cur = getattr(worker, "current_job", None)
        if cur is not None:
            err = getattr(cur, "error_message", None)
            if err:
                last_error = str(err)[:200]

        status = self._map_enispace_status(
            active=active,
            processing=processing,
            detail_state=detail_state or "",
        )

        return RemoteEniSpaceRuntimeStatus(
            status=status,
            available=True,
            active=active,
            pending_jobs=pending,
            current_job=current_job,
            last_job=last_job,
            last_mail_check=last_mail_check,
            last_error=last_error,
            detail_state=detail_state,
        )

    @staticmethod
    def _map_enispace_status(*, active: bool, processing: bool, detail_state: str) -> str:
        """Map legacy supervisor state → remote enum (no product branding)."""
        if not active:
            return "OFFLINE"
        if processing:
            return "PROCESSING"
        normalized = detail_state.strip().upper()
        if normalized in {"ERRORE", "INTERVENTO RICHIESTO"}:
            return "DEGRADED"
        processing_states = {
            "CONTROLLO MAIL",
            "NUOVA MAIL RILEVATA",
            "ANALISI MAIL",
            "CONTRATTO RICONOSCIUTO",
            "ACCESSO ENISPACE",
            "RICERCA DOCUMENTI",
            "DOWNLOAD",
            "PREPARAZIONE STAMPA",
            "STAMPA",
            "VERIFICA",
        }
        if normalized in processing_states:
            return "PROCESSING"
        if normalized == "OFFLINE":
            return "OFFLINE"
        if normalized in {"IN ATTESA", "COMPLETATO", ""}:
            return "IDLE"
        return "IDLE"

    @staticmethod
    def _sanitize_enispace_job(job: Any) -> Optional[dict[str, Any]]:
        """JSON-safe EniSpace job DTO — no secrets, no filesystem dumps."""
        if job is None:
            return None
        if isinstance(job, dict):
            # Already a dict (tests / mocks) — whitelist keys only
            allowed = (
                "id",
                "status",
                "state",
                "order_number",
                "contract_number",
                "docs_found",
                "docs_downloaded",
                "docs_printed",
                "attempts",
                "max_attempts",
                "error_message",
                "started_at",
                "finished_at",
                "last_event_at",
                "subject",
            )
            out = {k: job[k] for k in allowed if k in job and job[k] not in (None, "")}
            if "error_message" in out:
                out["error_message"] = str(out["error_message"])[:200]
            return out or None

        out: dict[str, Any] = {}
        for key in (
            "id",
            "status",
            "state",
            "order_number",
            "contract_number",
            "docs_found",
            "docs_downloaded",
            "docs_printed",
            "attempts",
            "max_attempts",
            "started_at",
            "finished_at",
            "last_event_at",
            "subject",
        ):
            val = getattr(job, key, None)
            if val not in (None, ""):
                out[key] = val
        err = getattr(job, "error_message", None)
        if err:
            out["error_message"] = str(err)[:200]
        return out or None

    def _resolve_enispace_worker(self) -> Any:
        core = self.core
        if core is None:
            return None
        modules = getattr(core, "modules", None)
        if modules is None:
            return None
        get = getattr(modules, "get", None)
        if not callable(get):
            return None
        eni = get("enispace")
        if eni is None:
            return None
        return getattr(eni, "jarvis", None)

    # ------------------------------------------------------------------ builders

    def _from_supervisor(self, snap: Any, missing: list[str]) -> RemoteStatusResponse:
        self._sync_agent_health(snap)
        skills = tuple(
            RemoteSkillStatus(
                skill_id=s.skill_id,
                name=s.name,
                enabled=bool(s.enabled),
                module_id=s.module_id,
                version=s.version,
                category=s.category,
                health=s.health,
            )
            for s in (snap.skills or ())
        )
        services = tuple(
            RemoteServiceStatus(
                service_id=s.service_id,
                available=bool(s.available),
                health=s.health,
            )
            for s in (snap.services or ())
        )
        if not skills:
            missing.append("skills")
        if not services:
            missing.append("services")

        modules = self._modules_from_supervisor(snap)
        if not modules:
            missing.append("modules")

        warnings = tuple(
            RemoteWarningStatus(
                code=w.code,
                severity=w.severity,
                component=w.component,
                message=w.message,
            )
            for w in (snap.warnings or ())
            if w.code not in _SELF_AGENT_WARNINGS
        )

        core_status = "UNKNOWN"
        if snap.core_health is not None:
            core_status = str(snap.core_health.status)
        overall = str(snap.overall_health or "UNKNOWN")
        current_job = snap.active_job.to_dict() if snap.active_job else None
        queue_size = self._queue_size()

        online = core_status == "ONLINE" or bool(
            self.core and getattr(self.core, "is_online", False)
        )
        return RemoteStatusResponse(
            device_id=self._device_id(),
            device_name=self._device_name(),
            agent_version=self._agent_version(),
            vision_version=self._vision_version(),
            platform_version=str(snap.platform_version or self._platform_version()),
            timestamp=_iso_now(),
            core_status=core_status,
            supervisor_status=str(snap.supervisor_status or "UNKNOWN"),
            overall_health=overall,
            current_job=current_job,
            queue_size=queue_size,
            modules=modules,
            skills=skills,
            services=services,
            warnings=warnings,
            remote_control_enabled=self._remote_enabled(),
            agent=self._agent_status_dto(),
            partial=bool(missing),
            missing_sections=tuple(dict.fromkeys(missing)),
            ok=True,
            vision_core={
                "online": online,
                "product": getattr(self.core, "product_name", "VIS•ION") if self.core else "VIS•ION",
                "product_name": "VISION",
                # LEGACY: assistant naming residual — do not rename in Phase 3D (compat)
                "assistant": getattr(self.core, "assistant_name", "JARVIS") if self.core else "JARVIS",
                "assistant_state": str(getattr(self.core, "assistant_state", "") or ""),
                "started_at": str(getattr(self.core, "started_at", "") or ""),
            },
        )

    def _from_platform(self, platform_snap: dict, missing: list[str]) -> RemoteStatusResponse:
        missing.append("supervisor_view")
        skills_raw = platform_snap.get("skills") or []
        services_raw = platform_snap.get("services") or []
        modules_raw = platform_snap.get("modules") or []
        skills = tuple(
            RemoteSkillStatus(
                skill_id=str(s.get("id") or s.get("skill_id") or ""),
                name=str(s.get("name") or ""),
                enabled=bool(s.get("enabled", False)),
                module_id=str(s.get("module_id") or ""),
                version=str(s.get("version") or ""),
                category=str(s.get("category") or ""),
                health="unknown",
            )
            for s in skills_raw
            if isinstance(s, dict)
        )
        services = tuple(
            RemoteServiceStatus(
                service_id=str(s.get("service_id") or ""),
                available=bool(s.get("available", False)),
                health="ONLINE" if s.get("available") else "OFFLINE",
            )
            for s in services_raw
            if isinstance(s, dict) and s.get("service_id")
        )
        modules = []
        for m in modules_raw:
            if not isinstance(m, dict):
                continue
            mid = str(m.get("id") or m.get("module_id") or "")
            if mid not in ("enispace", "coin_transport"):
                continue
            st = str(m.get("status") or "UNKNOWN")
            health = "DEGRADED" if st == "IN_DEVELOPMENT" else st
            modules.append(
                RemoteModuleStatus(
                    module_id=mid,
                    display_name=_MODULE_DISPLAY.get(mid, mid),
                    version=str(m.get("version") or ""),
                    status=st,
                    health=health,
                    enabled=mid == "enispace",
                )
            )
        overall = str(platform_snap.get("overall_health") or "UNKNOWN")
        if isinstance(platform_snap.get("components_health"), dict):
            overall = str(
                platform_snap["components_health"].get("overall_status") or overall
            )
        core_online = bool(self.core and getattr(self.core, "is_online", False))
        return RemoteStatusResponse(
            device_id=self._device_id(),
            device_name=self._device_name(),
            agent_version=self._agent_version(),
            vision_version=self._vision_version(),
            platform_version=str(
                platform_snap.get("platform_version") or self._platform_version()
            ),
            timestamp=_iso_now(),
            core_status="ONLINE" if core_online else "OFFLINE",
            supervisor_status="ONLINE" if core_online else "UNKNOWN",
            overall_health=overall,
            current_job=None,
            queue_size=self._queue_size(),
            modules=tuple(modules),
            skills=skills,
            services=services,
            warnings=(),
            remote_control_enabled=self._remote_enabled(),
            agent=self._agent_status_dto(),
            partial=True,
            missing_sections=tuple(dict.fromkeys(missing + (["warnings"] if True else []))),
            ok=True,
            vision_core={"online": core_online},
        )

    def _from_legacy(self, legacy: dict, missing: list[str]) -> RemoteStatusResponse:
        missing.extend(["skills", "services", "warnings"])
        modules = []
        for m in legacy.get("modules") or []:
            if not isinstance(m, dict):
                continue
            mid = str(m.get("id") or "")
            if mid not in ("enispace", "coin_transport"):
                continue
            st = str(m.get("status") or "UNKNOWN")
            health = "DEGRADED" if st == "IN_DEVELOPMENT" else st
            modules.append(
                RemoteModuleStatus(
                    module_id=mid,
                    display_name=str(m.get("name") or _MODULE_DISPLAY.get(mid, mid)),
                    version=str(m.get("version") or ""),
                    status=st,
                    health=health,
                    enabled=mid == "enispace" and st == "ONLINE",
                )
            )
        if not modules:
            missing.append("modules")
        kpi = legacy.get("kpi") or {}
        queue = int(kpi.get("queued", 0) or 0) + int(kpi.get("processing", 0) or 0)
        online = bool(legacy.get("core_online"))
        return RemoteStatusResponse(
            device_id=self._device_id(),
            device_name=self._device_name(),
            agent_version=self._agent_version(),
            vision_version=self._vision_version(),
            platform_version=self._platform_version() or "unavailable",
            timestamp=_iso_now(),
            core_status="ONLINE" if online else "OFFLINE",
            supervisor_status="ONLINE" if online else "OFFLINE",
            overall_health="DEGRADED" if online else "OFFLINE",
            current_job=None,
            queue_size=queue,
            modules=tuple(modules),
            skills=(),
            services=(),
            warnings=(),
            remote_control_enabled=self._remote_enabled(),
            agent=self._agent_status_dto(),
            partial=True,
            missing_sections=tuple(dict.fromkeys(missing)),
            ok=True,
            vision_core={
                "online": online,
                "product": legacy.get("product"),
                "product_name": "VISION",
                "assistant": legacy.get("assistant"),
                "assistant_state": legacy.get("assistant_state"),
                "started_at": legacy.get("started_at"),
            },
        )

    def _modules_from_supervisor(self, snap: Any) -> tuple[RemoteModuleStatus, ...]:
        # Prefer capability modules + health
        by_cap = {c.module_id: c for c in (snap.capabilities or ())}
        by_skill = {s.module_id: s for s in (snap.skills or ())}
        out: list[RemoteModuleStatus] = []
        for mid in ("enispace", "coin_transport"):
            health = "unknown"
            # from skill health
            sk = by_skill.get(mid)
            if sk is not None:
                health = sk.health
            # from core health list via platform
            ctx = self._platform_context()
            if ctx is not None and getattr(ctx, "health", None) is not None:
                h = ctx.health.get(mid)
                if h is not None:
                    health = str(getattr(h, "status", health) or health)
            status = health
            enabled = bool(sk.enabled) if sk is not None else (mid == "enispace")
            # capability status if present
            cap = by_cap.get(mid)
            version = cap.version if cap else (sk.version if sk else "")
            display = _MODULE_DISPLAY.get(mid, mid)
            if ctx is not None and hasattr(ctx, "capability") and ctx.capability:
                mod = ctx.capability.get_module(mid)
                if mod is not None:
                    status = str(getattr(mod, "status", status) or status)
                    version = str(getattr(mod, "version", version) or version)
                    display = str(getattr(mod, "display_name", display) or display)
            # normalize IN_DEVELOPMENT
            if status == "IN_DEVELOPMENT":
                health = "DEGRADED"
            current_job = None
            if snap.active_job and getattr(snap.active_job, "module_id", "") == mid:
                current_job = snap.active_job.job_id
            out.append(
                RemoteModuleStatus(
                    module_id=mid,
                    display_name=display,
                    version=version,
                    status=status,
                    health=health,
                    enabled=enabled,
                    current_job=current_job,
                )
            )
        return tuple(out)

    # ------------------------------------------------------------------ sources

    def _try_supervisor_snapshot(self) -> Any:
        view = None
        if self.agent is not None:
            view = getattr(self.agent, "platform_view", None) or getattr(
                getattr(self.agent, "core", None), "platform_view", None
            )
        if view is None and self.core is not None:
            view = getattr(self.core, "platform_view", None)
        ctx = self._platform_context()
        if view is None and ctx is not None:
            view = getattr(ctx, "supervisor_view", None)
        if view is None and ctx is not None and hasattr(ctx, "get_supervisor_snapshot"):
            try:
                return ctx.get_supervisor_snapshot()
            except Exception as exc:  # noqa: BLE001
                remote_log.warning("get_supervisor_snapshot failed: %s", exc)
                return None
        if view is not None and hasattr(view, "get_supervisor_snapshot"):
            try:
                return view.get_supervisor_snapshot()
            except Exception as exc:  # noqa: BLE001
                remote_log.warning("SupervisorPlatformView failed: %s", exc)
        return None

    def _try_platform_snapshot(self) -> Optional[dict]:
        ctx = self._platform_context()
        if ctx is None or not hasattr(ctx, "get_platform_snapshot"):
            return None
        try:
            snap = ctx.get_platform_snapshot()
            return snap if isinstance(snap, dict) else None
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("platform snapshot failed: %s", exc)
            return None

    def _try_legacy_snapshot(self) -> Optional[dict]:
        if self.core is None or not hasattr(self.core, "snapshot"):
            return None
        try:
            snap = self.core.snapshot()
            return snap if isinstance(snap, dict) else None
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("legacy core.snapshot failed: %s", exc)
            return None

    def _platform_context(self) -> Any:
        try:
            from app.platform.bootstrap import get_platform_context

            ctx = get_platform_context()
            if ctx is not None:
                return ctx
        except Exception:
            pass
        # soft bootstrap if core available (tests / agent senza UI)
        if self.core is not None:
            try:
                from app.platform import bootstrap_platform

                return bootstrap_platform(self.core, force=False)
            except Exception as exc:  # noqa: BLE001
                remote_log.warning("bootstrap_platform soft failed: %s", exc)
        return None

    def _sync_agent_health(self, snap: Any = None) -> None:
        """Registra health agent (dual-write soft) quando Agent sta rispondendo."""
        ctx = self._platform_context()
        if ctx is None or getattr(ctx, "health", None) is None:
            return
        try:
            status = self._agent_runtime_status()
            health_status = "ONLINE" if status in ("ONLINE",) else (
                "DEGRADED" if status == "DEGRADED" else "OFFLINE"
            )
            if status == "DISABLED":
                health_status = "DISABLED"
            ctx.health.update(
                "agent",
                health_status,
                target_type="agent",
                message="Remote Agent GET_STATUS reporting",
                metadata={
                    "source": "remote_agent",
                    "remote_mode": self._remote_mode(),
                    "connected_backend": self._backend_name(),
                    "lifecycle": health_status,
                },
            )
        except Exception as exc:  # noqa: BLE001
            remote_log.warning("agent health sync failed: %s", exc)

    # ------------------------------------------------------------------ helpers

    def _device_id(self) -> str:
        if self.config is not None:
            return str(getattr(self.config, "device_id", "") or "VIS-TARANTO-01")
        return "VIS-TARANTO-01"

    def _device_name(self) -> str:
        if self.config is not None:
            return str(getattr(self.config, "device_name", "") or "PC VIS Taranto")
        return "PC VIS Taranto"

    def _agent_version(self) -> str:
        if self.config is not None:
            return str(getattr(self.config, "agent_version", "") or "0.1.0")
        return "0.1.0"

    def _vision_version(self) -> str:
        if self.config is not None:
            return str(getattr(self.config, "vision_version", "") or "2.0-vision")
        if self.core is not None:
            return "2.0-vision"
        return "2.0-vision"

    def _platform_version(self) -> str:
        ctx = self._platform_context()
        if ctx is not None:
            return str(getattr(ctx, "platform_version", "") or "")
        return ""

    def _remote_enabled(self) -> bool:
        if self.agent is not None:
            return bool(getattr(self.agent, "enabled", False))
        if self.config is not None:
            return bool(getattr(self.config, "enabled", False))
        return False

    def _remote_mode(self) -> str:
        if self.config is not None:
            return str(getattr(self.config, "mode", "mock") or "mock")
        return "mock"

    def _backend_name(self) -> str:
        if self.agent is not None:
            backend = getattr(self.agent, "backend", None)
            if backend is not None:
                return type(backend).__name__
        return self._remote_mode()

    def _agent_runtime_status(self) -> str:
        if self.agent is not None:
            return str(getattr(self.agent, "status", "DISABLED") or "DISABLED")
        if self._remote_enabled():
            return "ONLINE"
        return "DISABLED"

    def _agent_status_dto(self, last_error: str = "") -> RemoteAgentStatus:
        last_hb = ""
        if self.agent is not None:
            identity = getattr(self.agent, "identity", None)
            if identity is not None:
                last_hb = str(getattr(identity, "last_seen_at", "") or "")
        return RemoteAgentStatus(
            status=self._agent_runtime_status(),
            connected_backend=self._backend_name(),
            remote_mode=self._remote_mode(),
            last_heartbeat=last_hb,
            last_error=last_error[:200] if last_error else "",
        )

    def _queue_size(self) -> int:
        if self.core is None or not hasattr(self.core, "jobs"):
            return 0
        try:
            jobs = self.core.jobs.list_jobs(limit=50)
            return sum(
                1
                for j in jobs
                if str(getattr(j, "status", ""))
                in ("PROCESSING", "QUEUED", "PENDING", "WAITING_APPROVAL")
            )
        except Exception:
            return 0
