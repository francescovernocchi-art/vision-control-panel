"""PlatformBootstrap — livello superiore, dual-registration trasparente.

NON sostituisce app.bootstrap.create_vision_core.
Nessun componente operativo dipende ancora da questi registri.
"""

from __future__ import annotations

from typing import Any, Optional

from app.platform.capability_registry import CapabilityRegistry
from app.platform.context import PlatformContext
from app.platform.descriptors import (
    CommandDescriptor,
    EventDescriptor,
    ModuleDescriptor,
)
from app.platform.health_registry import HealthRegistry
from app.platform.service_registry import ServiceRegistry
from utils.logger import get_logger
from utils.paths import PRODUCT_NAME, config_dir, data_dir, logs_dir

logger = get_logger("platform.bootstrap")

_CONTEXT: Optional[PlatformContext] = None

# Cataloghi statici per dual-registration eniSpace (nessuna esecuzione)
_ENISPACE_COMMANDS = [
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
    Inizializza registri e dual-registra Core / eniSpace / Supervisor.
    Idempotente: chiamate successive senza force restituiscono il context esistente.
    """
    global _CONTEXT
    if _CONTEXT is not None and not force:
        return _CONTEXT

    capability = CapabilityRegistry()
    health = HealthRegistry()
    services = ServiceRegistry()

    ctx = PlatformContext(
        capability=capability,
        health=health,
        services=services,
        version="2.0-vision",
        platform_version="0.1.0-foundation",
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

    # --- Core ---
    _register_core(ctx, core)

    # --- eniSpace (catalogo parallelo; logica invariata) ---
    _register_enispace(ctx, core)

    # --- Supervisor (JARVIS / assistente) ---
    _register_supervisor(ctx, jarvis, core)

    # --- coin_transport catalog-only se già presente nel ModuleManager ---
    _register_coin_transport_catalog(ctx, core)

    _CONTEXT = ctx
    logger.info(
        "Platform initialized version=%s platform=%s services=%s modules=%s",
        ctx.version,
        ctx.platform_version,
        ctx.services.list_ids(),
        [m.id for m in ctx.capability.list_modules()],
    )
    return ctx


def _register_services(ctx: PlatformContext, core: Any) -> None:
    # Logger facade (modulo logging già usato) — non nuova infrastruttura
    ctx.services.register("logger", get_logger("platform"))
    ctx.services.register(
        "configuration",
        {
            "config_dir": str(config_dir()),
            "data_dir": str(data_dir()),
            "logs_dir": str(logs_dir()),
        },
    )
    ctx.services.register(
        "storage",
        {"data_dir": str(data_dir()), "logs_dir": str(logs_dir())},
    )

    if core is not None:
        if getattr(core, "event_bus", None) is not None:
            ctx.services.register("event_bus", core.event_bus)
        if getattr(core, "notifications", None) is not None:
            ctx.services.register("notification", core.notifications)
        if getattr(core, "jobs", None) is not None:
            ctx.services.register("jobs", core.jobs)


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
    # Normalizza IN_DEVELOPMENT → DEGRADED per health enum? Better map to ONLINE-ish
    health_status = "ONLINE" if status in ("ONLINE", "IN_DEVELOPMENT") else status
    if status == "IN_DEVELOPMENT":
        health_status = "DEGRADED"
    ctx.capability.register_module(
        ModuleDescriptor(
            id="coin_transport",
            display_name=str(getattr(info, "name", "Trasporto Monete")),
            version=str(getattr(info, "version", "0.1")),
            status=status,
            commands=["PREPARE_COIN_TRANSPORT", "APPROVE_JOB", "REJECT_JOB"],
            events=["PEC_PREPARED", "WAITING_APPROVAL", "JOB_CREATED"],
            permissions=["pec_prepare", "approval_gate"],
            dependencies=["service:logger"],
            metadata={"dual_registration": True, "skeleton": True},
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
    ctx.health.update(
        "coin_transport",
        health_status,
        target_type="module",
        message="coin_transport dual-registered (catalog)",
        metadata={"module_status": status},
    )
