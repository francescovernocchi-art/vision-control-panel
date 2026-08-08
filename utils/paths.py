"""Percorsi applicativi centralizzati."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "VIS eniSpace Utility"
APP_SHORT_NAME = "VIS-eniSpace-Utility"
DOWNLOAD_FOLDER_NAME = "VIS eniSpace"
KEYRING_SERVICE = "VIS-eniSpace-Utility"
# Credenziali casella IMAP/SMTP (separate dal login eniSpace)
KEYRING_MAIL_SERVICE = "VIS-eniSpace-Utility-Mail"
ENISPACE_HOME_URL = "https://enispace.eni.com/it_IT/home.page"
ENISPACE_MYHOME_URL = "https://enispace.eni.com/it_IT/private/myhome.page"
# Elenco ordini/consuntivi (verificato in REGISTRA NAVIGAZIONE) — percorso STABILE
ENISPACE_ORDINI_URL = (
    "https://enispace.eni.com/it_IT/private/gare_e_contratti/"
    "i_miei_contratti/i_miei_ordini_e_consuntivi/i_miei_ordini_e_consuntivi.page"
)
import re
from urllib.parse import urlparse

# Host Marketplace osservato (può essere ridistribuito da Eni; non usare come unica via)
ENISPACE_MARKETPLACE_HOST = (
    "68cf6643-b34c-44da-84b6-e015090c680a.abap-web.eu10.hana.ondemand.com"
)
ENISPACE_MARKETPLACE_URL = (
    f"https://{ENISPACE_MARKETPLACE_HOST}"
    "/ui#Launchpad-openFLPPage?pageId=Z_PG_MARKETPLACE&spaceId=Z_SP_MARKETPLACE"
)
# Dashboard filtri documenti Marketplace (passo dopo il Launchpad)
ENISPACE_MARKETPLACE_DASHBOARD_HASH = "ZMP_DSH-DISPLAY&/"
ENISPACE_MARKETPLACE_DASHBOARD_URL = (
    f"https://{ENISPACE_MARKETPLACE_HOST}/ui#{ENISPACE_MARKETPLACE_DASHBOARD_HASH}"
)
# Pattern host dinamici BTP/ABAP (UUID + abap-web)
ENISPACE_MARKETPLACE_HOST_SUFFIX = ".abap-web.eu10.hana.ondemand.com"
_MARKETPLACE_HOST_RE = re.compile(
    r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"
    r"\.abap-web\.eu10\.hana\.ondemand\.com$",
    re.IGNORECASE,
)


def is_valid_marketplace_host(host: str) -> bool:
    """Accetta solo host Marketplace reali (UUID), rifiuta test/finti tipo new-id."""
    h = (host or "").lower().strip()
    if not h:
        return False
    return bool(_MARKETPLACE_HOST_RE.match(h))


def marketplace_dashboard_url_from(any_marketplace_url: str) -> str:
    """Deriva #ZMP_DSH-DISPLAY&/ dall'origine host Marketplace corrente."""
    parsed = urlparse(any_marketplace_url)
    if not parsed.scheme or not parsed.netloc:
        return ENISPACE_MARKETPLACE_DASHBOARD_URL
    if not is_valid_marketplace_host(parsed.netloc):
        return ENISPACE_MARKETPLACE_DASHBOARD_URL
    return f"{parsed.scheme}://{parsed.netloc}/ui#{ENISPACE_MARKETPLACE_DASHBOARD_HASH}"


def project_root() -> Path:
    """Radice del progetto (cartella che contiene app.py) oppure cartella dell'EXE."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """File di risorsa (assets, ecc.): PyInstaller _MEIPASS o radice progetto."""
    rel = Path(*parts)
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundled = Path(meipass) / rel
            if bundled.exists():
                return bundled
        beside = Path(sys.executable).resolve().parent / rel
        if beside.exists():
            return beside
    return project_root() / rel


def assets_dir() -> Path:
    return resource_path("assets")


def brand_logo_png() -> Path:
    return resource_path("assets", "vis_jarvis_logo.png")


def brand_logo_ico() -> Path:
    return resource_path("assets", "vis_jarvis_logo.ico")


def data_dir() -> Path:
    path = project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = project_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "enispace.db"


def browser_profile_dir() -> Path:
    path = data_dir() / "browser-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_download_dir() -> Path:
    """Cartella download predefinita: Documenti\\VIS eniSpace\\"""
    documents = Path.home() / "Documents"
    if not documents.is_dir():
        # Fallback tipico su Windows localizzato
        documents = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents"
    path = documents / DOWNLOAD_FOLDER_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def contract_download_dir(base: Path | str, contract_number: str) -> Path:
    """Cartella dedicata a un singolo contratto / ordine (legacy)."""
    safe = "".join(c for c in contract_number.strip() if c.isalnum() or c in "-_")
    if not safe:
        raise ValueError("Numero contratto non valido per il percorso file.")
    path = Path(base) / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def mda_day_folder_name(acquisition_module: str, day: str | None = None) -> str:
    """Nome cartella download: MdA_{modulo}_{YYYY-MM-DD}."""
    from datetime import date as date_cls

    safe_mda = "".join(
        c for c in (acquisition_module or "").strip() if c.isalnum() or c in "-_"
    )
    if not safe_mda:
        raise ValueError("Modulo di Acquisizione non valido per il percorso file.")
    day_s = (day or "").strip()
    if not day_s:
        day_s = date_cls.today().isoformat()
    else:
        # Accetta già YYYY-MM-DD oppure normalizza prefisso data
        day_s = day_s[:10]
        if len(day_s) == 10 and day_s[4] == "-" and day_s[7] == "-":
            pass
        else:
            day_s = "".join(c for c in day_s if c.isalnum() or c in "-_") or (
                date_cls.today().isoformat()
            )
    return f"MdA_{safe_mda}_{day_s}"


def mda_day_download_dir(
    base: Path | str,
    acquisition_module: str,
    day: str | None = None,
) -> Path:
    """Cartella download per MdA del giorno sotto la root configurata."""
    path = Path(base) / mda_day_folder_name(acquisition_module, day)
    path.mkdir(parents=True, exist_ok=True)
    return path
