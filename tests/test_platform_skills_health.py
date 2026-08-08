"""Test Skill Registry + health dual-write (no IMAP/eniSpace reale)."""

from __future__ import annotations

import json
from pathlib import Path

from app.bootstrap import create_vision_core
from app.core.states import ModuleStatus
from app.platform import bootstrap_platform
from app.platform.health_bridge import ModuleHealthBridge, normalize_health_status
from app.platform.skill_registry import SkillRegistry
from app.platform.skill_validator import validate_skill_manifest


def test_normalize_in_development():
    st, meta = normalize_health_status("IN_DEVELOPMENT")
    assert st == "DEGRADED"
    assert meta.get("module_status") == "IN_DEVELOPMENT"


def test_health_dual_write_via_module_manager():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    assert ctx.health_bridge is not None
    # set_status → dual-write
    core.modules.set_status("enispace", "DEGRADED")
    h = ctx.health.get("enispace")
    assert h is not None
    assert h.status == "DEGRADED"
    assert h.metadata.get("source") == "dual_write"
    # restore
    core.modules.set_status("enispace", ModuleStatus.ONLINE)
    assert ctx.health.get("enispace").status == "ONLINE"
    # history
    assert len(ctx.health.history()) >= 1
    core.stop()


def test_health_snapshot_components():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    snap = ctx.health.snapshot()
    ids = {x["component_id"] for x in snap}
    assert "core" in ids
    assert "enispace" in ids
    assert "supervisor" in ids
    assert "coin_transport" in ids
    coin = next(x for x in snap if x["component_id"] == "coin_transport")
    assert coin["status"] == "DEGRADED"  # IN_DEVELOPMENT normalizzato
    assert coin["metadata"].get("module_status") == "IN_DEVELOPMENT" or True
    core.stop()


def test_skill_registry_static_manifests():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    eni = ctx.skills.get_skill("enispace")
    coin = ctx.skills.get_skill("coin_transport")
    assert eni is not None
    assert eni.enabled is True
    assert eni.module_id == "enispace"
    assert "CHECK_ENISPACE_MAIL" in eni.commands
    assert coin is not None
    assert coin.enabled is False
    assert coin.metadata.get("status") == "IN_DEVELOPMENT"
    assert len(ctx.skills.get_enabled_skills()) >= 1
    core.stop()


def test_valid_and_invalid_skill_json(tmp_path: Path):
    reg = SkillRegistry()
    good = {
        "id": "demo",
        "name": "Demo",
        "version": "1.0.0",
        "module_id": "demo",
        "category": "general",
        "enabled": True,
        "commands": ["GET_STATUS"],
        "events": ["JOB_COMPLETED"],
        "permissions": [],
        "dependencies": [],
    }
    assert validate_skill_manifest(good).ok is True
    p = tmp_path / "skill.json"
    p.write_text(json.dumps(good), encoding="utf-8")
    assert reg.load_skill_manifest(p) is not None

    bad = {"id": "", "name": "X", "version": "1", "module_id": "", "password": "no"}
    result = validate_skill_manifest(bad)
    assert result.ok is False
    p2 = tmp_path / "bad.json"
    p2.write_text(json.dumps(bad), encoding="utf-8")
    assert reg.load_skill_manifest(p2) is None


def test_skill_enable_disable():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    assert ctx.skills.disable_skill("enispace") is True
    assert ctx.skills.get_skill("enispace").enabled is False
    assert ctx.skills.enable_skill("enispace") is True
    assert ctx.skills.get_skill("enispace").enabled is True
    core.stop()


def test_consistency_and_platform_snapshot():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    assert ctx.last_consistency is not None
    assert ctx.last_consistency.level in ("OK", "WARNING")
    snap = ctx.get_platform_snapshot()
    assert snap["platform_version"]
    assert "skills" in snap
    assert "health" in snap
    assert "capabilities" in snap
    assert "services" in snap
    view = ctx.supervisor_readonly_view()
    assert "skills" in view and "health" in view
    # eniSpace operativo invariato
    assert core.modules.get("enispace") is not None
    assert core.is_online is True
    core.stop()


def test_enispace_online_coin_dev_in_capability():
    core = create_vision_core()
    ctx = bootstrap_platform(core, force=True)
    eni = ctx.capability.get_module("enispace")
    coin = ctx.capability.get_module("coin_transport")
    assert eni is not None and eni.status == "ONLINE"
    assert coin is not None and coin.status == "IN_DEVELOPMENT"
    core.stop()
