"""JarvisSupervisor — ON/OFF, polling, un job alla volta."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

from database.db import Database
from database.models import now_iso
from services.batch_service import BatchService
from services.imap_mail_service import ImapConfig, ImapMailService
from services.jarvis.logger import JarvisLogger
from services.jarvis.mail_watcher import MailWatcher
from services.jarvis.models import JarvisJob, JarvisSettings
from services.jarvis.notifications import NotificationService
from services.jarvis.processor import JobProcessor
from services.jarvis.queue import JobQueue
from services.jarvis.repository import JobRepository
from services.jarvis.states import JarvisState, LogLevel
from services.print_queue_service import PrintQueueService
from utils.logger import get_logger

logger = get_logger("jarvis.supervisor")

UiCallback = Callable[[], None]
BusyCheck = Callable[[], bool]


class JarvisSupervisor:
    """
    Supervisore background:
    - poll IMAP a intervallo configurabile
    - accoda job PENDING
    - processa un job alla volta
    - non spegne se un job fallisce
    """

    def __init__(
        self,
        *,
        db: Database,
        batch: BatchService,
        print_queue: PrintQueueService,
        imap_config_factory: Callable[[], Optional[ImapConfig]],
        settings_factory: Callable[[], JarvisSettings],
        is_app_busy: Optional[BusyCheck] = None,
        on_ui_refresh: Optional[UiCallback] = None,
    ) -> None:
        self.db = db
        self.batch = batch
        self.print_queue = print_queue
        self.imap_config_factory = imap_config_factory
        self.settings_factory = settings_factory
        self.is_app_busy = is_app_busy or (lambda: False)
        self.on_ui_refresh = on_ui_refresh

        self.logger = JarvisLogger()
        self.notifications = NotificationService()
        self.repo = JobRepository(db)
        self.queue = JobQueue(
            self.repo, logger=self.logger, notifications=self.notifications
        )
        self.watcher = MailWatcher(self.repo, jarvis_logger=self.logger)
        self.processor = JobProcessor(
            repo=self.repo,
            batch=batch,
            print_queue=print_queue,
            jarvis_logger=self.logger,
            notifications=self.notifications,
            mark_imap_read=self._mark_read,
        )

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._active = False
        self._processing = False
        self.state: str = JarvisState.OFFLINE
        self.last_check: str = ""
        self.last_job_summary: str = "—"
        self.current_job: Optional[JarvisJob] = None
        self._imap_cfg_cache: Optional[ImapConfig] = None

    # ------------------------------------------------------------------ properties
    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def is_processing(self) -> bool:
        return self._processing

    def pending_count(self) -> int:
        return self.queue.count_pending()

    def get_settings(self) -> JarvisSettings:
        return self.settings_factory()

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> bool:
        with self._lock:
            if self._active and self._thread and self._thread.is_alive():
                return True
            recovered = self.repo.recover_interrupted_processing()
            for job in recovered:
                self.logger.log(
                    f"Job #{job.id} PROCESSING → INTERVENTO RICHIESTO (riavvio)",
                    level=LogLevel.WARNING,
                    state=JarvisState.INTERVENTO_RICHIESTO,
                )
            self._stop.clear()
            self._active = True
            self.state = JarvisState.IN_ATTESA
            self.logger.log(
                "JARVIS attivato",
                level=LogLevel.SUCCESS,
                state=JarvisState.IN_ATTESA,
            )
            self._thread = threading.Thread(
                target=self._loop, name="jarvis-supervisor", daemon=True
            )
            self._thread.start()
            self._notify_ui()
            return True

    def stop(self) -> None:
        with self._lock:
            self._active = False
            self._stop.set()
            self.state = JarvisState.OFFLINE
            self.logger.log(
                "JARVIS disattivato",
                level=LogLevel.INFO,
                state=JarvisState.OFFLINE,
            )
            self._notify_ui()

    def run_mail_check_once(self) -> dict:
        """
        Esegue un singolo ciclo controllo mail (stessa logica di _cycle).
        Usato da VIS•ION Remote Agent / eniSpaceModule.check_mail_now.
        Non avvia il loop supervisore se non già attivo.
        """
        settings = self.get_settings()
        before_pending = self.pending_count()
        self._cycle(settings)
        after_pending = self.pending_count()
        return {
            "ok": True,
            "pending_before": before_pending,
            "pending_after": after_pending,
            "new_or_pending": after_pending,
            "state": str(self.state),
            "last_check": self.last_check,
            "snapshot": self.snapshot(),
        }

    def _loop(self) -> None:
        # Prima scansione subito
        first = True
        while not self._stop.is_set() and self._active:
            settings = self.get_settings()
            interval = max(15, int(settings.interval_seconds or 60))
            if first:
                first = False
                self._cycle(settings)
            else:
                # Attendi intervallo (interrompibile)
                if self._stop.wait(timeout=float(interval)):
                    break
                if not self._active:
                    break
                self._cycle(settings)

        self.state = JarvisState.OFFLINE
        self._processing = False
        self.current_job = None
        self._notify_ui()

    def _cycle(self, settings: JarvisSettings) -> None:
        if not self._active:
            return
        # Non interferire con sync manuale / ricerca UI
        if self.is_app_busy() or self._processing:
            self.logger.log(
                "Ciclo saltato: applicazione occupata",
                level=LogLevel.INFO,
                state=self.state,
            )
            return

        self.state = JarvisState.CONTROLLO_MAIL
        self.last_check = now_iso()
        self._notify_ui()

        cfg = self.imap_config_factory()
        self._imap_cfg_cache = cfg
        if cfg is None:
            self.logger.log(
                "Credenziali/config IMAP mancanti",
                level=LogLevel.WARNING,
                state=JarvisState.ERRORE,
            )
            self.state = JarvisState.IN_ATTESA
            self._notify_ui()
            return

        try:
            candidates = self.watcher.poll(cfg)
        except Exception as exc:
            self.logger.log(
                f"Controllo mail fallito: {exc}",
                level=LogLevel.ERROR,
                state=JarvisState.ERRORE,
            )
            self.state = JarvisState.IN_ATTESA
            self._notify_ui()
            return

        for cand in candidates:
            self.queue.enqueue(
                cand,
                simulation=bool(settings.simulation),
                max_attempts=max(1, int(settings.max_retries or 3)),
            )

        self._notify_ui()
        self._process_next(settings)

        if self._active and not self._processing:
            self.state = JarvisState.IN_ATTESA
            self._notify_ui()

    def _process_next(self, settings: JarvisSettings) -> None:
        while self._active and not self._stop.is_set():
            if self.is_app_busy():
                break
            job = self.queue.next_pending()
            if job is None:
                break
            self._processing = True
            self.current_job = job
            self.state = job.state or JarvisState.ANALISI_MAIL
            self._notify_ui()

            def on_state(st: str) -> None:
                self.state = st
                if self.current_job and self.current_job.id == job.id:
                    self.current_job.state = st
                self._notify_ui()

            try:
                jfolder = (settings.download_folder or "").strip()
                restore_folder = None
                if jfolder:
                    try:
                        Path(jfolder).mkdir(parents=True, exist_ok=True)
                        restore_folder = getattr(
                            self.batch.download_service, "base_folder", None
                        )
                        self.batch.download_service.set_base_folder(jfolder)
                    except Exception as exc:
                        logger.warning("Cartella download JARVIS: %s", exc)
                        restore_folder = None
                try:
                    result = self.processor.process(
                        job,
                        on_state=on_state,
                        printer_name=settings.printer or "",
                    )
                finally:
                    if restore_folder is not None:
                        try:
                            self.batch.download_service.set_base_folder(
                                str(restore_folder)
                            )
                        except Exception:
                            pass
                order = result.order_number or "—"
                self.last_job_summary = (
                    f"Ordine {order} — {result.outcome or result.status}"
                )
            except Exception as exc:
                logger.exception("Supervisor process error: %s", exc)
                self.logger.log(
                    f"Errore supervisore: {exc}",
                    level=LogLevel.ERROR,
                    state=JarvisState.ERRORE,
                )
            finally:
                self._processing = False
                self.current_job = None
                self._notify_ui()
            # Continua con il prossimo in coda (uno alla volta, sequenziale)

    def _mark_read(self, entry_id: str) -> None:
        cfg = self._imap_cfg_cache or self.imap_config_factory()
        if not cfg:
            return
        try:
            ImapMailService(cfg).mark_as_read(entry_id)
        except Exception as exc:
            logger.warning("Jarvis mark_as_read: %s", exc)

    def _notify_ui(self) -> None:
        if self.on_ui_refresh:
            try:
                self.on_ui_refresh()
            except Exception:
                pass

    # ------------------------------------------------------------------ snapshot UI
    def snapshot(self) -> dict:
        cur = self.current_job
        return {
            "active": self._active,
            "state": self.state,
            "last_check": self.last_check or "—",
            "last_job": self.last_job_summary,
            "pending": self.pending_count(),
            "current_job": (
                f"Ordine {cur.order_number or '—'} ({cur.state})"
                if cur
                else "—"
            ),
            "simulation": bool(self.get_settings().simulation),
            "processing": self._processing,
        }
