"""Factory client backend (mock | supabase stub)."""

from __future__ import annotations

from typing import Any

from app.remote.backends.mock import MockRemoteBackend
from app.remote.backends.supabase import SupabaseRemoteBackend
from app.remote.config import RemoteConfig
from app.remote.remote_log import remote_log


def create_backend(config: RemoteConfig) -> Any:
    mode = (config.mode or "mock").strip().lower()
    if mode == "supabase":
        remote_log.info(
            "Backend supabase selezionato (RPC Agent + status_only)"
        )
        return SupabaseRemoteBackend(config)
    remote_log.info("Backend mock attivo")
    return MockRemoteBackend()
