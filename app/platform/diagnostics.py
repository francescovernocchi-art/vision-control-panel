"""PlatformDiagnostics — unico consumer soft-DI non critico (fallback sicuro)."""

from __future__ import annotations

from typing import Any

from utils.logger import get_logger

_fallback_log = get_logger("platform.diagnostics")


def run_platform_diagnostics(ctx: Any) -> dict[str, Any]:
    """
    Consumer soft-DI: prova a usare logger dal ServiceRegistry.
    Se assente → fallback get_logger. Mai crash.
    Non altera comportamento operativo / UI / eniSpace.
    """
    result: dict[str, Any] = {
        "ok": True,
        "logger_source": "fallback",
        "message": "",
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
        try:
            info = getattr(log, "info", None)
            if callable(info):
                snap = {}
                try:
                    snap = ctx.get_platform_snapshot() if hasattr(ctx, "get_platform_snapshot") else {}
                except Exception:
                    snap = {}
                info(
                    "Platform diagnostics ok version=%s overall=%s skills=%s",
                    snap.get("platform_version"),
                    (snap.get("overall_health") or {}).get("overall_status")
                    if isinstance(snap.get("overall_health"), dict)
                    else snap.get("overall_health"),
                    len(snap.get("skills") or []),
                )
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["message"] = str(exc)
            _fallback_log.warning("Platform diagnostics log failed: %s", exc)

    result["message"] = result["message"] or "diagnostics completed"
    return result
