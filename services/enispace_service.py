"""Automazione portale eniSpace (Playwright).

IMPORTANTE — FASE DI ACQUISIZIONE SELETTORI
------------------------------------------
I selettori HTML e l'URL del portale NON sono inventati.
Finché non vengono verificati sul portale reale, i metodi
sollevano SelectorsNotConfiguredError.

URL portale (noto):
  https://enispace.eni.com/it_IT/home.page

Flusso documenti verificato:
  1) Ordini e consuntivi (STABILE):
     .../i_miei_ordini_e_consuntivi/i_miei_ordini_e_consuntivi.page
  2) Marketplace Launchpad:
     .../ui#Launchpad-openFLPPage?pageId=Z_PG_MARKETPLACE&spaceId=Z_SP_MARKETPLACE
  3) Dashboard filtri:
     .../ui#ZMP_DSH-DISPLAY&/
  4) [TODO] Compilare filtri (ordine / modulo / contratto) e scaricare

Punti da mappare (FASE 4):
  [TODO-SELECTOR] LOGIN_USERNAME
  [TODO-SELECTOR] LOGIN_PASSWORD
  [TODO-SELECTOR] LOGIN_SUBMIT
  [TODO-SELECTOR] LOGGED_IN_INDICATOR
  [TODO-SELECTOR] SEARCH_INPUT
  [TODO-SELECTOR] SEARCH_SUBMIT
  [TODO-SELECTOR] CONTRACT_RESULT_ROW
  [TODO-SELECTOR] ATTACHMENTS_TAB / LIST
  [TODO-SELECTOR] ATTACHMENT_ROW
  [TODO-SELECTOR] DOWNLOAD_BUTTON

Usare Impostazioni → «Registra navigazione» oppure
`playwright codegen https://enispace.eni.com/it_IT/home.page --channel=chrome`
per catturare i selettori reali.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from database.models import Document, DocumentStatus
from services.browser_service import BrowserConfig, BrowserService
from services.credential_service import CredentialService, Credentials
from services.exceptions import (
    BrowserError,
    CredentialsMissingError,
    LoginFailedError,
    NetworkError,
    PageStructureChangedError,
    PortalUnreachableError,
    SelectorsNotConfiguredError,
    SessionExpiredError,
    TimeoutErrorEni,
)
from utils.logger import get_logger
from utils.paths import (
    ENISPACE_HOME_URL,
    ENISPACE_MARKETPLACE_DASHBOARD_URL,
    ENISPACE_MARKETPLACE_HOST,
    ENISPACE_MARKETPLACE_HOST_SUFFIX,
    ENISPACE_MARKETPLACE_URL,
    ENISPACE_MYHOME_URL,
    ENISPACE_ORDINI_URL,
    ENISPACE_PROXY_LOGIN_URL,
    ENISPACE_STARTUP_URL,
    is_valid_marketplace_host,
    marketplace_dashboard_url_from,
)

logger = get_logger("enispace")


# =============================================================================
# SELETTORI / URL — solo valori verificati sul portale reale
# =============================================================================

class Selectors:
    """
    Contenitore selettori/URL. Valori vuoti = non ancora acquisiti.
    Non riempire con selettori inventati.
    """

    # URL home eniSpace (verificato)
    BASE_URL: str = ENISPACE_HOME_URL
    # Ingresso SSO (barra preferiti Chrome)
    PROXY_LOGIN_URL: str = ENISPACE_PROXY_LOGIN_URL
    MYHOME_URL: str = ENISPACE_MYHOME_URL
    ORDINI_URL: str = ENISPACE_ORDINI_URL

    # URL Marketplace FLP — host UUID può cambiare; aggiornato a runtime.
    MARKETPLACE_URL: str = ENISPACE_MARKETPLACE_URL
    # Dashboard dove si impostano i filtri di ricerca documenti
    MARKETPLACE_DASHBOARD_URL: str = ENISPACE_MARKETPLACE_DASHBOARD_URL

    # Filtri dashboard ZMP_DSH-DISPLAY (acquisiti dal DOM reale 2026-08-07)
    # ID stabili della worklist; usiamo suffisso per resistere a prefissi FLP.
    FILTER_ORDER_INPUT: str = "input[id$='iODAnumber-inner']"
    FILTER_CONTRACT_INPUT: str = "input[id$='iCTRnumber-inner']"
    FILTER_MODULE_INPUT: str = ""  # non presente nella barra filtri (MdA è in dettaglio)
    FILTER_APPLY_BUTTON: str = "Cerca"  # pulsante giallo osservato nel video
    FILTER_RESULT_ROW: str = (
        ".sapMListItems .sapMLIB, "
        "table.sapUiTableCtrl tr.sapUiTableTr, "
        ".sapMTable tbody tr"
    )

    # [TODO-SELECTOR] campo username / email login
    LOGIN_USERNAME: str = ""

    # [TODO-SELECTOR] campo password
    LOGIN_PASSWORD: str = ""

    # [TODO-SELECTOR] pulsante submit login
    LOGIN_SUBMIT: str = ""

    # [TODO-SELECTOR] elemento presente solo se autenticati
    LOGGED_IN_INDICATOR: str = ""

    # [TODO-SELECTOR] campo ricerca contratto
    SEARCH_INPUT: str = ""

    # [TODO-SELECTOR] pulsante ricerca
    SEARCH_SUBMIT: str = ""

    # [TODO-SELECTOR] riga risultato contratto
    CONTRACT_RESULT_ROW: str = ""

    # [TODO-SELECTOR] area / tab allegati
    ATTACHMENTS_AREA: str = ""

    # [TODO-SELECTOR] singola riga allegato
    ATTACHMENT_ROW: str = ""

    # Download PDF MdA/EM sul dettaglio ordine (testo pulsante reale)
    DOWNLOAD_BUTTON: str = "PDF MdA/EM"
    # Pulsante PDF ordine (opzionale)
    DOWNLOAD_ORDER_PDF_BUTTON: str = "PDF Ordine d'Acquisto"


@dataclass
class AttachmentInfo:
    """Metadati allegato rilevati dal portale (quando mappati)."""

    remote_id: Optional[str] = None
    filename: str = ""
    doc_type: Optional[str] = None
    remote_date: Optional[str] = None
    size: Optional[int] = None
    download_hint: Optional[str] = None  # selettore o URL relativo, da mappare


@dataclass
class SearchResult:
    found: bool
    contract_number: str
    attachments: list[AttachmentInfo] = field(default_factory=list)
    message: str = ""


def _selector_ready(value: str) -> bool:
    return bool(value and value.strip())


class EniSpaceService:
    """
    Isola tutta la logica di navigazione eniSpace.
    Sostituibile in futuro senza toccare la GUI.
    """

    def __init__(
        self,
        browser: BrowserService,
        credentials: CredentialService,
        *,
        base_url: str = "",
        timeout_ms: int = 60000,
        debug: bool = False,
        db: Any = None,
    ) -> None:
        self.browser = browser
        self.credentials = credentials
        self.base_url = (base_url or Selectors.BASE_URL).rstrip("/")
        self.timeout_ms = timeout_ms
        self.debug = debug
        self.db = db
        self._session_active = False
        self._learned_marketplace_url = ""
        self._last_order_number = ""
        self._last_acquisition_module: Optional[str] = None
        # Quando il browser vede un URL marketplace, lo memorizziamo
        self.browser.on_url_seen = self.note_navigation_url

    # ------------------------------------------------------------------ helpers
    def _require_base_url(self) -> str:
        if not self.base_url:
            raise SelectorsNotConfiguredError(
                "BASE_URL",
                message=(
                    "URL del portale eniSpace non configurato.\n"
                    "Impostarlo nelle Impostazioni oppure definirselo dopo "
                    "la mappatura con «Registra navigazione»."
                ),
            )
        return self.base_url

    def _require_selector(self, name: str, value: str) -> str:
        if not _selector_ready(value):
            raise SelectorsNotConfiguredError(name)
        return value

    def _debug_action(self, action: str, element: str = "") -> None:
        if self.debug:
            url = ""
            try:
                if self.browser.page:
                    url = self.browser.page.url
            except Exception:
                pass
            logger.debug(
                "eniSpace action=%s element=%s url=%s", action, element or "—", url
            )

    def configure_browser(
        self,
        *,
        visible: Optional[bool] = None,
        hidden: Optional[bool] = None,
        timeout_ms: int,
        debug: bool,
    ) -> None:
        """visible=True → browser in primo piano; hidden=True → headed nascosto.

        Non usa Playwright headless (rompe UI5/MFA). Preferire hidden.
        """
        self.timeout_ms = timeout_ms
        self.debug = debug
        prev = self.browser.config
        if hidden is not None:
            is_hidden = bool(hidden)
        elif visible is not None:
            is_hidden = not bool(visible)
        else:
            is_hidden = bool(prev.hidden)
        self.browser.config = BrowserConfig(
            headless=False,
            hidden=is_hidden,
            timeout_ms=timeout_ms,
            debug=debug,
            user_data_dir=prev.user_data_dir,
            downloads_path=prev.downloads_path,
            channel=prev.channel or "chrome",
            use_system_chrome_profile=bool(
                getattr(prev, "use_system_chrome_profile", True)
            ),
            chrome_profile_directory=getattr(prev, "chrome_profile_directory", None)
            or "Default",
            executable_path=getattr(prev, "executable_path", None),
            startup_url=getattr(prev, "startup_url", None) or ENISPACE_STARTUP_URL,
        )

    # ------------------------------------------------------------------ session
    @property
    def is_session_active(self) -> bool:
        return self._session_active

    def is_logged_in(self) -> bool:
        """
        Verifica sessione attiva.
        [TODO-SELECTOR] LOGGED_IN_INDICATOR richiesto per verifica automatica.
        """
        return self.browser.run(self._is_logged_in_impl)

    def _is_logged_in_impl(self) -> bool:
        page = self.browser.page
        if not page:
            self._session_active = False
            return False

        indicator = Selectors.LOGGED_IN_INDICATOR
        if not _selector_ready(indicator):
            self._debug_action("is_logged_in_heuristic")
            ok = self._looks_like_authenticated_portal_impl()
            self._session_active = ok
            return ok

        try:
            self._debug_action("is_logged_in", indicator)
            el = page.locator(indicator).first
            visible = el.is_visible(timeout=3000)
            self._session_active = bool(visible)
            return self._session_active
        except Exception as exc:
            logger.debug("is_logged_in fallito: %s", exc)
            self._session_active = False
            return False

    def ensure_browser(self) -> None:
        try:
            self.browser.start()
        except RuntimeError:
            raise
        except Exception as exc:
            raise BrowserError(
                "Errore browser. Consultare il log tecnico.",
                technical=str(exc),
            ) from exc

    def login(self, allow_manual: bool = True) -> bool:
        """
        Tenta login automatico se selettori e credenziali sono disponibili.
        In caso di MFA / Entra ID apre Chrome e attende login manuale.
        Credenziali keyring non obbligatorie se allow_manual (SSO aziendale).
        """
        creds = self.credentials.load()
        has_creds = bool(creds and creds.is_complete)
        if not has_creds and not allow_manual:
            raise CredentialsMissingError(
                "Credenziali eniSpace mancanti.\n"
                "Aprire Impostazioni e salvare username/password."
            )
        if not has_creds:
            logger.info(
                "Credenziali keyring assenti o incomplete: "
                "si procede con login manuale / sessione Chrome."
            )

        logger.info("Avvio/verifica Chrome per eniSpace...")
        self.ensure_browser()
        page = self.browser.page
        assert page is not None

        if self._manual_login_probe():
            logger.info("Sessione eniSpace già attiva.")
            self._session_active = True
            self.browser.enable_interactive()
            return True

        url = (
            self.base_url
            or Selectors.BASE_URL
            or ENISPACE_HOME_URL
            or Selectors.PROXY_LOGIN_URL
            or ENISPACE_PROXY_LOGIN_URL
            or Selectors.MYHOME_URL
            or ENISPACE_MYHOME_URL
        )
        if not url:
            if allow_manual:
                logger.info(
                    "URL eniSpace non configurato. Chrome aperto per login manuale."
                )
                self.browser.config.headless = False
                # MFA: wait_for_manual_login mostra temporaneamente se hidden
                logger.info(
                    "ATTESA LOGIN eniSpace: completare l'accesso in Chrome "
                    "(MFA/OTP consentiti). La sync non è bloccata — attendere..."
                )
                ok = self.browser.wait_for_manual_login(
                    is_logged_in=self._manual_login_probe,
                    max_wait_seconds=600,
                )
                self._session_active = ok
                if not ok:
                    raise LoginFailedError(
                        "Login non riuscito o tempo scaduto.\n"
                        "Completare l'accesso nel browser e riprovare."
                    )
                return True
            raise SelectorsNotConfiguredError("BASE_URL")

        # Se il browser è già su myhome/private dopo startup, non rifare goto.
        current = self.browser.current_url() or ""
        if self._url_looks_authenticated(current) or self._is_identity_provider_url(
            current
        ):
            logger.info("Browser già su sessione/IdP: %s", current[:120])
        else:
            try:
                self._debug_action("goto_login", url)
                self.browser.goto(url)
            except Exception as exc:
                err = str(exc).lower()
                logger.error("Apertura eniSpace fallita: %s", exc)
                if "timeout" in err:
                    raise TimeoutErrorEni(
                        "Timeout durante la connessione a eniSpace.",
                        technical=str(exc),
                    ) from exc
                if "net::" in err or "network" in err or "err_" in err:
                    raise NetworkError(
                        "Assenza connessione internet o portale non raggiungibile.",
                        technical=str(exc),
                    ) from exc
                if any(
                    k in err
                    for k in (
                        "destroyed",
                        "closed",
                        "aborted",
                        "interrupted",
                        "detached",
                    )
                ):
                    raise BrowserError(
                        "Navigazione interrotta (scheda Marketplace/popup ancora attiva).\n"
                        "Chiudere le schede non necessarie oppure riprovare "
                        "«Test accesso» / «Registra navigazione».",
                        technical=str(exc),
                    ) from exc
                raise PortalUnreachableError(
                    "Portale eniSpace non raggiungibile.\n"
                    "Se hai appena usato il Marketplace, riprova: "
                    "verrà aperta una nuova scheda eniSpace.",
                    technical=str(exc),
                ) from exc

        # Se siamo già su myhome privata dopo startup, la sessione è ok.
        if self._enispace_private_online() or self._manual_login_probe():
            logger.info("Sessione valida su area privata / portale.")
            self._session_active = True
            self.browser.enable_interactive()
            return True

        # home.page è pubblica: non basta. Prova area privata (myhome).
        if self._probe_private_session():
            logger.info("Sessione valida dopo verifica area privata.")
            self.browser.enable_interactive()
            return True

        can_auto = has_creds and all(
            _selector_ready(s)
            for s in (
                Selectors.LOGIN_USERNAME,
                Selectors.LOGIN_PASSWORD,
                Selectors.LOGIN_SUBMIT,
            )
        )

        if can_auto and creds is not None:
            try:
                return self._automated_login(creds)
            except SelectorsNotConfiguredError:
                raise
            except Exception as exc:
                logger.warning(
                    "Login automatico non riuscito (%s). Passaggio a login manuale.",
                    exc,
                )

        if not allow_manual:
            raise LoginFailedError("Login automatico non riuscito.")

        logger.info(
            "Login richiede intervento manuale (MFA/OTP/Entra o selettori non mappati)."
        )
        self.browser.config.headless = False
        if self.browser.config.hidden:
            logger.warning(
                "Serve login: Chrome verrà mostrato. "
                "Per il primo accesso puoi anche disattivare «Nascondi browser»."
            )
        logger.info(
            "ATTESA LOGIN eniSpace: completare l'accesso in Chrome "
            "(MFA/OTP consentiti). La sync non è bloccata — attendere..."
        )
        ok = self._wait_for_sso_if_needed(
            max_wait_seconds=600,
            context="eniSpace",
            require_enispace_private=True,
        )
        if not ok:
            raise LoginFailedError(
                "Sessione eniSpace scaduta o login non completato.\n"
                "È necessario effettuare nuovamente l'accesso."
            )
        logger.info("Sessione valida.")
        self.browser.enable_interactive()
        return True

    def _looks_like_authenticated_portal(self) -> bool:
        """Euristica URL: sessione attiva su eniSpace o Marketplace (qualsiasi scheda)."""
        return self.browser.run(self._looks_like_authenticated_portal_impl)

    @staticmethod
    def _is_identity_provider_url(url: str) -> bool:
        current_l = (url or "").lower()
        if not current_l or current_l == "about:blank":
            return False
        idp_hints = (
            "login.microsoftonline.com",
            "login.microsoft.com",
            "login.eni.com",
            "/saml2",
            "adfs",
            "oauth",
            "signin",
            "sts.",
            "authentication.eu10.hana.ondemand.com/login",
            "proxylogin",
        )
        return any(h in current_l for h in idp_hints)

    def _url_looks_authenticated(self, current: str) -> bool:
        """
        Sessione reale: area privata eniSpace o Marketplace già aperto.
        La home pubblica (home.page) NON basta: è raggiungibile senza SSO.
        """
        current_l = (current or "").lower()
        if not current_l or current_l == "about:blank":
            return False

        if self._is_identity_provider_url(current_l):
            return False

        # Qualsiasi host Marketplace BTP/ABAP (UUID può cambiare)
        if self._is_marketplace_url(current):
            return True

        # Solo area privata eniSpace (myhome / private pages)
        if "enispace.eni.com" in current_l:
            if "proxylogin" in current_l or "/login" in current_l:
                return False
            if "/private/" in current_l or "myhome.page" in current_l:
                return True
            # home.page e altre pagine pubbliche: non autenticate
            return False

        return False

    def _resolve_login_username(self) -> str:
        """Username portale da keyring o settings (es. anna.boccuni@guest.eni.com)."""
        try:
            user = (self.credentials.get_username() or "").strip()
            if user:
                return user
        except Exception:
            pass
        try:
            creds = self.credentials.load()
            if creds and (creds.username or "").strip():
                return creds.username.strip()
        except Exception:
            pass
        if self.db is not None:
            try:
                user = (self.db.get_settings().username or "").strip()
                if user:
                    return user
            except Exception:
                pass
        return ""

    def _resolve_login_password(self) -> str:
        try:
            creds = self.credentials.load()
            if creds and creds.password:
                return creds.password
        except Exception:
            pass
        return ""

    def _enispace_private_online(self) -> bool:
        """True solo se esiste una scheda eniSpace in area /private/."""
        return self.browser.run(self._enispace_private_online_impl)

    def _enispace_private_online_impl(self) -> bool:
        pages = []
        try:
            if self.browser.context:
                pages = list(self.browser.context.pages)
        except Exception:
            pages = []
        if self.browser.page is not None and self.browser.page not in pages:
            pages.insert(0, self.browser.page)
        for page in pages:
            try:
                current = page.url or ""
            except Exception:
                continue
            current_l = current.lower()
            if self._is_identity_provider_url(current_l):
                continue
            if "enispace.eni.com" not in current_l:
                continue
            if "/private/" in current_l or "myhome.page" in current_l:
                try:
                    self.browser.focus_page(page)
                except Exception:
                    pass
                return True
        return False

    def _assist_sso_login_once(self) -> None:
        """Su Microsoft/ADFS: inserisce username salvato e clicca Avanti (rate-limited)."""
        import time

        now = time.monotonic()
        if now - getattr(self, "_sso_assist_ts", 0.0) < 2.5:
            return
        self._sso_assist_ts = now
        username = self._resolve_login_username()
        if not username:
            return
        try:
            self.browser.run(self._assist_sso_login_impl, username)
        except Exception as exc:
            logger.debug("SSO assist: %s", exc)

    def _assist_sso_login_impl(self, username: str) -> None:
        pages = []
        try:
            if self.browser.context:
                pages = list(self.browser.context.pages)
        except Exception:
            pages = []
        if self.browser.page is not None and self.browser.page not in pages:
            pages.insert(0, self.browser.page)

        for page in pages:
            try:
                url = (page.url or "").lower()
            except Exception:
                continue
            if not self._is_identity_provider_url(url):
                continue
            try:
                if "login.microsoftonline.com" in url or "login.microsoft.com" in url:
                    self._assist_microsoft_online_page(page, username)
                elif "login.eni.com" in url or "adfs" in url:
                    self._assist_eni_adfs_page(page, username)
            except Exception as exc:
                logger.debug("SSO assist page (%s): %s", url[:60], exc)

    def _assist_microsoft_online_page(self, page, username: str) -> None:
        """Compila email su Entra ID e clicca Avanti / seleziona account."""
        # 1) Account picker: clicca tile con l'email
        try:
            tile = page.locator(f'[data-test-id="{username}"]').first
            if tile.count() and tile.is_visible(timeout=800):
                logger.info("SSO assist: selezione account %s", username)
                tile.click(timeout=3000)
                return
        except Exception:
            pass
        try:
            acc = page.get_by_text(username, exact=False).first
            if acc.count() and acc.is_visible(timeout=800):
                # Evita click su titoli generici: preferisci riga account
                logger.info("SSO assist: click account visibile %s", username)
                acc.click(timeout=3000)
                return
        except Exception:
            pass

        # 2) Campo email Microsoft (#i0116 / loginfmt)
        email_selectors = (
            "#i0116",
            'input[name="loginfmt"]',
            'input[type="email"]',
            'input[name="username"]',
        )
        filled = False
        for sel in email_selectors:
            try:
                el = page.locator(sel).first
                if not el.count() or not el.is_visible(timeout=600):
                    continue
                current_val = ""
                try:
                    current_val = (el.input_value(timeout=500) or "").strip()
                except Exception:
                    current_val = ""
                if current_val.lower() != username.lower():
                    el.click(timeout=2000)
                    el.fill("")
                    el.fill(username)
                    logger.info("SSO assist: email inserita su Microsoft (%s)", username)
                filled = True
                break
            except Exception:
                continue
        if not filled:
            return

        # 3) Avanti / Next
        for sel in ("#idSIButton9", 'input[type="submit"]', 'button[type="submit"]'):
            try:
                btn = page.locator(sel).first
                if btn.count() and btn.is_visible(timeout=600):
                    btn.click(timeout=3000)
                    logger.info("SSO assist: click Avanti su Microsoft")
                    return
            except Exception:
                continue
        try:
            nxt = page.get_by_role("button", name="Next").first
            if nxt.count() and nxt.is_visible(timeout=600):
                nxt.click(timeout=3000)
                logger.info("SSO assist: click Next")
                return
        except Exception:
            pass
        try:
            nxt = page.get_by_role("button", name="Avanti").first
            if nxt.count() and nxt.is_visible(timeout=600):
                nxt.click(timeout=3000)
                logger.info("SSO assist: click Avanti")
        except Exception:
            pass

    def _assist_eni_adfs_page(self, page, username: str) -> None:
        """Su ADFS Eni: username (se manca) + password da keyring, poi submit."""
        user_selectors = (
            "#userNameInput",
            'input[name="UserName"]',
            'input[type="email"]',
            'input[name="username"]',
            "#username",
        )
        for sel in user_selectors:
            try:
                el = page.locator(sel).first
                if not el.count() or not el.is_visible(timeout=500):
                    continue
                current_val = ""
                try:
                    current_val = (el.input_value(timeout=400) or "").strip()
                except Exception:
                    current_val = ""
                if not current_val:
                    el.fill(username)
                    logger.info("SSO assist: username su ADFS Eni (%s)", username)
                break
            except Exception:
                continue

        password = self._resolve_login_password()
        if not password:
            return
        pwd_selectors = (
            "#passwordInput",
            'input[name="Password"]',
            'input[type="password"]',
        )
        for sel in pwd_selectors:
            try:
                el = page.locator(sel).first
                if not el.count() or not el.is_visible(timeout=500):
                    continue
                current_val = ""
                try:
                    current_val = (el.input_value(timeout=400) or "").strip()
                except Exception:
                    current_val = ""
                if not current_val:
                    el.fill(password)
                    logger.info("SSO assist: password inserita su ADFS Eni")
                break
            except Exception:
                continue

        # Evita submit ripetuti sulla stessa URL
        try:
            url_key = (page.url or "")[:180]
        except Exception:
            url_key = ""
        if getattr(self, "_sso_adfs_submit_for", "") == url_key:
            return

        for sel in (
            "#submitButton",
            'span#submitButton',
            'input[type="submit"]',
            'button[type="submit"]',
        ):
            try:
                btn = page.locator(sel).first
                if btn.count() and btn.is_visible(timeout=500):
                    btn.click(timeout=3000)
                    self._sso_adfs_submit_for = url_key
                    logger.info("SSO assist: submit ADFS Eni")
                    return
            except Exception:
                continue

    def _sso_wait_probe(self, *, require_enispace_private: bool = False) -> bool:
        """Probe durante wait: assiste SSO, poi verifica sessione."""
        self._assist_sso_login_once()
        if require_enispace_private:
            ok = self._enispace_private_online()
        else:
            ok = self._manual_login_probe()
        if ok:
            self._session_active = True
        return ok

    def _wait_for_sso_if_needed(
        self,
        *,
        max_wait_seconds: float = 600.0,
        context: str = "eniSpace",
        require_enispace_private: bool = False,
    ) -> bool:
        """Se siamo su IdP / senza sessione, attende login (con assist email)."""
        if require_enispace_private:
            if self._enispace_private_online():
                self._session_active = True
                return True
        elif self._manual_login_probe():
            return True

        current = self.browser.current_url() or ""
        on_idp = self._is_identity_provider_url(current)
        if (
            not require_enispace_private
            and not on_idp
            and self._url_looks_authenticated(current)
        ):
            self._session_active = True
            return True

        username = self._resolve_login_username()
        if username:
            logger.info(
                "SSO richiesto per %s: assist login con %s "
                "(MFA/OTP manuale se richiesto, attesa max %.0fs)...",
                context,
                username,
                max_wait_seconds,
            )
        else:
            logger.info(
                "SSO richiesto per %s: completare il login in Chrome "
                "(salva username in Impostazioni per assist automatico, attesa max %.0fs)...",
                context,
                max_wait_seconds,
            )
        # Assist immediato prima del loop
        self._assist_sso_login_once()
        ok = self.browser.wait_for_manual_login(
            is_logged_in=lambda: self._sso_wait_probe(
                require_enispace_private=require_enispace_private
            ),
            max_wait_seconds=max_wait_seconds,
        )
        self._session_active = ok
        return ok

    def ensure_enispace_online(self) -> bool:
        """
        Prerequisito supervisor/Marketplace: eniSpace area privata autenticata.
        Non apre Marketplace finché myhome/private non è online.
        """
        logger.info("STEP 0 — Verifica eniSpace online (area privata)")
        self.login(allow_manual=True)
        if self._enispace_private_online():
            logger.info("eniSpace online: area privata confermata.")
            self._session_active = True
            return True

        # Forza myhome e attendi SSO fino a private
        if not self._probe_private_session():
            if not self._wait_for_sso_if_needed(
                max_wait_seconds=600,
                context="eniSpace (prerequisito Marketplace)",
                require_enispace_private=True,
            ):
                raise LoginFailedError(
                    "eniSpace non è online (area privata non raggiungibile).\n"
                    "Completare il login Microsoft/ADFS in Chrome "
                    f"({self._resolve_login_username() or 'username in Impostazioni'}) "
                    "e riprovare prima del Marketplace."
                )
        if not self._enispace_private_online():
            raise LoginFailedError(
                "eniSpace non confermato online.\n"
                "Attendere il redirect su myhome/private dopo il login."
            )
        logger.info("eniSpace online: area privata confermata dopo SSO.")
        self._session_active = True
        return True

    def _probe_private_session(self) -> bool:
        """
        Verifica sessione aprendo myhome (privata).
        Se redirect a Microsoft/SSO → non autenticati.
        """
        probe = ENISPACE_MYHOME_URL or Selectors.ORDINI_URL or ENISPACE_ORDINI_URL
        if not probe:
            return False
        try:
            logger.info("Verifica sessione su area privata: %s", probe)
            self.browser.goto(probe, wait_until="domcontentloaded")
        except Exception as exc:
            logger.warning("Probe sessione privata fallito: %s", exc)
            return False

        current = self.browser.current_url() or ""
        if self._is_identity_provider_url(current):
            logger.info("Sessione assente: redirect IdP (%s)", current[:120])
            return False
        if self._enispace_private_online() or self._manual_login_probe():
            logger.info("Sessione privata confermata.")
            self._session_active = True
            return True
        return False

    @staticmethod
    def _is_marketplace_url(url: str) -> bool:
        u = (url or "").lower()
        if not u or u == "about:blank":
            return False
        if ENISPACE_MARKETPLACE_HOST_SUFFIX in u:
            return True
        if ENISPACE_MARKETPLACE_HOST in u:
            return True
        if "z_pg_marketplace" in u or "zmp_dsh-display" in u:
            return True
        return False

    @staticmethod
    def _marketplace_launch_url(base: str) -> str:
        """Costruisce l'URL Launchpad Marketplace a partire dall'origine osservata."""
        parsed = urlparse(base)
        if not parsed.scheme or not parsed.netloc:
            return base
        origin = f"{parsed.scheme}://{parsed.netloc}"
        return (
            f"{origin}/ui#Launchpad-openFLPPage"
            f"?pageId=Z_PG_MARKETPLACE&spaceId=Z_SP_MARKETPLACE"
        )

    def resolve_marketplace_url(self) -> str:
        """URL Marketplace: ultimo imparato valido > settings > fallback reale."""
        candidates = [
            self._learned_marketplace_url,
        ]
        if self.db is not None:
            try:
                from app.modules.config.enispace_runtime import load_portal_browser_runtime

                candidates.append(load_portal_browser_runtime(self.db).marketplace_base_url)
            except Exception:
                try:
                    candidates.append(self.db.get_settings().marketplace_base_url)
                except Exception:
                    pass
        candidates.append(Selectors.MARKETPLACE_URL)
        candidates.append(ENISPACE_MARKETPLACE_URL)

        for cand in candidates:
            if not cand:
                continue
            host = urlparse(cand).netloc
            if is_valid_marketplace_host(host):
                return cand
            logger.warning("Ignoro URL Marketplace non valida: %s", cand)

        return ENISPACE_MARKETPLACE_URL

    def note_navigation_url(self, url: str) -> None:
        """Chiamato dal browser quando cambia URL: memorizza host Marketplace se valido."""
        if not self._is_marketplace_url(url):
            return
        if "authentication." in url.lower() and "/login" in url.lower():
            return
        host = urlparse(url).netloc
        if not is_valid_marketplace_host(host):
            logger.debug("Host Marketplace non valido (non salvato): %s", host)
            return
        launch = self._marketplace_launch_url(url)
        if launch == self._learned_marketplace_url:
            return
        prev = self._learned_marketplace_url or "(nessuno)"
        self._learned_marketplace_url = launch
        Selectors.MARKETPLACE_URL = launch
        logger.info(
            "Marketplace URL aggiornato dalla navigazione:\n  prima: %s\n  ora:   %s",
            prev,
            launch,
        )
        if self.db is not None:
            try:
                settings = self.db.get_settings()
                if settings.marketplace_base_url != launch:
                    settings.marketplace_base_url = launch
                    self.db.save_settings(settings)
            except Exception as exc:
                logger.debug("Salvataggio marketplace_base_url: %s", exc)

    def _looks_like_authenticated_portal_impl(self) -> bool:
        # Controlla tutte le schede del context (non solo quella attiva):
        # dopo Marketplace la scheda attiva è SAP, ma eniSpace può essere ancora aperta.
        pages = []
        try:
            if self.browser.context:
                pages = list(self.browser.context.pages)
        except Exception:
            pages = []

        if self.browser.page is not None and self.browser.page not in pages:
            pages.insert(0, self.browser.page)

        for page in pages:
            try:
                current = page.url or ""
            except Exception:
                continue
            if self._url_looks_authenticated(current):
                try:
                    self.browser.focus_page(page)
                except Exception:
                    pass
                logger.debug("Sessione rilevata su: %s", current)
                return True
        return False

    def _manual_login_probe(self) -> bool:
        """
        Probe per login manuale.
        Con selettore: verifica reale.
        Senza selettore: euristica URL sul dominio enispace.eni.com.
        """
        if _selector_ready(Selectors.LOGGED_IN_INDICATOR):
            return self.is_logged_in()
        if self._looks_like_authenticated_portal():
            self._session_active = True
            return True
        return False

    def _automated_login(self, creds: Credentials) -> bool:
        page = self.browser.page
        assert page is not None
        user_sel = self._require_selector("LOGIN_USERNAME", Selectors.LOGIN_USERNAME)
        pass_sel = self._require_selector("LOGIN_PASSWORD", Selectors.LOGIN_PASSWORD)
        submit_sel = self._require_selector("LOGIN_SUBMIT", Selectors.LOGIN_SUBMIT)

        self._debug_action("fill_username", user_sel)
        page.locator(user_sel).fill(creds.username)
        self._debug_action("fill_password", pass_sel)
        page.locator(pass_sel).fill(creds.password)
        self._debug_action("click_submit", submit_sel)
        page.locator(submit_sel).click()

        # Dopo submit potrebbe comparire MFA: non aggirarla
        if _selector_ready(Selectors.LOGGED_IN_INDICATOR):
            try:
                page.locator(Selectors.LOGGED_IN_INDICATOR).first.wait_for(
                    state="visible", timeout=15000
                )
                self._session_active = True
                logger.info("Login automatico riuscito.")
                return True
            except Exception:
                logger.info(
                    "Possibile MFA o redirect. Attendere completamento manuale..."
                )
                ok = self.browser.wait_for_manual_login(
                    is_logged_in=self.is_logged_in, max_wait_seconds=600
                )
                self._session_active = ok
                if not ok:
                    raise LoginFailedError("Login non riuscito (possibile MFA non completata).")
                return True

        raise SelectorsNotConfiguredError("LOGGED_IN_INDICATOR")

    def logout(self) -> None:
        """Logout — selettore non ancora mappato: chiude solo lo stato locale."""
        self._debug_action("logout")
        # [TODO-SELECTOR] aggiungere click logout quando noto
        self._session_active = False
        logger.info("Sessione locale impostata come non connessa.")

    def mark_session(self, active: bool) -> None:
        """Permette alla GUI di aggiornare lo stato dopo login manuale confermato."""
        self._session_active = active

    # ------------------------------------------------------------------ contract / documenti
    def search_contract(
        self,
        contract_number: str,
        *,
        order_number: Optional[str] = None,
        framework_contract: Optional[str] = None,
        acquisition_module: Optional[str] = None,
    ) -> SearchResult:
        """
        Flusso documenti Marketplace:
          Ordini → Marketplace Launchpad → Dashboard filtri (#ZMP_DSH-DISPLAY&/)

        ``contract_number`` in pratica è la chiave di ricerca (di solito = ordine).
        Prima di ogni ricerca chiude eventuali dettagli ODA e riparte dai filtri.
        """
        number = (order_number or contract_number).strip()
        if not number:
            raise ValueError("Numero ordine vuoto.")

        logger.info(
            "Ricerca documenti: ordine=%s contratto=%s modulo=%s",
            number,
            framework_contract or "—",
            acquisition_module or "—",
        )

        # Nuova ricerca: non riusare ordine precedente se questa fallisce
        self._last_order_number = ""
        self._last_acquisition_module = None

        current = ""
        if self.browser.is_open:
            try:
                current = self.browser.current_url() or ""
            except Exception:
                current = ""

        self.login(allow_manual=True)
        if not current or "ZMP_DSH-DISPLAY" not in current.upper():
            self.open_document_flow()

        # Sempre chiudi dettaglio ODA e attendi i campi filtro reali
        final_url = self.return_to_dashboard_filters()
        logger.info("Dashboard filtri: %s", final_url)
        filled = self.apply_dashboard_filters(
            order_number=number,
            framework_contract=framework_contract,
            acquisition_module=acquisition_module,
        )
        if filled == 0:
            return SearchResult(
                found=False,
                contract_number=number,
                message=(
                    "Dashboard aperta, ma i campi filtro non sono stati trovati automaticamente.\n"
                    f"URL: {final_url}\n\n"
                    "Compila manualmente Ordine/Contratto in Chrome.\n"
                    "Campi attesi: iODAnumber (ordine), iCTRnumber (contratto)."
                ),
                attachments=[],
            )

        # Attendi risultati worklist, apri dettaglio ordine, elenca MdA
        import time

        time.sleep(2.0)
        opened = self.browser.run(self._open_order_detail, number)
        if not opened:
            return SearchResult(
                found=False,
                contract_number=number,
                message=(
                    f"Filtri applicati per ordine {number}, ma la riga ordine "
                    "non è stata aperta automaticamente.\n"
                    "Apri manualmente l'ordine in Chrome e riprova."
                ),
                attachments=[],
            )

        self._last_order_number = number
        self._last_acquisition_module = acquisition_module

        # La tabella MdA arriva dopo l'header (UI5 async)
        time.sleep(1.5)
        attachments = self.browser.run(self._list_mda_modules)
        if acquisition_module:
            preferred = [
                a
                for a in attachments
                if (a.remote_id or "") == acquisition_module
                or acquisition_module in (a.filename or "")
            ]
            others = [a for a in attachments if a not in preferred]
            if preferred:
                attachments = preferred + others
            else:
                logger.warning(
                    "Modulo acquisizione %s non trovato nelle righe MdA "
                    "(trovati: %s)",
                    acquisition_module,
                    [a.remote_id for a in attachments],
                )

        if not attachments:
            return SearchResult(
                found=True,
                contract_number=number,
                message=(
                    f"Dettaglio ordine {number} aperto, ma nessuna riga "
                    "MdA/EM rilevata.\nControlla la tabella in Chrome."
                ),
                attachments=[],
            )

        target = acquisition_module or "(tutti)"
        return SearchResult(
            found=True,
            contract_number=number,
            message=(
                f"Ordine {number} aperto. MdA trovati: {len(attachments)}. "
                f"Modulo mail: {target}."
            ),
            attachments=attachments,
        )

    def open_contract(self, contract_number: str) -> None:
        """
        Nel flusso Marketplace la «apertura» corrisponde all'ingresso in dashboard.
        Mantenuto per compatibilità con la GUI.
        """
        _ = contract_number
        current = self.browser.current_url() or ""
        cur_u = current.upper()
        if "ZMP_DSH-DISPLAY" in cur_u and "/ODA/" not in cur_u:
            return
        if "ZMP_DSH-DISPLAY" in cur_u and "/ODA/" in cur_u:
            self.return_to_dashboard_filters()
            return
        self.open_marketplace_dashboard()

    def get_attachments(self) -> list[AttachmentInfo]:
        """Elenco Moduli di Acquisizione (MdA/EM) sul dettaglio ordine."""
        return self.browser.run(self._list_mda_modules)

    def _open_order_detail(self, order_number: str) -> bool:
        """Dalla worklist filtri, apre il dettaglio dell'ordine (click riga ordine)."""
        import re
        import time

        page = self.browser.page
        if not page:
            raise BrowserError("Browser non avviato.")

        url = page.url or ""
        if "/ODA/" in url.upper() and order_number in url:
            logger.info("Già sul dettaglio ordine %s", order_number)
            return True

        # Attendi che l'ordine compaia nei risultati dopo «Cerca»
        found_text = False
        for _ in range(35):
            try:
                n = page.get_by_text(order_number, exact=True).count()
                if n > 0:
                    found_text = True
                    break
            except Exception:
                pass
            time.sleep(0.4)
        if not found_text:
            logger.warning("Ordine %s non presente nei risultati dopo Cerca", order_number)
            return False

        # Espandi gerarchia Emittente→Società→Contratto se collassata
        # (non cliccare se già sul dettaglio)
        if "/ODA/" not in (page.url or "").upper():
            try:
                # Solo Espandi nella toolbar risultati, non ovunque
                espandi = page.locator(
                    "button:has-text('Espandi'), [role=button]:has-text('Espandi')"
                ).first
                if espandi.count() and espandi.is_visible(timeout=800):
                    espandi.click(timeout=3000)
                    logger.info("Click «Espandi» sulla worklist")
                    time.sleep(1.2)
            except Exception:
                pass

        # Click sul numero ordine (evita l'input filtro)
        clicked = False
        try:
            matches = page.get_by_text(order_number, exact=True)
            for i in range(min(matches.count(), 12)):
                el = matches.nth(i)
                try:
                    if not el.is_visible(timeout=500):
                        continue
                    tag = (el.evaluate("e => (e.closest('input,textarea') ? 'INPUT' : e.tagName)") or "").upper()
                    if tag in ("INPUT", "TEXTAREA"):
                        continue
                    # Preferisci celle in tabella / lista
                    el.click(timeout=4000)
                    clicked = True
                    logger.info("Apertura dettaglio: click testo ordine %s", order_number)
                    break
                except Exception as exc:
                    logger.debug("Click match[%s] fallito: %s", i, exc)
        except Exception as exc:
            logger.debug("Enum match ordine fallita: %s", exc)

        if not clicked:
            candidates = [
                page.get_by_role("link", name=re.compile(re.escape(order_number))),
                page.locator(
                    ".sapMListItems .sapMLIB, tr, [role=row], [role=listitem]"
                ).filter(has_text=order_number),
            ]
            for loc in candidates:
                try:
                    target = loc.first
                    if target.count() == 0:
                        continue
                    if not target.is_visible(timeout=1500):
                        continue
                    target.click(timeout=5000)
                    clicked = True
                    logger.info("Apertura dettaglio ordine (fallback): %s", order_number)
                    break
                except Exception as exc:
                    logger.debug("Click ordine fallito: %s", exc)

        if not clicked:
            logger.warning("Riga ordine %s non cliccabile in worklist", order_number)
            return False

        # Attendi navigazione /ODA/ o titolo Numero Ordine
        for _ in range(25):
            time.sleep(0.4)
            cur = page.url or ""
            if "/ODA/" in cur.upper():
                logger.info("Dettaglio ordine raggiunto: %s", cur)
                return True
            try:
                if page.get_by_text(f"Numero Ordine: {order_number}", exact=False).count():
                    logger.info("Dettaglio ordine rilevato via titolo.")
                    return True
                if page.get_by_role(
                    "button", name=re.compile(r"PDF\s*MdA", re.I)
                ).count():
                    logger.info("Dettaglio ordine rilevato via pulsanti PDF MdA.")
                    return True
            except Exception:
                pass
        logger.warning("Timeout attesa dettaglio ordine dopo click.")
        return "/ODA/" in (page.url or "").upper()

    def _list_mda_modules(self) -> list[AttachmentInfo]:
        """
        Legge la tabella MdA/EM sul dettaglio ordine.
        Ogni riga ha numero modulo e pulsante «PDF MdA/EM».
        """
        import re
        import time

        page = self.browser.page
        if not page:
            raise BrowserError("Browser non avviato.")

        self._wait_detail_ready(page)

        docs: list[AttachmentInfo] = []
        seen: set[str] = set()

        # Dump diagnostico: testi pulsanti / link con PDF o MdA
        try:
            hints = page.evaluate(
                """() => {
                  const isVis = (el) => !!(el && (el.offsetParent || el.getClientRects().length));
                  const nodes = Array.from(document.querySelectorAll(
                    'button, a, [role=button], .sapMBtn, span.sapMBtnContent, bdi'
                  )).filter(isVis);
                  const out = [];
                  for (const el of nodes) {
                    const t = (el.innerText || el.textContent || '').replace(/\\s+/g,' ').trim();
                    if (!t || t.length > 80) continue;
                    if (!/pdf|mda|em/i.test(t)) continue;
                    out.push(t);
                  }
                  return [...new Set(out)].slice(0, 30);
                }"""
            )
            logger.info("Testi UI PDF/MdA visibili: %s", hints or "(nessuno)")
        except Exception as exc:
            logger.debug("Dump PDF/MdA fallito: %s", exc)

        # Strategia 1: pulsanti / testi «PDF MdA/EM»
        button_locs = [
            page.get_by_role("button", name=re.compile(r"PDF\s*MdA", re.I)),
            page.get_by_text(re.compile(r"PDF\s*MdA\s*/?\s*EM", re.I)),
            page.locator("button.sapMBtn, .sapMBtn").filter(
                has_text=re.compile(r"PDF\s*MdA", re.I)
            ),
        ]
        for buttons in button_locs:
            try:
                n = buttons.count()
            except Exception:
                n = 0
            if n == 0:
                continue
            logger.info("Elementi PDF MdA trovati: %d (%s)", n, buttons)
            for i in range(min(n, 80)):
                btn = buttons.nth(i)
                text = self._row_text_near(btn)
                modules = re.findall(r"\b(20\d{8})\b", text)
                module = modules[0] if modules else ""
                if not module:
                    continue
                if module in seen:
                    continue
                seen.add(module)
                date_match = re.search(
                    r"\b(\d{2}/\d{2}/\d{4})\b", text.replace("-", "/")
                )
                docs.append(
                    AttachmentInfo(
                        remote_id=module,
                        filename=f"{module}_MDA.pdf",
                        doc_type="PDF",
                        remote_date=date_match.group(1) if date_match else None,
                        download_hint="PDF MdA/EM",
                    )
                )
            if docs:
                break

        # Strategia 2: scrape JS — numeri 20xxxxxxxx vicino a PDF MdA
        if not docs:
            try:
                raw = page.evaluate(
                    """() => {
                      const isVis = (el) => !!(el && (el.offsetParent || el.getClientRects().length));
                      const out = [];
                      const seen = new Set();
                      const rows = Array.from(document.querySelectorAll(
                        'tr, [role=row], li, .sapMListItems > *, .sapMLnk, .sapMText, .sapMObjStatus'
                      ));
                      for (const row of rows) {
                        if (!isVis(row)) continue;
                        const t = (row.innerText || '').trim();
                        if (!t || t.length > 800) continue;
                        const m = t.match(/\\b(20\\d{8})\\b/);
                        if (!m) continue;
                        // riga tabella MdA tipica: modulo + valore EUR + data + PDF
                        const looksMda = /pdf\\s*mda|mda\\/em|eur|pos\\.?\\s*ordine/i.test(t)
                          || (t.includes(m[1]) && /\\d{2}\\/\\d{2}\\/\\d{4}/.test(t));
                        if (!looksMda) continue;
                        if (seen.has(m[1])) continue;
                        seen.add(m[1]);
                        const d = t.match(/\\b(\\d{2}\\/\\d{2}\\/\\d{4})\\b/);
                        out.push({ module: m[1], date: d ? d[1] : null, text: t.slice(0, 180) });
                      }
                      // fallback: qualsiasi 20xxxxxxxx nella pagina dettaglio
                      if (!out.length) {
                        const body = (document.body && document.body.innerText) || '';
                        const all = body.match(/\\b(20\\d{8})\\b/g) || [];
                        for (const mod of [...new Set(all)]) {
                          out.push({ module: mod, date: null, text: '' });
                        }
                      }
                      return out.slice(0, 80);
                    }"""
                )
                for item in raw or []:
                    module = str(item.get("module") or "")
                    if not module or module in seen:
                        continue
                    seen.add(module)
                    docs.append(
                        AttachmentInfo(
                            remote_id=module,
                            filename=f"{module}_MDA.pdf",
                            doc_type="PDF",
                            remote_date=item.get("date"),
                            download_hint="PDF MdA/EM",
                        )
                    )
                if docs:
                    logger.info("MdA da scrape JS: %d", len(docs))
            except Exception as exc:
                logger.debug("Scrape MdA JS fallito: %s", exc)

        # Strategia 3: se la mail indica un modulo e compare in pagina, usalo
        if not docs and self._last_acquisition_module:
            mod = self._last_acquisition_module
            try:
                if page.get_by_text(mod, exact=False).count() > 0:
                    docs.append(
                        AttachmentInfo(
                            remote_id=mod,
                            filename=f"{mod}_MDA.pdf",
                            doc_type="PDF",
                            download_hint="PDF MdA/EM",
                        )
                    )
                    logger.info("MdA dalla mail presente in pagina: %s", mod)
            except Exception:
                pass

        logger.info(
            "MdA rilevati: %s",
            ", ".join(d.remote_id or "?" for d in docs) or "(nessuno)",
        )
        return docs

    def _wait_detail_ready(self, page: Any) -> None:
        """Attende header dettaglio + tabella MdA (UI5 spesso carica in ritardo)."""
        import time

        # Busy indicator UI5
        for _ in range(40):
            try:
                busy = page.locator(
                    ".sapUiLocalBusyIndicator:visible, .sapUiBusy:visible"
                ).count()
                if busy == 0:
                    break
            except Exception:
                break
            time.sleep(0.25)

        # Header / pulsanti tipici del dettaglio
        for i in range(50):
            try:
                has_header = page.get_by_text("Numero Ordine", exact=False).count() > 0
                has_pdf_order = page.get_by_text("PDF Ordine", exact=False).count() > 0
                has_mda_col = page.get_by_text("MdA/EM", exact=False).count() > 0
                has_pdf_mda = (
                    page.get_by_text("PDF MdA", exact=False).count() > 0
                    or page.locator("button, .sapMBtn, [role=button]").filter(
                        has_text="PDF MdA"
                    ).count()
                    > 0
                )
                if has_pdf_mda or (has_header and has_mda_col) or (has_pdf_order and i > 8):
                    if has_pdf_mda or has_mda_col:
                        logger.info(
                            "Dettaglio pronto (pdf_mda=%s mda_col=%s header=%s) after %ss",
                            has_pdf_mda,
                            has_mda_col,
                            has_header,
                            round(i * 0.4, 1),
                        )
                        time.sleep(0.8)
                        return
            except Exception:
                pass
            time.sleep(0.4)

        # Scroll verso il basso: la tabella MdA può essere sotto la piega
        try:
            page.mouse.wheel(0, 800)
            time.sleep(0.6)
        except Exception:
            pass
        logger.warning("Timeout attesa tabella MdA — provo comunque lo scrape.")

    def _row_text_near(self, loc: Any) -> str:
        """Testo della riga/antenato vicino a un elemento PDF MdA."""
        try:
            row = loc.locator(
                "xpath=ancestor::tr[1] | "
                "xpath=ancestor::*[@role='row'][1] | "
                "xpath=ancestor::li[1] | "
                "xpath=ancestor::*[contains(@class,'sapMList')][1]"
            ).first
            if row.count():
                text = (row.inner_text(timeout=2000) or "").strip()
                if text:
                    return text
        except Exception:
            pass
        try:
            return (
                loc.evaluate(
                    """el => {
                      let p = el.parentElement;
                      for (let i = 0; i < 8 && p; i++, p = p.parentElement) {
                        const t = (p.innerText || '').trim();
                        if (t && t.length < 600 && /20\\d{8}/.test(t)) return t;
                      }
                      return (el.innerText || '').trim();
                    }"""
                )
                or ""
            )
        except Exception:
            return ""

    def _click_result_containing(self, needle: str) -> bool:
        """Clicca una riga/link risultato che contiene il testo cercato."""
        page = self.browser.page
        if not page or not needle:
            return False
        try:
            loc = page.get_by_text(needle, exact=False).first
            if loc.count() and loc.is_visible(timeout=2000):
                loc.click(timeout=3000)
                logger.info("Cliccato risultato contenente «%s»", needle)
                return True
        except Exception as exc:
            logger.debug("Click risultato %s fallito: %s", needle, exc)
        return False

    def download_attachment(
        self, attachment: AttachmentInfo, destination: str
    ) -> str:
        """
        Sul dettaglio ordine: trova la riga del Modulo di Acquisizione
        e clicca «PDF MdA/EM», salvando il file in ``destination``.
        """
        return self.browser.run(
            self._download_attachment_impl, attachment, destination
        )

    def _download_attachment_impl(
        self, attachment: AttachmentInfo, destination: str
    ) -> str:
        import re
        import time
        from pathlib import Path

        page = self.browser.page
        if not page:
            raise BrowserError("Browser non avviato.")

        module = (attachment.remote_id or "").strip()
        if not module and attachment.filename:
            m = re.search(r"(20\d{8})", attachment.filename)
            module = m.group(1) if m else ""
        if not module:
            raise PageStructureChangedError(
                "Numero Modulo di Acquisizione mancante per il download."
            )

        # Se non siamo sul dettaglio, riprova SOLO con l'ordine della ricerca corrente
        url = page.url or ""
        if "/ODA/" not in url.upper():
            order = (self._last_order_number or "").strip()
            if not order:
                raise PageStructureChangedError(
                    "Non sul dettaglio ordine e nessun ordine della ricerca corrente.\n"
                    "Eseguire prima la ricerca; non si riapre un ordine precedente."
                )
            logger.info(
                "Non sul dettaglio ordine: riapro ordine corrente %s prima del download",
                order,
            )
            if not self._open_order_detail(order):
                raise PageStructureChangedError(
                    f"Impossibile riaprire l'ordine corrente {order} per il download."
                )
            time.sleep(1.5)

        logger.info("Download PDF MdA/EM per modulo %s → %s", module, destination)

        # Assicura che la tabella sia pronta / scrollata
        self._wait_detail_ready(page)
        try:
            page.get_by_text(module, exact=False).first.scroll_into_view_if_needed(
                timeout=5000
            )
        except Exception:
            pass
        time.sleep(0.5)

        clicked = self._click_mda_pdf_button(page, module)
        if not clicked:
            raise PageStructureChangedError(
                f"Pulsante «PDF MdA/EM» non trovato per il modulo {module}.\n"
                "Controlla in Chrome la riga MdA e il pulsante giallo PDF."
            )

        dest = Path(destination)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Nome file tipico dal portale: 2013627432_MDA.pdf
        if dest.name.startswith("MdA_"):
            dest = dest.with_name(f"{module}_MDA.pdf")

        try:
            # Dopo click PDF: dialog Scarica, oppure scheda/blob PDF
            logger.info("Click PDF MdA eseguito — attendo dialog Scarica / PDF")
            time.sleep(1.2)

            try:
                shown = page.evaluate(
                    """() => {
                      const isVis = (el) => !!(el && (el.offsetParent || el.getClientRects().length));
                      return Array.from(document.querySelectorAll(
                        'button, [role=button], .sapMBtn, a'
                      )).filter(isVis).map(el => ({
                        t: (el.innerText||'').trim().slice(0,60),
                        title: (el.getAttribute('title')||'').slice(0,40),
                        aria: (el.getAttribute('aria-label')||'').slice(0,40),
                      })).filter(x => x.t || x.title || x.aria).slice(0, 40);
                    }"""
                )
                logger.info("Pulsanti dopo click PDF: %s", shown)
            except Exception:
                pass

            scarica = self._find_scarica_button(page)
            if scarica is None:
                saved = self._save_pdf_from_open_pages(dest, module)
                if saved:
                    return saved
                logger.warning("Dialog «Scarica» non trovato")
                raise TimeoutError("no-scarica-dialog")

            saved_path = None
            try:
                with page.expect_download(timeout=20000) as dl_info:
                    scarica.click(timeout=8000)
                download = dl_info.value
                suggested = download.suggested_filename or dest.name
                if suggested and suggested.lower().endswith(".pdf"):
                    dest = dest.with_name(suggested)
                download.save_as(str(dest))
                saved_path = str(dest)
                logger.info("PDF salvato via event download: %s", dest)
            except Exception as dl_exc:
                logger.info(
                    "Nessun event download (%s): provo scheda/blob PDF", dl_exc
                )
                time.sleep(1.0)
                saved_path = self._save_pdf_from_open_pages(dest, module)

            if not saved_path:
                raise TimeoutError("download-or-pdf-tab-missing")

            try:
                chiudi = page.get_by_role("button", name="Chiudi", exact=False).first
                if chiudi.count() and chiudi.is_visible(timeout=800):
                    chiudi.click(timeout=2000)
            except Exception:
                pass
            return saved_path
        except Exception as first_exc:
            logger.debug(
                "Percorso Scarica fallito (%s): tentativo download diretto", first_exc
            )
            try:
                scarica = self._find_scarica_button(page)
                if scarica is not None:
                    with page.expect_download(timeout=30000) as dl_info:
                        scarica.click(timeout=5000)
                    download = dl_info.value
                    suggested = download.suggested_filename or dest.name
                    if suggested and suggested.lower().endswith(".pdf"):
                        dest = dest.with_name(suggested)
                    download.save_as(str(dest))
                    logger.info("PDF salvato (retry Scarica): %s", dest)
                    return str(dest)

                saved = self._save_pdf_from_open_pages(dest, module)
                if saved:
                    return saved

                with page.expect_download(timeout=30000) as dl_info:
                    self._click_mda_pdf_button(page, module)
                download = dl_info.value
                suggested = download.suggested_filename or dest.name
                if suggested and suggested.lower().endswith(".pdf"):
                    dest = dest.with_name(suggested)
                download.save_as(str(dest))
                logger.info("PDF salvato (fallback click): %s", dest)
                return str(dest)
            except Exception as exc:
                logger.exception("Download PDF MdA fallito: %s", exc)
                raise TimeoutErrorEni(
                    f"Download PDF MdA/EM fallito per modulo {module}.\n"
                    "Flusso atteso: PDF MdA/EM → dialog → Scarica.\n"
                    f"Dettaglio: {exc}"
                ) from exc

    def _click_mda_pdf_button(self, page: Any, module: str) -> bool:
        """
        Clicca il controllo PDF della riga MdA corretta.

        Evita falsi positivi su id tipo ``mdalist`` / shell: usa la riga più
        stretta che contiene UN solo numero modulo, poi il controllo PDF lì
        (o alla stessa altezza, colonna fissa UI5).
        """
        import time

        # 1) Playwright: testo esatto visto nello screenshot / video
        try:
            row = page.locator(
                "tr, [role=row], li, .sapMLIB, .sapMListTblRow, .sapMListItems > *"
            ).filter(has_text=module)
            # restringi a righe con un solo modulo
            for i in range(min(row.count(), 30)):
                r = row.nth(i)
                try:
                    txt = (r.inner_text(timeout=1000) or "").strip()
                except Exception:
                    continue
                mods = __import__("re").findall(r"\b20\d{8}\b", txt)
                if len(set(mods)) != 1:
                    continue
                btn = r.locator(
                    "button, .sapMBtn, [role=button], a, .sapMBtnBase"
                ).filter(has_text="PDF")
                if btn.count() == 0:
                    btn = r.get_by_text("PDF MdA/EM", exact=False)
                if btn.count() == 0:
                    btn = r.locator("button, .sapMBtn, [role=button], a")
                if btn.count() == 0:
                    continue
                target = btn.first
                target.scroll_into_view_if_needed(timeout=3000)
                target.click(timeout=5000)
                logger.info("Click PDF nella riga stretta del modulo %s", module)
                return True
        except Exception as exc:
            logger.debug("Click riga Playwright fallito: %s", exc)

        # 2) JS: riga con un solo modulo + match PDF (testo/title) o nearest-Y
        try:
            result = page.evaluate(
                """(module) => {
                  const isVis = (el) => !!(el && (el.offsetParent || el.getClientRects().length));
                  const textOf = (el) => (el.innerText || el.textContent || '').trim();

                  // Riga più stretta con ESATTAMENTE questo modulo
                  const candidates = Array.from(document.querySelectorAll(
                    'tr, [role=row], li, .sapMLIB, .sapMListTblRow, .sapMListItems > *, div, td'
                  )).filter(isVis);

                  let row = null;
                  let bestLen = Infinity;
                  for (const el of candidates) {
                    const t = textOf(el);
                    if (!t.includes(module)) continue;
                    const mods = t.match(/\\b20\\d{8}\\b/g) || [];
                    const uniq = [...new Set(mods)];
                    if (uniq.length !== 1 || uniq[0] !== module) continue;
                    if (t.length < 8) continue;
                    if (t.length < bestLen) {
                      row = el;
                      bestLen = t.length;
                    }
                  }
                  if (!row) {
                    return { ok: false, reason: 'no-tight-row' };
                  }

                  const rowTop = row.getBoundingClientRect().top;
                  const rowBottom = row.getBoundingClientRect().bottom;
                  const rowMid = (rowTop + rowBottom) / 2;

                  const inRow = (el) => row.contains(el);
                  const sameBand = (el) => {
                    const r = el.getBoundingClientRect();
                    const mid = (r.top + r.bottom) / 2;
                    return Math.abs(mid - rowMid) < 28;
                  };

                  const allClick = Array.from(document.querySelectorAll(
                    'button, a, [role=button], .sapMBtn, .sapMBtnBase, [data-sap-ui*="Button"]'
                  )).filter(isVis);

                  const meta = [];
                  const scored = [];
                  for (const el of allClick) {
                    if (!inRow(el) && !sameBand(el)) continue;
                    const t = textOf(el);
                    const title = el.getAttribute('title') || '';
                    const aria = el.getAttribute('aria-label') || '';
                    const id = el.id || '';
                    // NON usare id per score (mdalist genera falsi positivi)
                    const blob = (t + ' ' + title + ' ' + aria).toLowerCase();
                    let s = 0;
                    if (/pdf/.test(blob)) s += 100;
                    if (/mda/.test(blob)) s += 40;
                    if (/scarica|download/.test(blob)) s += 20;
                    if (/pdf\\s*mda/i.test(t) || /pdf\\s*mda/i.test(title)) s += 50;
                    // preferisci controlli dentro la riga stretta
                    if (inRow(el)) s += 15;
                    // ignora chrome shell
                    if (/shell|marketplace|espandi|comprimi|navigazione|full.?screen|chiudi/i.test(blob + id)) {
                      s -= 200;
                    }
                    if (/mdalist--MDAMNGPage|enterFullSc|closeColumn|odaOverflo|btn_expand|btn_collap|shellAppTitle/i.test(id)) {
                      s -= 200;
                    }
                    meta.push({
                      text: t.slice(0, 50),
                      title: title.slice(0, 40),
                      aria: aria.slice(0, 40),
                      id: id.slice(0, 70),
                      score: s,
                      inRow: inRow(el),
                    });
                    if (s >= 40) scored.push({ el, s });
                  }

                  scored.sort((a, b) => b.s - a.s);
                  if (scored.length) {
                    scored[0].el.scrollIntoView({ block: 'center' });
                    scored[0].el.click();
                    return {
                      ok: true,
                      how: 'scored',
                      score: scored[0].s,
                      rowLen: bestLen,
                      meta: meta.sort((a,b)=>b.score-a.score).slice(0, 12),
                    };
                  }

                  // Nessun PDF testuale: qualsiasi bottone nella riga stretta
                  // (esclusi overflow), preferendo l'ultimo (azione a destra)
                  const rowBtns = allClick.filter(el => inRow(el) && !/overflow|overflo|more|opzioni/i.test(
                    (el.id||'') + (el.getAttribute('title')||'') + (el.getAttribute('aria-label')||'')
                  ));
                  if (rowBtns.length) {
                    const el = rowBtns[rowBtns.length - 1];
                    el.scrollIntoView({ block: 'center' });
                    el.click();
                    return {
                      ok: true,
                      how: 'last-in-row',
                      rowLen: bestLen,
                      meta: meta.slice(0, 12),
                      btnText: textOf(el).slice(0, 40),
                    };
                  }

                  // Colonna fissa: bottone nella stessa banda Y, a destra del testo modulo
                  const band = allClick
                    .filter(sameBand)
                    .filter(el => {
                      const id = el.id || '';
                      return !/shell|expand|collap|overflo|FullSc|closeColumn/i.test(id);
                    });
                  if (band.length) {
                    // più a destra = tipico pulsante azione
                    band.sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right);
                    band[0].scrollIntoView({ block: 'center' });
                    band[0].click();
                    return {
                      ok: true,
                      how: 'rightmost-same-y',
                      rowLen: bestLen,
                      meta: meta.slice(0, 12),
                      btnText: textOf(band[0]).slice(0, 40),
                    };
                  }

                  return {
                    ok: false,
                    reason: 'no-btn-in-row',
                    rowLen: bestLen,
                    rowText: textOf(row).slice(0, 180),
                    meta: meta.slice(0, 15),
                  };
                }""",
                module,
            )
            logger.info("Click PDF JS: %s", result)
            if result and result.get("ok"):
                time.sleep(0.4)
                return True
        except Exception as exc:
            logger.debug("Click PDF JS fallito: %s", exc)

        # 3) Click sul numero modulo (a volte apre il documento)
        try:
            link = page.get_by_text(module, exact=True).first
            if link.count() and link.is_visible(timeout=1500):
                link.click(timeout=4000)
                logger.info("Click sul numero modulo %s (fallback)", module)
                time.sleep(0.8)
                return True
        except Exception:
            pass

        return False

    def _find_scarica_button(self, page: Any) -> Any:
        """Trova il pulsante Scarica nel dialog anteprima MdA."""
        import re
        import time

        for _ in range(25):
            for factory in (
                lambda: page.get_by_role("button", name="Scarica", exact=True),
                lambda: page.get_by_role(
                    "button", name=re.compile(r"^\s*Scarica\s*$", re.I)
                ),
                lambda: page.locator(
                    ".sapMDialog button:has-text('Scarica'), "
                    "[role=dialog] button:has-text('Scarica'), "
                    ".sapMPopover button:has-text('Scarica'), "
                    "button:has-text('Scarica')"
                ),
                lambda: page.get_by_text("Scarica", exact=True),
                lambda: page.locator(
                    "button:has-text('Download'), button:has-text('Salva')"
                ),
            ):
                try:
                    loc = factory().first
                    if loc.count() and loc.is_visible(timeout=400):
                        return loc
                except Exception:
                    continue
            time.sleep(0.4)
        return None

    def _save_pdf_from_open_pages(self, dest: Any, module: str) -> Optional[str]:
        """Salva PDF se aperto in scheda/iframe/blob invece che come download."""
        import time
        from pathlib import Path

        dest = Path(dest)
        page = self.browser.page
        if not page:
            return None
        context = page.context
        time.sleep(1.0)

        pages = list(context.pages)
        for p in pages:
            try:
                url = (p.url or "").lower()
            except Exception:
                continue
            interesting = any(
                k in url
                for k in (".pdf", "blob:", "application/pdf", module.lower())
            )
            try:
                for frame in p.frames:
                    furl = (frame.url or "").lower()
                    if ".pdf" in furl or furl.startswith("blob:"):
                        interesting = True
            except Exception:
                pass
            if not interesting and p != page:
                # nuova scheda non-dashboard
                if "zmp_dsh" not in url and url not in ("about:blank", ""):
                    interesting = True
            if not interesting:
                continue

            data = None
            try:
                if url.endswith(".pdf") or url.startswith("blob:"):
                    data = p.evaluate(
                        """async () => {
                          const r = await fetch(location.href);
                          const buf = await r.arrayBuffer();
                          return Array.from(new Uint8Array(buf));
                        }"""
                    )
            except Exception:
                data = None
            if not data:
                try:
                    data = p.evaluate(
                        """async () => {
                          const nodes = [
                            ...document.querySelectorAll(
                              'embed[type*=pdf], object[type*=pdf], iframe'
                            )
                          ];
                          for (const n of nodes) {
                            const u = n.src || n.data || '';
                            if (!u) continue;
                            try {
                              const r = await fetch(u);
                              const buf = await r.arrayBuffer();
                              return Array.from(new Uint8Array(buf));
                            } catch (e) {}
                          }
                          return null;
                        }"""
                    )
                except Exception:
                    data = None
            if data and len(data) > 100:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(bytes(data))
                logger.info(
                    "PDF salvato da scheda/blob: %s (%s bytes)", dest, len(data)
                )
                return str(dest)

        # Link download nel dialog sulla pagina corrente
        try:
            href = page.evaluate(
                """() => {
                  const as = Array.from(document.querySelectorAll(
                    'a[href*=".pdf"], a[download], a[href^="blob:"]'
                  ));
                  for (const a of as) {
                    if (a.offsetParent || a.getClientRects().length) {
                      return a.href || a.getAttribute('href');
                    }
                  }
                  return null;
                }"""
            )
            if href:
                resp = context.request.get(href)
                body = resp.body()
                if body and len(body) > 100:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(body)
                    logger.info("PDF salvato via href: %s", dest)
                    return str(dest)
        except Exception as exc:
            logger.debug("Fetch href PDF fallito: %s", exc)
        return None

    def _marketplace_sso_probe(self) -> bool:
        self._assist_sso_login_once()
        current = self.browser.current_url() or ""
        return self._is_marketplace_url(current) or self._manual_login_probe()

    def open_document_flow(self) -> str:
        """
        Percorso osservato nel video (mail MdA → PDF):
          0. eniSpace online (area privata) — prerequisito
          1. Ordini e consuntivi (eniSpace)
          2. Click «Accedi a Marketplace» (nuova scheda)
          3. Tile «Consuntivazione» → dashboard filtri ZMP_DSH-DISPLAY
        """
        import time

        # Supervisor: prima eniSpace online, poi Marketplace
        self.ensure_enispace_online()

        logger.info("STEP 1/4 — Ordini e consuntivi")
        self.open_ordini()
        time.sleep(1.2)

        if not self._enispace_private_online():
            if not self._wait_for_sso_if_needed(
                max_wait_seconds=600,
                context="Ordini e consuntivi",
                require_enispace_private=True,
            ):
                raise LoginFailedError(
                    "Login eniSpace non completato su Ordini.\n"
                    "Completare MFA/SSO nella finestra Chrome e riprovare "
                    "prima di aprire Marketplace."
                )

        logger.info("STEP 2/4 — Accedi a Marketplace (pulsante pagina)")
        mp_url = self.browser.run(self._click_accedi_marketplace)
        if not mp_url:
            logger.info("Pulsante non trovato: fallback URL Marketplace diretto")
            mp_url = self.open_marketplace(force_direct=True)
        self.note_navigation_url(mp_url)

        time.sleep(1.5)
        current = self.browser.current_url() or ""
        if self._is_identity_provider_url(current):
            logger.info(
                "SSO richiesto per Marketplace: assist + login in Chrome..."
            )
            ok = self.browser.wait_for_manual_login(
                is_logged_in=self._marketplace_sso_probe,
                max_wait_seconds=300,
            )
            if not ok:
                raise LoginFailedError(
                    "Login Marketplace non completato.\n"
                    "Completare MFA/SSO nella finestra Chrome e riprovare."
                )
            self.note_navigation_url(self.browser.current_url())

        logger.info("STEP 3/4 — Tile Consuntivazione")
        opened = self.browser.run(self._click_consuntivazione_tile)
        if not opened:
            logger.info("Tile non trovata: goto diretto #ZMP_DSH-DISPLAY&/")
            return self.open_marketplace_dashboard()

        logger.info("STEP 4/4 — Attesa dashboard filtri")
        for _ in range(25):
            time.sleep(0.4)
            cur = self.browser.current_url() or ""
            if "ZMP_DSH-DISPLAY" in cur.upper():
                self.note_navigation_url(cur)
                self.browser.enable_interactive()
                logger.info("Dashboard filtri: %s", cur)
                return cur
        # Ultimo tentativo: hash diretto
        return self.open_marketplace_dashboard()

    def _click_accedi_marketplace(self) -> str:
        """Clicca «Accedi a Marketplace» su ordini e consuntivi; adotta la nuova scheda."""
        import time

        page = self.browser.page
        if not page:
            raise BrowserError("Browser non avviato.")

        btn = None
        for factory in (
            lambda: page.get_by_role("button", name="Accedi a Marketplace", exact=False),
            lambda: page.get_by_role("link", name="Accedi a Marketplace", exact=False),
            lambda: page.get_by_text("Accedi a Marketplace", exact=False),
        ):
            try:
                loc = factory().first
                if loc.count() and loc.is_visible(timeout=2500):
                    btn = loc
                    break
            except Exception:
                continue
        if btn is None:
            logger.warning("Pulsante «Accedi a Marketplace» non trovato.")
            return ""

        logger.info("Click «Accedi a Marketplace»")
        try:
            with page.context.expect_page(timeout=15000) as new_page_info:
                btn.click(timeout=8000)
            new_page = new_page_info.value
            try:
                new_page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            try:
                self.browser._adopt_page(new_page, reason="accedi-marketplace")  # type: ignore[attr-defined]
            except Exception:
                pass
            time.sleep(1.0)
            url = new_page.url or self.browser.current_url() or ""
            logger.info("Marketplace aperto: %s", url)
            return url
        except Exception as exc:
            logger.info("Nessuna nuova scheda (%s): resto sulla corrente", exc)
            try:
                btn.click(timeout=5000)
            except Exception:
                pass
            time.sleep(2.0)
            url = self.browser.current_url() or ""
            return url if self._is_marketplace_url(url) else ""

    def _click_consuntivazione_tile(self) -> bool:
        """Sulla launchpad Marketplace clicca la tile «Consuntivazione»."""
        import time

        page = self.browser.page
        if not page:
            return False

        # Già sulla dashboard filtri (non sul dettaglio ODA)
        url_u = (page.url or "").upper()
        if "ZMP_DSH-DISPLAY" in url_u and "/ODA/" not in url_u:
            return True

        for _ in range(20):
            try:
                tile = page.get_by_text("Consuntivazione", exact=True).first
                if tile.count() and tile.is_visible(timeout=800):
                    tile.click(timeout=5000)
                    logger.info("Click tile «Consuntivazione»")
                    time.sleep(1.5)
                    return True
            except Exception:
                pass
            # Varianti: link/tile role
            try:
                loc = page.locator(
                    "[data-targeturl*='ZMP_DSH'], "
                    "a:has-text('Consuntivazione'), "
                    "div.sapUshellTile:has-text('Consuntivazione')"
                ).first
                if loc.count() and loc.is_visible(timeout=500):
                    loc.click(timeout=5000)
                    logger.info("Click tile Consuntivazione (selettore UI5)")
                    time.sleep(1.5)
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        logger.warning("Tile «Consuntivazione» non trovata.")
        return False

    def open_marketplace_dashboard(self) -> str:
        """Apre #ZMP_DSH-DISPLAY&/ sull'host Marketplace corrente/imparato."""
        base = self.resolve_marketplace_url()
        url = marketplace_dashboard_url_from(base)
        Selectors.MARKETPLACE_DASHBOARD_URL = url
        self.ensure_browser()
        self.browser.enable_interactive()
        logger.info("Apertura dashboard filtri Marketplace: %s", url)
        self.browser.goto(url, wait_until="domcontentloaded")
        final = self.browser.current_url() or url
        self.note_navigation_url(final)
        return final

    def return_to_dashboard_filters(self) -> str:
        """
        Chiude il dettaglio ordine (dialog/colonna ODA) e torna alla worklist
        con i campi filtro ``iODAnumber`` / ``iCTRnumber`` visibili e vuoti.
        """
        return self.browser.run(self._return_to_dashboard_filters_impl)

    def _return_to_dashboard_filters_impl(self) -> str:
        import time

        page = self.browser.page
        if not page:
            raise BrowserError("Browser non avviato.")

        # Evita riuso ordine precedente sulla mail successiva
        self._last_order_number = ""
        self._last_acquisition_module = None

        url = page.url or ""
        base = url if "ZMP_DSH" in url.upper() else (self.resolve_marketplace_url() or url)
        clean = marketplace_dashboard_url_from(base or ENISPACE_MARKETPLACE_DASHBOARD_URL)
        Selectors.MARKETPLACE_DASHBOARD_URL = clean

        on_detail = "/ODA/" in url.upper()
        filters_ok = self._filter_fields_ready(page)
        if on_detail or not filters_ok:
            logger.info(
                "Ritorno alla dashboard filtri (dettaglio=%s filtri_ok=%s)",
                on_detail,
                filters_ok,
            )
            self._try_close_order_detail(page)
            time.sleep(0.4)
            try:
                page.goto(clean, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                logger.debug("goto filtri fallito (%s), retry", exc)
                try:
                    page.evaluate(
                        "(u) => { window.location.hash = 'ZMP_DSH-DISPLAY&/'; }",
                        clean,
                    )
                except Exception:
                    pass
            time.sleep(0.8)

        if not self._wait_filter_fields_ready(page, timeout_s=20):
            logger.warning(
                "Filtri non visibili: ritento Chiudi + navigazione %s", clean
            )
            self._try_close_order_detail(page)
            try:
                page.goto(clean, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            time.sleep(1.0)
            if not self._wait_filter_fields_ready(page, timeout_s=15):
                logger.warning(
                    "Campi iODAnumber/iCTRnumber ancora non visibili dopo ritorno."
                )

        self._clear_dashboard_filter_inputs(page)
        final = page.url or clean
        self.note_navigation_url(final)
        return final

    def _filter_fields_ready(self, page: Any) -> bool:
        """True solo se Ordine e Contratto worklist sono presenti e visibili."""
        try:
            oda = page.locator(Selectors.FILTER_ORDER_INPUT).first
            if oda.count() == 0 or not oda.is_visible(timeout=400):
                return False
            ctr = page.locator(Selectors.FILTER_CONTRACT_INPUT).first
            if ctr.count() == 0 or not ctr.is_visible(timeout=400):
                return False
            return True
        except Exception:
            return False

    def _wait_filter_fields_ready(self, page: Any, *, timeout_s: float = 20) -> bool:
        import time

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._filter_fields_ready(page):
                return True
            time.sleep(0.4)
        return False

    def _try_close_order_detail(self, page: Any) -> None:
        """Chiude dialog PDF / dettaglio ODA (Chiudi, Escape, closeColumn)."""
        import time

        try:
            page.keyboard.press("Escape")
            time.sleep(0.25)
        except Exception:
            pass

        for name in ("Chiudi", "Close"):
            try:
                btns = page.get_by_role("button", name=name, exact=False)
                n = min(btns.count(), 4)
                for i in range(n):
                    b = btns.nth(i)
                    try:
                        if b.is_visible(timeout=300):
                            b.click(timeout=1500)
                            logger.info("Click «%s» per chiudere overlay/dettaglio", name)
                            time.sleep(0.35)
                    except Exception:
                        continue
            except Exception:
                pass

        try:
            loc = page.locator(
                "[id*='closeColumn'], button[title*='Chiudi' i], "
                "button[aria-label*='Chiudi' i], "
                ".sapMDialog .sapMDialogCloseBtn, "
                "[data-sap-ui*='closeColumn']"
            ).first
            if loc.count() and loc.is_visible(timeout=400):
                loc.click(timeout=1500)
                logger.info("Click closeColumn / dialog close")
                time.sleep(0.35)
        except Exception:
            pass

    def _clear_dashboard_filter_inputs(self, page: Any) -> None:
        """Svuota Ordine e Contratto prima di una nuova ricerca."""
        for sel, label in (
            (Selectors.FILTER_ORDER_INPUT, "Ordine"),
            (Selectors.FILTER_CONTRACT_INPUT, "Contratto"),
        ):
            if not _selector_ready(sel):
                continue
            try:
                loc = page.locator(sel).first
                if loc.count() == 0 or not loc.is_visible(timeout=600):
                    continue
                loc.click(timeout=1500)
                try:
                    loc.fill("")
                except Exception:
                    loc.press("Control+a")
                    loc.press("Backspace")
                try:
                    loc.press("Tab")
                except Exception:
                    pass
                logger.info("Filtro %s svuotato", label)
            except Exception as exc:
                logger.debug("Clear filtro %s fallito: %s", label, exc)

    def apply_dashboard_filters(
        self,
        *,
        order_number: str,
        framework_contract: Optional[str] = None,
        acquisition_module: Optional[str] = None,
    ) -> bool:
        """
        Compila i filtri sulla dashboard ZMP_DSH-DISPLAY.

        Usa selettori espliciti worklist (iODAnumber / iCTRnumber). Non compila
        input clone senza etichetta (vista dettaglio). Restituisce True se
        almeno un campo è stato compilato.
        """
        return self.browser.run(
            self._apply_dashboard_filters_impl,
            order_number,
            framework_contract,
            acquisition_module,
        )

    def _apply_dashboard_filters_impl(
        self,
        order_number: str,
        framework_contract: Optional[str],
        acquisition_module: Optional[str],
    ) -> bool:
        import time

        page = self.browser.page
        if not page:
            raise BrowserError("Browser non avviato.")

        _ = acquisition_module  # MdA non è nella barra filtri

        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

        # Attendi campi worklist VISIBILI (count>0 non basta: restano nel DOM sotto ODA)
        if not self._wait_filter_fields_ready(page, timeout_s=12):
            url = (page.url or "").upper()
            if "/ODA/" in url or "ZMP_DSH-DISPLAY" in url:
                logger.info(
                    "Filtri non pronti in apply: forzatura ritorno worklist"
                )
                self._try_close_order_detail(page)
                clean = marketplace_dashboard_url_from(
                    page.url or ENISPACE_MARKETPLACE_DASHBOARD_URL
                )
                try:
                    page.goto(clean, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                time.sleep(0.8)
            if not self._wait_filter_fields_ready(page, timeout_s=15):
                self._log_visible_inputs(page)
                logger.warning(
                    "Campi filtro iODAnumber/iCTRnumber non visibili: "
                    "niente fill su clone."
                )
                return False

        time.sleep(0.3)
        self._clear_dashboard_filter_inputs(page)
        self._log_visible_inputs(page)

        filled = 0
        self._debug_action("apply_dashboard_filters", order_number)
        filled_values: set[str] = set()

        # 1) Selettori espliciti worklist — Ordine e Contratto
        if order_number and _selector_ready(Selectors.FILTER_ORDER_INPUT):
            if self._fill_locator(page, Selectors.FILTER_ORDER_INPUT, order_number):
                filled += 1
                filled_values.add(order_number)
                logger.info("Filtro Ordine (ODA) compilato: %s", order_number)
        if framework_contract and _selector_ready(Selectors.FILTER_CONTRACT_INPUT):
            if self._fill_locator(
                page, Selectors.FILTER_CONTRACT_INPUT, framework_contract
            ):
                filled += 1
                filled_values.add(framework_contract)
                logger.info("Filtro Contratto (CTR) compilato: %s", framework_contract)

        # 2) Fallback solo se i campi worklist esistono (niente clone)
        if (
            order_number
            and order_number not in filled_values
            and self._filter_fields_ready(page)
        ):
            if self._fill_by_labels(
                page, order_number, ("numero ordine",)
            ):
                filled += 1
                filled_values.add(order_number)
                logger.info("Filtro Numero Ordine via label: %s", order_number)

        if (
            framework_contract
            and framework_contract not in filled_values
            and self._filter_fields_ready(page)
        ):
            if self._fill_by_labels(
                page, framework_contract, ("numero contratto", "contratto")
            ):
                filled += 1
                filled_values.add(framework_contract)
                logger.info("Filtro Contratto via label: %s", framework_contract)

        # 3) Euristica UI5 solo sui campi worklist (id iODA/iCTR), mai su __clone
        if self._filter_fields_ready(page):
            mapping = [
                (
                    order_number,
                    ("numero ordine", "n.ordine", "n. ordine", "n° ordine"),
                ),
                (
                    framework_contract,
                    ("numero contratto", "n. contratto", "contratto"),
                ),
            ]
            for value, labels in mapping:
                if not value or value in filled_values:
                    continue
                if self._fill_ui5_by_labels(page, value, labels):
                    filled += 1
                    filled_values.add(value)
                    logger.info("Filtro UI5/DOM ok per %s", value)

        if framework_contract and framework_contract not in filled_values:
            logger.warning(
                "Contratto %s non compilato (ordine ok=%s)",
                framework_contract,
                order_number in filled_values,
            )

        # Pulsante giallo «Cerca» — obbligatorio dopo i filtri
        clicked = False
        if filled > 0:
            clicked = self._click_cerca_button(page)
            if not clicked:
                try:
                    page.locator(Selectors.FILTER_ORDER_INPUT).first.press("Enter")
                    logger.info("Fallback: Enter sul campo Ordine.")
                    clicked = True
                except Exception:
                    pass
            if clicked:
                time.sleep(2.0)

        if filled == 0:
            logger.warning(
                "Nessun campo filtro trovato automaticamente sulla dashboard."
            )
            return False

        logger.info("Filtri compilati: %d campo/i.", filled)
        return True

    def _log_visible_inputs(self, page: Any) -> None:
        """Scrive nel log tecnico campi input + etichette UI5 (per mappare i filtri)."""
        try:
            data = page.evaluate(
                """() => {
                  const isVis = (el) => !!(el && (el.offsetParent || el.getClientRects().length));
                  const inputs = Array.from(document.querySelectorAll(
                    'input.sapMInputBaseInner, input:not([type=hidden]), textarea, [role=textbox]'
                  )).filter(isVis).slice(0, 50).map((el, i) => {
                    let nearLabel = '';
                    let p = el.parentElement;
                    for (let d = 0; d < 6 && p; d++, p = p.parentElement) {
                      const lab = p.querySelector('.sapMLabel, label, [class*=Label]');
                      if (lab && lab.textContent) {
                        nearLabel = lab.textContent.trim().slice(0, 80);
                        break;
                      }
                    }
                    return {
                      i,
                      id: el.id || '',
                      name: el.getAttribute('name') || '',
                      placeholder: el.getAttribute('placeholder') || '',
                      aria: el.getAttribute('aria-label') || '',
                      title: el.getAttribute('title') || '',
                      nearLabel,
                      cls: (el.className || '').toString().slice(0, 60)
                    };
                  });
                  const labels = Array.from(document.querySelectorAll(
                    '.sapMLabel, label, .sapMSelectListItemText'
                  )).filter(isVis).map(el => (el.textContent || '').trim())
                    .filter(t => t.length > 1 && t.length < 80).slice(0, 40);
                  return { inputs, labels };
                }"""
            )
            inputs = (data or {}).get("inputs") or []
            labels = (data or {}).get("labels") or []
            logger.info("Campi visibili dashboard: %d", len(inputs))
            for item in inputs:
                logger.info(
                    "  input[%s] nearLabel=%s aria=%s placeholder=%s id=%s",
                    item.get("i"),
                    item.get("nearLabel") or "—",
                    item.get("aria") or "—",
                    item.get("placeholder") or "—",
                    (item.get("id") or "—")[:60],
                )
            if labels:
                logger.info("Etichette UI visibili: %s", " | ".join(labels[:25]))
        except Exception as exc:
            logger.debug("Dump input fallito: %s", exc)

    def _fill_locator(self, page: Any, selector: str, value: str) -> bool:
        try:
            loc = page.locator(selector).first
            loc.wait_for(state="visible", timeout=8000)
            loc.click(timeout=3000)
            try:
                loc.fill("")
            except Exception:
                pass
            loc.fill(value, timeout=5000)
            # Forza eventi UI5
            try:
                loc.press("Tab")
            except Exception:
                pass
            return True
        except Exception as exc:
            logger.debug("Fill selector %s fallito: %s", selector, exc)
            # Fallback: type carattere per carattere
            try:
                loc = page.locator(selector).first
                loc.click(timeout=3000)
                loc.press("Control+a")
                loc.type(value, delay=40)
                return True
            except Exception as exc2:
                logger.debug("Type fallback %s fallito: %s", selector, exc2)
                return False

    def _click_locator(self, page: Any, selector: str) -> bool:
        try:
            loc = page.locator(selector).first
            loc.wait_for(state="visible", timeout=5000)
            loc.click()
            return True
        except Exception as exc:
            logger.debug("Click selector %s fallito: %s", selector, exc)
            return False

    def _fill_by_labels(self, page: Any, value: str, labels: tuple[str, ...]) -> bool:
        for label in labels:
            candidates = [
                lambda lbl=label: page.get_by_label(lbl, exact=False),
                lambda lbl=label: page.get_by_placeholder(lbl, exact=False),
                lambda lbl=label: page.locator(
                    f"input[aria-label*='{lbl}' i], "
                    f"input[placeholder*='{lbl}' i], "
                    f"input[title*='{lbl}' i]"
                ),
            ]
            for factory in candidates:
                try:
                    loc = factory().first
                    if loc.count() == 0:
                        continue
                    if not loc.is_visible(timeout=1500):
                        continue
                    loc.click(timeout=2000)
                    loc.fill(value, timeout=3000)
                    logger.info("Campo trovato con label/placeholder «%s»", label)
                    return True
                except Exception:
                    continue
        return False

    def _fill_ui5_by_labels(
        self, page: Any, value: str, labels: tuple[str, ...]
    ) -> bool:
        """Compila input SAP UI5 abbinando testo etichetta vicino al campo."""
        try:
            ok = page.evaluate(
                """({ value, labels }) => {
                  const norm = (s) => (s || '').toLowerCase()
                    .normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                    .replace(/\\s+/g, ' ').trim();
                  const wants = labels.map(norm).filter(Boolean);
                  const isVis = (el) => !!(el && (el.offsetParent || el.getClientRects().length));
                  const inputs = Array.from(document.querySelectorAll(
                    'input.sapMInputBaseInner, input:not([type=hidden]), textarea'
                  )).filter(isVis).filter((el) => {
                    const id = (el.id || '');
                    // Mai compilare clone del dettaglio ODA
                    if (/__clone/i.test(id)) return false;
                    return true;
                  });

                  const scoreFor = (text) => {
                    const t = norm(text);
                    if (!t) return 0;
                    for (const w of wants) {
                      if (w.length < 4) continue; // evita match ambigui (oda, …)
                      if (t === w) return 100;
                      if (t.includes(w)) return 80 - Math.min(30, t.length - w.length);
                    }
                    return 0;
                  };

                  let best = null;
                  let bestScore = 0;
                  for (const el of inputs) {
                    const id = el.id || '';
                    // Preferisci i campi worklist stabili
                    if (/iODAnumber|iCTRnumber/i.test(id)) {
                      const bits = [
                        el.getAttribute('aria-label'),
                        'numero ordine',
                        'contratto',
                      ];
                      let sc = 0;
                      for (const b of bits) sc = Math.max(sc, scoreFor(b));
                      if (/iODAnumber/i.test(id) && wants.some(w => w.includes('ordin')))
                        sc = Math.max(sc, 95);
                      if (/iCTRnumber/i.test(id) && wants.some(w => w.includes('contratt')))
                        sc = Math.max(sc, 95);
                      if (sc > bestScore) { bestScore = sc; best = el; }
                      continue;
                    }
                    const bits = [
                      el.getAttribute('aria-label'),
                      el.getAttribute('placeholder'),
                      el.getAttribute('title'),
                      el.getAttribute('name'),
                    ];
                    let p = el.parentElement;
                    for (let d = 0; d < 8 && p; d++, p = p.parentElement) {
                      const labs = p.querySelectorAll(
                        '.sapMLabel, label, [class*="Label"], .sapMText'
                      );
                      for (const lab of labs) {
                        if (isVis(lab)) bits.push(lab.textContent || '');
                      }
                      if ((p.className || '').toString().match(/Filter|SmartField|FormItem/i)) {
                        bits.push((p.innerText || '').split('\\n')[0]);
                      }
                    }
                    let sc = 0;
                    for (const b of bits) sc = Math.max(sc, scoreFor(b));
                    if (sc > bestScore) {
                      bestScore = sc;
                      best = el;
                    }
                  }
                  if (!best || bestScore < 50) return { ok: false, score: bestScore };

                  best.focus();
                  best.click();
                  const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                  )?.set;
                  if (setter) setter.call(best, value);
                  else best.value = value;
                  best.dispatchEvent(new Event('input', { bubbles: true }));
                  best.dispatchEvent(new Event('change', { bubbles: true }));
                  best.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }));
                  best.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter' }));
                  return {
                    ok: true,
                    score: bestScore,
                    id: best.id || '',
                    aria: best.getAttribute('aria-label') || ''
                  };
                }""",
                {"value": value, "labels": list(labels)},
            )
            if ok and ok.get("ok"):
                logger.info(
                    "UI5 fill «%s» score=%s id=%s aria=%s",
                    value,
                    ok.get("score"),
                    (ok.get("id") or "—")[:50],
                    ok.get("aria") or "—",
                )
                return True
        except Exception as exc:
            logger.debug("UI5 fill fallito per %s: %s", value, exc)
        return False

    def _click_filter_go(self, page: Any) -> bool:
        """Clicca Go/Cerca tipici della FilterBar Fiori."""
        if self._click_cerca_button(page):
            return True
        # Selettori comuni UI5 FilterBar (classi, non ID inventati)
        ui5_selectors = (
            "button.sapUiCompFilterBarGoButton",
            "button[id*='btnGo']",
            "button[id*='BtnGo']",
            "button[id*='filterbar'][id*='btn']",
            ".sapUiCompFilterBar .sapMBtn",
        )
        for sel in ui5_selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible(timeout=800):
                    loc.click(timeout=2500)
                    logger.info("Click filtro via %s", sel)
                    return True
            except Exception:
                continue
        return self._click_by_texts(
            page,
            (
                "Vai",
                "Go",
                "Cerca",
                "Search",
                "Esegui",
                "Filtra",
                "Applica",
                "Avvia",
                "OK",
            ),
        )

    def _click_cerca_button(self, page: Any) -> bool:
        """Clicca il pulsante giallo «Cerca» della dashboard (video)."""
        import re

        candidates = [
            lambda: page.get_by_role("button", name=re.compile(r"^\s*Cerca\s*$", re.I)),
            lambda: page.get_by_role("button", name="Cerca", exact=False),
            lambda: page.locator("button:has-text('Cerca'), bdi:has-text('Cerca')"),
        ]
        for factory in candidates:
            try:
                loc = factory().first
                if loc.count() == 0:
                    continue
                if not loc.is_visible(timeout=2000):
                    continue
                loc.click(timeout=4000)
                logger.info("Click pulsante «Cerca»")
                return True
            except Exception:
                continue
        return False

    def _click_by_texts(self, page: Any, texts: tuple[str, ...]) -> bool:
        for text in texts:
            try:
                btn = page.get_by_role("button", name=text, exact=False).first
                if btn.count() and btn.is_visible(timeout=1500):
                    btn.click(timeout=3000)
                    return True
            except Exception:
                pass
            try:
                loc = page.get_by_text(text, exact=False).first
                if loc.count() and loc.is_visible(timeout=1000):
                    loc.click(timeout=3000)
                    return True
            except Exception:
                pass
        return False

    # ------------------------------------------------------------------ high-level
    def open_ordini(self) -> str:
        """
        Apre «I miei ordini e consuntivi» su eniSpace (URL stabile dalla mail).
        Se la sessione non è valida, resta sull'IdP e attende SSO (non naviga via).
        """
        url = Selectors.ORDINI_URL or ENISPACE_ORDINI_URL
        self.ensure_browser()
        self.browser.enable_interactive()
        logger.info("Apertura Ordini e consuntivi (eniSpace stabile): %s", url)
        self.browser.goto(url, wait_until="domcontentloaded")
        current = self.browser.current_url() or url
        if self._is_identity_provider_url(current) or not self._url_looks_authenticated(
            current
        ):
            if not self._wait_for_sso_if_needed(
                max_wait_seconds=600,
                context="Ordini e consuntivi",
                require_enispace_private=True,
            ):
                raise LoginFailedError(
                    "Login eniSpace non completato.\n"
                    "Completare MFA/SSO nella finestra Chrome e riprovare."
                )
            current = self.browser.current_url() or url
        return current

    def open_marketplace(self, *, force_direct: bool = False) -> str:
        """
        Apre il Marketplace FLP.

        L'host (UUID.abap-web...) può cambiare: usiamo l'ultimo URL imparato
        dalla navigazione reale. Preferire open_ordini() quando possibile.
        """
        url = self.resolve_marketplace_url()
        self.ensure_browser()
        self.browser.enable_interactive()

        current = self.browser.current_url() or ""
        if self._is_identity_provider_url(current):
            logger.info(
                "SSO Microsoft in corso: attendo il login prima di aprire Marketplace."
            )
            if not self._wait_for_sso_if_needed(
                max_wait_seconds=600,
                context="Marketplace (pre-navigazione)",
            ):
                raise LoginFailedError(
                    "Login Microsoft non completato.\n"
                    "Completare MFA/SSO nella finestra Chrome e riprovare."
                )

        if force_direct:
            logger.info("Apertura diretta Marketplace (ultimo URL noto): %s", url)
            self.browser.goto(url, wait_until="domcontentloaded")
            final = self.browser.current_url() or url
            self.note_navigation_url(final)
            return final

        current = self.browser.current_url()
        if current and self._is_marketplace_url(current):
            logger.info("Marketplace già aperto: %s", current)
            self.note_navigation_url(current)
            return current

        if not current or current == "about:blank" or not self._is_marketplace_url(current):
            logger.info(
                "Navigazione Marketplace con URL risolto (può aggiornarsi al prossimo click da eniSpace)."
            )
            self.browser.goto(url, wait_until="domcontentloaded")
            final = self.browser.current_url() or url
            if not final or final == "about:blank":
                self.browser.new_page()
                self.browser.goto(url, wait_until="load")
                final = self.browser.current_url() or url
            self.note_navigation_url(final)
            logger.info("Marketplace URL attivo: %s", final)
            return final

        return current

    def test_access(self) -> tuple[bool, str]:
        """
        Test esclusivo sessione/login (Impostazioni → TEST ACCESSO ENISPACE).
        Non esegue ricerca contratti.
        """
        try:
            logger.info("Connessione a eniSpace...")
            self.login(allow_manual=True)
            home = self.base_url or Selectors.BASE_URL
            if home:
                current = self.browser.current_url()
                if not current or current == "about:blank" or "enispace.eni.com" not in current:
                    try:
                        self.browser.goto(home)
                    except Exception as exc:
                        logger.warning("Goto home dopo login: %s", exc)
            self.browser.enable_interactive()

            if self.is_logged_in() or self._session_active or self._manual_login_probe():
                logger.info("Sessione valida.")
                self._session_active = True
                return True, "Accesso eniSpace riuscito. Sessione attiva."

            raise SessionExpiredError(
                "Sessione eniSpace non confermata.\n"
                "Completare il login Microsoft/SSO in Chrome e riprovare."
            )
        except SelectorsNotConfiguredError as exc:
            return False, exc.message
        except (
            CredentialsMissingError,
            LoginFailedError,
            NetworkError,
            PortalUnreachableError,
            TimeoutErrorEni,
            BrowserError,
            SessionExpiredError,
        ) as exc:
            return False, exc.message
        except Exception as exc:
            logger.exception("Test accesso: errore imprevisto")
            return False, (
                "Errore durante il test di accesso. Consultare il log tecnico."
            )

    def start_navigation_recording(self) -> None:
        """Apre Google Chrome visibile per mappare login/ricerca/allegati."""
        self.browser.config.headless = False
        self.browser.config.hidden = False
        self.browser.config.debug = True
        page = self.browser.start_recording()
        url = self.base_url or Selectors.BASE_URL
        if url:
            try:
                self.browser.goto(url)
            except Exception as exc:
                logger.warning("Impossibile aprire URL base: %s", exc)
        else:
            logger.info(
                "Nessun URL configurato: navigare manualmente verso eniSpace "
                "nella finestra Chrome."
            )
        self.browser.enable_interactive()
        logger.info(
            "REGISTRA NAVIGAZIONE: login manuale consentito. "
            "Pump eventi CDP attivo (popup/schede). "
            "Se Marketplace resta blank: usare «Apri Marketplace»."
        )
        _ = page

    def attachments_to_documents(
        self, contract_id: int, attachments: list[AttachmentInfo]
    ) -> list[Document]:
        docs: list[Document] = []
        for att in attachments:
            docs.append(
                Document(
                    contract_id=contract_id,
                    remote_id=att.remote_id,
                    filename=att.filename,
                    doc_type=att.doc_type,
                    remote_date=att.remote_date,
                    size=att.size,
                    status=DocumentStatus.NEW,
                )
            )
        return docs
