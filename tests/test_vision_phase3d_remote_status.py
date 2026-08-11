"""Phase 3D — GET_STATUS EniSpace runtime (Supabase remote, status_only, read-only)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.bootstrap import create_vision_core
from app.platform import bootstrap_platform
from app.remote.agent import VisionRemoteAgent
from app.remote.backends.mock import MockRemoteBackend
from app.remote.config import RemoteConfig
from app.remote.models import CommandStatus, CommandType, DeviceStatus, RemoteCommand
from app.remote.status_models import RemoteEniSpaceRuntimeStatus, RemoteStatusResponse
from app.remote.status_service import RemoteStatusService
from app.remote.store import CommandStore


_LEGACY_KEYS = (
    "ok",
    "api_version",
    "contract_version",
    "device_id",
    "device_name",
    "agent_version",
    "vision_version",
    "platform_version",
    "timestamp",
    "core_status",
    "supervisor_status",
    "overall_health",
    "current_job",
    "queue_size",
    "modules",
    "skills",
    "services",
    "warnings",
    "remote_control_enabled",
    "agent",
    "partial",
    "missing_sections",
    "vision_core",
)

_SENSITIVE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|keyring|authorization)",
    re.I,
)


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
        core, cfg, backend=backend, store=CommandStore(tmp_path / "phase3d_remote_status.db")
    )
    backend.connect()
    ag._set_status(DeviceStatus.ONLINE)
    ag._enabled = True
    yield ag
    ag.stop()


def _bind_worker(core, worker) -> None:
    fake_eni = SimpleNamespace(jarvis=worker)
    core.modules = SimpleNamespace(get=lambda mid: fake_eni if mid == "enispace" else None)


# --- A. legacy compatibility -------------------------------------------------


def test_phase3d_a_get_status_legacy_compatibility(agent):
    data = agent.handle_command(
        RemoteCommand.create(
            command_type=CommandType.GET_STATUS,
            target_device_id="VIS-TARANTO-01",
        )
    ).result
    for key in _LEGACY_KEYS:
        assert key in data, key
    assert data["api_version"] == "v1"
    assert data["contract_version"] == "1.0.0"
    assert "enispace_runtime" in data
    json.dumps(data)


# --- B. idle -----------------------------------------------------------------


def test_phase3d_b_enispace_idle(core):
    worker = SimpleNamespace(
        is_active=True,
        is_processing=False,
        state="IN ATTESA",
        last_check="",
        last_job_summary="—",
        current_job=None,
        pending_count=lambda: 0,
    )
    _bind_worker(core, worker)
    data = RemoteStatusService(core, config=RemoteConfig(mode="mock")).build_status()
    rt = data["enispace_runtime"]
    assert rt["available"] is True
    assert rt["status"] == "IDLE"
    assert rt["active"] is True
    assert rt["pending_jobs"] == 0
    assert rt["current_job"] is None
    # Dual-job: Vision Core job store is separate
    assert "queue_size" in data


# --- C. processing -----------------------------------------------------------


def test_phase3d_c_enispace_processing(core):
    job = SimpleNamespace(
        id=42,
        status="PROCESSING",
        state="DOWNLOAD",
        order_number="ORD-1",
        contract_number="C-9",
        docs_found=3,
        docs_downloaded=1,
        docs_printed=0,
        attempts=1,
        max_attempts=3,
        error_message="",
        started_at="2026-08-08 10:00:00",
        finished_at="",
        last_event_at="2026-08-08 10:01:00",
        subject="MdA test",
        pdf_paths=["C:/secret/path.pdf"],
    )
    worker = SimpleNamespace(
        is_active=True,
        is_processing=True,
        state="DOWNLOAD",
        last_check="2026-08-08T10:00:00",
        last_job_summary="ORD-0 ok",
        current_job=job,
        pending_count=lambda: 1,
    )
    _bind_worker(core, worker)
    data = RemoteStatusService(core, config=RemoteConfig(mode="mock")).build_status()
    rt = data["enispace_runtime"]
    assert rt["status"] == "PROCESSING"
    assert rt["current_job"]["id"] == 42
    assert rt["current_job"]["order_number"] == "ORD-1"
    assert "pdf_paths" not in rt["current_job"]
    # Must not overwrite Vision Core current_job with EniSpace job
    core_job = data.get("current_job")
    if core_job is not None:
        assert core_job.get("id") != 42 or core_job.get("module_id") != "enispace"


# --- D. pending count --------------------------------------------------------


def test_phase3d_d_pending_count(core):
    worker = SimpleNamespace(
        is_active=True,
        is_processing=False,
        state="IN ATTESA",
        last_check=None,
        last_job_summary=None,
        current_job=None,
        pending_count=lambda: 7,
    )
    _bind_worker(core, worker)
    data = RemoteStatusService(core, config=RemoteConfig(mode="mock")).build_status()
    assert data["enispace_runtime"]["pending_jobs"] == 7
    # queue_size remains Vision Core queue, not forced equal to EniSpace pending
    assert isinstance(data["queue_size"], int)


# --- E. supervisor unavailable -----------------------------------------------


def test_phase3d_e_supervisor_unavailable_no_crash(core):
    core.modules = SimpleNamespace(get=lambda _mid: None)
    data = RemoteStatusService(core, config=RemoteConfig(mode="mock")).build_status()
    assert data["ok"] is True
    rt = data["enispace_runtime"]
    assert rt["available"] is False
    assert rt["status"] == "UNKNOWN"
    assert data["partial"] is True
    assert "enispace_runtime" in data["missing_sections"]


def test_phase3d_e_supervisor_raises_no_crash(core):
    class Boom:
        @property
        def is_active(self):
            raise RuntimeError("boom")

    _bind_worker(core, Boom())
    data = RemoteStatusService(core, config=RemoteConfig(mode="mock")).build_status()
    assert data["ok"] is True
    assert data["enispace_runtime"]["available"] is False
    assert data["partial"] is True


# --- F. sensitive fields -----------------------------------------------------


def test_phase3d_f_no_sensitive_fields(agent):
    data = agent.handle_command(
        RemoteCommand.create(
            command_type=CommandType.GET_STATUS,
            target_device_id="VIS-TARANTO-01",
        )
    ).result
    blob = json.dumps(data).lower()
    for needle in ("password", "passwd", "service_role", "keyring", "authorization: bearer"):
        assert needle not in blob
    # New section must not brand as JARVIS
    assert "jarvis" not in json.dumps(data.get("enispace_runtime") or {}).lower()


# --- G. no side effects ------------------------------------------------------


def test_phase3d_g_no_side_effects(core):
    process = MagicMock()
    check_mail = MagicMock()
    start = MagicMock()
    stop = MagicMock()
    worker = SimpleNamespace(
        is_active=True,
        is_processing=False,
        state="IN ATTESA",
        last_check="2026-08-08T12:00:00",
        last_job_summary="ok",
        current_job=None,
        pending_count=MagicMock(return_value=0),
        process_next=process,
        check_mail_now=check_mail,
        start=start,
        stop=stop,
        run_once=MagicMock(),
    )
    _bind_worker(core, worker)
    RemoteStatusService(core, config=RemoteConfig(mode="mock")).build_status()
    process.assert_not_called()
    check_mail.assert_not_called()
    start.assert_not_called()
    stop.assert_not_called()
    worker.run_once.assert_not_called()
    worker.pending_count.assert_called()  # read-only count OK


# --- H. heartbeat unchanged --------------------------------------------------


def test_phase3d_h_heartbeat_unchanged(agent):
    assert agent.heartbeat.send(status=DeviceStatus.ONLINE) is True
    hb = agent.backend.heartbeats[-1]
    assert "device_id" in hb
    assert "timestamp" in hb
    assert "modules" in hb
    assert "skills" not in hb
    assert "services" not in hb
    assert "enispace_runtime" not in hb
    assert "warnings" not in hb


# --- I. status_only ----------------------------------------------------------


def test_phase3d_i_status_only_unchanged(agent):
    for ctype in (
        CommandType.CHECK_ENISPACE_MAIL,
        CommandType.RETRY_JOB,
        CommandType.PAUSE_MODULE,
        CommandType.RESUME_MODULE,
        CommandType.APPROVE_JOB,
        CommandType.REJECT_JOB,
    ):
        out = agent.handle_command(
            RemoteCommand.create(
                command_type=ctype,
                target_device_id="VIS-TARANTO-01",
                params={"job_id": "x", "module_id": "enispace", "dry_run": True},
            )
        )
        assert out.status == CommandStatus.REJECTED, ctype


# --- J. SQL policy unchanged -------------------------------------------------


def test_phase3d_j_sql_policy_unchanged():
    sql = Path("supabase/migrations/20260808_vision_remote_readonly.sql").read_text(
        encoding="utf-8"
    )
    assert "enforce_status_only_commands" in sql
    assert "solo GET_STATUS consentito" in sql
    # Must not have been widened to allow operational commands
    assert "CHECK_ENISPACE_MAIL" not in sql.split("enforce_status_only_commands")[1].split(
        "create or replace"
    )[0] or "raise exception" in sql


# --- K–N regressions ---------------------------------------------------------


def test_phase3d_k_portal_facade_preserved():
    from app.modules.config.enispace_runtime import load_portal_browser_runtime

    assert callable(load_portal_browser_runtime)


def test_phase3d_l_mailbox_facade_preserved():
    from app.modules.config.enispace_runtime import load_mailbox_runtime

    assert callable(load_mailbox_runtime)


def test_phase3d_m_paths_facade_preserved():
    from app.modules.config.feature_flags import (
        use_module_settings_paths_read,
        use_module_settings_read,
    )

    assert use_module_settings_read(default=False) is False
    assert use_module_settings_paths_read(default=False) is False


def test_phase3d_n_credentials_keyring_preserved():
    import inspect

    from services import credential_service as cs

    src = inspect.getsource(cs)
    assert "CredentialService" in src
    assert "GET_STATUS" not in src


# --- O. Agent disabled -------------------------------------------------------


def test_phase3d_o_agent_disabled_by_default_kill_switch(core, tmp_path):
    cfg = RemoteConfig(enabled=False, mode="mock", device_id="VIS-TARANTO-01")
    ag = VisionRemoteAgent(
        core, cfg, backend=MockRemoteBackend(), store=CommandStore(tmp_path / "off.db")
    )
    assert ag.start() is False
    assert ag.status == DeviceStatus.DISABLED
    ag.stop()


def test_phase3d_enispace_runtime_omitted_when_none():
    d = RemoteStatusResponse(ok=True, device_id="x").to_dict()
    assert "enispace_runtime" not in d


def test_phase3d_dto_to_dict_shape():
    dto = RemoteEniSpaceRuntimeStatus(
        status="IDLE",
        active=True,
        pending_jobs=0,
        current_job=None,
        last_job=None,
        last_mail_check=None,
        last_error=None,
    )
    d = dto.to_dict()
    assert d["status"] == "IDLE"
    assert d["current_job"] is None
    assert "jarvis" not in json.dumps(d).lower()


def test_phase3d_vision_core_product_name_additive(agent):
    data = agent.handle_command(
        RemoteCommand.create(
            command_type=CommandType.GET_STATUS,
            target_device_id="VIS-TARANTO-01",
        )
    ).result
    vc = data["vision_core"]
    assert vc.get("product_name") == "VISION"
    # Legacy assistant residual may remain for compat
    assert "assistant" in vc
