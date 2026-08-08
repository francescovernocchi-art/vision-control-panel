"""Smoke test IMAP wiring (senza rete)."""

from database.db import Database
from services.imap_mail_service import (
    DEFAULT_FOLDER,
    ImapConfig,
    normalize_folder_candidates,
)

s = Database().get_settings()
print("imap_host =", s.imap_host)
print("imap_folder =", s.imap_folder)
print("imap_unread =", s.imap_unread_only)
print("smtp_host =", s.smtp_host)
print("candidates =", normalize_folder_candidates(s.imap_folder or DEFAULT_FOLDER))

cfg = ImapConfig(
    host=s.imap_host,
    port=s.imap_port,
    security=s.imap_security,
    folder=s.imap_folder,
)
print("config_ok =", bool(cfg.host and cfg.folder))

with Database().connect() as conn:
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
print("has imap_processed =", "imap_processed" in tables)
print("SMOKE_OK")
