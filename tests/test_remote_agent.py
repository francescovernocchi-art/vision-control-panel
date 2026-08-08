"""Test Remote Agent — mock only, niente eniSpace/IMAP/stampa reale."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.bootstrap import create_vision_core
from app.remote.agent import VisionRemoteAgent
from app.remote.backends.mock import MockRemoteBackend
from app.remote.command_validator import validate_command
from app.remote.config import RemoteConfig
from app.remote.models import CommandStatus, CommandType, DeviceStatus, RemoteCommand
from app.remote.store import CommandStore


@pytest.fixture()
def core():
    c = create_vision_core()
    yield c
    c.stop()


@pytest.fixture()
def mock_backend():
    return MockRemoteBackend()


@pytest.fixture()
def agent(core, mock_backend, tmp_path: Path):
    cfg = RemoteConfig(
        enabled=True,
        mode="mock",
        device_id="VIS-TARANTO-01",
        device_name="PC VIS Taranto",
        heartbeat_seconds=15,
        command_poll_seconds=3,
    )
    store = CommandStore(tmp_path / "vision_remote_test.db")
    ag = VisionRemoteAgent(core, cfg, backend=mock_backend, store=store)
    mock_backend.connect()
    yield ag
    ag.stop()


def test_kill_switch_default_off(monkeypatch):
    monkeypatch.delenv("VISION_REMOTE_ENABLED", raising=False)
    cfg = RemoteConfig.load()
    assert cfg.enabled is False
    assert cfg.mode == "mock"


def test_get_status_command(agent, mock_backend):
    cmd = RemoteCommand.create(
        command_type=CommandType.GET_STATUS,
        target_device_id="VIS-TARANTO-01",
        source="test",
    )
    out = agent.handle_command(cmd)
    assert out.status == CommandStatus.COMPLETED
    assert out.result.get("ok") is True
    assert "vision_core" in out.result
    assert out.result["vision_core"]["online"] is True
    assert any(e["event_type"] == "COMMAND_COMPLETED" for e in mock_backend.events)


def test_check_enispace_mail_dry_run(agent):
    cmd = RemoteCommand.create(
        command_type=CommandType.CHECK_ENISPACE_MAIL,
        target_device_id="VIS-TARANTO-01",
        params={"dry_run": True},
        source="test",
    )
    out = agent.handle_command(cmd)
    assert out.status == CommandStatus.COMPLETED
    assert out.result.get("ok") is True
    assert out.result.get("dry_run") is True


def test_idempotency_no_double_exec(agent):
    cmd = RemoteCommand.create(
        command_type=CommandType.GET_STATUS,
        target_device_id="VIS-TARANTO-01",
        command_id="cmd-idem-1",
        source="test",
    )
    first = agent.handle_command(cmd)
    assert first.status == CommandStatus.COMPLETED
    second = agent.handle_command(cmd)
    assert second.status == CommandStatus.REJECTED
    assert "idempotenza" in (second.error or "").lower() or "già" in (second.error or "").lower()


def test_reject_wrong_device(agent):
    cmd = RemoteCommand.create(
        command_type=CommandType.GET_STATUS,
        target_device_id="OTHER-DEVICE",
        source="test",
    )
    out = agent.handle_command(cmd)
    assert out.status == CommandStatus.REJECTED


def test_reject_non_whitelist(agent):
    cmd = RemoteCommand.create(
        command_type="SHELL_EXEC",
        target_device_id="VIS-TARANTO-01",
        source="test",
    )
    out = agent.handle_command(cmd)
    assert out.status == CommandStatus.REJECTED


def test_approve_job_not_implemented(agent):
    cmd = RemoteCommand.create(
        command_type=CommandType.APPROVE_JOB,
        target_device_id="VIS-TARANTO-01",
        params={"job_id": "VISION-2026-000001"},
        source="test",
    )
    out = agent.handle_command(cmd)
    assert out.status == CommandStatus.COMPLETED
    assert out.result.get("code") == "NOT_IMPLEMENTED"


def test_validator_expired():
    cmd = RemoteCommand.create(
        command_type=CommandType.GET_STATUS,
        target_device_id="VIS-TARANTO-01",
        expires_at="2000-01-01 00:00:00",
    )
    res = validate_command(cmd, device_id="VIS-TARANTO-01")
    assert res.ok is False
    assert "scaduto" in res.reason.lower()


def test_agent_disabled_does_not_run(core, mock_backend, tmp_path):
    cfg = RemoteConfig(enabled=False, mode="mock", device_id="VIS-TARANTO-01")
    ag = VisionRemoteAgent(
        core, cfg, backend=mock_backend, store=CommandStore(tmp_path / "r.db")
    )
    assert ag.start() is False
    assert ag.status == DeviceStatus.DISABLED
    ag.stop()


def test_heartbeat_mock(agent, mock_backend):
    mock_backend.connect()
    assert agent.heartbeat.send() is True
    assert len(mock_backend.heartbeats) >= 1
    hb = mock_backend.heartbeats[-1]
    assert hb["device_id"] == "VIS-TARANTO-01"
    assert "modules" in hb
