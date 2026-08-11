"""Percorsi e branding applicativi centralizzati — VIS•ION."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Product branding (VIS•ION) — assistant name kept separate for gradual rename
# ---------------------------------------------------------------------------
PRODUCT_NAME = "VIS•ION"
PRODUCT_FULL_NAME = "Intelligent Operations Network"
PRODUCT_DESCRIPTION = "Controllo • Sicurezza • Affidabilità"
PRODUCT_TAGLINE_IT = "CONTROLLO • SICUREZZA • AFFIDABILITÀ"
ASSISTANT_TAGLINE = "IL TUO ASSISTENTE OPERATIVO"
ASSISTANT_NAME = "JARVIS"  # futuro: VISION Assistant / VIS•ION Supervisor
ASSISTANT_TECHNICAL_NAME = "JARVIS"

# Compatibility aliases used across legacy UI / services
APP_NAME = PRODUCT_NAME
APP_SHORT_NAME = "VIS-ION"
APP_LEGACY_NAME = "VIS eniSpace Utility"
APP_SUBTITLE = PRODUCT_FULL_NAME

DOWNLOAD_FOLDER_NAME = "VIS-ION"

# Keyring: product-specific + legacy fallback for verification without re-entry
KEYRING_SERVICE = "VIS-ION"
KEYRING_SERVICE_LEGACY = "VIS-eniSpace-Utility"
KEYRING_MAIL_SERVICE = "VIS-ION-Mail"
KEYRING_MAIL_SERVICE_LEGACY = "VIS-eniSpace-Utility-Mail"

ENISPACE_HOME_URL = "https://enispace.eni.com/it_IT/home.page"
# Ingresso SSO (preferito Chrome / barra preferiti utente)
ENISPACE_PROXY_LOGIN_URL = (
    "https://enispace.eni.com/it_IT/private/proxyLogin.page"
)
ENISPACE_MYHOME_URL = "https://enispace.eni.com/it_IT/private/myhome.page"
# All'avvio / login: come VIS eniSpace Utility (home pubblica → SSO)
ENISPACE_STARTUP_URL = ENISPACE_HOME_URL
# PWA / Chrome App installata nel profilo Default (scorciatoia chrome_proxy)
CHROME_ENISPACE_APP_ID = "letterifpgkdakfajbgbohcmfmopheedhe"
ENISPACE_ORDINI_URL = (
    "https://enispace.eni.com/it_IT/private/gare_e_contratti/"
    "i_miei_contratti/i_miei_ordini_e_consuntivi/i_miei_ordini_e_consuntivi.page"
)
ENISPACE_MARKETPLACE_HOST = (
    "68cf6643-b34c-44da-84b6-e015090c680a.abap-web.eu10.hana.ondemand.com"
)
ENISPACE_MARKETPLACE_URL = (
    f"https://{ENISPACE_MARKETPLACE_HOST}"
    "/ui#Launchpad-openFLPPage?pageId=Z_PG_MARKETPLACE&spaceId=Z_SP_MARKETPLACE"
)
ENISPACE_MARKETPLACE_DASHBOARD_HASH = "ZMP_DSH-DISPLAY&/"
ENISPACE_MARKETPLACE_DASHBOARD_URL = (
    f"https://{ENISPACE_MARKETPLACE_HOST}/ui#{ENISPACE_MARKETPLACE_DASHBOARD_HASH}"
)
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
    """Logo aquila VISION — PNG ufficiale trasparente (contenuto opaco)."""
    official = resource_path("assets", "brand", "vision_icon_official.png")
    if official.is_file():
        return official
    brand = resource_path("assets", "brand", "vision_icon.png")
    if brand.is_file():
        return brand
    primary = resource_path("assets", "vision_logo.png")
    if primary.is_file():
        return primary
    eagle = resource_path("assets", "reference", "vision_eagle_logo.png")
    if eagle.is_file():
        return eagle
    return resource_path("assets", "vis_jarvis_logo.png")


def brand_logo_svg() -> Path:
    return resource_path("assets", "brand", "vision_icon.svg")


def brand_logo_ico() -> Path:
    brand = resource_path("assets", "brand", "vision_icon.ico")
    if brand.is_file():
        return brand
    primary = resource_path("assets", "vision_logo.ico")
    if primary.is_file():
        return primary
    return resource_path("assets", "vis_jarvis_logo.ico")


def brand_title_lockup_png() -> Path:
    """Titolo VIS•ION ufficiale (metallo) con sfondo trasparente."""
    official = resource_path("assets", "brand", "vision_title_official.png")
    if official.is_file():
        return official
    # Originale di riferimento (prima del SVG semplificato)
    ref = resource_path("assets", "reference", "vision_title_lockup.png")
    if ref.is_file():
        return ref
    brand = resource_path("assets", "brand", "vision_title_raster.png")
    if brand.is_file():
        return brand
    return ref


def brand_title_lockup_svg() -> Path:
    """SVG titolo (opzionale); in UI preferiamo PNG ufficiale metallico."""
    return resource_path("assets", "brand", "vision_title.svg")


def brand_lockup_png() -> Path:
    """Aquila + titolo — PNG ufficiale trasparente."""
    official = resource_path("assets", "brand", "vision_lockup_official.png")
    if official.is_file():
        return official
    brand = resource_path("assets", "brand", "vision_lockup.png")
    if brand.is_file():
        return brand
    return resource_path("assets", "reference", "vision_brand_lockup.png")


def brand_lockup_svg() -> Path:
    return resource_path("assets", "brand", "vision_lockup.svg")


def vision_brand_hero_png() -> Path:
    return resource_path("assets", "reference", "vision_brand_hero.png")


def vision_avatar_profile_png() -> Path:
    """Default bust for VisionAvatar — android profilo brand hero."""
    primary = resource_path("assets", "avatar", "vision_avatar_profile_opaque.png")
    if primary.is_file():
        return primary
    return resource_path("assets", "avatar", "vision_avatar_profile.png")


def vision_avatar_bible_dir() -> Path:
    """Directory of official Character Bible state frames (same android)."""
    return resource_path("assets", "avatar", "bible")


def vision_avatar_model_glb() -> Path:
    """Canonical optimized GLB (Meshy cleanup). Fallback legacy name."""
    v1 = resource_path("assets", "avatar", "models", "vision_avatar_v1.glb")
    if v1.is_file():
        return v1
    return resource_path("assets", "avatar", "models", "vision.glb")


def vision_avatar_models_dir() -> Path:
    """Directory of selectable avatar GLB files (non-recursive)."""
    return resource_path("assets", "avatar", "models")


def vision_avatar_glb_frames_dir() -> Path:
    """Pre-rendered yaw/state frames from the hero GLB (UI turntable)."""
    return resource_path("assets", "avatar", "glb_frames")


def vision_avatar_model_frames_dir(model_id: str) -> Path:
    """Per-model preview/clip frames for non-Meshy avatar packs."""
    mid = (model_id or "vision_avatar_v1").strip() or "vision_avatar_v1"
    return resource_path("assets", "avatar", "model_frames", mid)


def vision_istituto_logo_backdrop_png() -> Path:
    """Circular VIS / Istituto di Vigilanza emblem for avatar cinematic backdrop."""
    return resource_path("assets", "brand", "vision_istituto_logo_backdrop.png")


def vision_character_bible_png() -> Path:
    """Canonical Character Bible / brand android — single source of truth."""
    hero = resource_path("assets", "reference", "vision_android_profile_hero.png")
    if hero.is_file():
        return hero
    primary = resource_path("assets", "reference", "vision_character_bible.png")
    if primary.is_file():
        return primary
    return resource_path("assets", "avatar", "vision_character_bible.png")


def config_dir() -> Path:
    path = project_root() / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def module_config_dir(module_id: str) -> Path:
    path = config_dir() / module_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    path = project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = project_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def module_logs_dir(module_id: str) -> Path:
    """Legacy LoggingService path: logs/modules/<module_id>/ (unchanged for EniSpace)."""
    path = logs_dir() / "modules" / module_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_module_id_segment(module_id: str) -> str:
    mid = (module_id or "").strip().lower()
    if not mid or any(c in mid for c in ("/", "\\", "..")):
        raise ValueError(f"module_id non valido per path: {module_id!r}")
    safe = "".join(c for c in mid if c.isalnum() or c in "-_")
    if not safe or safe != mid:
        raise ValueError(f"module_id non valido per path: {module_id!r}")
    return safe


def module_data_dir(module_id: str, *, create: bool = True) -> Path:
    """Phase 1 root: data/modules/<module_id>/ (does not replace Documents\\VIS-ION)."""
    path = data_dir() / "modules" / _safe_module_id_segment(module_id)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def module_input_dir(module_id: str, *, create: bool = True) -> Path:
    path = module_data_dir(module_id, create=create) / "input"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def module_output_dir(module_id: str, *, create: bool = True) -> Path:
    path = module_data_dir(module_id, create=create) / "output"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def module_archive_dir(module_id: str, *, create: bool = True) -> Path:
    path = module_data_dir(module_id, create=create) / "archive"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def module_temp_dir(module_id: str, *, create: bool = True) -> Path:
    path = module_data_dir(module_id, create=create) / "temp"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def module_templates_dir(module_id: str, *, create: bool = True) -> Path:
    path = module_data_dir(module_id, create=create) / "templates"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def module_data_logs_dir(module_id: str, *, create: bool = True) -> Path:
    """
    Phase 1 data-tree logs: data/modules/<module_id>/logs.

    Distinct from legacy ``module_logs_dir`` (logs/modules/...) used by LoggingService.
    """
    path = module_data_dir(module_id, create=create) / "logs"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def module_spool_dir(module_id: str = "print", *, create: bool = True) -> Path:
    path = module_data_dir(module_id, create=create) / "spool"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_module_data_tree(module_id: str) -> Path:
    """Create the Phase 1 data/modules/<id>/{input,output,archive,temp,templates,logs} tree."""
    root = module_data_dir(module_id, create=True)
    module_input_dir(module_id, create=True)
    module_output_dir(module_id, create=True)
    module_archive_dir(module_id, create=True)
    module_temp_dir(module_id, create=True)
    module_templates_dir(module_id, create=True)
    module_data_logs_dir(module_id, create=True)
    if module_id.strip().lower() == "print":
        module_spool_dir("print", create=True)
    return root


def database_path() -> Path:
    """SQLite VIS•ION — indipendente da data/enispace.db del progetto legacy."""
    return data_dir() / "vision.db"


def browser_profile_dir() -> Path:
    """Profilo Playwright isolato (fallback se non si usa Chrome di sistema)."""
    path = data_dir() / "browser-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def chrome_executable_candidates() -> list[Path]:
    """Percorsi tipici di Google Chrome su Windows."""
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return [
        Path(pf86) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]


def chrome_executable_path() -> Path | None:
    for candidate in chrome_executable_candidates():
        try:
            if candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def chrome_proxy_executable_path() -> Path | None:
    """chrome_proxy.exe accanto a chrome.exe (scorciatoie / PWA)."""
    chrome = chrome_executable_path()
    if chrome is None:
        return None
    proxy = chrome.parent / "chrome_proxy.exe"
    try:
        if proxy.is_file():
            return proxy
    except Exception:
        pass
    return None


def chrome_system_user_data_dir() -> Path:
    """User Data di Chrome di sistema (contiene Default, Profile 1, …)."""
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "Google" / "Chrome" / "User Data"


def chrome_cdp_user_data_dir() -> Path:
    """
    User Data NON di sistema per remote debugging (Chrome 136+).
    Chrome blocca CDP su …\\Google\\Chrome\\User Data; qui CDP funziona.
    """
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(local) / "VISION" / "ChromeCDP"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_browser_user_data_dir(*, use_system_profile: bool = False) -> Path:
    """
    Directory user-data per Playwright persistent context.
    Come VIS eniSpace Utility: sempre profilo isolato data/browser-profile.
    (Chrome 151+ blocca CDP sul User Data di sistema; non usarlo.)
    """
    _ = use_system_profile  # opzione UI mantenuta ma ignorata in launch
    return browser_profile_dir()


def sync_system_chrome_profile_to_cdp(
    *,
    profile_directory: str = "Default",
) -> Path:
    """
    Copia credenziali/cookie/PWA dal profilo Chrome di sistema nel profilo CDP Vision.
    Solo file leggeri (niente Extensions/IndexedDB/cache) per evitare freeze/crash.
    """
    import shutil

    src_root = chrome_system_user_data_dir()
    dst_root = chrome_cdp_user_data_dir()
    profile = (profile_directory or "Default").strip() or "Default"
    src_profile = src_root / profile
    dst_profile = dst_root / profile
    dst_profile.mkdir(parents=True, exist_ok=True)

    def _copy_file(src: Path, dst: Path) -> None:
        try:
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except Exception:
            pass

    def _copy_dir(src: Path, dst: Path) -> None:
        if not src.is_dir():
            return
        try:
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(
                src,
                dst,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(
                    "Cache",
                    "Code Cache",
                    "GPUCache",
                    "ShaderCache",
                    "GrShaderCache",
                    "Service Worker",
                ),
            )
        except Exception:
            pass

    _copy_file(src_root / "Local State", dst_root / "Local State")
    for name in (
        "Login Data",
        "Login Data For Account",
        "Cookies",
        "Cookies-journal",
        "Web Data",
        "Web Data-journal",
        "Preferences",
        "Secure Preferences",
        "Bookmarks",
    ):
        _copy_file(src_profile / name, dst_profile / name)

    _copy_dir(src_profile / "Network", dst_profile / "Network")
    _copy_dir(src_profile / "Web Applications", dst_profile / "Web Applications")
    return dst_root


def default_download_dir() -> Path:
    """Cartella download predefinita: Documenti\\VIS-ION\\"""
    documents = Path.home() / "Documents"
    if not documents.is_dir():
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
