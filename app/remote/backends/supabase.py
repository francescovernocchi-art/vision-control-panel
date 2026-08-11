"""SupabaseRemoteBackend — cloud via RPC Agent (thin channel).

Auth Agent:
  Token dedicato per device (VISION_AGENT_TOKEN) validato server-side
  come SHA-256 in public.agent_api_tokens.
  Le RPC sono SECURITY DEFINER: il client Python usa solo
  SUPABASE_URL + SUPABASE_ANON_KEY + VISION_AGENT_TOKEN.
  NON richiede service_role nel processo Agent.
  VISION_AGENT_TOKEN NON è una chiave nativa Supabase.
  Live Lovable RPC arg name: p_token (plaintext token).

Canale sottile (Control Panel ↔ Agent):
  heartbeat + GET_STATUS / WAKE_SUPERVISOR / DEACTIVATE_SUPERVISOR.
  Schema: supabase/migrations/20260811_agent_thin_channel_pwa_compat.sql
  Contratto: docs/VISION_CP_AGENT_THIN_CHANNEL.md
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional
from uuid import UUID

from app.remote.config import RemoteConfig
from app.remote.models import DeviceIdentity, RemoteCommand, RemoteEvent, now_iso
from app.remote.remote_log import remote_log


class SupabaseRemoteBackend:
    def __init__(self, config: RemoteConfig) -> None:
        self.config = config
        self.connected = False
        self._url = (config.supabase_url or "").rstrip("/")
        self._anon = (getattr(config, "supabase_anon_key", None) or "").strip()
        self._agent_token = (
            getattr(config, "vision_agent_token", None)
            or getattr(config, "supabase_agent_key", None)
            or ""
        ).strip()
        self._configured = bool(self._url and self._agent_token and self._anon)
        self._last_error = ""

    @property
    def last_error(self) -> str:
        return self._last_error or ""

    def connect(self) -> None:
        if not self._configured:
            self.connected = False
            raise RuntimeError(
                "Supabase not configured — set SUPABASE_URL, SUPABASE_ANON_KEY, VISION_AGENT_TOKEN"
            )
        if not self._anon:
            raise RuntimeError(
                "SUPABASE_ANON_KEY mancante — necessaria per RPC Agent (no service_role)"
            )
        try:
            # Reachability only — do NOT assume Vision contract columns (device_id).
            # Live PWA projects may expose a different devices shape; real contract
            # validation happens on agent_* RPC (heartbeat / fetch_commands).
            self._rest(
                "GET", "/rest/v1/devices", params={"select": "*", "limit": "1"}
            )
            self.connected = True
            self._last_error = ""
            remote_log.info("SupabaseRemoteBackend connected url=%s", self._url)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if self._is_soft_connect_error(msg):
                self.connected = True
                self._last_error = ""
                remote_log.info(
                    "Supabase reachable (auth/schema pending ok for connect): %s",
                    msg[:120],
                )
                return
            self.connected = False
            self._last_error = self._humanize_error(msg)
            raise RuntimeError(f"Supabase connect failed: {self._last_error}") from exc

    def disconnect(self) -> None:
        self.connected = False

    def health_check(self) -> bool:
        return bool(self.connected and self._configured)

    def probe_agent_rpc(self) -> tuple[bool, str]:
        """
        Lightweight outbound check: connect + agent_heartbeat.
        Returns (ok, human message). Does not mutate permanent ONLINE state
        beyond what connect/heartbeat already do.
        """
        try:
            self.connect()
        except Exception as exc:  # noqa: BLE001
            msg = self._humanize_error(str(exc))
            self._last_error = msg
            return False, msg
        try:
            identity = DeviceIdentity(
                device_id=self.config.device_id,
                device_name=self.config.device_name,
                agent_version=self.config.agent_version,
                vision_version=self.config.vision_version,
                hostname="probe",
                status="ONLINE",
                modules=[],
                platform_version="",
                last_seen_at=now_iso(),
            )
            self.heartbeat(identity)
            self._last_error = ""
            return True, "Agent RPC OK (heartbeat riuscito)"
        except Exception as exc:  # noqa: BLE001
            msg = self._humanize_error(str(exc))
            self._last_error = msg
            return False, msg

    def heartbeat(self, identity: DeviceIdentity) -> None:
        # Lovable/PWA live RPC uses p_token (not p_agent_token) and a shorter
        # signature — omit p_current_job_id / p_timestamp to avoid PGRST202.
        payload = {
            "p_device_id": identity.device_id,
            "p_token": self._agent_token,
            "p_status": identity.status,
            "p_agent_version": identity.agent_version,
            "p_vision_version": identity.vision_version,
            "p_platform_version": getattr(identity, "platform_version", "") or "",
            "p_modules": identity.modules or [],
        }
        try:
            self._rpc("agent_heartbeat", payload)
            self._last_error = ""
        except Exception as exc:  # noqa: BLE001
            self._last_error = self._humanize_error(str(exc))
            raise RuntimeError(self._last_error) from exc

    @staticmethod
    def _is_soft_connect_error(msg: str) -> bool:
        """Table reachable / auth pending — not a hard network failure."""
        lower = (msg or "").lower()
        if "urlopen" in lower or "timed out" in lower or "name or service not known" in lower:
            return False
        # HTTP 400 with missing Vision column is OK for reachability (PWA schema may differ)
        if "42703" in msg or "does not exist" in lower:
            return True
        if "401" in msg or "406" in msg or "PGRST" in msg or "404" in msg:
            return True
        if "HTTP Error" in msg or "HTTP 4" in msg:
            # 4xx from PostgREST usually means project is reachable
            return "HTTP 5" not in msg
        return False

    @staticmethod
    def _humanize_error(msg: str) -> str:
        raw = (msg or "").strip()
        lower = raw.lower()
        if "agent_heartbeat" in lower and (
            "pgrst202" in lower or "could not find the function" in lower or "404" in lower
        ):
            if "p_agent_token" in lower and "p_token" not in lower:
                return (
                    "RPC agent_heartbeat: firma non allineata "
                    "(client deve usare p_token, non p_agent_token)"
                )
            return (
                "RPC agent_heartbeat assente su Supabase - "
                "applicare migration thin channel "
                "(supabase/migrations/20260811_agent_thin_channel_pwa_compat.sql)"
            )
        if "agent_fetch_pending_commands" in lower and (
            "pgrst202" in lower or "could not find the function" in lower or "404" in lower
        ):
            return (
                "RPC agent_fetch_pending_commands assente su Supabase - "
                "applicare migration thin channel 20260811"
            )
        if "device_id does not exist" in lower or (
            "42703" in raw and "device_id" in lower
        ):
            return (
                "Tabella devices senza colonna device_id - "
                "applicare migration thin channel PWA-compat (ADD device_id)"
            )
        if "not configured" in lower or "mancante" in lower:
            return raw[:240]
        return raw[:240]

    def fetch_commands(self, device_id: str) -> list[RemoteCommand]:
        rows = self._rpc(
            "agent_fetch_pending_commands",
            {
                "p_device_id": device_id,
                "p_token": self._agent_token,
                "p_limit": 10,
            },
        )
        if rows is None:
            return []
        if isinstance(rows, dict):
            rows = [rows]
        out: list[RemoteCommand] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            out.append(self._row_to_command(row))
        return out

    def acknowledge_command(self, command: RemoteCommand) -> None:
        self._update_command_rpc(
            command,
            status="ACKNOWLEDGED",
            acknowledged_at=command.acknowledged_at or now_iso(),
        )

    def update_command(self, command: RemoteCommand) -> None:
        self._update_command_rpc(
            command,
            status=command.status,
            result=command.result or None,
            error=command.error or None,
            acknowledged_at=command.acknowledged_at or None,
            started_at=command.started_at or None,
            finished_at=command.finished_at or None,
        )

    def sync_job(self, job: dict[str, Any]) -> None:
        return None

    def publish_event(self, event: RemoteEvent) -> None:
        return None

    def create_notification(
        self,
        *,
        event_type: str,
        message: str,
        job_id: str = "",
        device_id: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        return None

    def _update_command_rpc(
        self,
        command: RemoteCommand,
        *,
        status: str,
        result: Any = None,
        error: Optional[str] = None,
        acknowledged_at: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> None:
        # Live Lovable signature: p_token + status/result/error only
        # (no p_acknowledged_at / p_started_at / p_finished_at).
        _ = (acknowledged_at, started_at, finished_at)
        payload: dict[str, Any] = {
            "p_device_id": command.target_device_id,
            "p_token": self._agent_token,
            "p_command_id": command.command_id,
            "p_status": status,
        }
        if result is not None:
            payload["p_result"] = result
        if error is not None:
            payload["p_error"] = error
        self._rpc("agent_update_command", payload)

    def _rpc(self, fn: str, body: dict[str, Any]) -> Any:
        return self._rest(
            "POST",
            f"/rest/v1/rpc/{fn}",
            body=body,
            prefer="return=representation",
        )

    def _rest(
        self,
        method: str,
        path: str,
        *,
        body: Optional[dict] = None,
        params: Optional[dict[str, str]] = None,
        prefer: str = "",
    ) -> Any:
        if not self._url:
            raise RuntimeError("SUPABASE_URL missing")
        q = ""
        if params:
            q = "?" + "&".join(
                f"{k}={urllib.request.quote(str(v))}" for k, v in params.items()
            )
        url = f"{self._url}{path}{q}"
        data = None
        headers = {
            "apikey": self._anon,
            "Authorization": f"Bearer {self._anon}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        if body is not None:
            data = json.dumps(body, default=str).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8") or "null"
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:
                pass
            raw = f"HTTP {exc.code}: {err_body}"
            self._last_error = self._humanize_error(raw)
            remote_log.warning(
                "Supabase %s %s failed: %s", method, path, raw[:240]
            )
            raise RuntimeError(self._last_error) from exc

    @staticmethod
    def _row_to_command(row: dict[str, Any]) -> RemoteCommand:
        cid = str(row.get("command_id") or "")
        try:
            UUID(cid)
        except Exception:
            pass
        params = row.get("parameters") or row.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        return RemoteCommand(
            command_id=cid or str(row.get("id") or ""),
            command_type=str(row.get("command_type") or ""),
            target_device_id=str(
                row.get("target_device_id") or row.get("device_id") or ""
            ),
            status=str(row.get("status") or "PENDING"),
            params=params,
            created_at=str(row.get("created_at") or row.get("requested_at") or ""),
            expires_at=str(row.get("expires_at") or ""),
            acknowledged_at=str(row.get("acknowledged_at") or ""),
            started_at=str(row.get("started_at") or ""),
            finished_at=str(row.get("finished_at") or ""),
            result=row.get("result") if isinstance(row.get("result"), dict) else {},
            error=str(row.get("error") or ""),
            source="backend",
        )
