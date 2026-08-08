"""PlatformConsistencyCheck — skill vs capability (non blocca runtime)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.logger import get_logger

logger = get_logger("platform.consistency")


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
    if capability is None or skills is None:
        return ConsistencyReport("ERROR", [
            ConsistencyIssue("ERROR", "MISSING_REGISTRY", "capability/skills assenti")
        ])

    modules = {m.id: m for m in capability.list_modules()}
    registered_commands = {c.id for c in capability.list_commands()}
    registered_events = {e.event for e in capability.list_events()}

    for skill in skills.list_skills():
        if skill.module_id not in modules and skill.module_id not in ("core",):
            # core may be registered as module id core
            if skill.module_id != "core" or "core" not in modules:
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
        if health is not None and skill.module_id:
            if health.get(skill.module_id) is None and skill.module_id not in ("core",):
                # core/supervisor have separate health ids
                if skill.module_id not in ("supervisor",):
                    issues.append(
                        ConsistencyIssue(
                            "WARNING",
                            "HEALTH_MISSING",
                            f"skill {skill.id}: nessun health per {skill.module_id}",
                        )
                    )
        for dep in skill.dependencies:
            if dep.startswith("service:"):
                svc = dep.split(":", 1)[1]
                if hasattr(ctx, "services") and not ctx.services.has(svc):
                    issues.append(
                        ConsistencyIssue(
                            "WARNING",
                            "DEP_SERVICE_MISSING",
                            f"skill {skill.id}: dependency {dep} non registrata",
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
