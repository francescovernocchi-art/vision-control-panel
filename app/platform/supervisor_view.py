"""SupervisorPlatformView — vista read-only del PlatformContext per VIS•ION Supervisor.

Il Supervisor osserva skills/health/services/capabilities senza mutare registri
e senza eseguire comandi. Soft: se PlatformContext manca, snapshot degradato
senza crash.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from utils.logger import get_logger

logger = get_logger("platform.supervisor_view")

# Servizi esposti in vista (mai istanze Python)
_SERVICE_IDS = (
    "logger",
    "configuration",
    "storage",
    "event_bus",
    "notification",
    "jobs",
)

_SENSITIVE_META_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "api_key",
        "apikey",
        "supabase_agent_key",
        "keyring",
        "credential",
    }
)


@dataclass(frozen=True)
class SupervisorWarning:
    code: str
    severity: str  # INFO | WARNING | ERROR
    component: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SupervisorSkillView:
    skill_id: str
    name: str
    module_id: str
    version: str
    category: str
    enabled: bool
    health: str
    commands: tuple[str, ...]
    events: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "module_id": self.module_id,
            "version": self.version,
            "category": self.category,
            "enabled": self.enabled,
            "health": self.health,
            "commands": list(self.commands),
            "events": list(self.events),
        }


@dataclass(frozen=True)
class SupervisorHealthView:
    component_id: str
    component_type: str
    status: str
    ok: bool
    message: str
    updated_at: str
    source: str
    metadata: tuple[tuple[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "component_type": self.component_type,
            "status": self.status,
            "ok": self.ok,
            "message": self.message,
            "updated_at": self.updated_at,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SupervisorServiceView:
    service_id: str
    available: bool
    health: str
    version: str
    lifetime: str
    metadata: tuple[tuple[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_id": self.service_id,
            "available": self.available,
            "health": self.health,
            "version": self.version,
            "lifetime": self.lifetime,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SupervisorCapabilityView:
    module_id: str
    version: str
    commands_supported: tuple[str, ...]
    events_supported: tuple[str, ...]
    permissions: tuple[str, ...]
    dependencies: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "version": self.version,
            "commands_supported": list(self.commands_supported),
            "events_supported": list(self.events_supported),
            "permissions": list(self.permissions),
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True)
class SupervisorActiveJobView:
    job_id: str
    status: str
    module_id: str
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SupervisorSnapshot:
    supervisor_status: str
    platform_version: str
    overall_health: str
    core_health: Optional[SupervisorHealthView]
    agent_health: Optional[SupervisorHealthView]
    skills: tuple[SupervisorSkillView, ...]
    services: tuple[SupervisorServiceView, ...]
    capabilities: tuple[SupervisorCapabilityView, ...]
    warnings: tuple[SupervisorWarning, ...]
    active_job: Optional[SupervisorActiveJobView]
    last_updated: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "supervisor_status": self.supervisor_status,
            "platform_version": self.platform_version,
            "overall_health": self.overall_health,
            "core_health": self.core_health.to_dict() if self.core_health else None,
            "agent_health": self.agent_health.to_dict() if self.agent_health else None,
            "skills": [s.to_dict() for s in self.skills],
            "services": [s.to_dict() for s in self.services],
            "capabilities": [c.to_dict() for c in self.capabilities],
            "warnings": [w.to_dict() for w in self.warnings],
            "active_job": self.active_job.to_dict() if self.active_job else None,
            "last_updated": self.last_updated,
        }


def _safe_meta(raw: Optional[Mapping[str, Any]]) -> tuple[tuple[str, Any], ...]:
    if not raw:
        return ()
    out: list[tuple[str, Any]] = []
    for k, v in raw.items():
        key = str(k)
        if key.lower() in _SENSITIVE_META_KEYS or "password" in key.lower():
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out.append((key, v))
        else:
            out.append((key, str(v)[:120]))
    return tuple(out)


def _health_view_from_snap(snap: Any) -> Optional[SupervisorHealthView]:
    if snap is None:
        return None
    report = snap.to_report() if hasattr(snap, "to_report") else None
    if report is not None:
        return SupervisorHealthView(
            component_id=report.component_id,
            component_type=report.component_type,
            status=report.status,
            ok=bool(report.ok),
            message=report.message or "",
            updated_at=report.updated_at or "",
            source=report.source or "dual_write",
            metadata=_safe_meta(report.metadata),
        )
    # dict fallback
    if isinstance(snap, dict):
        return SupervisorHealthView(
            component_id=str(snap.get("component_id") or snap.get("target_id") or ""),
            component_type=str(snap.get("component_type") or snap.get("target_type") or "module"),
            status=str(snap.get("status") or "UNKNOWN"),
            ok=bool(snap.get("ok", True)),
            message=str(snap.get("message") or ""),
            updated_at=str(snap.get("updated_at") or snap.get("checked_at") or ""),
            source=str(snap.get("source") or "unknown"),
            metadata=_safe_meta(snap.get("metadata") if isinstance(snap.get("metadata"), dict) else {}),
        )
    return None


class SupervisorPlatformView:
    """
    Adapter read-only: PlatformContext → SupervisorSnapshot.
    Nessun execute/pause/enable/update/register.
    """

    def __init__(self, platform_context: Any = None) -> None:
        self._ctx = platform_context

    @property
    def available(self) -> bool:
        return self._ctx is not None

    def get_supervisor_snapshot(self) -> SupervisorSnapshot:
        try:
            return self._build_snapshot()
        except Exception as exc:  # noqa: BLE001 — soft: mai crash Supervisor
            logger.warning("SupervisorPlatformView snapshot failed: %s", exc)
            return SupervisorSnapshot(
                supervisor_status="UNKNOWN",
                platform_version="unavailable",
                overall_health="UNKNOWN",
                core_health=None,
                agent_health=None,
                skills=(),
                services=(),
                capabilities=(),
                warnings=(
                    SupervisorWarning(
                        code="SNAPSHOT_ERROR",
                        severity="WARNING",
                        component="supervisor_view",
                        message=str(exc)[:200],
                    ),
                ),
                active_job=None,
                last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

    def _build_snapshot(self) -> SupervisorSnapshot:
        ctx = self._ctx
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if ctx is None:
            return SupervisorSnapshot(
                supervisor_status="UNKNOWN",
                platform_version="unavailable",
                overall_health="UNKNOWN",
                core_health=None,
                agent_health=None,
                skills=(),
                services=(),
                capabilities=(),
                warnings=(
                    SupervisorWarning(
                        code="PLATFORM_CONTEXT_MISSING",
                        severity="WARNING",
                        component="platform",
                        message="PlatformContext non disponibile — vista vuota",
                    ),
                ),
                active_job=None,
                last_updated=now,
            )

        platform_version = str(getattr(ctx, "platform_version", None) or "unavailable")
        supervisor_status = self._resolve_supervisor_status(ctx)
        overall_health, health_components = self._resolve_health(ctx)
        skills = self._resolve_skills(ctx)
        services = self._resolve_services(ctx)
        capabilities = self._resolve_capabilities(ctx)
        core_health = next((h for h in health_components if h.component_id == "core"), None)
        agent_health = self._resolve_agent_health(ctx, health_components)
        warnings = self._build_warnings(
            ctx,
            skills=skills,
            services=services,
            overall_health=overall_health,
            agent_health=agent_health,
            health_components=health_components,
        )
        active_job = self._resolve_active_job(ctx)
        last_updated = now
        if health_components:
            stamps = [h.updated_at for h in health_components if h.updated_at]
            if stamps:
                last_updated = max(stamps)

        return SupervisorSnapshot(
            supervisor_status=supervisor_status,
            platform_version=platform_version,
            overall_health=overall_health,
            core_health=core_health,
            agent_health=agent_health,
            skills=skills,
            services=services,
            capabilities=capabilities,
            warnings=warnings,
            active_job=active_job,
            last_updated=last_updated,
        )

    def _resolve_supervisor_status(self, ctx: Any) -> str:
        """Stato Supervisor operativo — indipendente da overall platform health."""
        core = getattr(ctx, "core", None)
        if core is not None:
            if bool(getattr(core, "is_online", False)):
                return "ONLINE"
            return "OFFLINE"
        # fallback: health entry supervisor/core
        health = getattr(ctx, "health", None)
        if health is not None:
            for tid in ("supervisor", "core"):
                snap = health.get(tid) if hasattr(health, "get") else None
                if snap is not None and str(getattr(snap, "status", "")) == "ONLINE":
                    return "ONLINE"
            if health.get("core") is not None or health.get("supervisor") is not None:
                return "OFFLINE"
        return "UNKNOWN"

    def _resolve_health(
        self, ctx: Any
    ) -> tuple[str, tuple[SupervisorHealthView, ...]]:
        health = getattr(ctx, "health", None)
        if health is None:
            return "UNKNOWN", ()
        try:
            overall = "UNKNOWN"
            if hasattr(health, "compute_overall_status"):
                overall = str(health.compute_overall_status() or "UNKNOWN")
            elif hasattr(health, "get_health_snapshot"):
                hs = health.get_health_snapshot() or {}
                overall = str(hs.get("overall_status") or "UNKNOWN")
            items = []
            if hasattr(health, "list"):
                for snap in health.list():
                    view = _health_view_from_snap(snap)
                    if view is not None:
                        items.append(view)
            return overall, tuple(items)
        except Exception as exc:  # noqa: BLE001
            logger.warning("health resolve failed: %s", exc)
            return "UNKNOWN", ()

    def _resolve_skills(self, ctx: Any) -> tuple[SupervisorSkillView, ...]:
        skills_reg = getattr(ctx, "skills", None)
        if skills_reg is None or not hasattr(skills_reg, "list_skills"):
            return ()
        health = getattr(ctx, "health", None)
        out: list[SupervisorSkillView] = []
        try:
            for skill in skills_reg.list_skills():
                mid = str(getattr(skill, "module_id", "") or "")
                h_status = "unknown"
                if health is not None and mid and hasattr(health, "get"):
                    snap = health.get(mid)
                    if snap is not None:
                        h_status = str(getattr(snap, "status", "unknown") or "unknown")
                out.append(
                    SupervisorSkillView(
                        skill_id=str(getattr(skill, "id", "") or ""),
                        name=str(getattr(skill, "name", "") or ""),
                        module_id=mid,
                        version=str(getattr(skill, "version", "") or ""),
                        category=str(getattr(skill, "category", "") or ""),
                        enabled=bool(getattr(skill, "enabled", False)),
                        health=h_status,
                        commands=tuple(str(x) for x in (getattr(skill, "commands", None) or [])),
                        events=tuple(str(x) for x in (getattr(skill, "events", None) or [])),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("skills resolve failed: %s", exc)
            return ()
        return tuple(out)

    def _resolve_services(self, ctx: Any) -> tuple[SupervisorServiceView, ...]:
        services = getattr(ctx, "services", None)
        if services is None:
            return ()
        health = getattr(ctx, "health", None)
        out: list[SupervisorServiceView] = []
        try:
            # Prefer descriptors (no Python instances exposed)
            descriptors = []
            if hasattr(services, "list_descriptors"):
                descriptors = list(services.list_descriptors())
            by_id = {getattr(d, "service_id", ""): d for d in descriptors}
            for sid in _SERVICE_IDS:
                desc = by_id.get(sid)
                available = False
                version = "unavailable"
                lifetime = "external"
                meta: tuple[tuple[str, Any], ...] = ()
                if desc is not None:
                    available = bool(getattr(desc, "available", False)) and (
                        services.has(sid) if hasattr(services, "has") else available
                    )
                    version = str(getattr(desc, "version", "") or "unavailable")
                    lifetime = str(getattr(desc, "lifetime", "") or "external")
                    meta = _safe_meta(getattr(desc, "metadata", None) or {})
                elif hasattr(services, "has") and services.has(sid):
                    available = True
                    version = "1.0"
                h_status = "unavailable"
                if health is not None and hasattr(health, "get"):
                    snap = health.get(f"service:{sid}")
                    if snap is not None:
                        h_status = str(getattr(snap, "status", "unavailable") or "unavailable")
                    elif available:
                        h_status = "ONLINE"
                    else:
                        h_status = "OFFLINE"
                elif not available:
                    h_status = "unavailable"
                else:
                    h_status = "ONLINE"
                # Always list expected services (even if empty registry → unavailable)
                if desc is None and not available and not by_id:
                    # registry present but no descriptors/instances — still report unavailable rows
                    pass
                out.append(
                    SupervisorServiceView(
                        service_id=sid,
                        available=available,
                        health=h_status,
                        version=version if available or desc is not None else "unavailable",
                        lifetime=lifetime,
                        metadata=meta,
                    )
                )
            # If registry missing entirely we already returned (); if empty descriptors
            # and no has(), all six rows are unavailable — correct.
        except Exception as exc:  # noqa: BLE001
            logger.warning("services resolve failed: %s", exc)
            return ()
        return tuple(out)

    def _resolve_capabilities(self, ctx: Any) -> tuple[SupervisorCapabilityView, ...]:
        capability = getattr(ctx, "capability", None)
        if capability is None or not hasattr(capability, "list_modules"):
            return ()
        out: list[SupervisorCapabilityView] = []
        try:
            for mod in capability.list_modules():
                out.append(
                    SupervisorCapabilityView(
                        module_id=str(getattr(mod, "id", "") or ""),
                        version=str(getattr(mod, "version", "") or ""),
                        commands_supported=tuple(
                            str(x) for x in (getattr(mod, "commands", None) or [])
                        ),
                        events_supported=tuple(
                            str(x) for x in (getattr(mod, "events", None) or [])
                        ),
                        permissions=tuple(
                            str(x) for x in (getattr(mod, "permissions", None) or [])
                        ),
                        dependencies=tuple(
                            str(x) for x in (getattr(mod, "dependencies", None) or [])
                        ),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("capabilities resolve failed: %s", exc)
            return ()
        return tuple(out)

    def _resolve_agent_health(
        self,
        ctx: Any,
        health_components: tuple[SupervisorHealthView, ...],
    ) -> Optional[SupervisorHealthView]:
        for h in health_components:
            if h.component_type == "agent" or h.component_id in ("agent", "remote", "remote_agent"):
                return h
        health = getattr(ctx, "health", None)
        if health is not None and hasattr(health, "get"):
            for tid in ("agent", "remote", "remote_agent"):
                snap = health.get(tid)
                view = _health_view_from_snap(snap)
                if view is not None:
                    return view
        return None  # unavailable — represented as null, not inventato

    def _resolve_active_job(self, ctx: Any) -> Optional[SupervisorActiveJobView]:
        core = getattr(ctx, "core", None)
        jobs = None
        if core is not None:
            jobs = getattr(core, "jobs", None)
        if jobs is None:
            services = getattr(ctx, "services", None)
            if services is not None and hasattr(services, "get"):
                try:
                    jobs = services.get("jobs")
                except Exception:
                    jobs = None
        if jobs is None or not hasattr(jobs, "list_jobs"):
            return None
        try:
            for job in jobs.list_jobs(limit=50):
                status = str(getattr(job, "status", "") or "")
                if status in ("PROCESSING", "QUEUED", "PENDING", "WAITING_APPROVAL"):
                    return SupervisorActiveJobView(
                        job_id=str(getattr(job, "job_id", "") or ""),
                        status=status,
                        module_id=str(getattr(job, "module_id", "") or ""),
                        message=str(getattr(job, "message", "") or "")[:200],
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("active_job resolve failed: %s", exc)
        return None

    def _build_warnings(
        self,
        ctx: Any,
        *,
        skills: tuple[SupervisorSkillView, ...],
        services: tuple[SupervisorServiceView, ...],
        overall_health: str,
        agent_health: Optional[SupervisorHealthView],
        health_components: tuple[SupervisorHealthView, ...],
    ) -> tuple[SupervisorWarning, ...]:
        warnings: list[SupervisorWarning] = []

        # notification DEGRADED — evidenza da service health / vista
        for svc in services:
            if svc.service_id == "notification" and svc.health == "DEGRADED":
                warnings.append(
                    SupervisorWarning(
                        code="NOTIFICATION_DEGRADED",
                        severity="WARNING",
                        component="service:notification",
                        message="notification service DEGRADED (stub / no external providers)",
                    )
                )

        # coin_transport IN_DEVELOPMENT — evidenza da health metadata / skill
        coin_h = next((h for h in health_components if h.component_id == "coin_transport"), None)
        if coin_h is not None:
            meta = dict(coin_h.metadata)
            lifecycle = str(meta.get("lifecycle") or meta.get("module_status") or "")
            if lifecycle == "IN_DEVELOPMENT" or coin_h.status == "DEGRADED":
                # only emit IN_DEVELOPMENT if lifecycle evidence or skill metadata
                skill_coin = next((s for s in skills if s.skill_id == "coin_transport"), None)
                if lifecycle == "IN_DEVELOPMENT" or (
                    skill_coin is not None and not skill_coin.enabled
                ):
                    warnings.append(
                        SupervisorWarning(
                            code="COIN_TRANSPORT_IN_DEVELOPMENT",
                            severity="INFO",
                            component="coin_transport",
                            message="coin_transport in sviluppo (health DEGRADED / disabled skill)",
                        )
                    )

        # agent unavailable — evidenza: nessun health agent in registry
        if agent_health is None:
            warnings.append(
                SupervisorWarning(
                    code="AGENT_UNAVAILABLE",
                    severity="WARNING",
                    component="agent",
                    message="Remote Agent health non presente in HealthRegistry",
                )
            )

        # consistency issues (solo WARNING/ERROR già noti)
        consistency = getattr(ctx, "last_consistency", None)
        if consistency is not None:
            for issue in getattr(consistency, "issues", []) or []:
                code = str(getattr(issue, "code", "") or "")
                level = str(getattr(issue, "level", "WARNING") or "WARNING")
                if code and code not in {w.code for w in warnings}:
                    if level in ("WARNING", "ERROR"):
                        warnings.append(
                            SupervisorWarning(
                                code=code,
                                severity=level,
                                component="consistency",
                                message=str(getattr(issue, "message", "") or code)[:200],
                            )
                        )

        # overall DEGRADED info (non ERROR inventato)
        if overall_health == "DEGRADED" and not any(
            w.code == "PLATFORM_DEGRADED" for w in warnings
        ):
            warnings.append(
                SupervisorWarning(
                    code="PLATFORM_DEGRADED",
                    severity="INFO",
                    component="platform",
                    message="overall_health=DEGRADED (Supervisor può restare ONLINE)",
                )
            )

        return tuple(warnings)
