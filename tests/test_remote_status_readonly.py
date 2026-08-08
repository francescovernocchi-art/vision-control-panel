"""Test RemoteStatusService + GET_STATUS platform read-only (mock only)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.bootstrap import create_vision_core
from app.platform import bootstrap_platform
from app.remote.agent import VisionRemoteAgent
from app.remote.backends.mock import MockRemoteBackend
from app.remote.command_dispatcher import CommandDispatcher
from app.remote.config import RemoteConfig
from app.remote.models import CommandStatus, CommandType, DeviceStatus, RemoteCommand
from app.remote.status_models import RemoteStatusResponse
from app.remote.status_service import RemoteStatusService
from app.remote.store import CommandStore


@pytest.fixture()
def core():
    c = create_vision_core()
    bootstrap_platform(c, force=True)
    yield c
    c.stop()


@pytest.fixture()
def agent(core, tmp_path: Path):
    backend = MockRemoteBackend()
    cfg = RemoteConfig(
        enabled=True,
        mode="mock",
        device_id="VIS-TARANTO-01",
        device_name="PC VIS Taranto",
        remote_execution_policy="status_only",
    )
    ag = VisionRemoteAgent(
        core, cfg, backend=backend, store=CommandStore(tmp_path / "remote_status.db")
    )
    backend.connect()
    # simula agent online per health reporting
    ag._set_status(DeviceStatus.ONLINE)
    ag._enabled = True
    yield ag
    ag.stop()


def test_get_status_via_remote_status_service(core):
    svc = RemoteStatusService(core, config=RemoteConfig(enabled=False, mode="mock"))
    data = svc.build_status()
    assert data["ok"] is True
    assert data["api_version"] == "v1"
    assert data["contract_version"] == "1.0.0"
    assert data["platform_version"] == "0.5.0-remote-readonly"
    assert data["device_id"] == "VIS-TARANTO-01"
    json.dumps(data)  # JSON-safe


def test_get_status_command_uses_platform(agent):
    cmd = RemoteCommand.create(
        command_type=CommandType.GET_STATUS,
        target_device_id="VIS-TARANTO-01",
        source="backend",
    )
    out = agent.handle_command(cmd)
    assert out.status == CommandStatus.COMPLETED
    r = out.result
    assert r["ok"] is True
    assert r["api_version"] == "v1"
    assert r["overall_health"] == "DEGRADED"
    assert r["supervisor_status"] == "ONLINE"
    assert r["vision_core"]["online"] is True
    mods = {m["module_id"]: m for m in r["modules"]}
    assert mods["enispace"]["health"] == "ONLINE" or mods["enispace"]["status"] == "ONLINE"
    assert mods["coin_transport"]["health"] == "DEGRADED"
    skills = {s["skill_id"]: s for s in r["skills"]}
    assert skills["enispace"]["enabled"] is True
    assert skills["coin_transport"]["enabled"] is False
    services = {s["service_id"]: s for s in r["services"]}
    assert services["event_bus"]["health"] == "ONLINE"
    assert services["notification"]["health"] == "DEGRADED"
    codes = {w["code"] for w in r["warnings"]}
    assert "NOTIFICATION_DEGRADED" in codes
    assert "COIN_TRANSPORT_IN_DEVELOPMENT" in codes
    assert "AGENT_UNAVAILABLE" not in codes  # agent sta rispondendo
    assert r["agent"] is not None
    assert r["agent"]["remote_mode"] == "mock"
    assert "remote_control_enabled" in r
    json.dumps(r)


def test_status_only_rejects_check_enispace_mail(agent):
    cmd = RemoteCommand.create(
        command_type=CommandType.CHECK_ENISPACE_MAIL,
        target_device_id="VIS-TARANTO-01",
        params={"dry_run": True},
        source="backend",
    )
    out = agent.handle_command(cmd)
    assert out.status == CommandStatus.REJECTED
    assert out.result.get("code") == "REMOTE_OPERATION_NOT_ENABLED"


def test_status_only_rejects_retry_and_pause(agent):
    for ctype, params in (
        (CommandType.RETRY_JOB, {"job_id": "VISION-2026-000001"}),
        (CommandType.PAUSE_MODULE, {"module_id": "enispace"}),
        (CommandType.APPROVE_JOB, {"job_id": "VISION-2026-000001"}),
    ):
        cmd = RemoteCommand.create(
            command_type=ctype,
            target_device_id="VIS-TARANTO-01",
            params=params,
            source="backend",
        )
        out = agent.handle_command(cmd)
        assert out.status == CommandStatus.REJECTED, ctype
        assert out.result.get("code") == "REMOTE_OPERATION_NOT_ENABLED"


def test_json_serialization_remote_status_response(core):
    svc = RemoteStatusService(core, config=RemoteConfig(mode="mock"))
    resp = svc.build_response()
    assert isinstance(resp, RemoteStatusResponse)
    raw = resp.to_json()
    parsed = json.loads(raw)
    assert parsed["api_version"] == "v1"


def test_fallback_legacy_status(core):
    # forza assenza platform view
    if hasattr(core, "platform_view"):
        core.platform_view = None
    from app.platform import bootstrap as pb

    saved = pb._CONTEXT
    pb._CONTEXT = None
    try:
        svc = RemoteStatusService(core, config=RemoteConfig(mode="mock"))
        # senza context: tenta soft bootstrap; con force isolation mockiamo _platform_context
        svc._platform_context = lambda: None  # type: ignore[method-assign]
        data = svc.build_status()
        assert data["ok"] is True
        assert data["partial"] is True
        assert "skills" in data["missing_sections"] or data["overall_health"] in (
            "DEGRADED",
            "ONLINE",
            "OFFLINE",
            "UNKNOWN",
        )
        assert data["vision_core"] is not None
    finally:
        pb._CONTEXT = saved


def test_partial_response_explicit():
    resp = RemoteStatusResponse(
        ok=True,
        core_status="DEGRADED",
        overall_health="DEGRADED",
        partial=True,
        missing_sections=("skills", "services"),
        device_id="VIS-TARANTO-01",
    )
    d = resp.to_dict()
    assert d["partial"] is True
    assert d["missing_sections"] == ["skills", "services"]
    json.dumps(d)


def test_kill_switch_still_blocks_start(core, tmp_path):
    cfg = RemoteConfig(enabled=False, mode="mock", device_id="VIS-TARANTO-01")
    ag = VisionRemoteAgent(
        core, cfg, backend=MockRemoteBackend(), store=CommandStore(tmp_path / "k.db")
    )
    assert ag.start() is False
    assert ag.status == DeviceStatus.DISABLED
    ag.stop()


def test_heartbeat_lightweight(agent):
    backend = agent.backend
    assert agent.heartbeat.send(status=DeviceStatus.ONLINE) is True
    hb = backend.heartbeats[-1]
    assert hb["device_id"] == "VIS-TARANTO-01"
    assert "platform_version" in hb
    assert hb["platform_version"] == "0.5.0-remote-readonly"
    assert "timestamp" in hb
    assert "modules" in hb
    # non deve essere un full GET_STATUS
    assert "skills" not in hb
    assert "services" not in hb


def test_dispatcher_status_only_policy_unit(core):
    svc = RemoteStatusService(core, config=RemoteConfig(mode="mock"))
    disp = CommandDispatcher(core, status_service=svc, remote_execution_policy="status_only")
    ok = disp.dispatch(
        RemoteCommand.create(command_type=CommandType.GET_STATUS, target_device_id="VIS-TARANTO-01")
    )
    assert ok["ok"] is True
    bad = disp.dispatch(
        RemoteCommand.create(
            command_type=CommandType.CHECK_ENISPACE_MAIL,
            target_device_id="VIS-TARANTO-01",
            params={"dry_run": True},
        )
    )
    assert bad["code"] == "REMOTE_OPERATION_NOT_ENABLED"


def test_mock_mode_reflects_degraded_not_fake_online(agent):
    out = agent.handle_command(
        RemoteCommand.create(
            command_type=CommandType.GET_STATUS,
            target_device_id="VIS-TARANTO-01",
        )
    )
    assert out.result["overall_health"] == "DEGRADED"
    coin = next(m for m in out.result["modules"] if m["module_id"] == "coin_transport")
    assert coin["health"] == "DEGRADED"
