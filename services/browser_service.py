"""Gestione browser Playwright con profilo persistente.

Playwright sync API è vincolato a un solo thread: tutte le operazioni
passano da un executor dedicato. L'executor esegue anche un pump CDP
periodico così popup/nuove schede (es. Marketplace) non restano su about:blank.

Avvio allineato a VIS eniSpace Utility:
launch_persistent_context + channel=chrome + data/browser-profile.
"""

from __future__ import annotations

import queue
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar
from urllib.parse import urlparse

from utils.logger import get_logger
from utils.paths import (
    CHROME_ENISPACE_APP_ID,
    ENISPACE_STARTUP_URL,
    browser_profile_dir,
    chrome_cdp_user_data_dir,
    chrome_executable_path,
    chrome_proxy_executable_path,
    chrome_system_user_data_dir,
    resolve_browser_user_data_dir,
    sync_system_chrome_profile_to_cdp,
)

logger = get_logger("browser")

BrowserContext = Any
BrowserPage = Any
Playwright = Any

CHROME_CHANNEL = "chrome"
# Porta CDP dedicata VISION (evita 9222 già usata da altri tool)
VISION_CDP_PORT_DEFAULT = 9333

T = TypeVar("T")


class PlaywrightExecutor:
    """Thread unico che esegue tutto il codice Playwright sync + pump eventi."""

    def __init__(self) -> None:
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._loop, name="playwright-thread", daemon=True
        )
        self._started = False
        self._lock = threading.Lock()
        self._pump: Optional[Callable[[], None]] = None

    def set_pump(self, pump: Optional[Callable[[], None]]) -> None:
        self._pump = pump

    def ensure_started(self) -> None:
        with self._lock:
            if not self._started:
                self._thread.start()
                self._started = True

    def _loop(self) -> None:
        while True:
            try:
                item = self._q.get(timeout=0.2)
            except queue.Empty:
                pump = self._pump
                if pump is not None:
                    try:
                        pump()
                    except Exception:
                        pass
                continue

            if item is None:
                break
            fn, args, kwargs, box = item
            try:
                box["result"] = fn(*args, **kwargs)
            except BaseException as exc:
                box["error"] = exc
            finally:
                box["event"].set()

    def run(
        self,
        fn: Callable[..., T],
        *args: Any,
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> T:
        self.ensure_started()
        if threading.current_thread() is self._thread:
            return fn(*args, **kwargs)

        event = threading.Event()
        box: dict[str, Any] = {"event": event, "result": None, "error": None}
        self._q.put((fn, args, kwargs, box))
        if not event.wait(timeout=timeout):
            raise TimeoutError(
                f"Timeout operazione browser "
                f"({int(timeout) if timeout else '?'}s)."
            )
        if box["error"] is not None:
            raise box["error"]
        return box["result"]

    def stop(self) -> None:
        if self._started:
            self._q.put(None)


_executor = PlaywrightExecutor()


@dataclass
class BrowserConfig:
    headless: bool = False
    # Finestra headed ma nascosta (off-screen / win32). Preferire a headless
    # per eniSpace/SAP UI5 e cookie di sessione; MFA richiede show temporaneo.
    hidden: bool = False
    timeout_ms: int = 60000
    debug: bool = False
    user_data_dir: Optional[Path] = None
    downloads_path: Optional[Path] = None
    channel: str = CHROME_CHANNEL
    # Usa Chrome di sistema + profilo Default — DEPRECATO (Chrome 151+).
    # Il launch usa sempre il profilo isolato data/browser-profile (come Utility).
    use_system_chrome_profile: bool = False
    chrome_profile_directory: str = "Default"
    executable_path: Optional[str] = None
    # PWA eniSpace (non usato nel launch Utility-style)
    chrome_app_id: str = CHROME_ENISPACE_APP_ID
    # Pagina iniziale (home.page come Utility)
    startup_url: str = ENISPACE_STARTUP_URL


class BrowserService:
    """Avvia e gestisce Google Chrome via Playwright con sessione persistente."""

    def __init__(self, config: Optional[BrowserConfig] = None) -> None:
        self.config = config or BrowserConfig()
        self._playwright: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[BrowserPage] = None
        self._cdp_browser: Any = None
        self._chrome_proc: Optional[subprocess.Popen] = None
        self._owns_chrome: bool = False
        self._cdp_port: Optional[int] = None
        self._recording = False
        self._interactive = False
        self._nav_log: list[dict] = []
        self._known_pages: set[int] = set()
        self._chrome_pids: set[int] = set()
        self.on_url_seen: Optional[Callable[[str], None]] = None

    @property
    def page(self) -> Optional[BrowserPage]:
        return self._page

    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context

    @property
    def is_open(self) -> bool:
        return self._context is not None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def is_interactive(self) -> bool:
        return self._interactive

    def _debug(self, action: str, detail: str = "", error: str = "") -> None:
        if self.config.debug or self._recording:
            entry = {
                "action": action,
                "detail": detail,
                "error": error,
                "url": "",
            }
            try:
                if self._page:
                    entry["url"] = self._page.url
            except Exception:
                pass
            self._nav_log.append(entry)
            msg = f"[DEBUG] {action}"
            if detail:
                msg += f" | {detail}"
            if entry["url"]:
                msg += f" | URL={entry['url']}"
            if error:
                msg += f" | ERR={error}"
            logger.debug(msg)

    def start(self) -> BrowserPage:
        """Apre Google Chrome con profilo persistente (sul thread Playwright)."""
        try:
            return _executor.run(self._start_impl, timeout=120.0)
        except TimeoutError as exc:
            raise RuntimeError(
                "Timeout avvio Google Chrome (120s).\n"
                "Chiudere le finestre Chrome avviate da VISION e riprovare."
            ) from exc

    def _start_impl(self) -> BrowserPage:
        if self._context is not None and self._page is not None:
            try:
                _ = self._page.url
                self._debug("reuse_session")
                self._enable_interactive_unlocked()
                self._remember_chrome_pids_unlocked()
                if self.config.hidden and not self.config.headless:
                    self._set_chrome_windows_visible_unlocked(False)
                elif not self.config.hidden:
                    self._set_chrome_windows_visible_unlocked(True)
                try:
                    cur = self._page.url or ""
                except Exception:
                    cur = ""
                self._open_startup_url_unlocked(
                    force=self._is_blank_url(cur)
                )
                return self._page
            except Exception:
                logger.warning("Sessione browser non più valida: riavvio.")
                self._force_reset_unlocked()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright non è installato. Eseguire: pip install playwright"
            ) from exc

        use_system = bool(self.config.use_system_chrome_profile)
        # Come VIS eniSpace Utility: SEMPRE profilo isolato + launch_persistent_context.
        # Chrome 151+ non espone CDP sul User Data di sistema (crash/timeout).
        if use_system:
            logger.warning(
                "Profilo Chrome di sistema richiesto ma non supportato "
                "(Chrome 151+). Uso profilo isolato VISION come Utility."
            )
        profile = browser_profile_dir()
        if self.config.user_data_dir is not None:
            # Solo se esplicitamente un path isolato (non User Data sistema)
            requested = Path(self.config.user_data_dir)
            system_root = chrome_system_user_data_dir()
            cdp_root = chrome_cdp_user_data_dir()
            try:
                same_system = requested.resolve() == system_root.resolve()
                same_cdp = requested.resolve() == cdp_root.resolve()
            except Exception:
                same_system = False
                same_cdp = False
            if not same_system and not same_cdp:
                profile = requested
        profile.mkdir(parents=True, exist_ok=True)

        channel = self.config.channel or CHROME_CHANNEL
        use_hidden = bool(self.config.hidden) and not bool(self.config.headless)
        visible_lbl = (
            "nascosto"
            if use_hidden
            else ("headless" if self.config.headless else "visibile")
        )
        logger.info(
            "Avvio Google Chrome (channel=%s, modalità=%s, user_data=%s) "
            "[stile Utility]",
            channel,
            visible_lbl,
            profile,
        )
        self._debug(
            "start_browser",
            f"channel={channel} headless={self.config.headless} "
            f"hidden={use_hidden} profile={profile}",
        )

        self._playwright = sync_playwright().start()
        startup = self._startup_url()

        chrome_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-popup-blocking",
        ]
        if use_hidden:
            chrome_args.extend(
                [
                    "--window-position=-32000,-32000",
                    "--start-minimized",
                    "--window-size=1400,900",
                ]
            )

        launch_args: dict[str, Any] = {
            "user_data_dir": str(profile),
            "channel": channel,
            "headless": self.config.headless,
            "viewport": {"width": 1400, "height": 900},
            "accept_downloads": True,
            "args": chrome_args,
            # Playwright aggiunge --no-sandbox di default: su Windows desktop
            # non serve e riduce l'isolamento del processo Chrome.
            "ignore_default_args": ["--no-sandbox"],
        }
        if self.config.downloads_path:
            Path(self.config.downloads_path).mkdir(parents=True, exist_ok=True)
            launch_args["downloads_path"] = str(self.config.downloads_path)

        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                **launch_args
            )
        except Exception as exc:
            self._cleanup_playwright_unlocked()
            err = str(exc).lower()
            if any(k in err for k in ("executable", "browser", "chrome", "chromium")):
                raise RuntimeError(
                    "Google Chrome non trovato.\n"
                    "Installare Google Chrome e riprovare.\n"
                    "Playwright userà il Chrome di sistema (channel=chrome)."
                ) from exc
            raise RuntimeError(f"Errore avvio browser: {exc}") from exc

        return self._finish_start_unlocked(startup=startup, use_hidden=use_hidden)

    def _start_system_chrome_cdp_unlocked(
        self,
        *,
        profile: Path,
        profile_dir_name: str,
        chrome_exe: str,
        startup: str,
        use_hidden: bool,
    ) -> BrowserPage:
        """
        Chrome 136+ blocca CDP sul User Data di sistema → usiamo un user-data
        Vision dedicato (%LOCALAPPDATA%\\VISION\\ChromeCDP), sincronizzato dal
        profilo Default (password/cookie/PWA), poi connect_over_cdp.
        """
        app_id = (self.config.chrome_app_id or CHROME_ENISPACE_APP_ID).strip()
        port = self._pick_cdp_port()
        self._cdp_port = port

        if not chrome_exe:
            found = chrome_executable_path()
            chrome_exe = str(found) if found else ""
        if not chrome_exe:
            self._cleanup_playwright_unlocked()
            raise RuntimeError(
                "Google Chrome non trovato.\n"
                r"Atteso: C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            )

        # Mai usare il path sistema reale: CDP viene ignorato (Chrome 151+).
        system_root = chrome_system_user_data_dir()
        cdp_root = chrome_cdp_user_data_dir()
        try:
            if system_root.is_dir():
                logger.info(
                    "Sync credenziali Chrome Default → profilo CDP Vision (%s)",
                    cdp_root,
                )
                sync_system_chrome_profile_to_cdp(
                    profile_directory=profile_dir_name
                )
                logger.info("Sync profilo CDP completato")
            else:
                logger.warning(
                    "User Data Chrome di sistema assente — uso solo profilo CDP"
                )
        except Exception as exc:
            logger.warning("Sync profilo Chrome saltato/parziale: %s", exc)

        profile = cdp_root

        endpoint = f"http://127.0.0.1:{port}"
        if self._cdp_endpoint_ready(port, timeout_s=0.8):
            logger.info("CDP già attivo su %s — riconnessione", endpoint)
            return self._connect_cdp_and_finish_unlocked(
                endpoint=endpoint,
                startup=startup,
                use_hidden=use_hidden,
            )

        # Preferisci chrome.exe (inoltra sempre --remote-debugging-port).
        # --app=URL apre subito eniSpace (come scorciatoia, senza about:blank).
        launchers: list[str] = [chrome_exe]
        proxy = chrome_proxy_executable_path()
        if proxy is not None and str(proxy) != chrome_exe:
            launchers.append(str(proxy))

        def _spawn(cmd_exe: str, *, use_app_id: bool) -> subprocess.Popen:
            full_cmd = [
                cmd_exe,
                f"--user-data-dir={profile}",
                f"--profile-directory={profile_dir_name}",
                f"--remote-debugging-port={port}",
                "--remote-allow-origins=*",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ]
            if use_app_id and app_id:
                full_cmd.append(f"--app-id={app_id}")
            else:
                full_cmd.append(f"--app={startup}")
            if use_hidden:
                full_cmd.extend(
                    [
                        "--window-position=-32000,-32000",
                        "--start-minimized",
                    ]
                )
            logger.info(
                "Spawn Chrome CDP: exe=%s user_data=%s app=%s",
                cmd_exe,
                profile,
                f"app-id={app_id}" if use_app_id else f"app={startup}",
            )
            self._debug(
                "start_chrome_cdp",
                f"exe={cmd_exe} port={port} data={profile}",
            )
            return subprocess.Popen(
                full_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

        last_err = ""
        for launcher in launchers:
            # Prima --app=URL (CDP affidabile), poi app-id PWA se presente
            for use_app_id in (False, True):
                try:
                    self._terminate_owned_chrome_unlocked()
                    self._chrome_proc = _spawn(launcher, use_app_id=use_app_id)
                    self._owns_chrome = True
                    if self._chrome_proc.pid:
                        self._chrome_pids.add(int(self._chrome_proc.pid))
                except Exception as exc:
                    last_err = str(exc)
                    logger.warning("Spawn fallito (%s): %s", launcher, exc)
                    continue

                if self._cdp_endpoint_ready(port, timeout_s=18.0):
                    return self._connect_cdp_and_finish_unlocked(
                        endpoint=endpoint,
                        startup=startup,
                        use_hidden=use_hidden,
                    )

                try:
                    proc = self._chrome_proc
                    if proc is not None and proc.poll() is not None:
                        err_b = proc.stderr.read() if proc.stderr else b""
                        last_err = (err_b or b"").decode("utf-8", errors="replace")[
                            :500
                        ]
                        logger.warning(
                            "Chrome uscito subito (code=%s): %s",
                            proc.returncode,
                            last_err or "(no stderr)",
                        )
                except Exception:
                    pass
                self._terminate_owned_chrome_unlocked()

        self._cleanup_playwright_unlocked()
        raise RuntimeError(
            "Timeout: Chrome non ha esposto CDP sul profilo Vision.\n"
            "Chiudere tutte le finestre Chrome e riprovare «Test accesso».\n"
            f"Porta: {port}\n"
            f"Profilo CDP: {profile}\n"
            f"Dettaglio: {last_err or 'nessuno'}"
        )

    def _connect_cdp_and_finish_unlocked(
        self,
        *,
        endpoint: str,
        startup: str,
        use_hidden: bool,
    ) -> BrowserPage:
        assert self._playwright is not None
        try:
            self._cdp_browser = self._playwright.chromium.connect_over_cdp(endpoint)
        except Exception as exc:
            self._terminate_owned_chrome_unlocked()
            self._cleanup_playwright_unlocked()
            raise RuntimeError(
                f"Connessione CDP a Chrome fallita ({endpoint}): {exc}\n"
                "Chiudere Chrome e riprovare."
            ) from exc

        contexts = list(self._cdp_browser.contexts or [])
        if not contexts:
            self._terminate_owned_chrome_unlocked()
            self._cleanup_playwright_unlocked()
            raise RuntimeError(
                "Chrome aperto ma senza contesto CDP.\n"
                "Chiudere Chrome e riprovare."
            )
        self._context = contexts[0]
        return self._finish_start_unlocked(startup=startup, use_hidden=use_hidden)

    def _finish_start_unlocked(
        self, *, startup: str, use_hidden: bool
    ) -> BrowserPage:
        assert self._context is not None
        self._context.set_default_timeout(self.config.timeout_ms)
        self._attach_context_listeners()

        self._page = self._pick_startup_page_unlocked(startup)
        if self._page is None:
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = self._context.new_page()

        self._known_pages = {id(p) for p in self._context.pages}
        self._attach_page_listeners(self._page)
        self._enable_interactive_unlocked()
        self._remember_chrome_pids_unlocked()
        if use_hidden:
            self._set_chrome_windows_visible_unlocked(False)
        else:
            self._set_chrome_windows_visible_unlocked(True)

        try:
            cur = self._page.url or ""
        except Exception:
            cur = ""
        # Se la PWA è già su eniSpace non rifare goto; solo se blank
        self._open_startup_url_unlocked(force=self._is_blank_url(cur))
        self._debug(
            "browser_ready",
            f"pages={len(self._context.pages)} url={getattr(self._page, 'url', '')}",
        )
        return self._page

    @staticmethod
    def _pick_cdp_port() -> int:
        # Preferisci porta dedicata VISION se libera
        for candidate in (VISION_CDP_PORT_DEFAULT, 9222):
            if BrowserService._port_is_free(candidate):
                return candidate
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _port_is_free(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False

    @staticmethod
    def _cdp_endpoint_ready(port: int, *, timeout_s: float) -> bool:
        url = f"http://127.0.0.1:{port}/json/version"
        deadline = time.time() + max(0.0, timeout_s)
        while True:
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    if getattr(resp, "status", 200) == 200:
                        return True
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
            if time.time() >= deadline:
                return False
            time.sleep(0.25)

    def _terminate_owned_chrome_unlocked(self) -> None:
        proc = self._chrome_proc
        self._chrome_proc = None
        self._owns_chrome = False
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
        except Exception as exc:
            logger.debug("terminate chrome_proxy: %s", exc)

    def _startup_url(self) -> str:
        url = (self.config.startup_url or "").strip()
        return url or ENISPACE_STARTUP_URL

    @staticmethod
    def _is_blank_url(url: str) -> bool:
        current = (url or "").strip().lower()
        if not current or current == "about:blank":
            return True
        if current.startswith("chrome://newtab"):
            return True
        if current.startswith("chrome://new-tab-page"):
            return True
        return False

    def _pick_startup_page_unlocked(self, startup: str) -> Optional[BrowserPage]:
        if not self._context:
            return None
        startup_l = (startup or "").lower()
        pages = list(self._context.pages)
        for page in pages:
            try:
                url = (page.url or "").lower()
            except Exception:
                continue
            if "proxylogin.page" in url:
                return page
            if "myhome.page" in url or "/private/" in url:
                return page
            if "enispace.eni.com" in url:
                return page
            if startup_l and startup_l.rstrip("?").lower() in url:
                return page
        return None

    def _open_startup_url_unlocked(self, *, force: bool = False) -> None:
        """All'avvio apre proxyLogin eniSpace invece di about:blank."""
        if self._context is None:
            return
        target = self._startup_url()
        page = self._page
        if page is None and self._context.pages:
            page = self._context.pages[0]
            self._page = page
        if page is None:
            try:
                page = self._context.new_page()
                self._page = page
            except Exception as exc:
                logger.warning("Impossibile creare scheda startup: %s", exc)
                return

        try:
            current = page.url or ""
        except Exception:
            current = ""

        cur_l = current.lower()
        already_ok = (
            "proxylogin.page" in cur_l
            or "myhome.page" in cur_l
            or (
                "enispace.eni.com" in cur_l
                and "/private/" in cur_l
                and "about:blank" not in cur_l
            )
        )
        if already_ok and not self._is_blank_url(current) and not force:
            logger.info("Pagina iniziale già ok: %s", current)
            try:
                page.bring_to_front()
            except Exception:
                pass
            return

        last_err: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                logger.info(
                    "Apertura pagina iniziale eniSpace (tentativo %s/3): %s",
                    attempt,
                    target,
                )
                self._debug("startup_goto", f"{target} try={attempt}")
                page.goto(
                    target,
                    wait_until="domcontentloaded",
                    timeout=max(30000, int(self.config.timeout_ms)),
                )
                try:
                    page.bring_to_front()
                except Exception:
                    pass
                final = ""
                try:
                    final = page.url or ""
                except Exception:
                    final = ""
                if self._is_blank_url(final):
                    raise RuntimeError(f"ancora blank dopo goto ({final!r})")
                logger.info("Pagina iniziale attiva: %s", final)
                self._page = page
                return
            except Exception as exc:
                last_err = exc
                logger.warning(
                    "Goto startup fallito (tentativo %s/3): %s", attempt, exc
                )
                try:
                    page = self._context.new_page()
                    self._page = page
                except Exception:
                    pass
                time.sleep(0.6)
        if last_err is not None:
            logger.error(
                "Impossibile aprire %s all'avvio: %s", target, last_err
            )

    def _attach_context_listeners(self) -> None:
        if not self._context:
            return

        def on_page(page: BrowserPage) -> None:
            try:
                self._adopt_page(page, reason="context.page")
            except Exception as exc:
                logger.warning("Adozione nuova scheda fallita: %s", exc)

        self._context.on("page", on_page)

    def _attach_page_listeners(self, page: BrowserPage) -> None:
        def on_nav(frame: Any) -> None:
            if page and frame == page.main_frame:
                self._debug("navigation", frame.url)
                if self._recording or self.config.debug:
                    logger.info("Navigazione: %s", frame.url)
                self._emit_url(frame.url)

        def on_popup(popup: BrowserPage) -> None:
            try:
                self._adopt_page(popup, reason="page.popup")
            except Exception as exc:
                logger.warning("Adozione popup fallita: %s", exc)

        try:
            page.on("framenavigated", on_nav)
            page.on("popup", on_popup)
        except Exception:
            pass

    def _adopt_page(self, page: BrowserPage, *, reason: str) -> None:
        """Porta in primo piano una nuova scheda/popup e attende uscita da about:blank."""
        self._known_pages.add(id(page))
        self._page = page
        self._attach_page_listeners(page)
        try:
            page.bring_to_front()
        except Exception:
            pass

        url = ""
        try:
            url = page.url or ""
        except Exception:
            url = ""

        logger.info("Nuova scheda/popup (%s): %s", reason, url or "about:blank")
        self._debug("new_page", f"{reason} -> {url or 'about:blank'}")

        if not url or url == "about:blank":
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            try:
                # Attende navigazione reale (marketplace / FLP / eniSpace)
                page.wait_for_function(
                    "() => location.href && location.href !== 'about:blank'",
                    timeout=20000,
                )
            except Exception:
                logger.warning(
                    "La nuova scheda è rimasta su about:blank. "
                    "Usare navigazione diretta al Marketplace se necessario."
                )
            try:
                url = page.url or ""
            except Exception:
                url = ""
            if url and url != "about:blank":
                logger.info("Scheda aggiornata: %s", url)
                self._emit_url(url)
            elif url:
                self._emit_url(url)

    def _emit_url(self, url: str) -> None:
        if not url or not self.on_url_seen:
            return
        try:
            self.on_url_seen(url)
        except Exception as exc:
            logger.debug("on_url_seen: %s", exc)

    def _pump_events(self) -> None:
        """Processa eventi CDP mentre il browser è in modalità interattiva."""
        if not self._interactive or not self._context:
            return
        try:
            # Scopre schede aperte manualmente non ancora adottate
            for page in list(self._context.pages):
                if id(page) not in self._known_pages:
                    self._adopt_page(page, reason="pump.discover")

            page = self._page
            if page is not None:
                # wait_for_timeout pompa la coda eventi Playwright sync
                page.wait_for_timeout(50)
            else:
                time.sleep(0.05)
        except Exception:
            # Context chiuso dall'utente: reset soft
            try:
                if self._context is None:
                    self._interactive = False
            except Exception:
                self._interactive = False

    def _enable_interactive_unlocked(self) -> None:
        self._interactive = True
        _executor.set_pump(self._pump_events)

    def enable_interactive(self) -> None:
        """Attiva pump CDP (necessario dopo login / registra navigazione)."""
        _executor.run(self._enable_interactive_unlocked)

    def disable_interactive(self) -> None:
        def _impl() -> None:
            self._interactive = False
            _executor.set_pump(None)

        _executor.run(_impl)

    def new_page(self) -> BrowserPage:
        return _executor.run(self._new_page_impl)

    def _new_page_impl(self) -> BrowserPage:
        if not self._context:
            return self._start_impl()
        try:
            self._page = self._context.new_page()
        except Exception as exc:
            err = str(exc).lower()
            if "closed" in err or "target" in err:
                logger.warning(
                    "Context browser chiuso: riavvio Chrome e nuova scheda (%s)", exc
                )
                self._force_reset_unlocked()
                return self._start_impl()
            raise
        self._known_pages.add(id(self._page))
        self._attach_page_listeners(self._page)
        return self._page

    def goto(self, url: str, wait_until: str = "domcontentloaded") -> None:
        _executor.run(self._goto_impl, url, wait_until)

    def _host_of(self, url: str) -> str:
        try:
            return (urlparse(url).netloc or "").lower()
        except Exception:
            return ""

    @staticmethod
    def _is_identity_provider_url(url: str) -> bool:
        """True se la scheda è su login Microsoft/SAML (non interrompere)."""
        current_l = (url or "").lower()
        if not current_l or current_l == "about:blank":
            return False
        hints = (
            "login.microsoftonline.com",
            "login.microsoft.com",
            "login.live.com",
            "login.eni.com",
            "/saml2",
            "adfs",
            "sts.",
            "authentication.eu10.hana.ondemand.com/login",
            "proxylogin",
        )
        return any(h in current_l for h in hints)

    def _context_alive(self) -> bool:
        if not self._context:
            return False
        try:
            _ = self._context.pages
            return True
        except Exception:
            return False

    def _focus_identity_provider_page_unlocked(self) -> bool:
        """Porta in primo piano una scheda SSO/MFA se presente."""
        pages: list = []
        try:
            if self._context:
                pages = list(self._context.pages)
        except Exception:
            pages = []
        if self._page is not None and self._page not in pages:
            pages.insert(0, self._page)
        for page in pages:
            try:
                current = page.url or ""
            except Exception:
                continue
            if not self._is_identity_provider_url(current):
                continue
            try:
                page.bring_to_front()
            except Exception:
                pass
            self._page = page
            self._known_pages.add(id(page))
            return True
        return False

    def _pick_page_for_url(self, url: str) -> BrowserPage:
        """
        Sceglie la scheda giusta per navigare.
        Se il context è chiuso, riavvia Chrome.
        Preferisce riusare una scheda esistente; se l'host è diverso
        naviga sulla scheda corrente (goto) invece di forzare sempre new_page.
        Mai navigare via da una scheda Microsoft/SAML in corso.
        """
        if not self._context_alive():
            logger.warning("Browser non attivo: riavvio.")
            self._force_reset_unlocked()
            return self._start_impl()

        target_host = self._host_of(url)
        # Preferisci scheda già sullo stesso host
        try:
            pages = list(self._context.pages)
        except Exception:
            self._force_reset_unlocked()
            return self._start_impl()

        for page in pages:
            try:
                current = page.url or ""
            except Exception:
                continue
            if target_host and self._host_of(current) == target_host:
                self._page = page
                self._known_pages.add(id(page))
                return page

        # Riusa la scheda attiva (anche su altro host): evita new_page su context instabile
        current_page = self._page
        if current_page is not None:
            try:
                current_url = current_page.url or ""
                # Critico: non interrompere SSO Microsoft sulla stessa scheda
                if self._is_identity_provider_url(current_url):
                    logger.warning(
                        "SSO attivo (%s): apro nuova scheda per %s "
                        "senza interrompere il login Microsoft.",
                        self._host_of(current_url) or "idp",
                        target_host or url,
                    )
                    return self._new_page_impl()
                if target_host:
                    current_host = self._host_of(current_url)
                    if current_host and current_host != target_host:
                        logger.info(
                            "Navigazione cross-host sulla scheda corrente: %s → %s",
                            current_host,
                            target_host,
                        )
                return current_page
            except Exception:
                pass

        # Ultima risorsa: nuova scheda o riavvio
        try:
            return self._new_page_impl()
        except Exception as exc:
            logger.warning("new_page fallita (%s): riavvio browser", exc)
            self._force_reset_unlocked()
            return self._start_impl()

    def _goto_impl(self, url: str, wait_until: str) -> None:
        page = self._pick_page_for_url(url)

        self._debug("goto", url)
        logger.info("Apertura URL: %s", url)
        try:
            page.goto(url, wait_until=wait_until, timeout=self.config.timeout_ms)
            self._page = page
            try:
                page.bring_to_front()
            except Exception:
                pass
        except Exception as exc:
            err = str(exc)
            self._debug("goto", url, error=err)
            logger.error("Navigazione fallita verso %s: %s", url, err)
            # Retry su nuova scheda se la corrente era problematica
            lowered = err.lower()
            if any(
                k in lowered
                for k in (
                    "destroyed",
                    "closed",
                    "aborted",
                    "interrupted",
                    "detached",
                    "navigation",
                )
            ):
                logger.info("Retry navigazione su nuova scheda...")
                page = self._new_page_impl()
                page.goto(url, wait_until=wait_until, timeout=self.config.timeout_ms)
                self._page = page
                try:
                    page.bring_to_front()
                except Exception:
                    pass
            else:
                raise
        self._enable_interactive_unlocked()

    def current_url(self) -> str:
        def _impl() -> str:
            if not self._page:
                return ""
            try:
                return self._page.url or ""
            except Exception:
                return ""

        return _executor.run(_impl)

    def start_recording(self) -> BrowserPage:
        """Modalità REGISTRA NAVIGAZIONE: Chrome sempre visibile + log + pump."""

        def _impl() -> BrowserPage:
            self._recording = True
            self.config.headless = False
            self.config.hidden = False
            self.config.debug = True
            self._nav_log.clear()
            logger.info("Modalità REGISTRA NAVIGAZIONE attiva.")
            page = self._start_impl()
            self._set_chrome_windows_visible_unlocked(True)
            self._enable_interactive_unlocked()
            return page

        return _executor.run(_impl)

    def stop_recording(self) -> list[dict]:
        self._recording = False
        logger.info(
            "Registrazione navigazione terminata (%d eventi).", len(self._nav_log)
        )
        return list(self._nav_log)

    def get_navigation_log(self) -> list[dict]:
        return list(self._nav_log)

    def show_browser_window(self) -> None:
        """Mostra Chrome (es. login MFA)."""

        def _impl() -> None:
            self._set_chrome_windows_visible_unlocked(True)

        try:
            _executor.run(_impl, timeout=15.0)
        except Exception as exc:
            logger.debug("show_browser_window: %s", exc)

    def hide_browser_window(self) -> None:
        """Nasconde Chrome se modalità hide attiva."""
        if not self.config.hidden:
            return

        def _impl() -> None:
            self._set_chrome_windows_visible_unlocked(False)

        try:
            _executor.run(_impl, timeout=15.0)
        except Exception as exc:
            logger.debug("hide_browser_window: %s", exc)

    def wait_for_manual_login(
        self,
        is_logged_in: Callable[[], bool],
        poll_seconds: float = 2.0,
        max_wait_seconds: float = 600.0,
    ) -> bool:
        """Attende login/MFA manuale; il polling gira sul thread Playwright."""
        return _executor.run(
            self._wait_for_manual_login_impl,
            is_logged_in,
            poll_seconds,
            max_wait_seconds,
        )

    def _wait_for_manual_login_impl(
        self,
        is_logged_in: Callable[[], bool],
        poll_seconds: float,
        max_wait_seconds: float,
    ) -> bool:
        restore_hidden = bool(self.config.hidden)
        if self.config.headless:
            logger.warning(
                "Login manuale richiesto: riapertura browser in modalità visibile."
            )
            self._close_impl()
            self.config.headless = False
            was_hidden = self.config.hidden
            self.config.hidden = False
            self._start_impl()
            self.config.hidden = was_hidden
            restore_hidden = was_hidden

        # MFA: finestra deve essere usabile — mostra temporaneamente
        if restore_hidden:
            logger.warning(
                "Serve login/MFA: Chrome reso temporaneamente visibile. "
                "Se non vedi la finestra, in Impostazioni disattiva "
                "«Nascondi browser»."
            )
            self._set_chrome_windows_visible_unlocked(True)

        self._enable_interactive_unlocked()
        self._focus_identity_provider_page_unlocked()
        self._set_chrome_windows_visible_unlocked(True)
        logger.info(
            "Completare il login manualmente nel browser (MFA/OTP consentiti). "
            "Attesa massima: %.0f secondi. "
            "Usa la finestra Chrome su login.microsoftonline.com — non chiudere VISION.",
            max_wait_seconds,
        )
        self._debug("wait_manual_login")
        elapsed = 0.0
        last_ping = -30.0
        ok = False
        while elapsed < max_wait_seconds:
            try:
                # Pompa eventi durante l'attesa (nuove schede SSO/MFA)
                self._pump_events()
                if is_logged_in():
                    logger.info("Login manuale rilevato: sessione attiva.")
                    ok = True
                    break
            except Exception as exc:
                self._debug("check_login", error=str(exc))
            if elapsed - last_ping >= 30.0:
                remaining = max(0.0, max_wait_seconds - elapsed)
                # Solo al ping: non rubare il focus mentre l'utente digita.
                self._focus_identity_provider_page_unlocked()
                logger.info(
                    "ATTESA LOGIN eniSpace in corso… "
                    "completare l'accesso in Chrome su Microsoft "
                    f"(ancora ~{int(remaining)}s)."
                )
                last_ping = elapsed
            time.sleep(max(0.05, poll_seconds - 0.05))
            elapsed += poll_seconds
        if not ok:
            logger.error("Timeout attesa login manuale.")
        elif restore_hidden and self.config.hidden:
            logger.info(
                "Login completato: ripristino modalità hide (Chrome nascosto)."
            )
            self._set_chrome_windows_visible_unlocked(False)
        return ok

    def _remember_chrome_pids_unlocked(self) -> None:
        """Memorizza i PID del browser Playwright (per ShowWindow/Hide)."""
        self._chrome_pids.clear()
        if self._chrome_proc is not None and self._chrome_proc.pid:
            try:
                self._chrome_pids.add(int(self._chrome_proc.pid))
            except Exception:
                pass
        try:
            if self._cdp_browser is not None:
                # CDP: nessun process handle Playwright — resta cmdline / owned proc
                pass
            elif self._context is not None:
                browser = getattr(self._context, "browser", None)
                if browser is not None:
                    proc = getattr(browser, "process", None)
                    if proc is not None and getattr(proc, "pid", None):
                        self._chrome_pids.add(int(proc.pid))
        except Exception:
            pass
        # Persistent / CDP: PID da cmdline sul profilo
        if not self._chrome_pids or self._cdp_browser is not None:
            try:
                profile = str(
                    Path(self.config.user_data_dir or browser_profile_dir()).resolve()
                ).lower()
                self._chrome_pids |= self._pids_with_cmdline_fragment(profile)
            except Exception:
                pass

    @staticmethod
    def _pids_with_cmdline_fragment(fragment: str) -> set[int]:
        """Trova PID i cui argomenti contengono fragment (profilo Chrome)."""
        found: set[int] = set()
        if not fragment:
            return found
        frag = fragment.lower()
        try:
            import subprocess

            # PowerShell: un solo giro, niente dipendenze extra
            ps = (
                "Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | "
                "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
            )
            raw = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps],
                text=True,
                timeout=8,
                stderr=subprocess.DEVNULL,
            )
            import json

            data = json.loads(raw or "[]")
            if isinstance(data, dict):
                data = [data]
            for row in data or []:
                cmd = (row.get("CommandLine") or "").lower()
                if frag in cmd:
                    try:
                        found.add(int(row["ProcessId"]))
                    except (KeyError, TypeError, ValueError):
                        pass
        except Exception:
            pass
        return found

    def _set_chrome_windows_visible_unlocked(self, visible: bool) -> None:
        """Mostra/nasconde la finestra Chrome di QUESTO contesto (CDP + win32)."""
        # 1) CDP: agisce solo sulla finestra del target Playwright (preferito)
        if self._apply_cdp_window_bounds_unlocked(visible):
            return

        # 2) win32: solo se abbiamo PID noti (mai EnumWindows “cieco” su tutto Chrome)
        if not self._chrome_pids:
            self._remember_chrome_pids_unlocked()
        if not self._chrome_pids:
            logger.debug(
                "Hide/show Chrome: nessun PID/CDP — resto su args off-screen."
            )
            return

        try:
            import win32con
            import win32gui
            import win32process
        except ImportError:
            logger.debug("pywin32 non disponibile: skip hide/show finestra Chrome.")
            return

        pids = set(self._chrome_pids)
        target_hwnds: list[int] = []

        def _enum(hwnd: int, _: Any) -> bool:
            try:
                if not win32gui.IsWindow(hwnd):
                    return True
                _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid not in pids:
                    return True
                class_name = win32gui.GetClassName(hwnd) or ""
                if "Chrome_WidgetWin" not in class_name:
                    return True
                # Solo top-level con titolo (scheda reale)
                if not (win32gui.GetWindowText(hwnd) or "").strip():
                    return True
                target_hwnds.append(hwnd)
            except Exception:
                pass
            return True

        try:
            win32gui.EnumWindows(_enum, None)
        except Exception as exc:
            logger.debug("EnumWindows Chrome: %s", exc)
            return

        for hwnd in target_hwnds:
            try:
                if visible:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    try:
                        win32gui.SetWindowPos(
                            hwnd,
                            win32con.HWND_TOP,
                            80,
                            80,
                            1400,
                            900,
                            win32con.SWP_SHOWWINDOW,
                        )
                    except Exception:
                        pass
                else:
                    win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                    try:
                        win32gui.SetWindowPos(
                            hwnd,
                            win32con.HWND_BOTTOM,
                            -32000,
                            -32000,
                            1400,
                            900,
                            win32con.SWP_HIDEWINDOW | win32con.SWP_NOACTIVATE,
                        )
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("ShowWindow(%s): %s", hwnd, exc)

        if target_hwnds:
            logger.debug(
                "Chrome finestre %s: %d HWND",
                "visibili" if visible else "nascoste",
                len(target_hwnds),
            )

    def _apply_cdp_window_bounds_unlocked(self, visible: bool) -> bool:
        """Posiziona la finestra del target corrente via CDP. True se riuscito."""
        page = self._page
        ctx = self._context
        if page is None or ctx is None:
            return False
        try:
            session = ctx.new_cdp_session(page)
            try:
                info = session.send("Target.getTargetInfo")
                target_id = (info.get("targetInfo") or {}).get("targetId")
                if not target_id:
                    return False
                win = session.send(
                    "Browser.getWindowForTarget", {"targetId": target_id}
                )
                window_id = win.get("windowId")
                if window_id is None:
                    return False
                if visible:
                    bounds = {
                        "left": 80,
                        "top": 80,
                        "width": 1400,
                        "height": 900,
                        "windowState": "normal",
                    }
                else:
                    bounds = {
                        "left": -32000,
                        "top": -32000,
                        "width": 1400,
                        "height": 900,
                        "windowState": "minimized",
                    }
                session.send(
                    "Browser.setWindowBounds",
                    {"windowId": window_id, "bounds": bounds},
                )
                logger.debug(
                    "CDP window bounds → %s",
                    "visible" if visible else "hidden",
                )
                return True
            finally:
                try:
                    session.detach()
                except Exception:
                    pass
        except Exception as exc:
            logger.debug("CDP setWindowBounds: %s", exc)
            return False

    def close(self) -> None:
        try:
            _executor.run(self._close_impl)
        except Exception as exc:
            logger.warning("Chiusura browser: %s", exc)
            self._force_reset_unlocked()

    def _close_impl(self) -> None:
        self._debug("close_browser")
        self._interactive = False
        _executor.set_pump(None)
        try:
            if self._cdp_browser is not None:
                try:
                    self._cdp_browser.close()
                except Exception as exc:
                    logger.warning("Chiusura CDP browser: %s", exc)
            elif self._context:
                self._context.close()
        except Exception as exc:
            logger.warning("Chiusura context: %s", exc)
        finally:
            self._cdp_browser = None
            self._context = None
            self._page = None
            self._known_pages.clear()
            self._chrome_pids.clear()
            self._terminate_owned_chrome_unlocked()
            self._cleanup_playwright_unlocked()
            logger.info("Browser chiuso.")

    def _force_reset_unlocked(self) -> None:
        self._interactive = False
        _executor.set_pump(None)
        try:
            if self._cdp_browser is not None:
                self._cdp_browser.close()
        except Exception:
            pass
        self._cdp_browser = None
        self._context = None
        self._page = None
        self._known_pages.clear()
        self._chrome_pids.clear()
        self._terminate_owned_chrome_unlocked()
        self._cleanup_playwright_unlocked()

    def _cleanup_playwright_unlocked(self) -> None:
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._playwright = None
        self._cdp_port = None

    def focus_page(self, page: BrowserPage) -> None:
        """Imposta la scheda attiva (da chiamare sul thread Playwright)."""
        self._page = page
        self._known_pages.add(id(page))
        try:
            page.bring_to_front()
        except Exception:
            pass

    def run(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Esegue una callable sul thread Playwright (per EniSpaceService)."""
        return _executor.run(fn, *args, **kwargs)
