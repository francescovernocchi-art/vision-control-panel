"""PlatformDiagnostics — soft-DI + verifica SupervisorPlatformView (non critico)."""

from __future__ import annotations

from typing import Any

from utils.logger import get_logger

_fallback_log = get_logger("platform.diagnostics")


def run_platform_diagnostics(ctx: Any) -> dict[str, Any]:
    """
    Consumer soft-DI: prova logger dal ServiceRegistry + check Supervisor view.
    Se assente → fallback. Mai crash. Non altera comportamento operativo.
    """
    result: dict[str, Any] = {
        "ok": True,
        "logger_source": "fallback",
        "message": "",
        "supervisor_view": {
            "available": False,
            "snapshot_ok": False,
            "immutable": False,
            "registries_untouched": True,
        },
    }
    log = None
    try:
        if ctx is not None and hasattr(ctx, "get_service"):
            log = ctx.get_service("logger")
    except Exception as exc:  # noqa: BLE001
        _fallback_log.warning("get_service(logger) failed: %s", exc)
        log = None

    if log is None:
        log = _fallback_log
        result["logger_source"] = "fallback"
        try:
            log.warning("Platform diagnostics: service logger unavailable — fallback")
        except Exception:
            pass
    else:
        result["logger_source"] = "service_registry"

    # --- SupervisorPlatformView checks ---
    try:
        _diagnose_supervisor_view(ctx, result)
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["supervisor_view"]["error"] = str(exc)[:200]
        _fallback_log.warning("Supervisor view diagnostics failed: %s", exc)

    try:
        info = getattr(log, "info", None)
        if callable(info):
            snap = {}
            try:
                snap = ctx.get_platform_snapshot() if ctx and hasattr(ctx, "get_platform_snapshot") else {}
            except Exception:
                snap = {}
            sv = result.get("supervisor_view") or {}
            info(
                "Platform diagnostics ok version=%s overall=%s skills=%s supervisor_view=%s",
                snap.get("platform_version"),
                (snap.get("overall_health") or {}).get("overall_status")
                if isinstance(snap.get("overall_health"), dict)
                else snap.get("overall_health"),
                len(snap.get("skills") or []),
                sv.get("available"),
            )
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["message"] = str(exc)
        _fallback_log.warning("Platform diagnostics log failed: %s", exc)

    result["message"] = result["message"] or "diagnostics completed"
    return result


def _diagnose_supervisor_view(ctx: Any, result: dict[str, Any]) -> None:
    from app.platform.supervisor_view import SupervisorPlatformView, SupervisorSnapshot

    sv = result["supervisor_view"]
    if ctx is None:
        view = SupervisorPlatformView(None)
        snap = view.get_supervisor_snapshot()
        sv["available"] = False
        sv["snapshot_ok"] = isinstance(snap, SupervisorSnapshot)
        sv["fallback_ok"] = snap.overall_health == "UNKNOWN"
        return

    view = getattr(ctx, "supervisor_view", None)
    if view is None:
        view = SupervisorPlatformView(ctx)
        sv["available"] = True
        sv["created_on_the_fly"] = True
    else:
        sv["available"] = True

    # fingerprint registri prima
    before = _registry_fingerprint(ctx)
    snap = view.get_supervisor_snapshot()
    after = _registry_fingerprint(ctx)
    sv["snapshot_ok"] = isinstance(snap, SupervisorSnapshot)
    sv["immutable"] = _assert_frozen(snap)
    sv["registries_untouched"] = before == after
    if before != after:
        result["ok"] = False
        sv["mutation_detected"] = True
    # soft attach su Core
    core = getattr(ctx, "core", None)
    if core is not None:
        sv["core_platform_view"] = getattr(core, "platform_view", None) is not None


def _registry_fingerprint(ctx: Any) -> tuple:
    try:
        skills = tuple(
            (s.id, s.enabled) for s in (ctx.skills.list_skills() if ctx.skills else [])
        )
    except Exception:
        skills = ()
    try:
        health = tuple(
            (h.target_id, h.status) for h in (ctx.health.list() if ctx.health else [])
        )
    except Exception:
        health = ()
    try:
        services = tuple(ctx.services.list_ids() if ctx.services else [])
    except Exception:
        services = ()
    try:
        caps = tuple(m.id for m in (ctx.capability.list_modules() if ctx.capability else []))
    except Exception:
        caps = ()
    return (skills, health, services, caps)


def _assert_frozen(snap: Any) -> bool:
    try:
        snap.overall_health = "HACKED"  # type: ignore[misc]
        return False
    except Exception:
        return True
