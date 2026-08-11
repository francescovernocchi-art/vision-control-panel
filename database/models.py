"""Modelli e costanti del database locale."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Optional


class DocumentStatus(StrEnum):
    AVAILABLE = "available"
    DOWNLOADED = "downloaded"
    NEW = "new"
    FAILED = "failed"
    SKIPPED = "skipped"


class OperationResult(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Contract:
    id: Optional[int] = None
    # Chiave applicativa / cartella download (di solito = numero ordine)
    contract_number: str = ""
    order_number: Optional[str] = None  # es. 4310758365
    framework_contract: Optional[str] = None  # contratto quadro es. 2500036209
    acquisition_module: Optional[str] = None  # modulo acquisizione es. 2013627410
    first_seen: Optional[str] = None
    last_checked: Optional[str] = None


@dataclass
class Document:
    id: Optional[int] = None
    contract_id: int = 0
    remote_id: Optional[str] = None
    filename: str = ""
    doc_type: Optional[str] = None
    remote_date: Optional[str] = None
    size: Optional[int] = None
    local_path: Optional[str] = None
    sha256: Optional[str] = None
    downloaded_at: Optional[str] = None
    status: str = DocumentStatus.AVAILABLE


@dataclass
class Operation:
    id: Optional[int] = None
    timestamp: Optional[str] = None
    contract_number: Optional[str] = None
    operation: str = ""
    result: str = OperationResult.INFO
    message: str = ""


@dataclass
class PrintQueueItem:
    """Elemento in coda di stampa (PDF scaricato da batch mail)."""

    id: Optional[int] = None
    local_path: str = ""
    order_number: str = ""
    acquisition_module: str = ""
    eml_name: str = ""
    filename: str = ""
    created_at: Optional[str] = None
    printed_at: Optional[str] = None
    status: str = "pending"  # pending | printed | error


@dataclass
class AppSettings:
    """Impostazioni non sensibili (la password è solo in keyring)."""

    username: str = ""
    download_folder: str = ""
    browser_visible: bool = False  # legacy: inverso di browser_hidden
    browser_hidden: bool = True  # default ON: Chrome headed ma nascosto
    # Chrome di sistema + profilo Default (credenziali già salvate nel browser)
    chrome_use_system_profile: bool = True
    chrome_profile_directory: str = "Default"
    debug_mode: bool = False
    browser_timeout_ms: int = 60000
    open_folder_after_download: bool = False
    setup_completed: bool = False
    enispace_base_url: str = "https://enispace.eni.com/it_IT/home.page"
    # Ultimo host Marketplace osservato (può cambiare; aggiornato dalla navigazione)
    marketplace_base_url: str = ""
    # Casella IMAP (SecureMail) — cartella dedicata MdA
    imap_host: str = "pop.securemail.pro"
    imap_port: int = 993
    imap_security: str = "SSL"  # SSL | STARTTLS | NONE
    imap_username: str = ""
    imap_folder: str = "INBOX.MdA_Eni"
    imap_unread_only: bool = True
    # Autosync casella IMAP (polling periodico in background)
    autosync_enabled: bool = False
    autosync_interval_minutes: int = 15
    smtp_host: str = "authsmtp.securemail.pro"
    smtp_port: int = 465
    smtp_security: str = "SSL"  # SSL | STARTTLS | NONE
    # Legacy Outlook (non usato — preferire IMAP)
    outlook_folder: str = "Inbox/MdA_Eni"
    outlook_unread_only: bool = True
    # JARVIS — modalità supervisore
    jarvis_enabled: bool = False
    jarvis_interval_seconds: int = 60
    jarvis_autostart: bool = False
    jarvis_max_retries: int = 3
    jarvis_printer: str = ""
    jarvis_download_folder: str = ""
    jarvis_keep_pdfs: bool = True
    jarvis_debug: bool = False
    jarvis_simulation: bool = False
    # UI only: animazioni avatar (full | reduced | off)
    jarvis_avatar_level: str = "full"
    # UI only: selected avatar GLB stem under assets/avatar/models/
    jarvis_avatar_model: str = "vision_avatar_v1"
    # UI only: avatar presentation mode (3d | png)
    jarvis_avatar_mode: str = "3d"
    extra: dict = field(default_factory=dict)


@dataclass
class MailRegisterEntry:
    """Voce del registro cronologico mail gestite (IMAP / batch)."""

    id: Optional[int] = None
    entry_id: str = ""
    folder: str = ""
    uid: str = ""
    subject: str = ""
    order_number: str = ""
    acquisition_module: str = ""
    status: str = ""  # success | error | skipped | info
    note: str = ""
    processed_at: Optional[str] = None


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
