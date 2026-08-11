"""JobProcessor — orchestra batch/eniSpace/print con retry e simulazione."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional

from database.models import now_iso
from services.batch_service import BatchService
from services.email_parser import AcquisitionNotification
from services.exceptions import (
    ContractNotFoundError,
    CredentialsMissingError,
    DownloadFailedError,
    EniSpaceError,
    LoginFailedError,
    NetworkError,
    PageStructureChangedError,
    PortalUnreachableError,
    SessionExpiredError,
    TimeoutErrorEni,
)
from services.jarvis.logger import JarvisLogger
from services.jarvis.models import JarvisJob
from services.jarvis.notifications import NotificationService
from services.jarvis.repository import JobRepository
from services.jarvis.states import (
    RETRY_DELAYS_SEC,
    JobOutcome,
    JobStatus,
    JarvisState,
    LogLevel,
    NotifyEvent,
)
from services.print_queue_service import PrintQueueService
from utils.logger import get_logger

logger = get_logger("jarvis.processor")

StateCallback = Callable[[str], None]


class NeedsAttentionError(Exception):
    """Errore non ritentabile → INTERVENTO RICHIESTO."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TransientError(Exception):
    """Errore temporaneo ritentabile."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class JobProcessor:
    """Elabora un job alla volta; riusa BatchService per download reale."""

    def __init__(
        self,
        *,
        repo: JobRepository,
        batch: BatchService,
        print_queue: PrintQueueService,
        jarvis_logger: JarvisLogger,
        notifications: NotificationService,
        mark_imap_read: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.repo = repo
        self.batch = batch
        self.print_queue = print_queue
        self.jlog = jarvis_logger
        self.notifications = notifications
        self.mark_imap_read = mark_imap_read

    def process(
        self,
        job: JarvisJob,
        *,
        on_state: Optional[StateCallback] = None,
        printer_name: str = "",
    ) -> JarvisJob:
        """Esegue il flusso completo (o simulato) per un job."""
        job.status = JobStatus.PROCESSING
        job.started_at = job.started_at or now_iso()
        job.state = JarvisState.ANALISI_MAIL
        job.printer_name = printer_name or job.printer_name or ""
        self.repo.update(job)
        self._event(job, "Avvio lavorazione", JarvisState.ANALISI_MAIL)
        self.jlog.progress(
            "Inizio lavorazione",
            level=LogLevel.INFO,
            state=JarvisState.ANALISI_MAIL,
        )
        self._set_state(job, JarvisState.ANALISI_MAIL, on_state)

        max_attempts = max(1, int(job.max_attempts or 3))
        last_error = ""

        while job.attempts < max_attempts:
            job.attempts += 1
            self.repo.update(job)
            try:
                if job.simulation:
                    return self._process_simulation(job, on_state=on_state)
                return self._process_real(job, on_state=on_state)
            except NeedsAttentionError as exc:
                return self._finish_attention(job, str(exc.message), on_state)
            except TransientError as exc:
                last_error = str(exc.message)
                self._event(
                    job,
                    f"Errore temporaneo (tentativo {job.attempts}/{max_attempts}): {last_error}",
                    job.state or JarvisState.ERRORE,
                    level=LogLevel.WARNING,
                )
                if job.attempts >= max_attempts:
                    break
                delay_idx = min(job.attempts - 1, len(RETRY_DELAYS_SEC) - 1)
                delay = RETRY_DELAYS_SEC[delay_idx]
                self.jlog.log(
                    f"Retry tra {delay}s...",
                    level=LogLevel.WARNING,
                    state=JarvisState.ERRORE,
                )
                time.sleep(delay)
            except Exception as exc:
                logger.exception("Errore imprevisto job %s: %s", job.id, exc)
                return self._finish_attention(
                    job,
                    f"Errore imprevisto: {exc}",
                    on_state,
                )

        return self._finish_attention(
            job,
            f"Fallito dopo {max_attempts} tentativi: {last_error or 'errore'}",
            on_state,
        )

    # ------------------------------------------------------------------ simulation
    def _process_simulation(
        self,
        job: JarvisJob,
        *,
        on_state: Optional[StateCallback],
    ) -> JarvisJob:
        self._set_state(job, JarvisState.ANALISI_MAIL, on_state)
        self._event(job, "Analisi mail (simulazione)", JarvisState.ANALISI_MAIL)
        self.jlog.progress(
            "Analisi mail",
            level=LogLevel.INFO,
            state=JarvisState.ANALISI_MAIL,
        )

        order = (job.order_number or "").strip()
        module = (job.acquisition_module or "").strip()
        if not order and not module:
            raise NeedsAttentionError(
                "Contratto/ordine non riconosciuto nella mail (dati insufficienti)."
            )
        if not order:
            raise NeedsAttentionError(
                "Ordine non trovato nella mail — intervento richiesto."
            )
        if not module:
            raise NeedsAttentionError(
                "Modulo di Acquisizione non trovato — intervento richiesto."
            )

        self._set_state(job, JarvisState.CONTRATTO_RICONOSCIUTO, on_state)
        self.jlog.log(
            f"Ordine identificato: {order} / MdA {module}",
            level=LogLevel.SUCCESS,
            state=JarvisState.CONTRATTO_RICONOSCIUTO,
        )
        self.jlog.progress(
            f"Ordine riconosciuto: {order}",
            level=LogLevel.SUCCESS,
            state=JarvisState.CONTRATTO_RICONOSCIUTO,
        )
        self._event(
            job,
            f"Ordine {order}, contratto {job.contract_number or '—'}, MdA {module}",
            JarvisState.CONTRATTO_RICONOSCIUTO,
            level=LogLevel.SUCCESS,
        )

        for st, msg, chat in (
            (JarvisState.ACCESSO_ENISPACE, "Simulazione accesso eniSpace", "Accesso eniSpace"),
            (JarvisState.RICERCA_DOCUMENTI, "Simulazione ricerca documenti", "Ricerca documenti marketplace"),
            (JarvisState.DOWNLOAD, "Simulazione download (nessun file reale)", "Download documenti"),
            (JarvisState.PREPARAZIONE_STAMPA, "Simulazione preparazione stampa", "Preparazione stampa"),
            (JarvisState.STAMPA, "Simulazione stampa — NON inviato alla stampante", "Invio in stampa (simulazione)"),
            (JarvisState.VERIFICA, "Verifica simulazione OK", "Verifica completata"),
        ):
            self._set_state(job, st, on_state)
            self._event(job, msg, st)
            self.jlog.log(msg, level=LogLevel.INFO, state=st)
            self.jlog.progress(chat, level=LogLevel.INFO, state=st)

        job.docs_found = 1
        job.docs_downloaded = 0
        job.docs_printed = 0
        return self._finish_ok(
            job,
            outcome=JobOutcome.SIMULATA,
            message="Simulazione completata (nessun download/stampa reale)",
            on_state=on_state,
        )

    # ------------------------------------------------------------------ real
    def _process_real(
        self,
        job: JarvisJob,
        *,
        on_state: Optional[StateCallback],
    ) -> JarvisJob:
        self._set_state(job, JarvisState.ANALISI_MAIL, on_state)
        order = (job.order_number or "").strip()
        module = (job.acquisition_module or "").strip()
        framework = (job.contract_number or "").strip() or None

        if not order:
            raise NeedsAttentionError("Ordine non riconosciuto nella mail.")
        if not module:
            raise NeedsAttentionError(
                "Modulo di Acquisizione non riconosciuto nella mail."
            )

        self.jlog.progress(
            "Analisi mail",
            level=LogLevel.INFO,
            state=JarvisState.ANALISI_MAIL,
        )

        self._set_state(job, JarvisState.CONTRATTO_RICONOSCIUTO, on_state)
        self.jlog.log(
            f"Ordine identificato: {order}",
            level=LogLevel.SUCCESS,
            state=JarvisState.CONTRATTO_RICONOSCIUTO,
        )
        self.jlog.progress(
            f"Ordine riconosciuto: {order}",
            level=LogLevel.SUCCESS,
            state=JarvisState.CONTRATTO_RICONOSCIUTO,
        )
        self._event(
            job,
            f"Ordine {order} / MdA {module}",
            JarvisState.CONTRATTO_RICONOSCIUTO,
            level=LogLevel.SUCCESS,
        )

        notice = AcquisitionNotification(
            acquisition_module=module,
            order_number=order,
            contract_number=framework or "",
            subject=job.subject,
            sender=job.sender,
        )

        self._set_state(job, JarvisState.ACCESSO_ENISPACE, on_state)
        self.jlog.log(
            "Avvio accesso eniSpace",
            level=LogLevel.INFO,
            state=JarvisState.ACCESSO_ENISPACE,
        )
        self.jlog.progress(
            "Accesso eniSpace",
            level=LogLevel.INFO,
            state=JarvisState.ACCESSO_ENISPACE,
        )
        self._event(job, "Accesso eniSpace / ricerca", JarvisState.ACCESSO_ENISPACE)

        def progress(msg: str) -> None:
            low = (msg or "").lower()
            if "ricerca" in low or "ordine" in low:
                if job.state != JarvisState.RICERCA_DOCUMENTI:
                    self._set_state(job, JarvisState.RICERCA_DOCUMENTI, on_state)
                    self.jlog.progress(
                        "Ricerca documenti marketplace",
                        level=LogLevel.INFO,
                        state=JarvisState.RICERCA_DOCUMENTI,
                    )
            elif "download" in low or "mdA" in low.lower() or "mda" in low:
                if job.state != JarvisState.DOWNLOAD:
                    self._set_state(job, JarvisState.DOWNLOAD, on_state)
                    self.jlog.progress(
                        "Download documenti",
                        level=LogLevel.INFO,
                        state=JarvisState.DOWNLOAD,
                    )
            self.jlog.log(msg, level=LogLevel.INFO, state=job.state)

        try:
            self._set_state(job, JarvisState.RICERCA_DOCUMENTI, on_state)
            self.jlog.progress(
                "Ricerca documenti marketplace",
                level=LogLevel.INFO,
                state=JarvisState.RICERCA_DOCUMENTI,
            )
            item = self.batch._process_notice(  # noqa: SLF001 — riuso intenzionale
                notice,
                source_name=job.subject[:80] or f"jarvis-{job.mail_id}",
                on_progress=progress,
                enqueue=True,  # visibile in coda stampa UI
                mail_day=(job.received_at or "")[:10] or None,
            )
        except LoginFailedError as exc:
            raise TransientError(f"Login fallito: {exc}") from exc
        except CredentialsMissingError as exc:
            raise NeedsAttentionError(f"Credenziali mancanti: {exc}") from exc
        except (NetworkError, PortalUnreachableError, TimeoutErrorEni, SessionExpiredError) as exc:
            raise TransientError(str(exc)) from exc
        except (ContractNotFoundError, PageStructureChangedError) as exc:
            raise NeedsAttentionError(str(exc)) from exc
        except DownloadFailedError as exc:
            raise TransientError(f"Download fallito: {exc}") from exc
        except EniSpaceError as exc:
            msg = getattr(exc, "message", None) or str(exc)
            # Ambiguo / strutturale → intervento; resto transient
            low = msg.lower()
            if any(
                h in low
                for h in (
                    "non trovato",
                    "non riconosci",
                    "ambigu",
                    "selettori",
                    "struttura",
                    "mfa",
                )
            ):
                raise NeedsAttentionError(msg) from exc
            raise TransientError(msg) from exc

        if not item.success:
            msg = item.message or "Elaborazione fallita"
            low = msg.lower()
            if any(
                h in low
                for h in (
                    "non trovato",
                    "ricerca ordine fallita",
                    "modulo",
                    "ordine non",
                )
            ):
                raise NeedsAttentionError(msg)
            raise TransientError(msg)

        pdf_path = (item.pdf_path or "").strip()
        if not pdf_path or not Path(pdf_path).is_file():
            raise NeedsAttentionError(
                "Download completato ma file PDF assente o non valido."
            )

        # PDF minimo valido (%PDF)
        try:
            with open(pdf_path, "rb") as fh:
                header = fh.read(5)
            if header != b"%PDF-":
                raise NeedsAttentionError(
                    f"PDF corrotto o non valido: {Path(pdf_path).name}"
                )
        except NeedsAttentionError:
            raise
        except OSError as exc:
            raise NeedsAttentionError(f"Impossibile verificare PDF: {exc}") from exc

        job.docs_found = 1
        job.docs_downloaded = 1
        job.pdf_paths = [pdf_path]
        job.order_number = item.order_number or order
        job.acquisition_module = item.acquisition_module or module
        self.repo.update(job)
        self._set_state(job, JarvisState.VERIFICA, on_state)
        self._event(
            job,
            f"Download OK: {Path(pdf_path).name}",
            JarvisState.DOWNLOAD,
            level=LogLevel.SUCCESS,
        )
        self.jlog.log(
            f"Download completato: {Path(pdf_path).name}",
            level=LogLevel.SUCCESS,
            state=JarvisState.DOWNLOAD,
        )
        self.jlog.progress(
            "Download completato",
            level=LogLevel.SUCCESS,
            state=JarvisState.DOWNLOAD,
        )

        # --- Stampa automatica Jarvis (non simulazione) ---
        self._set_state(job, JarvisState.PREPARAZIONE_STAMPA, on_state)
        self._event(job, "Preparazione stampa", JarvisState.PREPARAZIONE_STAMPA)
        self.jlog.progress(
            "Preparazione stampa",
            level=LogLevel.INFO,
            state=JarvisState.PREPARAZIONE_STAMPA,
        )
        self._set_state(job, JarvisState.STAMPA, on_state)
        self.jlog.log(
            "Invio documento alla coda di stampa",
            level=LogLevel.INFO,
            state=JarvisState.STAMPA,
        )
        self.jlog.progress(
            "Invio in stampa",
            level=LogLevel.INFO,
            state=JarvisState.STAMPA,
        )
        try:
            self.print_queue.print_file(pdf_path)
            # Segna item coda come inviato se presente
            for qi in self.print_queue.list(pending_only=True):
                if Path(qi.local_path).resolve() == Path(pdf_path).resolve() and qi.id:
                    self.batch.db.mark_print_queue_printed(qi.id, status="printed")
                    break
            job.docs_printed = 1
            print_msg = "INVIATO CORRETTAMENTE ALLA CODA DI STAMPA"
            self._event(job, print_msg, JarvisState.STAMPA, level=LogLevel.SUCCESS)
            self.jlog.log(print_msg, level=LogLevel.SUCCESS, state=JarvisState.STAMPA)
            self.jlog.progress(
                "Documento inviato in stampa",
                level=LogLevel.SUCCESS,
                state=JarvisState.STAMPA,
            )
        except Exception as exc:
            raise NeedsAttentionError(
                f"Invio alla coda di stampa fallito: {exc}"
            ) from exc

        # Anti-dup allineato a sync manuale
        try:
            entry_id = ""
            if job.mail_folder and job.mail_uid:
                entry_id = f"{job.mail_folder}:{job.mail_uid}"
            elif job.mail_id and ":" in job.mail_id and not job.mail_id.startswith("<"):
                entry_id = job.mail_id
            if entry_id:
                self.batch.db.mark_imap_processed(
                    entry_id,
                    folder=job.mail_folder,
                    uid=job.mail_uid,
                    subject=job.subject,
                    order_number=job.order_number,
                    acquisition_module=job.acquisition_module,
                    result="success",
                    message="JARVIS completato",
                )
                self.batch.db.add_mail_register(
                    entry_id=entry_id,
                    folder=job.mail_folder,
                    uid=job.mail_uid,
                    subject=job.subject,
                    order_number=job.order_number,
                    acquisition_module=job.acquisition_module,
                    status="success",
                    note=f"JARVIS: {print_msg}",
                )
                if self.mark_imap_read:
                    try:
                        self.mark_imap_read(entry_id)
                    except Exception as mark_exc:
                        logger.warning("Mark read Jarvis fallito: %s", mark_exc)
        except Exception as reg_exc:
            logger.warning("Registro anti-dup Jarvis: %s", reg_exc)

        return self._finish_ok(
            job,
            outcome=JobOutcome.COMPLETATA,
            message=print_msg,
            on_state=on_state,
        )

    # ------------------------------------------------------------------ finish helpers
    def _finish_ok(
        self,
        job: JarvisJob,
        *,
        outcome: str,
        message: str,
        on_state: Optional[StateCallback],
    ) -> JarvisJob:
        job.status = JobStatus.COMPLETED
        job.outcome = outcome
        job.state = JarvisState.COMPLETATO
        job.finished_at = now_iso()
        job.error_message = ""
        self.repo.update(job)
        self._event(job, message, JarvisState.COMPLETATO, level=LogLevel.SUCCESS)
        self.jlog.log(
            f"Lavorazione completata — ordine {job.order_number or '—'}",
            level=LogLevel.SUCCESS,
            state=JarvisState.COMPLETATO,
        )
        self.jlog.progress(
            f"Lavorazione completata — ordine {job.order_number or '—'}",
            level=LogLevel.SUCCESS,
            state=JarvisState.COMPLETATO,
        )
        self._set_state(job, JarvisState.COMPLETATO, on_state)
        self.notifications.emit(
            NotifyEvent.JOB_COMPLETED,
            job_id=job.id,
            mail_id=job.mail_id,
            order_number=job.order_number,
            message=message,
        )
        return job

    def _finish_attention(
        self,
        job: JarvisJob,
        message: str,
        on_state: Optional[StateCallback],
    ) -> JarvisJob:
        job.status = JobStatus.NEEDS_ATTENTION
        job.outcome = JobOutcome.INTERVENTO_RICHIESTO
        job.state = JarvisState.INTERVENTO_RICHIESTO
        job.error_message = message
        job.finished_at = now_iso()
        self.repo.update(job)
        self._event(
            job, message, JarvisState.INTERVENTO_RICHIESTO, level=LogLevel.ERROR
        )
        self.jlog.log(message, level=LogLevel.ERROR, state=JarvisState.INTERVENTO_RICHIESTO)
        self.jlog.progress(
            f"Intervento richiesto: {message}",
            level=LogLevel.ERROR,
            state=JarvisState.INTERVENTO_RICHIESTO,
        )
        self._set_state(job, JarvisState.INTERVENTO_RICHIESTO, on_state)
        self.notifications.emit(
            NotifyEvent.NEEDS_ATTENTION,
            job_id=job.id,
            mail_id=job.mail_id,
            order_number=job.order_number,
            message=message,
        )
        # Job fallito: supervisore continua (non spegne)
        return job

    def _set_state(
        self,
        job: JarvisJob,
        state: str,
        on_state: Optional[StateCallback],
    ) -> None:
        job.state = state
        job.last_event_at = now_iso()
        try:
            self.repo.update(job)
        except Exception:
            pass
        if on_state:
            try:
                on_state(state)
            except Exception:
                pass

    def _event(
        self,
        job: JarvisJob,
        message: str,
        state: str,
        *,
        level: str = LogLevel.INFO,
    ) -> None:
        if job.id:
            self.repo.add_event(job.id, message, level=level, state=state)
