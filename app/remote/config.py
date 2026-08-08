"""Configurazione Remote Agent — solo da env / file locale, mai secret in codice."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from utils.paths import config_dir, project_root


def _load_dotenv(path: Path) -> None:
    """Carica .env semplice (KEY=VALUE) senza dipendenze esterne."""
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


def _bool(val: Optional[str], default: bool = False) -> bool:
    if val is None or val == "":
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _int(val: Optional[str], default: int) -> int:
    try:
        return int(val) if val is not None and str(val).strip() else default
    except (TypeError, ValueError):
        return default


@dataclass
class RemoteConfig:
    """Kill switch OFF di default — nessuna esecuzione remota senza opt-in locale."""

    enabled: bool = False
    mode: str = "mock"  # mock | supabase
    device_id: str = "VIS-TARANTO-01"
    device_name: str = "PC VIS Taranto"
    backend_provider: str = "supabase"
    supabase_url: str = ""
    supabase_agent_key: str = ""
    heartbeat_seconds: int = 15
    command_poll_seconds: int = 3
    agent_version: str = "0.1.0"
    vision_version: str = "2.0-vision"

    @classmethod
    def load(cls, env_path: Optional[Path] = None) -> "RemoteConfig":
        root = project_root()
        _load_dotenv(env_path or (root / ".env"))
        _load_dotenv(config_dir() / "remote.env")

        mode = (os.environ.get("VISION_REMOTE_MODE") or "mock").strip().lower()
        if mode not in ("mock", "supabase"):
            mode = "mock"

        return cls(
            enabled=_bool(os.environ.get("VISION_REMOTE_ENABLED"), False),
            mode=mode,
            device_id=(os.environ.get("VISION_DEVICE_ID") or "VIS-TARANTO-01").strip(),
            device_name=(os.environ.get("VISION_DEVICE_NAME") or "PC VIS Taranto").strip(),
            backend_provider=(
                os.environ.get("VISION_BACKEND_PROVIDER") or "supabase"
            ).strip().lower(),
            supabase_url=(os.environ.get("SUPABASE_URL") or "").strip(),
            supabase_agent_key=(os.environ.get("SUPABASE_AGENT_KEY") or "").strip(),
            heartbeat_seconds=max(
                5, _int(os.environ.get("VISION_HEARTBEAT_SECONDS"), 15)
            ),
            command_poll_seconds=max(
                2, _int(os.environ.get("VISION_COMMAND_POLL_SECONDS"), 3)
            ),
            agent_version=(os.environ.get("VISION_AGENT_VERSION") or "0.1.0").strip(),
            vision_version=(os.environ.get("VISION_VERSION") or "2.0-vision").strip(),
        )

    def redacted_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "backend_provider": self.backend_provider,
            "supabase_url_set": bool(self.supabase_url),
            "supabase_agent_key_set": bool(self.supabase_agent_key),
            "heartbeat_seconds": self.heartbeat_seconds,
            "command_poll_seconds": self.command_poll_seconds,
            "agent_version": self.agent_version,
            "vision_version": self.vision_version,
        }
