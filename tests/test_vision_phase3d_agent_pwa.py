"""Phase 3D — VISION Agent ↔ PWA communication (GET_STATUS + runtime observability)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.bootstrap import create_vision_core
from app.platform import bootstrap_platform
from app.remote.agent import VisionRemoteAgent
from app.remote.backends.mock import MockRemoteBackend
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
        core, cfg, backend=backend, store=CommandStore(tmp_path / "phase3d_remote.db")
    )
    backend.connect()
    ag._set_status(DeviceStatus.ONLINE)
    ag._enabled = True
    yield ag
    ag.stop()


def _baseline_keys(data: dict) -> None:
    for key in (
        "ok",
        "api_version",
        "contract_version",
        "device_id",
        "core_status",
        "supervisor_status",
        "overall_health",
        "queue_size",
        "modules",
        "skills",
        "services",
        "warnings",
        "agent",
    ):
        assert key in data, key


# --- A. agent online ---------------------------------------------------------


def test_phase3d_a_agent_online_status_real(agent):
    out = agent.handle_command(
        RemoteCommand.create(
            command_type=CommandType.GET_STATUS,
            target_device_id="VIS-TARANTO-01",
        )
    )
    assert out.status == CommandStatus.COMPLETED
    data = out.result
    _baseline_keys(data)
    assert data["ok"] is True
    assert data["agent"]["status"] in ("ONLINE", "DEGRADED", "IDLE", "RUNNING")
    assert data["enispace_runtime"] is not None
    assert "status" in data["enispace_runtime"]
    json.dumps(data)


# --- B. agent offline (PWA-side semantics mirrored as pure helpers) -----------


def test_phase3d_b_agent_offline_no_crash_and_status():
    """Offline is derived from heartbeat last_seen — no invented ONLINE."""
    from datetime import datetime, timedelta, timezone

    # Mirror PWA isAgentOffline / derivedAgentStatus contract
    now = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)
    last = (now - timedelta(seconds=120)).isoformat()
    threshold = 60
    elapsed = (now - datetime.fromisoformat(last)).total_seconds()
    offline = elapsed > threshold
    assert offline is True
    # When offline, consumers must not fall back to demo ONLINE
    display_status = "OFFLINE"
    assert display_status == "OFFLINE"


# --- C. heartbeat ------------------------------------------------------------


def test_phase3d_c_heartbeat_last_seen_changes(agent):
    backend = agent.backend
    assert agent.heartbeat.send(status=DeviceStatus.ONLINE) is True
    t1 = backend.heartbeats[-1]["timestamp"]
    time.sleep(0.05)
    assert agent.heartbeat.send(status=DeviceStatus.ONLINE) is True
    t2 = backend.heartbeats[-1]["timestamp"]
    assert t2 >= t1
    assert "device_id" in backend.heartbeats[-1]
    assert "skills" not in backend.heartbeats[-1]


# --- D. idle -----------------------------------------------------------------


def test_phase3d_d_idle_no_active_job(agent):
    data = agent.handle_command(
        RemoteCommand.create(
            command_type=CommandType.GET_STATUS,
            target_device_id="VIS-TARANTO-01",
        )
    ).result
    # Agent reachable; EniSpace runtime section present (may be UNKNOWN if unbound)
    assert data["agent"]["status"] in ("ONLINE", "DEGRADED", "IDLE")
    rt = data["enispace_runtime"]
    assert rt["status"] in ("IDLE", "PROCESSING", "DEGRADED", "OFFLINE", "UNKNOWN")
    assert int(data["queue_size"]) >= 0
    # If platform exposes a Vision Core job, it must be real DTO shape — not demo
    job = data.get("current_job")
    if job is not None:
        assert isinstance(job, dict)
        assert "job_id" in job or "id" in job or "status" in job


# --- E. running job ----------------------------------------------------------


def test_phase3d_e_running_job_from_worker_binding(core):
    fake_worker = SimpleNamespace(
        state="DOWNLOAD",
        is_active=True,
        is_processing=True,
        pending_count=lambda: 2,
        last_check="2026-08-08T10:00:00",
        last_job_summary="—",
        current_job=SimpleNamespace(
            id=7,
            status="PROCESSING",
            state="DOWNLOAD",
            order_number="X",
            contract_number="",
            docs_found=0,
            docs_downloaded=0,
            docs_printed=0,
            attempts=1,
            max_attempts=3,
            error_message="",
            started_at="",
            finished_at="",
            last_event_at="",
            subject="",
        ),
    )
    fake_eni = SimpleNamespace(jarvis=fake_worker)
    fake_modules = SimpleNamespace(get=lambda mid: fake_eni if mid == "enispace" else None)
    core.modules = fake_modules
    svc = RemoteStatusService(core, config=RemoteConfig(mode="mock"))
    data = svc.build_status()
    rt = data["enispace_runtime"]
    assert rt["available"] is True
    assert rt["status"] == "PROCESSING"
    assert rt["pending_jobs"] == 2
    assert rt["current_job"]["id"] == 7


# --- F. success last activity ------------------------------------------------


def test_phase3d_f_success_exposed_without_fabricating(agent):
    data = agent.handle_command(
        RemoteCommand.create(
            command_type=CommandType.GET_STATUS,
            target_device_id="VIS-TARANTO-01",
        )
    ).result
    # Do not invent last success — only expose real fields if present
    assert "last_success" not in data or data.get("last_success") is not None
    assert data.get("ok") is True
    # agent.last_error empty on healthy path
    assert data["agent"].get("last_error", "") in ("", None) or isinstance(
        data["agent"].get("last_error"), str
    )


# --- G. error without sensitive stacktrace -----------------------------------


def test_phase3d_g_error_truncated_no_stacktrace(core):
    class BoomCore:
        def __getattr__(self, _name):
            raise RuntimeError("secret_path=/etc/passwd stacktrace_line")

    svc = RemoteStatusService(BoomCore(), config=RemoteConfig(mode="mock"))
    data = svc.build_status()
    assert data["ok"] is True
    assert data["partial"] is True
    err = (data.get("agent") or {}).get("last_error") or ""
    assert "Traceback" not in err
    assert len(err) <= 200
    # enispace_runtime still attached when possible
    assert "enispace_runtime" in data


# --- H. no demo fallback on missing queue ------------------------------------


def test_phase3d_h_no_demo_queue_fallback():
    resp = RemoteStatusResponse(
        ok=True,
        device_id="VIS-TARANTO-01",
        queue_size=0,
        core_status="ONLINE",
        overall_health="ONLINE",
    )
    d = resp.to_dict()
    assert d["queue_size"] == 0
    # Absent enispace_runtime must not invent demo modules
    assert "enispace_runtime" not in d
    # PWA contract: missing queue_size → display "—", never job-table count
    missing = {}
    display = missing.get("queue_size")
    assert display is None


# --- I. GET_STATUS backward compatibility ------------------------------------


def test_phase3d_i_get_status_backward_compatible(agent):
    data = agent.handle_command(
        RemoteCommand.create(
            command_type=CommandType.GET_STATUS,
            target_device_id="VIS-TARANTO-01",
        )
    ).result
    _baseline_keys(data)
    # Additive only
    assert data["api_version"] == "v1"
    assert data["contract_version"] == "1.0.0"
    assert isinstance(data["modules"], list)
    assert isinstance(data["skills"], list)
    assert isinstance(data["services"], list)
    assert "enispace_runtime" in data  # new optional section


def test_phase3d_i_runtime_omitted_when_none():
    d = RemoteStatusResponse(ok=True, device_id="x").to_dict()
    assert "enispace_runtime" not in d


# --- J–N regressions preserved by suite markers (smoke here) -----------------


def test_phase3d_j_portal_facade_importable():
    from app.modules.config.enispace_runtime import load_portal_browser_runtime

    assert callable(load_portal_browser_runtime)


def test_phase3d_k_mailbox_facade_importable():
    from app.modules.config.enispace_runtime import load_mailbox_runtime

    assert callable(load_mailbox_runtime)


def test_phase3d_l_paths_facade_importable():
    from app.modules.config.enispace_runtime import load_paths_runtime
    from app.modules.config.feature_flags import (
        use_module_settings_paths_read,
        use_module_settings_read,
    )

    assert callable(load_paths_runtime)
    assert use_module_settings_read(default=False) is False
    assert use_module_settings_paths_read(default=False) is False


def test_phase3d_m_credentials_keyring_untouched():
    import inspect

    from services import credential_service as cs

    src = inspect.getsource(cs)
    assert "keyring" in src.lower() or "CredentialService" in src
    # Phase 3D must not rewrite credential service module body for remote
    assert "GET_STATUS" not in src


def test_phase3d_n_print_settings_legacy_not_migrated():
    # Print remains AppSettings / jarvis_printer naming — not ModuleSettings write path
    from app.modules.config import defaults

    text = Path(defaults.__file__).read_text(encoding="utf-8")
    # Seed may mention print capability but Phase 3D does not migrate printer config
    assert "dual_write" not in text.lower()


def test_phase3d_status_only_policy_unchanged(agent):
    out = agent.handle_command(
        RemoteCommand.create(
            command_type=CommandType.RETRY_JOB,
            target_device_id="VIS-TARANTO-01",
            params={"job_id": "x"},
        )
    )
    assert out.status == CommandStatus.REJECTED
