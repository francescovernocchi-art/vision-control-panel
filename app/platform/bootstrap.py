"""PlatformBootstrap — livello superiore, dual-registration trasparente.

NON sostituisce app.bootstrap.create_vision_core.
Nessun componente operativo dipende ancora da questi registri.
"""

from __future__ import annotations

from typing import Any, Optional

from app.platform.capability_registry import CapabilityRegistry
from app.platform.consistency import run_consistency_check
from app.platform.context import PlatformContext
from app.platform.descriptors import (
    CommandDescriptor,
    EventDescriptor,
    ModuleDescriptor,
    ServiceDescriptor,
)
from app.platform.diagnostics import run_platform_diagnostics
from app.platform.health_bridge import ModuleHealthBridge
from app.platform.health_registry import HealthRegistry
from app.platform.service_registry import ServiceRegistry
from app.platform.skill_registry import SkillRegistry
from app.platform.status_normalizer import normalize_health_status
from app.platform.supervisor_view import SupervisorPlatformView
from utils.logger import get_logger
from utils.paths import PRODUCT_NAME, config_dir, data_dir, logs_dir, project_root

logger = get_logger("platform.bootstrap")

PLATFORM_VERSION = "0.4.0-supervisor-readonly"

_CONTEXT: Optional[PlatformContext] = None

# Percorsi skill dichiarati esplicitamente (NON discovery)
_STATIC_SKILL_MANIFESTS = (
    "app/modules/enispace/skill.json",
    "app/modules/coin_transport/skill.json",
)

# Cataloghi statici per dual-registration eniSpace (nessuna esecuzione)
_ENISPACE_COMMANDS = [
    CommandDescriptor(
        id="GET_STATUS",
        display_name="Stato (via eniSpace catalog)",
        description="Esposto anche nel catalogo skill eniSpace",
        module="enispace",
        permission="status_read",
        implemented=True,
    ),
    CommandDescriptor(
        id="CHECK_ENISPACE_MAIL",
        display_name="Controllo mail eniSpace",
        description="Esegue un ciclo controllo mail via JARVIS esistente",
        module="enispace",
        permission="mail_watch",
        implemented=True,
    ),
    CommandDescriptor(
        id="RETRY_JOB",
        display_name="Riprova job",
        description="Rimettere in PENDING un job JARVIS fallito",
        module="enispace",
        permission="job_retry",
        implemented=True,
    ),
    CommandDescriptor(
        id="PAUSE_MODULE",
        display_name="Pausa modulo",
        description="Mette offline/disabled un modulo",
        module="enispace",
        permission="module_control",
        implemented=True,
    ),
    CommandDescriptor(
        id="RESUME_MODULE",
        display_name="Riprendi modulo",
        description="Riavvia un modulo",
        module="enispace",
        permission="module_control",
        implemented=True,
    ),
]

_ENISPACE_EVENTS = [
    EventDescriptor("MAIL_RECEIVED", "INFO", "enispace", "Mail rilevata"),
    EventDescriptor("MAIL_ANALYZED", "INFO", "enispace", "Mail analizzata"),
    EventDescriptor("JOB_CREATED", "INFO", "enispace", "Job creato"),
    EventDescriptor("JOB_STARTED", "INFO", "enispace", "Job avviato"),
    EventDescriptor("JOB_PROGRESS", "INFO", "enispace", "Avanzamento job"),
    EventDescriptor("JOB_COMPLETED", "INFO", "enispace", "Job completato"),
    EventDescriptor("JOB_FAILED", "ERROR", "enispace", "Job fallito"),
    EventDescriptor("DOWNLOAD_STARTED", "INFO", "enispace", "Download avviato"),
    EventDescriptor("DOWNLOAD_COMPLETED", "INFO", "enispace", "Download completato"),
    EventDescriptor("PRINT_STARTED", "INFO", "enispace", "Stampa avviata"),
    EventDescriptor("PRINT_COMPLETED", "INFO", "enispace", "Stampa completata"),
    EventDescriptor("PRINT_FAILED", "ERROR", "enispace", "Stampa fallita"),
    EventDescriptor("NEEDS_ATTENTION", "WARNING", "enispace", "Intervento richiesto"),
    EventDescriptor("MODULE_ONLINE", "INFO", "enispace", "Modulo online"),
    EventDescriptor("MODULE_OFFLINE", "WARNING", "enispace", "Modulo offline"),
]


def get_platform_context() -> Optional[PlatformContext]:
    return _CONTEXT


def bootstrap_platform(
    core: Any = None,
    *,
    jarvis: Any = None,
    force: bool = False,
) -> PlatformContext:
    """
    Inizializza registri e dual-registra Core / eniSpace / Supervisor / Skills.
    Idempotente: chiamate successive senza force restituiscono il context esistente.
    """
    global _CONTEXT
    if _CONTEXT is not None and not force:
        return _CONTEXT

    capability = CapabilityRegistry()
    health = HealthRegistry()
    services = ServiceRegistry()
    skills = SkillRegistry()

    ctx = PlatformContext(
        capability=capability,
        health=health,
        services=services,
        skills=skills,
        version="2.0-vision",
        platform_version=PLATFORM_VERSION,
        config={
            "product": PRODUCT_NAME,
            "config_dir": str(config_dir()),
            "data_dir": str(data_dir()),
            "logs_dir": str(logs_dir()),
        },
        core=core,
    )

    # --- services: solo riferimenti esistenti, nessuna nuova istanza ---
    _register_services(ctx, core)
    _register_service_health(ctx)

    # --- Core ---
    _register_core(ctx, core)

    # --- eniSpace (catalogo parallelo; logica invariata) ---
    _register_enispace(ctx, core)

    # --- Supervisor (JARVIS / assistente) ---
    _register_supervisor(ctx, jarvis, core)

    # --- coin_transport catalog-only se già presente nel ModuleManager ---
    _register_coin_transport_catalog(ctx, core)

    # --- Health dual-write bridge (source of truth resta ModuleManager) ---
    bridge = ModuleHealthBridge(health)
    ctx.health_bridge = bridge
    if core is not None and hasattr(core, "modules"):
        bridge.attach(core.modules)
        bridge.attach_event_bus(getattr(core, "event_bus", None))
        bridge.sync_from_manager(core.modules)
    bridge.sync_core_and_supervisor(core=core, jarvis=jarvis)

    # --- Skill manifests statici (percorsi espliciti) ---
    _load_static_skills(ctx)

    # --- Supervisor read-only view (soft adapter, no command execution) ---
    view = SupervisorPlatformView(ctx)
    ctx.supervisor_view = view
    if core is not None:
        # Soft attach: VisionCore osserva Platform senza dipendenza obbligatoria
        try:
            setattr(core, "platform_view", view)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Impossibile attach platform_view su Core: %s", exc)

    # --- Consistency (non blocca) ---
    ctx.last_consistency = run_consistency_check(ctx)

    # --- Soft-DI consumer non critico (diagnostica) + fallback ---
    ctx.last_diagnostics = run_platform_diagnostics(ctx)

    _CONTEXT = ctx
    logger.info(
        "Platform initialized version=%s platform=%s services=%s modules=%s skills=%s",
        ctx.version,
        ctx.platform_version,
        ctx.services.list_ids(),
        [m.id for m in ctx.capability.list_modules()],
        [s.id for s in ctx.skills.list_skills()],
    )
    return ctx


def _load_static_skills(ctx: PlatformContext) -> None:
    root = project_root()
    for rel in _STATIC_SKILL_MANIFESTS:
        path = root / rel
        skill = ctx.skills.load_skill_manifest(path)
        if skill is None:
            continue
        # Sync catalogo: warning se mismatch, no auto-fix runtime
        mod = ctx.capability.get_module(skill.module_id)
        if mod is None:
            logger.warning(
                "Skill %s: module_id=%s assente in CapabilityRegistry",
                skill.id,
                skill.module_id,
            )
            continue
        for cmd in skill.commands:
            if cmd not in mod.commands:
                logger.warning(
                    "Skill/capability mismatch: skill=%s command=%s non in module %s",
                    skill.id,
                    cmd,
                    mod.id,
                )
        for ev in skill.events:
            if ev not in mod.events:
                logger.warning(
                    "Skill/capability mismatch: skill=%s event=%s non in module %s",
                    skill.id,
                    ev,
                    mod.id,
                )


def _register_services(ctx: PlatformContext, core: Any) -> None:
    """Registra solo istanze esistenti + descriptor; no nuove implementazioni."""

    def _reg(
        service_id: str,
        instance: Any,
        *,
        lifetime: str = "external",
        required: bool = False,
        health_managed: bool = True,
        display_name: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        ctx.services.register(
            service_id,
            instance,
            descriptor=ServiceDescriptor(
                service_id=service_id,
                display_name=display_name or service_id,
                version="1.0",
                lifetime=lifetime,
                required=required,
                health_managed=health_managed,
                available=True,
                metadata=dict(metadata or {}),
            ),
        )

    def _unavail(service_id: str, reason: str, *, required: bool = False) -> None:
        ctx.services.register_unavailable(
            service_id,
            descriptor=ServiceDescriptor(
                service_id=service_id,
                display_name=service_id,
                lifetime="external",
                required=required,
                health_managed=True,
                available=False,
                metadata={"reason": reason},
            ),
            reason=reason,
        )

    # Logger facade (modulo logging già usato) — non nuova infrastruttura
    _reg("logger", get_logger("platform"), lifetime="singleton", required=True)
    _reg(
        "configuration",
        {
            "config_dir": str(config_dir()),
            "data_dir": str(data_dir()),
            "logs_dir": str(logs_dir()),
        },
        lifetime="singleton",
        metadata={"kind": "paths"},
    )
    _reg(
        "storage",
        {"data_dir": str(data_dir()), "logs_dir": str(logs_dir())},
        lifetime="singleton",
        metadata={"kind": "paths"},
    )

    if core is not None and getattr(core, "event_bus", None) is not None:
        _reg("event_bus", core.event_bus, required=True, lifetime="external")
    else:
        _unavail("event_bus", "core.event_bus assente", required=True)

    if core is not None and getattr(core, "notifications", None) is not None:
        _reg(
            "notification",
            core.notifications,
            lifetime="external",
            metadata={"stub": True, "providers": "none"},
        )
    else:
        _unavail("notification", "core.notifications assente")

    if core is not None and getattr(core, "jobs", None) is not None:
        _reg("jobs", core.jobs, lifetime="external")
    else:
        _unavail("jobs", "core.jobs assente")


def _register_service_health(ctx: PlatformContext) -> None:
    """Health leggero per servizi — senza monitor complessi."""
    for desc in ctx.services.list_descriptors():
        if not desc.health_managed:
            continue
        hid = f"service:{desc.service_id}"
        if not desc.available or not ctx.services.has(desc.service_id):
            ctx.health.update(
                hid,
                "OFFLINE",
                target_type="service",
                ok=False,
                message=f"service {desc.service_id} unavailable",
                metadata={
                    "source": "service_registry",
                    "service_id": desc.service_id,
                    "reason": (desc.metadata or {}).get("reason", "unavailable"),
                },
            )
            continue
        # notification senza provider esterni → DEGRADED (stub)
        if desc.service_id == "notification" and (desc.metadata or {}).get("stub"):
            status = "DEGRADED"
            message = "notification stub (no external providers)"
        else:
            status = "ONLINE"
            message = f"service {desc.service_id} registered"
        ctx.health.update(
            hid,
            status,
            target_type="service",
            message=message,
            metadata={
                "source": "service_registry",
                "service_id": desc.service_id,
                "lifetime": desc.lifetime,
                **dict(desc.metadata or {}),
            },
        )


def _register_core(ctx: PlatformContext, core: Any) -> None:
    online = bool(core and getattr(core, "is_online", False))
    status = "ONLINE" if online else "OFFLINE"
    ctx.capability.register_module(
        ModuleDescriptor(
            id="core",
            display_name="VIS•ION Core",
            version=ctx.version,
            status=status,
            commands=["GET_STATUS"],
            events=["MODULE_ONLINE", "MODULE_OFFLINE", "JARVIS_STATE_CHANGED"],
            permissions=["orchestration"],
            dependencies=[],
            metadata={"product": PRODUCT_NAME, "role": "kernel"},
        )
    )
    ctx.capability.register_command(
        CommandDescriptor(
            id="GET_STATUS",
            display_name="Stato piattaforma",
            description="Snapshot Core / moduli / job",
            module="core",
            permission="status_read",
            implemented=True,
        )
    )
    ctx.health.update(
        "core",
        status,
        target_type="core",
        message="VisionCore dual-registered",
        metadata={"version": ctx.version},
    )


def _register_enispace(ctx: PlatformContext, core: Any) -> None:
    status = "ONLINE"
    version = "1.0"
    if core is not None:
        info = None
        try:
            info = core.modules.get_info("enispace") if hasattr(core, "modules") else None
        except Exception:
            info = None
        if info is not None:
            status = str(getattr(info, "status", status) or status)
            version = str(getattr(info, "version", version) or version)

    commands = [c.id for c in _ENISPACE_COMMANDS]
    events = [e.event for e in _ENISPACE_EVENTS]
    ctx.capability.register_module(
        ModuleDescriptor(
            id="enispace",
            display_name="eniSpace Automation",
            version=version,
            status=status,
            commands=commands,
            events=events,
            permissions=[
                "mail_watch",
                "enispace_login",
                "document_download",
                "print_queue",
                "jarvis_supervisor",
            ],
            dependencies=[
                "service:logger",
                "service:event_bus",
                "service:notification",
            ],
            metadata={"dual_registration": True, "logic_unchanged": True},
        )
    )
    for cmd in _ENISPACE_COMMANDS:
        ctx.capability.register_command(cmd)
    for ev in _ENISPACE_EVENTS:
        ctx.capability.register_event(ev)

    ctx.health.update(
        "enispace",
        status,
        target_type="module",
        message="eniSpace dual-registered (catalog only)",
        metadata={"version": version},
    )


def _register_supervisor(ctx: PlatformContext, jarvis: Any, core: Any) -> None:
    # Supervisor = JARVIS tecnico + stato assistente Core
    if jarvis is not None and getattr(jarvis, "is_active", False):
        status = "ONLINE"
        message = "JARVIS Supervisor attivo"
    elif core is not None and getattr(core, "is_online", False):
        status = "ONLINE"
        message = "Supervisor platform online (JARVIS non attivo)"
    else:
        status = "OFFLINE"
        message = "Supervisor non attivo"

    version = "1.0"
    ctx.capability.register_module(
        ModuleDescriptor(
            id="supervisor",
            display_name="VIS•ION Supervisor",
            version=version,
            status=status,
            commands=[],
            events=["JARVIS_STATE_CHANGED", "NEEDS_ATTENTION"],
            permissions=["supervision"],
            dependencies=["core", "enispace"],
            metadata={
                "assistant": "JARVIS",
                "jarvis_bound": jarvis is not None,
                "dual_registration": True,
            },
        )
    )
    ctx.health.update(
        "supervisor",
        status,
        target_type="supervisor",
        message=message,
        metadata={"version": version, "jarvis_bound": jarvis is not None},
    )


def _register_coin_transport_catalog(ctx: PlatformContext, core: Any) -> None:
    """Catalogo opzionale se il modulo è già nel ModuleManager — zero logica."""
    if core is None or not hasattr(core, "modules"):
        return
    try:
        info = core.modules.get_info("coin_transport")
    except Exception:
        return
    if info is None:
        return
    status = str(getattr(info, "status", "IN_DEVELOPMENT") or "IN_DEVELOPMENT")
    health_status, meta = normalize_health_status(status)
    ctx.capability.register_module(
        ModuleDescriptor(
            id="coin_transport",
            display_name=str(getattr(info, "name", "Trasporto Monete")),
            version=str(getattr(info, "version", "0.1")),
            status=status,
            commands=["PREPARE_COIN_TRANSPORT", "APPROVE_JOB", "REJECT_JOB"],
            events=[
                "JOB_CREATED",
                "JOB_STARTED",
                "JOB_PROGRESS",
                "DOCUMENT_CREATED",
                "PEC_PREPARED",
                "WAITING_APPROVAL",
                "JOB_COMPLETED",
                "JOB_FAILED",
                "NEEDS_ATTENTION",
            ],
            permissions=["pec_prepare", "approval_gate", "mail_analysis", "document_generation"],
            dependencies=["service:logger", "service:notification"],
            metadata={"dual_registration": True, "skeleton": True, "status": "IN_DEVELOPMENT"},
        )
    )
    for cmd_id, title, impl in (
        ("PREPARE_COIN_TRANSPORT", "Prepara trasporto monete", False),
        ("APPROVE_JOB", "Approva job", False),
        ("REJECT_JOB", "Rifiuta job", False),
    ):
        ctx.capability.register_command(
            CommandDescriptor(
                id=cmd_id,
                display_name=title,
                module="coin_transport",
                implemented=impl,
            )
        )
    meta = dict(meta)
    meta["source"] = "dual_write"
    ctx.health.update(
        "coin_transport",
        health_status,
        target_type="module",
        message="coin_transport dual-registered (catalog)",
        metadata=meta,
    )
