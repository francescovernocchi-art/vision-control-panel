"""Unit test Supabase backend mapping — no network / no real Supabase."""

from __future__ import annotations

from app.remote.backends.supabase import SupabaseRemoteBackend
from app.remote.config import RemoteConfig
from app.remote.models import DeviceIdentity, is_remote_command_allowed


def test_status_only_policy_allows_thin_channel_only():
    assert is_remote_command_allowed("GET_STATUS", policy="status_only")
    assert is_remote_command_allowed("WAKE_SUPERVISOR", policy="status_only")
    assert is_remote_command_allowed("DEACTIVATE_SUPERVISOR", policy="status_only")
    assert not is_remote_command_allowed("CHECK_ENISPACE_MAIL", policy="status_only")
    assert not is_remote_command_allowed("PAUSE_MODULE", policy="status_only")
    assert not is_remote_command_allowed("RETRY_JOB", policy="status_only")


def test_supabase_backend_requires_anon_and_token():
    cfg = RemoteConfig(
        mode="supabase",
        supabase_url="https://example.supabase.co",
        vision_agent_token="tok",
        supabase_anon_key="",
    )
    be = SupabaseRemoteBackend(cfg)
    assert be._configured is False


def test_vision_agent_token_alias():
    cfg = RemoteConfig(vision_agent_token="secret-token-value")
    assert cfg.supabase_agent_key == "secret-token-value"
    assert cfg.vision_agent_token == "secret-token-value"


def test_row_to_command_mapping():
    row = {
        "command_id": "11111111-1111-1111-1111-111111111111",
        "command_type": "GET_STATUS",
        "target_device_id": "VIS-TARANTO-01",
        "status": "PENDING",
        "parameters": {},
        "requested_at": "2026-08-08T10:00:00",
    }
    cmd = SupabaseRemoteBackend._row_to_command(row)
    assert cmd.command_type == "GET_STATUS"
    assert cmd.target_device_id == "VIS-TARANTO-01"
    assert cmd.status == "PENDING"


def test_identity_heartbeat_shape_has_platform_version():
    ident = DeviceIdentity(
        device_id="VIS-TARANTO-01",
        device_name="PC VIS Taranto",
        agent_version="0.1.0",
        vision_version="2.0-vision",
        hostname="host",
        status="ONLINE",
        platform_version="0.5.0-remote-readonly",
        modules=[{"module_id": "enispace", "status": "ONLINE", "health": "ONLINE"}],
    )
    hb = ident.to_heartbeat()
    assert hb["platform_version"]
    assert "skills" not in hb


def test_humanize_missing_heartbeat_rpc():
    msg = (
        'HTTP 404: {"code":"PGRST202","message":'
        '"Could not find the function public.agent_heartbeat(...)"'
    )
    out = SupabaseRemoteBackend._humanize_error(msg)
    assert "agent_heartbeat" in out
    assert "migration" in out.lower()


def test_soft_connect_accepts_missing_device_id_column():
    msg = (
        'HTTP 400: {"code":"42703","message":'
        '"column devices.device_id does not exist"}'
    )
    assert SupabaseRemoteBackend._is_soft_connect_error(msg) is True


def test_connect_probe_uses_select_star(monkeypatch):
    cfg = RemoteConfig(
        mode="supabase",
        supabase_url="https://example.supabase.co",
        vision_agent_token="tok",
        supabase_anon_key="anon",
        device_id="VIS-TARANTO-01",
    )
    be = SupabaseRemoteBackend(cfg)
    calls = []

    def fake_rest(method, path, *, body=None, params=None, prefer=""):
        calls.append((method, path, params))
        return []

    monkeypatch.setattr(be, "_rest", fake_rest)
    be.connect()
    assert be.connected is True
    assert calls
    assert calls[0][1] == "/rest/v1/devices"
    assert calls[0][2].get("select") == "*"


def test_publish_message_uses_p_token(monkeypatch):
    cfg = RemoteConfig(
        mode="supabase",
        supabase_url="https://example.supabase.co",
        vision_agent_token="tok-secret",
        supabase_anon_key="anon",
        device_id="VIS-TARANTO-01",
    )
    be = SupabaseRemoteBackend(cfg)
    calls = []

    def fake_rpc(fn, body):
        calls.append((fn, body))
        return {"ok": True, "id": 1}

    monkeypatch.setattr(be, "_rpc", fake_rpc)
    be.publish_message(message="Supervisor attivato (WAKE)", level="info", source="remote")
    assert len(calls) == 1
    assert calls[0][0] == "agent_publish_message"
    assert calls[0][1]["p_token"] == "tok-secret"
    assert calls[0][1]["p_device_id"] == "VIS-TARANTO-01"
    assert "WAKE" in calls[0][1]["p_message"]


def test_publish_event_skips_job_noise(monkeypatch):
    from app.remote.models import RemoteEvent

    cfg = RemoteConfig(
        mode="supabase",
        supabase_url="https://example.supabase.co",
        vision_agent_token="tok",
        supabase_anon_key="anon",
        device_id="VIS-TARANTO-01",
    )
    be = SupabaseRemoteBackend(cfg)
    calls = []
    monkeypatch.setattr(be, "_rpc", lambda fn, body: calls.append((fn, body)))

    be.publish_event(
        RemoteEvent(
            event_type="JOB_STARTED",
            message="job",
            module="enispace",
            device_id="VIS-TARANTO-01",
        )
    )
    assert calls == []

    be.publish_event(
        RemoteEvent(
            event_type="COMMAND_COMPLETED",
            message="Supervisor attivato (WAKE)",
            module="remote",
            device_id="VIS-TARANTO-01",
            command_id="11111111-1111-1111-1111-111111111111",
        )
    )
    assert len(calls) == 1
    assert calls[0][0] == "agent_publish_message"
