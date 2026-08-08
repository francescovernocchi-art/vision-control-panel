"""PlatformConsistencyCheck — skill / health / service (non blocca runtime)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.logger import get_logger

logger = get_logger("platform.consistency")

# Servizi attesi (soft): assenza → WARNING, non ERROR obbligatorio salvo required
_EXPECTED_SERVICES = (
    "logger",
    "configuration",
    "storage",
    "event_bus",
    "notification",
    "jobs",
)


@dataclass
class ConsistencyIssue:
    level: str  # OK | WARNING | ERROR
    code: str
    message: str


@dataclass
class ConsistencyReport:
    level: str
    issues: list[ConsistencyIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "issues": [
                {"level": i.level, "code": i.code, "message": i.message} for i in self.issues
            ],
        }


def run_consistency_check(ctx: Any) -> ConsistencyReport:
    issues: list[ConsistencyIssue] = []
    capability = getattr(ctx, "capability", None)
    skills = getattr(ctx, "skills", None)
    health = getattr(ctx, "health", None)
    services = getattr(ctx, "services", None)
    if capability is None or skills is None:
        return ConsistencyReport(
            "ERROR",
            [ConsistencyIssue("ERROR", "MISSING_REGISTRY", "capability/skills assenti")],
        )

    modules = {m.id: m for m in capability.list_modules()}
    registered_commands = {c.id for c in capability.list_commands()}
    registered_events = {e.event for e in capability.list_events()}

    # --- skill → module ---
    for skill in skills.list_skills():
        if skill.module_id not in modules:
            issues.append(
                ConsistencyIssue(
                    "WARNING",
                    "MODULE_MISSING",
                    f"skill {skill.id}: module_id={skill.module_id} non in CapabilityRegistry",
                )
            )
        mod = modules.get(skill.module_id)
        if mod:
            for cmd in skill.commands:
                if cmd not in mod.commands and cmd not in registered_commands:
                    issues.append(
                        ConsistencyIssue(
                            "WARNING",
                            "COMMAND_MISMATCH",
                            f"skill {skill.id}: command {cmd} non in capability modulo/catalogo",
                        )
                    )
                elif cmd not in mod.commands and cmd in registered_commands:
                    issues.append(
                        ConsistencyIssue(
                            "WARNING",
                            "COMMAND_MODULE_GAP",
                            f"skill {skill.id}: command {cmd} in catalogo ma non nel ModuleDescriptor {mod.id}",
                        )
                    )
            for ev in skill.events:
                if ev not in mod.events and ev not in registered_events:
                    issues.append(
                        ConsistencyIssue(
                            "WARNING",
                            "EVENT_MISMATCH",
                            f"skill {skill.id}: event {ev} non in capability",
                        )
                    )

        # --- module → health ---
        if health is not None and skill.module_id:
            if health.get(skill.module_id) is None:
                issues.append(
                    ConsistencyIssue(
                        "WARNING",
                        "HEALTH_MISSING",
                        f"skill {skill.id}: nessun health per {skill.module_id}",
                    )
                )

        # --- module → capability (già sopra) + service deps ---
        for dep in skill.dependencies:
            if dep.startswith("service:"):
                svc = dep.split(":", 1)[1]
                if services is not None and not services.has(svc):
                    issues.append(
                        ConsistencyIssue(
                            "WARNING",
                            "DEP_SERVICE_MISSING",
                            f"skill {skill.id}: dependency {dep} non registrata",
                        )
                    )

    # --- module → health / capability (tutti i moduli catalogo) ---
    if health is not None:
        for mid, mod in modules.items():
            if mid in ("supervisor",):
                continue
            if health.get(mid) is None:
                issues.append(
                    ConsistencyIssue(
                        "WARNING",
                        "MODULE_HEALTH_GAP",
                        f"module {mid}: presente in capability ma senza health",
                    )
                )

    # --- servizi richiesti / attesi ---
    if services is not None:
        for sid in _EXPECTED_SERVICES:
            desc = services.get_descriptor(sid) if hasattr(services, "get_descriptor") else None
            has = services.has(sid)
            if not has:
                level = "WARNING"
                if desc is not None and getattr(desc, "required", False):
                    level = "ERROR"
                issues.append(
                    ConsistencyIssue(
                        level,
                        "SERVICE_UNAVAILABLE",
                        f"service {sid}: non registrato (descriptor available={getattr(desc, 'available', False)})",
                    )
                )
            elif desc is not None and not getattr(desc, "available", True):
                issues.append(
                    ConsistencyIssue(
                        "WARNING",
                        "SERVICE_MARKED_UNAVAILABLE",
                        f"service {sid}: descriptor available=False",
                    )
                )

        # event_bus disponibile
        if not services.has("event_bus"):
            issues.append(
                ConsistencyIssue(
                    "WARNING",
                    "EVENT_BUS_MISSING",
                    "event_bus non disponibile nel ServiceRegistry",
                )
            )

        # notification stato
        n_desc = services.get_descriptor("notification") if hasattr(services, "get_descriptor") else None
        if services.has("notification"):
            n_health = health.get("service:notification") if health is not None else None
            if n_health is not None and n_health.status == "DEGRADED":
                issues.append(
                    ConsistencyIssue(
                        "WARNING",
                        "NOTIFICATION_DEGRADED",
                        "notification service in DEGRADED (stub / senza provider esterni)",
                    )
                )
        elif n_desc is not None:
            issues.append(
                ConsistencyIssue(
                    "WARNING",
                    "NOTIFICATION_UNAVAILABLE",
                    "notification service non istanziato",
                )
            )

    # --- versioni compatibili (soft) ---
    platform_version = str(getattr(ctx, "platform_version", "") or "")
    vision_version = str(getattr(ctx, "version", "") or "")
    if not platform_version.startswith("0."):
        issues.append(
            ConsistencyIssue(
                "WARNING",
                "PLATFORM_VERSION_UNEXPECTED",
                f"platform_version={platform_version} fuori schema 0.x safe-migration",
            )
        )
    if vision_version and "vision" not in vision_version.lower():
        issues.append(
            ConsistencyIssue(
                "WARNING",
                "VISION_VERSION_UNEXPECTED",
                f"vision_version={vision_version}",
            )
        )

    if any(i.level == "ERROR" for i in issues):
        level = "ERROR"
    elif issues:
        level = "WARNING"
    else:
        level = "OK"

    report = ConsistencyReport(level=level, issues=issues)
    if level == "OK":
        logger.info("PlatformConsistencyCheck OK")
    else:
        for issue in issues:
            if issue.level == "ERROR":
                logger.error("Consistency %s: %s", issue.code, issue.message)
            else:
                logger.warning("Consistency %s: %s", issue.code, issue.message)
    return report
