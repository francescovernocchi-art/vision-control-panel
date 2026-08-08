"""Test SupervisorPlatformView — read-only PlatformContext (no UI / no eniSpace reale)."""

from __future__ import annotations

import dataclasses

import pytest

from app.bootstrap import create_vision_core
from app.platform import bootstrap_platform
from app.platform.capability_registry import CapabilityRegistry
from app.platform.context import PlatformContext
from app.platform.health_registry import HealthRegistry
from app.platform.service_registry import ServiceRegistry
from app.platform.skill_registry import SkillRegistry
from app.platform.supervisor_view import (
    SupervisorCapabilityView,
    SupervisorHealthView,
    SupervisorPlatformView,
    SupervisorServiceView,
    SupervisorSkillView,
    SupervisorSnapshot,
    SupervisorWarning,
)


def test_supervisor_platform_view_creation():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    assert isinstance(ctx.supervisor_view, SupervisorPlatformView)
    assert ctx.supervisor_view.available is True
    assert getattr(core, "platform_view", None) is ctx.supervisor_view
    # no command execution APIs
    for banned in (
        "execute_command",
        "pause_module",
        "resume_module",
        "enable_skill",
        "disable_skill",
        "update_health",
        "register_service",
    ):
        assert not hasattr(ctx.supervisor_view, banned)
    core.stop()


def test_supervisor_snapshot_complete():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    snap = ctx.get_supervisor_snapshot()
    assert isinstance(snap, SupervisorSnapshot)
    assert snap.platform_version == "0.5.0-remote-readonly"
    assert snap.supervisor_status == "ONLINE"
    assert snap.overall_health in ("ONLINE", "DEGRADED", "ERROR", "OFFLINE", "UNKNOWN")
    assert snap.core_health is not None
    assert snap.skills
    assert snap.services
    assert snap.capabilities
    assert isinstance(snap.warnings, tuple)
    assert snap.last_updated
    # Supervisor ONLINE + Platform DEGRADED (atteso con coin_transport / notification)
    assert snap.supervisor_status == "ONLINE"
    assert snap.overall_health == "DEGRADED"
    core.stop()


def test_skills_services_capabilities_health_readonly():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    snap = ctx.supervisor_view.get_supervisor_snapshot()

    by_skill = {s.skill_id: s for s in snap.skills}
    assert "enispace" in by_skill
    assert by_skill["enispace"].enabled is True
    assert isinstance(by_skill["enispace"], SupervisorSkillView)
    coin = by_skill["coin_transport"]
    assert coin.enabled is False
    assert coin.health == "DEGRADED"

    by_svc = {s.service_id: s for s in snap.services}
    for sid in ("logger", "configuration", "storage", "event_bus", "notification", "jobs"):
        assert sid in by_svc
        assert isinstance(by_svc[sid], SupervisorServiceView)
        # NO Python instances — only DTO fields
        assert not hasattr(by_svc[sid], "instance")
    assert by_svc["notification"].health == "DEGRADED"
    assert by_svc["event_bus"].available is True

    by_cap = {c.module_id: c for c in snap.capabilities}
    assert "enispace" in by_cap
    assert isinstance(by_cap["enispace"], SupervisorCapabilityView)
    assert "CHECK_ENISPACE_MAIL" in by_cap["enispace"].commands_supported

    assert isinstance(snap.core_health, SupervisorHealthView)
    assert snap.core_health.status == "ONLINE"
    # agent null (non inventato)
    assert snap.agent_health is None
    core.stop()


def test_warning_normalization():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    snap = ctx.get_supervisor_snapshot()
    codes = {w.code for w in snap.warnings}
    assert "NOTIFICATION_DEGRADED" in codes
    assert "COIN_TRANSPORT_IN_DEVELOPMENT" in codes
    assert "AGENT_UNAVAILABLE" in codes
    for w in snap.warnings:
        assert isinstance(w, SupervisorWarning)
        assert w.code and w.severity and w.component and w.message
    core.stop()


def test_platform_context_missing_fallback():
    view = SupervisorPlatformView(None)
    snap = view.get_supervisor_snapshot()
    assert snap.overall_health == "UNKNOWN"
    assert snap.skills == ()
    assert snap.services == ()
    assert snap.capabilities == ()
    assert snap.core_health is None
    assert any(w.code == "PLATFORM_CONTEXT_MISSING" for w in snap.warnings)


def test_missing_registries_fallback():
    # skills missing
    ctx1 = PlatformContext(
        capability=CapabilityRegistry(),
        health=HealthRegistry(),
        services=ServiceRegistry(),
        skills=None,  # type: ignore[arg-type]
        platform_version="0.5.0-remote-readonly",
    )
    snap1 = SupervisorPlatformView(ctx1).get_supervisor_snapshot()
    assert snap1.skills == ()

    # health missing
    ctx2 = PlatformContext(
        capability=CapabilityRegistry(),
        health=None,  # type: ignore[arg-type]
        services=ServiceRegistry(),
        skills=SkillRegistry(),
        platform_version="0.5.0-remote-readonly",
    )
    snap2 = SupervisorPlatformView(ctx2).get_supervisor_snapshot()
    assert snap2.overall_health == "UNKNOWN"

    # services missing
    ctx3 = PlatformContext(
        capability=CapabilityRegistry(),
        health=HealthRegistry(),
        services=None,  # type: ignore[arg-type]
        skills=SkillRegistry(),
        platform_version="0.5.0-remote-readonly",
    )
    snap3 = SupervisorPlatformView(ctx3).get_supervisor_snapshot()
    assert snap3.services == ()

    # capability missing
    ctx4 = PlatformContext(
        capability=None,  # type: ignore[arg-type]
        health=HealthRegistry(),
        services=ServiceRegistry(),
        skills=SkillRegistry(),
        platform_version="0.5.0-remote-readonly",
    )
    snap4 = SupervisorPlatformView(ctx4).get_supervisor_snapshot()
    assert snap4.capabilities == ()


def test_immutability_of_snapshot_and_registries():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    before_skills = [(s.id, s.enabled) for s in ctx.skills.list_skills()]
    before_health = [(h.target_id, h.status) for h in ctx.health.list()]
    snap = ctx.get_supervisor_snapshot()
    assert dataclasses.is_dataclass(snap) and snap.__dataclass_params__.frozen
    with pytest.raises(Exception):
        snap.overall_health = "HACKED"  # type: ignore[misc]
    with pytest.raises(Exception):
        snap.skills[0].enabled = True  # type: ignore[misc]
    # registries unchanged
    assert [(s.id, s.enabled) for s in ctx.skills.list_skills()] == before_skills
    assert [(h.target_id, h.status) for h in ctx.health.list()] == before_health
    # DTO to_dict is a copy — mutating it must not affect snapshot
    d = snap.to_dict()
    d["skills"][0]["enabled"] = not d["skills"][0]["enabled"]
    snap2 = ctx.get_supervisor_snapshot()
    assert snap2.skills[0].enabled == snap.skills[0].enabled
    core.stop()


def test_diagnostics_includes_supervisor_view():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    diag = ctx.last_diagnostics
    assert diag is not None
    sv = diag.get("supervisor_view") or {}
    assert sv.get("available") is True
    assert sv.get("snapshot_ok") is True
    assert sv.get("immutable") is True
    assert sv.get("registries_untouched") is True
    core.stop()
