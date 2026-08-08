"""Test soft-DI servizi + health normalizzato / overall / snapshot v2."""

from __future__ import annotations

from app.bootstrap import create_vision_core
from app.core.module_manager import ModuleInfo, ModuleManager
from app.core.states import ModuleStatus
from app.platform import bootstrap_platform
from app.platform.capability_registry import CapabilityRegistry
from app.platform.consistency import run_consistency_check
from app.platform.context import PlatformContext
from app.platform.descriptors import HealthReport, ServiceDescriptor
from app.platform.diagnostics import run_platform_diagnostics
from app.platform.health_registry import HealthRegistry
from app.platform.service_registry import ServiceRegistry
from app.platform.skill_registry import SkillRegistry
from app.platform.status_normalizer import ModuleStatusNormalizer, normalize_health_status


def test_status_normalization_matrix():
    cases = {
        "ONLINE": "ONLINE",
        "OFFLINE": "OFFLINE",
        "DEGRADED": "DEGRADED",
        "ERROR": "ERROR",
        "DISABLED": "DISABLED",
        "STARTING": "STARTING",
        "STOPPING": "STOPPING",
        "IN_DEVELOPMENT": "DEGRADED",
        "UNKNOWN_XYZ": "ERROR",
    }
    for raw, expected in cases.items():
        n = ModuleStatusNormalizer.normalize(raw)
        assert n.health_status == expected
        assert n.metadata.get("lifecycle")
    st, meta = normalize_health_status("IN_DEVELOPMENT")
    assert st == "DEGRADED"
    assert meta.get("lifecycle") == "IN_DEVELOPMENT"
    assert meta.get("module_status") == "IN_DEVELOPMENT"


def test_direct_status_update_syncs_health():
    """Assegnazione diretta info.status senza set_status → Health dual-write."""
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    mod = core.modules.get("enispace")
    assert mod is not None
    # bypass set_status: scrittura diretta
    mod.info.status = ModuleStatus.ERROR
    h = ctx.health.get("enispace")
    assert h is not None
    assert h.status == "ERROR"
    assert h.metadata.get("source") == "dual_write"
    # restore via set_status
    core.modules.set_status("enispace", ModuleStatus.ONLINE)
    assert ctx.health.get("enispace").status == "ONLINE"
    core.stop()


def test_health_overall_and_snapshot():
    reg = HealthRegistry()
    reg.update("core", "ONLINE", target_type="core")
    reg.update("enispace", "ONLINE", target_type="module")
    assert reg.compute_overall_status() == "ONLINE"

    reg.update(
        "coin_transport",
        "DEGRADED",
        target_type="module",
        metadata={"lifecycle": "IN_DEVELOPMENT"},
    )
    assert reg.compute_overall_status() == "DEGRADED"

    reg2 = HealthRegistry()
    reg2.update("core", "ERROR", target_type="core")
    reg2.update("enispace", "ONLINE", target_type="module")
    assert reg2.compute_overall_status() == "ERROR"

    reg3 = HealthRegistry()
    reg3.update("core", "ONLINE", target_type="core")
    reg3.update("enispace", "ONLINE", target_type="module")
    reg3.update("coin_transport", "OFFLINE", target_type="module")  # opzionale
    assert reg3.compute_overall_status() == "DEGRADED"

    snap = reg.get_health_snapshot()
    assert snap["overall_status"] == "DEGRADED"
    assert "components" in snap
    assert snap["degraded_count"] >= 1
    assert "online_count" in snap
    assert "error_count" in snap
    assert "offline_count" in snap
    assert "last_updated" in snap
    report = HealthReport(
        component_id="x",
        component_type="module",
        status="ONLINE",
        ok=True,
        message="ok",
        updated_at="t",
        source="test",
        metadata={},
    )
    assert report.to_dict()["component_id"] == "x"


def test_service_registration_and_descriptor():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    for sid in ("logger", "configuration", "storage", "event_bus", "notification", "jobs"):
        assert ctx.services.has(sid), sid
        desc = ctx.services.get_descriptor(sid)
        assert desc is not None
        assert isinstance(desc, ServiceDescriptor)
        assert desc.available is True
        assert desc.lifetime in ("singleton", "transient", "external")
    assert ctx.services.get("event_bus") is core.event_bus
    assert ctx.services.get("jobs") is core.jobs
    # service health
    assert ctx.health.get("service:event_bus") is not None
    assert ctx.health.get("service:event_bus").status == "ONLINE"
    n = ctx.health.get("service:notification")
    assert n is not None
    assert n.status == "DEGRADED"  # stub
    core.stop()


def test_missing_service_fallback():
    services = ServiceRegistry()
    services.register_unavailable("missing_svc", reason="not invented")
    assert services.has("missing_svc") is False
    assert services.get("missing_svc") is None
    desc = services.get_descriptor("missing_svc")
    assert desc is not None and desc.available is False

    ctx = PlatformContext(
        capability=CapabilityRegistry(),
        health=HealthRegistry(),
        services=services,
        skills=SkillRegistry(),
        platform_version="0.4.0-supervisor-readonly",
    )
    assert ctx.get_service("missing_svc") is None
    result = run_platform_diagnostics(ctx)
    assert result["logger_source"] == "fallback"
    assert result["ok"] is True


def test_platform_context_helpers_and_snapshot_v2():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    assert ctx.platform_version == "0.4.0-supervisor-readonly"
    assert ctx.get_service("logger") is not None
    assert ctx.get_skill("enispace") is not None
    assert ctx.get_health("core") is not None
    assert ctx.get_capability("enispace") is not None

    snap = ctx.get_platform_snapshot()
    assert snap["platform_version"] == "0.4.0-supervisor-readonly"
    assert snap["overall_health"] in ("ONLINE", "DEGRADED", "ERROR", "OFFLINE")
    assert "components_health" in snap
    assert isinstance(snap["services"], list)
    assert snap["services"][0].get("service_id")
    assert "skills" in snap
    assert "capabilities" in snap
    assert "modules" in snap
    assert "consistency" in snap
    assert ctx.last_diagnostics is not None
    assert ctx.last_diagnostics.get("logger_source") == "service_registry"
    core.stop()


def test_consistency_expanded():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    report = run_consistency_check(ctx)
    assert report.level in ("OK", "WARNING", "ERROR")
    codes = {i.code for i in report.issues}
    assert report.level in ("OK", "WARNING")
    assert "MISSING_REGISTRY" not in codes
    core.stop()


def test_module_manager_status_watch_unit():
    mgr = ModuleManager()
    seen: list[tuple[str, str]] = []

    class _Mod:
        def __init__(self) -> None:
            self.info = ModuleInfo(id="demo", name="Demo", version="1", status="OFFLINE")

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    mgr.add_status_listener(lambda mid, st: seen.append((mid, st)))
    m = _Mod()
    mgr.register(m)
    seen.clear()
    m.info.status = "ONLINE"
    assert ("demo", "ONLINE") in seen
    seen.clear()
    mgr.set_status("demo", "DEGRADED")
    assert ("demo", "DEGRADED") in seen
