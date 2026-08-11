"""Accesso SQLite locale — storico contratti, documenti, operazioni, impostazioni."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

from database.models import (
    AppSettings,
    Contract,
    Document,
    DocumentStatus,
    MailRegisterEntry,
    Operation,
    OperationResult,
    PrintQueueItem,
    now_iso,
)
from utils.logger import get_logger
from utils.paths import (
    database_path,
    default_download_dir,
    ensure_module_data_tree,
    ENISPACE_HOME_URL,
)

# Import lazy per evitare cicli: modelli Jarvis vivono in services.jarvis.models
# ma i metodi DB accettano/restituiscono quelli.

logger = get_logger("database")

SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_number TEXT NOT NULL UNIQUE,
    order_number TEXT,
    framework_contract TEXT,
    acquisition_module TEXT,
    first_seen TEXT NOT NULL,
    last_checked TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    remote_id TEXT,
    filename TEXT NOT NULL,
    doc_type TEXT,
    remote_date TEXT,
    size INTEGER,
    local_path TEXT,
    sha256 TEXT,
    downloaded_at TEXT,
    status TEXT NOT NULL DEFAULT 'available',
    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    contract_number TEXT,
    operation TEXT NOT NULL,
    result TEXT NOT NULL,
    message TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS print_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_path TEXT NOT NULL,
    order_number TEXT,
    acquisition_module TEXT,
    eml_name TEXT,
    filename TEXT,
    created_at TEXT NOT NULL,
    printed_at TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS outlook_processed (
    entry_id TEXT PRIMARY KEY,
    subject TEXT,
    order_number TEXT,
    acquisition_module TEXT,
    processed_at TEXT NOT NULL,
    result TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS imap_processed (
    entry_id TEXT PRIMARY KEY,
    folder TEXT,
    uid TEXT,
    subject TEXT,
    order_number TEXT,
    acquisition_module TEXT,
    processed_at TEXT NOT NULL,
    result TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS mail_register (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id TEXT,
    folder TEXT,
    uid TEXT,
    subject TEXT,
    order_number TEXT,
    acquisition_module TEXT,
    status TEXT NOT NULL,
    note TEXT,
    processed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_contract ON documents(contract_id);
CREATE INDEX IF NOT EXISTS idx_documents_remote ON documents(remote_id);
CREATE INDEX IF NOT EXISTS idx_operations_contract ON operations(contract_number);
CREATE INDEX IF NOT EXISTS idx_print_queue_status ON print_queue(status);
CREATE INDEX IF NOT EXISTS idx_mail_register_processed
    ON mail_register(processed_at DESC);
CREATE INDEX IF NOT EXISTS idx_imap_processed_at
    ON imap_processed(processed_at DESC);

CREATE TABLE IF NOT EXISTS jarvis_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mail_id TEXT NOT NULL UNIQUE,
    mail_uid TEXT,
    mail_folder TEXT,
    message_id TEXT,
    subject TEXT,
    sender TEXT,
    received_at TEXT,
    order_number TEXT,
    contract_number TEXT,
    acquisition_module TEXT,
    status TEXT NOT NULL,
    outcome TEXT,
    state TEXT,
    docs_found INTEGER NOT NULL DEFAULT 0,
    docs_downloaded INTEGER NOT NULL DEFAULT 0,
    docs_printed INTEGER NOT NULL DEFAULT 0,
    printer_name TEXT,
    pdf_paths TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    error_message TEXT,
    simulation INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    last_event_at TEXT
);

CREATE TABLE IF NOT EXISTS jarvis_job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    state TEXT,
    FOREIGN KEY (job_id) REFERENCES jarvis_jobs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_jarvis_jobs_status ON jarvis_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jarvis_jobs_created ON jarvis_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jarvis_events_job ON jarvis_job_events(job_id);

-- Phase 1: ModuleSettings / ModuleState (parallel to AppSettings; non-operative)
CREATE TABLE IF NOT EXISTS module_settings (
    module_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    version TEXT NOT NULL,
    capabilities TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS module_state (
    module_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'OFFLINE',
    health TEXT NOT NULL DEFAULT 'UNKNOWN',
    last_error TEXT,
    last_activity_at TEXT,
    last_sync_at TEXT,
    metrics TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate_contracts(conn)
            self._migrate_module_tables(conn)
        self._ensure_default_settings()
        self._ensure_module_settings_seed()
        logger.debug("Schema SQLite pronto: %s", self.path)

    def _migrate_module_tables(self, conn: sqlite3.Connection) -> None:
        """Idempotent Phase 1 tables (also covered by SCHEMA CREATE IF NOT EXISTS)."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS module_settings (
                module_id TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                version TEXT NOT NULL,
                capabilities TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS module_state (
                module_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'OFFLINE',
                health TEXT NOT NULL DEFAULT 'UNKNOWN',
                last_error TEXT,
                last_activity_at TEXT,
                last_sync_at TEXT,
                metrics TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            )
            """
        )

    def _ensure_module_settings_seed(self) -> None:
        """
        Insert safe non-operative ModuleSettings / ModuleState defaults.

        Does NOT overwrite existing rows and does NOT touch AppSettings.
        ModuleSettings remains parallel infrastructure (not operative SoT).
        """
        from app.modules.config.defaults import build_seed_envelope, seed_module_ids
        from app.modules.config.validate import validate_module_settings

        for module_id in seed_module_ids():
            existing = self.get_module_settings(module_id)
            if existing is not None:
                # Phase 3A: ensure explicit_fields present (empty ⇒ no legacy override)
                if "explicit_fields" not in existing:
                    patched = dict(existing)
                    patched["explicit_fields"] = []
                    try:
                        validated = validate_module_settings(
                            patched, expected_module_id=module_id
                        )
                        self.upsert_module_settings(validated, validate=False)
                    except Exception as exc:
                        logger.warning(
                            "normalize explicit_fields %s failed: %s", module_id, exc
                        )
                continue
            try:
                ensure_module_data_tree(module_id)
            except Exception as exc:
                logger.warning("module data tree %s: %s", module_id, exc)
            envelope = build_seed_envelope(module_id)
            validated = validate_module_settings(
                envelope, expected_module_id=module_id
            )
            self.upsert_module_settings(validated, validate=False)
            if self.get_module_state(module_id) is None:
                self.upsert_module_state(
                    {
                        "module_id": module_id,
                        "status": "DISABLED" if not validated.get("enabled") else "OFFLINE",
                        "health": "UNKNOWN",
                        "last_error": None,
                        "last_activity_at": None,
                        "last_sync_at": None,
                        "metrics": {},
                    }
                )
            logger.info("Seed ModuleSettings creato per %s (non-operative)", module_id)

    def _migrate_contracts(self, conn: sqlite3.Connection) -> None:
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(contracts)").fetchall()
        }
        if "order_number" not in cols:
            conn.execute("ALTER TABLE contracts ADD COLUMN order_number TEXT")
        if "framework_contract" not in cols:
            conn.execute("ALTER TABLE contracts ADD COLUMN framework_contract TEXT")
        if "acquisition_module" not in cols:
            conn.execute("ALTER TABLE contracts ADD COLUMN acquisition_module TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_contracts_order ON contracts(order_number)"
        )

    def _ensure_default_settings(self) -> None:
        defaults = AppSettings(
            download_folder=str(default_download_dir()),
            enispace_base_url=ENISPACE_HOME_URL,
        )
        existing = self.get_setting("setup_completed")
        if existing is None:
            self.save_settings(defaults)
        # Migrazione: URL eniSpace se assente o vuoto
        current_url = self.get_setting("enispace_base_url")
        if not current_url or not current_url.strip():
            self.set_setting("enispace_base_url", ENISPACE_HOME_URL)
        # Migrazione: impostazioni Outlook legacy (non usate)
        if self.get_setting("outlook_folder") is None:
            self.set_setting("outlook_folder", "Inbox/MdA_Eni")
        if self.get_setting("outlook_unread_only") is None:
            self.set_setting("outlook_unread_only", True)
        # Migrazione: IMAP (SecureMail / VIS)
        if self.get_setting("imap_host") is None:
            self.set_setting("imap_host", "pop.securemail.pro")
        if self.get_setting("imap_port") is None:
            self.set_setting("imap_port", 993)
        if self.get_setting("imap_security") is None:
            self.set_setting("imap_security", "SSL")
        if self.get_setting("imap_folder") is None:
            # Preferisci cartella Outlook legacy se già impostata
            legacy = self.get_setting("outlook_folder") or "INBOX.MdA_Eni"
            folder = (legacy or "INBOX.MdA_Eni").replace("/", ".")
            if folder.lower().startswith("inbox."):
                folder = "INBOX" + folder[5:]
            self.set_setting("imap_folder", folder or "INBOX.MdA_Eni")
        # Correzione: INBOX nuda con legacy MdA_Eni → INBOX.MdA_Eni
        imap_folder_now = (self.get_setting("imap_folder") or "").strip()
        legacy_now = (self.get_setting("outlook_folder") or "").strip().lower()
        if imap_folder_now.upper() == "INBOX" and "mda_eni" in legacy_now.replace(
            "/", "."
        ):
            self.set_setting("imap_folder", "INBOX.MdA_Eni")
        if self.get_setting("imap_unread_only") is None:
            unread = self.get_setting("outlook_unread_only")
            self.set_setting(
                "imap_unread_only",
                True if unread is None else unread in ("1", "true", "True"),
            )
        if self.get_setting("smtp_host") is None:
            self.set_setting("smtp_host", "authsmtp.securemail.pro")
        if self.get_setting("smtp_port") is None:
            self.set_setting("smtp_port", 465)
        if self.get_setting("smtp_security") is None:
            self.set_setting("smtp_security", "SSL")
        if self.get_setting("imap_username") is None:
            self.set_setting("imap_username", "")
        if self.get_setting("autosync_enabled") is None:
            self.set_setting("autosync_enabled", False)
        if self.get_setting("autosync_interval_minutes") is None:
            self.set_setting("autosync_interval_minutes", 15)
        # Migrazione / default: Nascondi browser (headed nascosto, non headless)
        if self.get_setting("browser_hidden") is None:
            vis = self.get_setting("browser_visible")
            if vis is None:
                self.set_setting("browser_hidden", True)
                self.set_setting("browser_visible", False)
            else:
                visible = vis in ("1", "true", "True", "yes")
                self.set_setting("browser_hidden", not visible)
        # JARVIS defaults
        if self.get_setting("jarvis_enabled") is None:
            self.set_setting("jarvis_enabled", False)
        if self.get_setting("jarvis_interval_seconds") is None:
            self.set_setting("jarvis_interval_seconds", 60)
        if self.get_setting("jarvis_autostart") is None:
            self.set_setting("jarvis_autostart", False)
        if self.get_setting("jarvis_max_retries") is None:
            self.set_setting("jarvis_max_retries", 3)
        if self.get_setting("jarvis_printer") is None:
            self.set_setting("jarvis_printer", "")
        if self.get_setting("jarvis_download_folder") is None:
            self.set_setting("jarvis_download_folder", "")
        if self.get_setting("jarvis_keep_pdfs") is None:
            self.set_setting("jarvis_keep_pdfs", True)
        if self.get_setting("jarvis_debug") is None:
            self.set_setting("jarvis_debug", False)
        if self.get_setting("jarvis_simulation") is None:
            self.set_setting("jarvis_simulation", False)
        if self.get_setting("jarvis_avatar_level") is None:
            self.set_setting("jarvis_avatar_level", "full")
        if self.get_setting("jarvis_avatar_model") is None:
            self.set_setting("jarvis_avatar_model", "vision_avatar_v1")
        if self.get_setting("jarvis_avatar_mode") is None:
            self.set_setting("jarvis_avatar_mode", "3d")
        # Upgrade host legacy Register.it → SecureMail (una sola volta se ancora default vecchio)
        old_imap = (self.get_setting("imap_host") or "").strip().lower()
        if old_imap in ("", "imap.register.it"):
            self.set_setting("imap_host", "pop.securemail.pro")
            self.set_setting("imap_port", 993)
            self.set_setting("imap_security", "SSL")
        old_smtp = (self.get_setting("smtp_host") or "").strip().lower()
        if old_smtp in ("", "smtp.register.it"):
            self.set_setting("smtp_host", "authsmtp.securemail.pro")
            self.set_setting("smtp_port", 465)
            self.set_setting("smtp_security", "SSL")

    # ------------------------------------------------------------------ settings
    def get_setting(self, key: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: Any) -> None:
        if isinstance(value, bool):
            stored = "1" if value else "0"
        elif isinstance(value, (dict, list)):
            stored = json.dumps(value, ensure_ascii=False)
        else:
            stored = str(value)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, stored),
            )

    def get_settings(self) -> AppSettings:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        raw = {r["key"]: r["value"] for r in rows}

        def _bool(key: str, default: bool) -> bool:
            if key not in raw:
                return default
            return raw[key] in ("1", "true", "True", "yes")

        def _int(key: str, default: int) -> int:
            try:
                return int(raw.get(key, default))
            except (TypeError, ValueError):
                return default

        extra: dict = {}
        if "extra" in raw:
            try:
                extra = json.loads(raw["extra"])
            except json.JSONDecodeError:
                extra = {}

        return AppSettings(
            username=raw.get("username", ""),
            download_folder=raw.get("download_folder") or str(default_download_dir()),
            browser_visible=_bool("browser_visible", False),
            browser_hidden=(
                _bool("browser_hidden", True)
                if "browser_hidden" in raw
                else (not _bool("browser_visible", True))
            ),
            chrome_use_system_profile=_bool("chrome_use_system_profile", True),
            chrome_profile_directory=(
                raw.get("chrome_profile_directory") or "Default"
            ).strip()
            or "Default",
            debug_mode=_bool("debug_mode", False),
            browser_timeout_ms=_int("browser_timeout_ms", 60000),
            open_folder_after_download=_bool("open_folder_after_download", False),
            setup_completed=_bool("setup_completed", False),
            enispace_base_url=raw.get("enispace_base_url") or ENISPACE_HOME_URL,
            marketplace_base_url=raw.get("marketplace_base_url", ""),
            imap_host=raw.get("imap_host") or "pop.securemail.pro",
            imap_port=_int("imap_port", 993),
            imap_security=raw.get("imap_security") or "SSL",
            imap_username=raw.get("imap_username", ""),
            imap_folder=raw.get("imap_folder") or "INBOX.MdA_Eni",
            imap_unread_only=_bool("imap_unread_only", True),
            autosync_enabled=_bool("autosync_enabled", False),
            autosync_interval_minutes=max(
                1, _int("autosync_interval_minutes", 15)
            ),
            smtp_host=raw.get("smtp_host") or "authsmtp.securemail.pro",
            smtp_port=_int("smtp_port", 465),
            smtp_security=raw.get("smtp_security") or "SSL",
            outlook_folder=raw.get("outlook_folder") or "Inbox/MdA_Eni",
            outlook_unread_only=_bool("outlook_unread_only", True),
            jarvis_enabled=_bool("jarvis_enabled", False),
            jarvis_interval_seconds=max(15, _int("jarvis_interval_seconds", 60)),
            jarvis_autostart=_bool("jarvis_autostart", False),
            jarvis_max_retries=max(1, _int("jarvis_max_retries", 3)),
            jarvis_printer=raw.get("jarvis_printer", "") or "",
            jarvis_download_folder=raw.get("jarvis_download_folder", "") or "",
            jarvis_keep_pdfs=_bool("jarvis_keep_pdfs", True),
            jarvis_debug=_bool("jarvis_debug", False),
            jarvis_simulation=_bool("jarvis_simulation", False),
            jarvis_avatar_level=(
                raw.get("jarvis_avatar_level") or "full"
            ).strip().lower()
            or "full",
            jarvis_avatar_model=(
                raw.get("jarvis_avatar_model") or "vision_avatar_v1"
            ).strip()
            or "vision_avatar_v1",
            jarvis_avatar_mode=(
                raw.get("jarvis_avatar_mode") or "3d"
            ).strip().lower()
            or "3d",
            extra=extra,
        )

    def save_settings(self, settings: AppSettings) -> None:
        mapping = {
            "username": settings.username,
            "download_folder": settings.download_folder,
            "browser_hidden": settings.browser_hidden,
            "browser_visible": not settings.browser_hidden,
            "chrome_use_system_profile": bool(settings.chrome_use_system_profile),
            "chrome_profile_directory": (
                (settings.chrome_profile_directory or "Default").strip() or "Default"
            ),
            "debug_mode": settings.debug_mode,
            "browser_timeout_ms": settings.browser_timeout_ms,
            "open_folder_after_download": settings.open_folder_after_download,
            "setup_completed": settings.setup_completed,
            "enispace_base_url": settings.enispace_base_url,
            "marketplace_base_url": settings.marketplace_base_url,
            "imap_host": settings.imap_host or "pop.securemail.pro",
            "imap_port": settings.imap_port or 993,
            "imap_security": settings.imap_security or "SSL",
            "imap_username": settings.imap_username or "",
            "imap_folder": settings.imap_folder or "INBOX.MdA_Eni",
            "imap_unread_only": settings.imap_unread_only,
            "autosync_enabled": settings.autosync_enabled,
            "autosync_interval_minutes": max(
                1, int(settings.autosync_interval_minutes or 15)
            ),
            "smtp_host": settings.smtp_host or "authsmtp.securemail.pro",
            "smtp_port": settings.smtp_port or 465,
            "smtp_security": settings.smtp_security or "SSL",
            "outlook_folder": settings.outlook_folder or "Inbox/MdA_Eni",
            "outlook_unread_only": settings.outlook_unread_only,
            "jarvis_enabled": bool(settings.jarvis_enabled),
            "jarvis_interval_seconds": max(
                15, int(settings.jarvis_interval_seconds or 60)
            ),
            "jarvis_autostart": bool(settings.jarvis_autostart),
            "jarvis_max_retries": max(1, int(settings.jarvis_max_retries or 3)),
            "jarvis_printer": settings.jarvis_printer or "",
            "jarvis_download_folder": settings.jarvis_download_folder or "",
            "jarvis_keep_pdfs": bool(settings.jarvis_keep_pdfs),
            "jarvis_debug": bool(settings.jarvis_debug),
            "jarvis_simulation": bool(settings.jarvis_simulation),
            "jarvis_avatar_level": (
                (settings.jarvis_avatar_level or "full").strip().lower()
                or "full"
            ),
            "jarvis_avatar_model": (
                (settings.jarvis_avatar_model or "vision_avatar_v1").strip()
                or "vision_avatar_v1"
            ),
            "jarvis_avatar_mode": (
                (settings.jarvis_avatar_mode or "3d").strip().lower()
                or "3d"
            ),
            "extra": settings.extra,
        }
        for key, value in mapping.items():
            self.set_setting(key, value)
        logger.info("Impostazioni salvate.")

    # ------------------------------------------------------------------ module settings / state (Phase 1)
    def get_module_settings(self, module_id: str) -> Optional[dict]:
        """Return full ModuleSettings envelope or None. Not used by legacy operations."""
        mid = (module_id or "").strip().lower()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM module_settings WHERE module_id = ?",
                (mid,),
            ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row["payload"])
        except json.JSONDecodeError:
            logger.error("module_settings payload corrupt for %s", mid)
            return None
        return data if isinstance(data, dict) else None

    def list_module_settings(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT module_id, payload FROM module_settings ORDER BY module_id"
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            try:
                data = json.loads(row["payload"])
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                out.append(data)
        return out

    def upsert_module_settings(
        self,
        payload: dict,
        *,
        validate: bool = True,
        expected_module_id: Optional[str] = None,
    ) -> dict:
        """
        Persist a ModuleSettings envelope.

        ``payload`` is the authoritative full envelope JSON. Columns
        schema_version/enabled/version/capabilities are denormalized projections.
        """
        from app.modules.config.models import ModuleSettingsRecord
        from app.modules.config.validate import validate_module_settings

        if validate:
            envelope = validate_module_settings(
                payload, expected_module_id=expected_module_id
            )
        else:
            envelope = payload
            if expected_module_id:
                mid = str(envelope.get("module_id", "")).strip().lower()
                if mid != expected_module_id.strip().lower():
                    raise ValueError("module_id mismatch on upsert")

        mid = str(envelope["module_id"]).strip().lower()
        caps = list(envelope.get("capabilities") or [])
        record = ModuleSettingsRecord(
            module_id=mid,
            schema_version=int(envelope["schema_version"]),
            enabled=bool(envelope["enabled"]),
            version=str(envelope["version"]),
            capabilities=caps,
            payload=envelope,
        )
        ts = now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM module_settings WHERE module_id = ?",
                (mid,),
            ).fetchone()
            created = existing["created_at"] if existing else ts
            conn.execute(
                """
                INSERT INTO module_settings(
                    module_id, schema_version, enabled, version,
                    capabilities, payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(module_id) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    enabled = excluded.enabled,
                    version = excluded.version,
                    capabilities = excluded.capabilities,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    record.module_id,
                    record.schema_version,
                    1 if record.enabled else 0,
                    record.version,
                    record.capabilities_json(),
                    record.payload_json(),
                    created,
                    ts,
                ),
            )
        return envelope

    def get_module_state(self, module_id: str) -> Optional[dict]:
        mid = (module_id or "").strip().lower()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM module_state WHERE module_id = ?",
                (mid,),
            ).fetchone()
        if not row:
            return None
        try:
            metrics = json.loads(row["metrics"] or "{}")
        except json.JSONDecodeError:
            metrics = {}
        if not isinstance(metrics, dict):
            metrics = {}
        return {
            "module_id": row["module_id"],
            "status": row["status"],
            "health": row["health"],
            "last_error": row["last_error"],
            "last_activity_at": row["last_activity_at"],
            "last_sync_at": row["last_sync_at"],
            "metrics": metrics,
            "updated_at": row["updated_at"],
        }

    def list_module_state(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT module_id FROM module_state ORDER BY module_id"
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            st = self.get_module_state(row["module_id"])
            if st:
                out.append(st)
        return out

    def upsert_module_state(self, state: dict) -> dict:
        """Persist runtime ModuleState only (no settings fields)."""
        from app.modules.config.capabilities import (
            MODULE_STATE_HEALTH,
            MODULE_STATE_STATUS,
        )

        mid = str(state.get("module_id") or "").strip().lower()
        if not mid:
            raise ValueError("module_state.module_id required")
        status = str(state.get("status") or "OFFLINE").strip().upper()
        health = str(state.get("health") or "UNKNOWN").strip().upper()
        if status not in MODULE_STATE_STATUS:
            raise ValueError(f"invalid module_state.status: {status}")
        if health not in MODULE_STATE_HEALTH:
            raise ValueError(f"invalid module_state.health: {health}")
        metrics = state.get("metrics") or {}
        if not isinstance(metrics, dict):
            raise ValueError("module_state.metrics must be an object")
        # Reject accidental settings keys
        forbidden = {"capabilities", "common", "module_specific", "payload", "password"}
        if forbidden.intersection(state.keys()):
            raise ValueError("module_state must not contain settings fields")
        ts = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO module_state(
                    module_id, status, health, last_error,
                    last_activity_at, last_sync_at, metrics, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(module_id) DO UPDATE SET
                    status = excluded.status,
                    health = excluded.health,
                    last_error = excluded.last_error,
                    last_activity_at = excluded.last_activity_at,
                    last_sync_at = excluded.last_sync_at,
                    metrics = excluded.metrics,
                    updated_at = excluded.updated_at
                """,
                (
                    mid,
                    status,
                    health,
                    state.get("last_error"),
                    state.get("last_activity_at"),
                    state.get("last_sync_at"),
                    json.dumps(metrics, ensure_ascii=False),
                    ts,
                ),
            )
        out = self.get_module_state(mid)
        assert out is not None
        return out

    # ------------------------------------------------------------------ contracts
    @staticmethod
    def _row_to_contract(row: sqlite3.Row, *, last_checked: Optional[str] = None) -> Contract:
        keys = set(row.keys())
        return Contract(
            id=row["id"],
            contract_number=row["contract_number"],
            order_number=row["order_number"] if "order_number" in keys else None,
            framework_contract=(
                row["framework_contract"] if "framework_contract" in keys else None
            ),
            acquisition_module=(
                row["acquisition_module"] if "acquisition_module" in keys else None
            ),
            first_seen=row["first_seen"],
            last_checked=last_checked if last_checked is not None else row["last_checked"],
        )

    def upsert_contract(
        self,
        key: str,
        *,
        order_number: Optional[str] = None,
        framework_contract: Optional[str] = None,
        acquisition_module: Optional[str] = None,
    ) -> Contract:
        """
        Registra/aggiorna un riferimento.

        ``key`` = identificativo cartella/ricerca (di solito numero ordine).
        """
        number = key.strip()
        now = now_iso()
        order = (order_number or number).strip() or None
        framework = (framework_contract or "").strip() or None
        module = (acquisition_module or "").strip() or None

        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM contracts
                WHERE contract_number = ?
                   OR order_number = ?
                   OR (? IS NOT NULL AND framework_contract = ?)
                """,
                (number, number, framework, framework),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE contracts SET
                        last_checked = ?,
                        order_number = COALESCE(?, order_number),
                        framework_contract = COALESCE(?, framework_contract),
                        acquisition_module = COALESCE(?, acquisition_module)
                    WHERE id = ?
                    """,
                    (now, order, framework, module, row["id"]),
                )
                refreshed = conn.execute(
                    "SELECT * FROM contracts WHERE id = ?", (row["id"],)
                ).fetchone()
                return self._row_to_contract(refreshed, last_checked=now)

            cur = conn.execute(
                """
                INSERT INTO contracts(
                    contract_number, order_number, framework_contract,
                    acquisition_module, first_seen, last_checked
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (number, order, framework, module, now, now),
            )
            return Contract(
                id=cur.lastrowid,
                contract_number=number,
                order_number=order,
                framework_contract=framework,
                acquisition_module=module,
                first_seen=now,
                last_checked=now,
            )

    def get_contract(self, contract_number: str) -> Optional[Contract]:
        key = contract_number.strip()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM contracts
                WHERE contract_number = ? OR order_number = ? OR framework_contract = ?
                """,
                (key, key, key),
            ).fetchone()
        if not row:
            return None
        return self._row_to_contract(row)

    def list_contracts(self) -> list[Contract]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM contracts ORDER BY last_checked DESC"
            ).fetchall()
        return [self._row_to_contract(r) for r in rows]

    def contract_stats(self, contract_id: int) -> dict[str, int]:
        with self.connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM documents WHERE contract_id = ?",
                (contract_id,),
            ).fetchone()["c"]
            new = conn.execute(
                "SELECT COUNT(*) AS c FROM documents WHERE contract_id = ? AND status = ?",
                (contract_id, DocumentStatus.NEW),
            ).fetchone()["c"]
            downloaded = conn.execute(
                "SELECT COUNT(*) AS c FROM documents WHERE contract_id = ? AND status = ?",
                (contract_id, DocumentStatus.DOWNLOADED),
            ).fetchone()["c"]
        return {"total": total, "new": new, "downloaded": downloaded}

    # ------------------------------------------------------------------ documents
    def list_documents(self, contract_id: int) -> list[Document]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE contract_id = ? ORDER BY filename",
                (contract_id,),
            ).fetchall()
        return [self._row_to_document(r) for r in rows]

    def find_document(
        self,
        contract_id: int,
        *,
        remote_id: Optional[str] = None,
        filename: Optional[str] = None,
        sha256: Optional[str] = None,
    ) -> Optional[Document]:
        with self.connect() as conn:
            if remote_id:
                row = conn.execute(
                    "SELECT * FROM documents WHERE contract_id = ? AND remote_id = ?",
                    (contract_id, remote_id),
                ).fetchone()
                if row:
                    return self._row_to_document(row)
            if sha256:
                row = conn.execute(
                    "SELECT * FROM documents WHERE contract_id = ? AND sha256 = ?",
                    (contract_id, sha256),
                ).fetchone()
                if row:
                    return self._row_to_document(row)
            if filename:
                row = conn.execute(
                    "SELECT * FROM documents WHERE contract_id = ? AND filename = ?",
                    (contract_id, filename),
                ).fetchone()
                if row:
                    return self._row_to_document(row)
        return None

    def upsert_document(self, doc: Document) -> Document:
        existing = None
        if doc.remote_id:
            existing = self.find_document(doc.contract_id, remote_id=doc.remote_id)
        if not existing and doc.sha256:
            existing = self.find_document(doc.contract_id, sha256=doc.sha256)
        if not existing and doc.filename:
            existing = self.find_document(doc.contract_id, filename=doc.filename)

        with self.connect() as conn:
            if existing:
                conn.execute(
                    """
                    UPDATE documents SET
                        remote_id = COALESCE(?, remote_id),
                        filename = ?,
                        doc_type = COALESCE(?, doc_type),
                        remote_date = COALESCE(?, remote_date),
                        size = COALESCE(?, size),
                        local_path = COALESCE(?, local_path),
                        sha256 = COALESCE(?, sha256),
                        downloaded_at = COALESCE(?, downloaded_at),
                        status = ?
                    WHERE id = ?
                    """,
                    (
                        doc.remote_id,
                        doc.filename,
                        doc.doc_type,
                        doc.remote_date,
                        doc.size,
                        doc.local_path,
                        doc.sha256,
                        doc.downloaded_at,
                        doc.status,
                        existing.id,
                    ),
                )
                doc.id = existing.id
            else:
                cur = conn.execute(
                    """
                    INSERT INTO documents(
                        contract_id, remote_id, filename, doc_type, remote_date,
                        size, local_path, sha256, downloaded_at, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc.contract_id,
                        doc.remote_id,
                        doc.filename,
                        doc.doc_type,
                        doc.remote_date,
                        doc.size,
                        doc.local_path,
                        doc.sha256,
                        doc.downloaded_at,
                        doc.status,
                    ),
                )
                doc.id = cur.lastrowid
        return doc

    def mark_documents_status(
        self, contract_id: int, from_status: str, to_status: str
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE documents SET status = ? WHERE contract_id = ? AND status = ?",
                (to_status, contract_id, from_status),
            )

    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> Document:
        return Document(
            id=row["id"],
            contract_id=row["contract_id"],
            remote_id=row["remote_id"],
            filename=row["filename"],
            doc_type=row["doc_type"],
            remote_date=row["remote_date"],
            size=row["size"],
            local_path=row["local_path"],
            sha256=row["sha256"],
            downloaded_at=row["downloaded_at"],
            status=row["status"],
        )

    # ------------------------------------------------------------------ operations
    def log_operation(
        self,
        operation: str,
        result: str = OperationResult.INFO,
        message: str = "",
        contract_number: Optional[str] = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO operations(timestamp, contract_number, operation, result, message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (now_iso(), contract_number, operation, result, message),
            )

    def recent_operations(self, limit: int = 100) -> list[Operation]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM operations ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            Operation(
                id=r["id"],
                timestamp=r["timestamp"],
                contract_number=r["contract_number"],
                operation=r["operation"],
                result=r["result"],
                message=r["message"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ print queue
    def add_print_queue_item(
        self,
        *,
        local_path: str,
        order_number: str = "",
        acquisition_module: str = "",
        eml_name: str = "",
        filename: str = "",
    ) -> PrintQueueItem:
        # Evita duplicati sullo stesso path ancora pending
        with self.connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM print_queue
                WHERE local_path = ? AND status = 'pending'
                LIMIT 1
                """,
                (local_path,),
            ).fetchone()
            if existing:
                return self._row_to_print_item(existing)

            name = filename or Path(local_path).name
            cur = conn.execute(
                """
                INSERT INTO print_queue(
                    local_path, order_number, acquisition_module,
                    eml_name, filename, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    local_path,
                    order_number,
                    acquisition_module,
                    eml_name,
                    name,
                    now_iso(),
                ),
            )
            item_id = int(cur.lastrowid)
        return PrintQueueItem(
            id=item_id,
            local_path=local_path,
            order_number=order_number,
            acquisition_module=acquisition_module,
            eml_name=eml_name,
            filename=name,
            created_at=now_iso(),
            status="pending",
        )

    def list_print_queue(
        self, *, pending_only: bool = False
    ) -> list[PrintQueueItem]:
        with self.connect() as conn:
            if pending_only:
                rows = conn.execute(
                    """
                    SELECT * FROM print_queue
                    WHERE status = 'pending'
                    ORDER BY id ASC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM print_queue ORDER BY id ASC"
                ).fetchall()
        return [self._row_to_print_item(r) for r in rows]

    def remove_print_queue_item(self, item_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM print_queue WHERE id = ?", (item_id,))

    def clear_print_queue(self, *, pending_only: bool = False) -> int:
        with self.connect() as conn:
            if pending_only:
                cur = conn.execute(
                    "DELETE FROM print_queue WHERE status = 'pending'"
                )
            else:
                cur = conn.execute("DELETE FROM print_queue")
            return int(cur.rowcount or 0)

    def mark_print_queue_printed(
        self, item_id: int, *, status: str = "printed", error: str = ""
    ) -> None:
        with self.connect() as conn:
            if status == "error" and error:
                conn.execute(
                    """
                    UPDATE print_queue
                    SET status = ?, printed_at = ?, filename = COALESCE(filename, '')
                    WHERE id = ?
                    """,
                    (status, now_iso(), item_id),
                )
                # keep message in operations log instead of altering schema
            else:
                conn.execute(
                    """
                    UPDATE print_queue
                    SET status = ?, printed_at = ?
                    WHERE id = ?
                    """,
                    (status, now_iso(), item_id),
                )

    @staticmethod
    def _row_to_print_item(row: sqlite3.Row) -> PrintQueueItem:
        return PrintQueueItem(
            id=row["id"],
            local_path=row["local_path"] or "",
            order_number=row["order_number"] or "",
            acquisition_module=row["acquisition_module"] or "",
            eml_name=row["eml_name"] or "",
            filename=row["filename"] or "",
            created_at=row["created_at"],
            printed_at=row["printed_at"],
            status=row["status"] or "pending",
        )

    # ------------------------------------------------------------------ outlook processed (legacy)
    def is_outlook_processed(self, entry_id: str) -> bool:
        """True solo se elaborata con successo (errori restano ritentabili)."""
        if not entry_id:
            return False
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM outlook_processed
                WHERE entry_id = ? AND lower(coalesce(result, '')) = 'success'
                LIMIT 1
                """,
                (entry_id,),
            ).fetchone()
        return row is not None

    def mark_outlook_processed(
        self,
        entry_id: str,
        *,
        subject: str = "",
        order_number: str = "",
        acquisition_module: str = "",
        result: str = "success",
        message: str = "",
    ) -> None:
        if not entry_id:
            return
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO outlook_processed(
                    entry_id, subject, order_number, acquisition_module,
                    processed_at, result, message
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO UPDATE SET
                    processed_at = excluded.processed_at,
                    result = excluded.result,
                    message = excluded.message
                """,
                (
                    entry_id,
                    subject,
                    order_number,
                    acquisition_module,
                    now_iso(),
                    result,
                    message,
                ),
            )

    # ------------------------------------------------------------------ imap processed
    def is_imap_processed(self, entry_id: str) -> bool:
        """True solo se la mail è già stata gestita con successo.

        Gli errori non bloccano i retry (non vengono più registrati qui,
        e le righe storiche con result != success vengono ignorate).
        """
        if not entry_id:
            return False
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM imap_processed
                WHERE entry_id = ? AND lower(coalesce(result, '')) = 'success'
                LIMIT 1
                """,
                (entry_id,),
            ).fetchone()
        return row is not None

    def clear_imap_processed_errors(self, *, on_date: str = "") -> int:
        """Rimuove skip permanenti da errori (opz. solo processed_at del giorno)."""
        with self.connect() as conn:
            if on_date:
                cur = conn.execute(
                    """
                    DELETE FROM imap_processed
                    WHERE lower(coalesce(result, '')) != 'success'
                      AND substr(processed_at, 1, 10) = ?
                    """,
                    (on_date,),
                )
            else:
                cur = conn.execute(
                    """
                    DELETE FROM imap_processed
                    WHERE lower(coalesce(result, '')) != 'success'
                    """
                )
            return int(cur.rowcount or 0)

    def mark_imap_processed(
        self,
        entry_id: str,
        *,
        folder: str = "",
        uid: str = "",
        subject: str = "",
        order_number: str = "",
        acquisition_module: str = "",
        result: str = "success",
        message: str = "",
    ) -> None:
        if not entry_id:
            return
        folder_v = folder
        uid_v = uid
        if (not folder_v or not uid_v) and ":" in entry_id:
            folder_v, uid_v = entry_id.rsplit(":", 1)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO imap_processed(
                    entry_id, folder, uid, subject, order_number,
                    acquisition_module, processed_at, result, message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO UPDATE SET
                    processed_at = excluded.processed_at,
                    result = excluded.result,
                    message = excluded.message
                """,
                (
                    entry_id,
                    folder_v,
                    uid_v,
                    subject,
                    order_number,
                    acquisition_module,
                    now_iso(),
                    result,
                    message,
                ),
            )

    def list_imap_processed(self, *, limit: int = 200) -> list[dict]:
        """Elenco cronologico mail IMAP già gestite (più recenti prima)."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT entry_id, folder, uid, subject, order_number,
                       acquisition_module, processed_at, result, message
                FROM imap_processed
                ORDER BY processed_at DESC, rowid DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ mail register
    def add_mail_register(
        self,
        *,
        entry_id: str = "",
        folder: str = "",
        uid: str = "",
        subject: str = "",
        order_number: str = "",
        acquisition_module: str = "",
        status: str = "success",
        note: str = "",
    ) -> MailRegisterEntry:
        """Aggiunge una voce al registro cronologico mail gestite."""
        ts = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO mail_register(
                    entry_id, folder, uid, subject, order_number,
                    acquisition_module, status, note, processed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id or "",
                    folder or "",
                    uid or "",
                    subject or "",
                    order_number or "",
                    acquisition_module or "",
                    status or "info",
                    note or "",
                    ts,
                ),
            )
            rid = int(cur.lastrowid)
        return MailRegisterEntry(
            id=rid,
            entry_id=entry_id or "",
            folder=folder or "",
            uid=uid or "",
            subject=subject or "",
            order_number=order_number or "",
            acquisition_module=acquisition_module or "",
            status=status or "info",
            note=note or "",
            processed_at=ts,
        )

    def list_mail_register(self, *, limit: int = 300) -> list[MailRegisterEntry]:
        """Registro cronologico (più recenti prima)."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, entry_id, folder, uid, subject, order_number,
                       acquisition_module, status, note, processed_at
                FROM mail_register
                ORDER BY processed_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        return [
            MailRegisterEntry(
                id=r["id"],
                entry_id=r["entry_id"] or "",
                folder=r["folder"] or "",
                uid=r["uid"] or "",
                subject=r["subject"] or "",
                order_number=r["order_number"] or "",
                acquisition_module=r["acquisition_module"] or "",
                status=r["status"] or "",
                note=r["note"] or "",
                processed_at=r["processed_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ JARVIS jobs
    def _row_to_jarvis_job(self, row: sqlite3.Row) -> "JarvisJob":
        from services.jarvis.models import JarvisJob

        return JarvisJob(
            id=row["id"],
            mail_id=row["mail_id"] or "",
            mail_uid=row["mail_uid"] or "",
            mail_folder=row["mail_folder"] or "",
            message_id=row["message_id"] or "",
            subject=row["subject"] or "",
            sender=row["sender"] or "",
            received_at=row["received_at"] or "",
            order_number=row["order_number"] or "",
            contract_number=row["contract_number"] or "",
            acquisition_module=row["acquisition_module"] or "",
            status=row["status"] or "",
            outcome=row["outcome"] or "",
            state=row["state"] or "",
            docs_found=int(row["docs_found"] or 0),
            docs_downloaded=int(row["docs_downloaded"] or 0),
            docs_printed=int(row["docs_printed"] or 0),
            printer_name=row["printer_name"] or "",
            pdf_paths=JarvisJob.parse_pdf_paths(row["pdf_paths"]),
            attempts=int(row["attempts"] or 0),
            max_attempts=int(row["max_attempts"] or 3),
            error_message=row["error_message"] or "",
            simulation=bool(int(row["simulation"] or 0)),
            created_at=row["created_at"] or "",
            started_at=row["started_at"] or "",
            finished_at=row["finished_at"] or "",
            last_event_at=row["last_event_at"] or "",
        )

    def create_jarvis_job(self, job: "JarvisJob") -> "JarvisJob":
        ts = job.created_at or now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO jarvis_jobs(
                    mail_id, mail_uid, mail_folder, message_id, subject, sender,
                    received_at, order_number, contract_number, acquisition_module,
                    status, outcome, state, docs_found, docs_downloaded, docs_printed,
                    printer_name, pdf_paths, attempts, max_attempts, error_message,
                    simulation, created_at, started_at, finished_at, last_event_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.mail_id,
                    job.mail_uid,
                    job.mail_folder,
                    job.message_id,
                    job.subject,
                    job.sender,
                    job.received_at,
                    job.order_number,
                    job.contract_number,
                    job.acquisition_module,
                    job.status,
                    job.outcome,
                    job.state,
                    job.docs_found,
                    job.docs_downloaded,
                    job.docs_printed,
                    job.printer_name,
                    job.pdf_paths_json,
                    job.attempts,
                    job.max_attempts,
                    job.error_message,
                    1 if job.simulation else 0,
                    ts,
                    job.started_at or "",
                    job.finished_at or "",
                    job.last_event_at or ts,
                ),
            )
            job.id = int(cur.lastrowid)
            job.created_at = ts
        return job

    def update_jarvis_job(self, job: "JarvisJob") -> "JarvisJob":
        if not job.id:
            raise ValueError("job.id obbligatorio per update")
        job.last_event_at = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jarvis_jobs SET
                    mail_uid = ?, mail_folder = ?, message_id = ?,
                    subject = ?, sender = ?, received_at = ?,
                    order_number = ?, contract_number = ?, acquisition_module = ?,
                    status = ?, outcome = ?, state = ?,
                    docs_found = ?, docs_downloaded = ?, docs_printed = ?,
                    printer_name = ?, pdf_paths = ?, attempts = ?, max_attempts = ?,
                    error_message = ?, simulation = ?,
                    started_at = ?, finished_at = ?, last_event_at = ?
                WHERE id = ?
                """,
                (
                    job.mail_uid,
                    job.mail_folder,
                    job.message_id,
                    job.subject,
                    job.sender,
                    job.received_at,
                    job.order_number,
                    job.contract_number,
                    job.acquisition_module,
                    job.status,
                    job.outcome,
                    job.state,
                    job.docs_found,
                    job.docs_downloaded,
                    job.docs_printed,
                    job.printer_name,
                    job.pdf_paths_json,
                    job.attempts,
                    job.max_attempts,
                    job.error_message,
                    1 if job.simulation else 0,
                    job.started_at or "",
                    job.finished_at or "",
                    job.last_event_at,
                    job.id,
                ),
            )
        return job

    def get_jarvis_job(self, job_id: int) -> Optional["JarvisJob"]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM jarvis_jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return self._row_to_jarvis_job(row) if row else None

    def get_jarvis_job_by_mail_id(self, mail_id: str) -> Optional["JarvisJob"]:
        if not mail_id:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM jarvis_jobs WHERE mail_id = ?", (mail_id,)
            ).fetchone()
        return self._row_to_jarvis_job(row) if row else None

    def list_jarvis_jobs(self, *, limit: int = 200) -> list["JarvisJob"]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jarvis_jobs
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        return [self._row_to_jarvis_job(r) for r in rows]

    def list_jarvis_jobs_by_status(self, status: str) -> list["JarvisJob"]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jarvis_jobs
                WHERE status = ?
                ORDER BY id ASC
                """,
                (status,),
            ).fetchall()
        return [self._row_to_jarvis_job(r) for r in rows]

    def count_jarvis_jobs_by_status(self, status: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM jarvis_jobs WHERE status = ?",
                (status,),
            ).fetchone()
        return int(row["c"] if row else 0)

    def add_jarvis_job_event(
        self,
        *,
        job_id: int,
        message: str,
        level: str = "INFO",
        state: str = "",
    ) -> "JarvisJobEvent":
        from services.jarvis.models import JarvisJobEvent

        ts = now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO jarvis_job_events(job_id, timestamp, level, message, state)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, ts, level, message, state),
            )
            eid = int(cur.lastrowid)
        return JarvisJobEvent(
            id=eid,
            job_id=job_id,
            timestamp=ts,
            level=level,
            message=message,
            state=state,
        )

    def list_jarvis_job_events(self, job_id: int) -> list["JarvisJobEvent"]:
        from services.jarvis.models import JarvisJobEvent

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM jarvis_job_events
                WHERE job_id = ?
                ORDER BY id ASC
                """,
                (job_id,),
            ).fetchall()
        return [
            JarvisJobEvent(
                id=r["id"],
                job_id=r["job_id"],
                timestamp=r["timestamp"] or "",
                level=r["level"] or "INFO",
                message=r["message"] or "",
                state=r["state"] or "",
            )
            for r in rows
        ]
