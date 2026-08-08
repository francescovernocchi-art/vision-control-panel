"""SupabaseRemoteBackend — stub sicuro senza schema inventato.

Attende URL/schema/RLS reali dalla PWA prima del collegamento cloud.
In questa fase: connect fallisce in modo controllato se mancano credenziali,
oppure resta in modalità "not configured" senza chiamate HTTP.
"""

from __future__ import annotations

from typing import Any, Optional

from app.remote.config import RemoteConfig
from app.remote.models import DeviceIdentity, RemoteCommand, RemoteEvent
from app.remote.remote_log import remote_log


class SupabaseRemoteBackend:
    """
    Adapter preparatorio.
    NON assume colonne SQL: nessun INSERT/SELECT fino a contratto PWA.
    """

    def __init__(self, config: RemoteConfig) -> None:
        self.config = config
        self.connected = False
        self._configured = bool(config.supabase_url and config.supabase_agent_key)

    def connect(self) -> None:
        if not self._configured:
            remote_log.warning(
                "Supabase non configurato (mancano SUPABASE_URL / SUPABASE_AGENT_KEY) — "
                "backend stub inattivo"
            )
            self.connected = False
            raise RuntimeError("Supabase not configured — provide URL, schema and agent auth")
        # Collegamento reale differito: serve schema + auth agent dalla PWA
        remote_log.warning(
            "SupabaseRemoteBackend: schema/RLS non ancora forniti — "
            "nessuna chiamata cloud eseguita"
        )
        self.connected = False
        raise RuntimeError(
            "Supabase schema not provided yet — use VISION_REMOTE_MODE=mock until contract ready"
        )

    def disconnect(self) -> None:
        self.connected = False

    def health_check(self) -> bool:
        return False

    def heartbeat(self, identity: DeviceIdentity) -> None:
        raise RuntimeError("Supabase backend not ready")

    def fetch_commands(self, device_id: str) -> list[RemoteCommand]:
        return []

    def acknowledge_command(self, command: RemoteCommand) -> None:
        return None

    def update_command(self, command: RemoteCommand) -> None:
        return None

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
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        return None
