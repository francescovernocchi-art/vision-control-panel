"""Orchestrazione batch: .eml / IMAP → ricerca Marketplace → download MdA → coda stampa."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from database.db import Database
from database.models import Document, DocumentStatus, OperationResult, now_iso
from services.download_service import DownloadService
from services.email_parser import AcquisitionNotification, parse_eml_file
from services.enispace_service import AttachmentInfo, EniSpaceService
from services.imap_mail_service import (
    IMAP_OP_TIMEOUT_SEC,
    ImapConfig,
    ImapMailError,
    ImapMailService,
)
from services.print_queue_service import PrintQueueService
from utils.logger import get_logger

logger = get_logger("batch")

ProgressCallback = Callable[[str], None]
ItemDoneCallback = Callable[["BatchItemResult"], None]


@dataclass
class BatchItemResult:
    eml_path: str
    order_number: str = ""
    acquisition_module: str = ""
    pdf_path: str = ""
    success: bool = False
    skipped: bool = False
    message: str = ""
    queued: bool = False


@dataclass
class BatchRunResult:
    results: list[BatchItemResult] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.success)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.success)


class BatchService:
    """Ciclo multi-mail senza chiudere il browser tra un'elaborazione e l'altra."""

    def __init__(
        self,
        *,
        db: Database,
        enispace: EniSpaceService,
        download_service: DownloadService,
        print_queue: PrintQueueService,
    ) -> None:
        self.db = db
        self.enispace = enispace
        self.download_service = download_service
        self.print_queue = print_queue

    def process_eml_files(
        self,
        eml_paths: list[Path | str],
        *,
        on_progress: Optional[ProgressCallback] = None,
        on_item_done: Optional[ItemDoneCallback] = None,
        enqueue: bool = True,
        continue_on_error: bool = True,
    ) -> BatchRunResult:
        paths = [Path(p) for p in eml_paths]
        total = len(paths)
        run = BatchRunResult()

        for idx, path in enumerate(paths, start=1):
            label = f"[{idx}/{total}] {path.name}"
            self._progress(on_progress, f"{label} — avvio...")
            try:
                item = self._process_one(path, on_progress=on_progress, enqueue=enqueue)
                run.results.append(item)
                self._item_done(on_item_done, item)
                status = "success" if item.success else "error"
                note = self._register_note(
                    subject=path.name,
                    success=item.success,
                    detail=item.message,
                    order_number=item.order_number,
                    acquisition_module=item.acquisition_module,
                )
                self.db.add_mail_register(
                    subject=path.name,
                    order_number=item.order_number,
                    acquisition_module=item.acquisition_module,
                    status=status,
                    note=note,
                )
                status_lbl = "OK" if item.success else "ERRORE"
                self._progress(
                    on_progress,
                    f"{label} — {status_lbl}: {item.message}",
                )
            except Exception as exc:
                logger.exception("Batch fallito su %s: %s", path, exc)
                fail = BatchItemResult(
                    eml_path=str(path),
                    success=False,
                    message=str(exc),
                )
                run.results.append(fail)
                self._item_done(on_item_done, fail)
                self.db.add_mail_register(
                    subject=path.name,
                    status="error",
                    note=self._register_note(
                        subject=path.name, success=False, detail=str(exc)
                    ),
                )
                self._progress(on_progress, f"{label} — ERRORE: {exc}")
                if not continue_on_error:
                    break

        self.db.log_operation(
            "batch_eml",
            OperationResult.SUCCESS if run.fail_count == 0 else OperationResult.WARNING,
            f"ok={run.ok_count} errori={run.fail_count} totale={total}",
        )
        return run

    def process_imap_folder(
        self,
        config: ImapConfig,
        *,
        unread_only: Optional[bool] = None,
        mark_read: bool = True,
        skip_processed: bool = True,
        on_date: Optional[str] = None,
        clear_error_skips: bool = False,
        on_progress: Optional[ProgressCallback] = None,
        on_item_done: Optional[ItemDoneCallback] = None,
        enqueue: bool = True,
        continue_on_error: bool = True,
        limit: int = 50,
    ) -> BatchRunResult:
        """Legge IMAP → per ogni notifica MdA scarica PDF e mette in coda stampa.

        Mark \\Seen e registro «già elaborata» solo a successo.
        Gli errori restano non letti e ritentabili.
        on_date (YYYY-MM-DD): limita alle mail di quel giorno (es. rielabora oggi).
        """
        imap = ImapMailService(config)
        folder = config.folder or "INBOX.MdA_Eni"
        day = (on_date or "").strip()[:10] or None
        self._progress(on_progress, f"Connessione IMAP: {config.host} / {folder}...")

        if clear_error_skips:
            removed = self.db.clear_imap_processed_errors(on_date=day or "")
            if removed:
                self._progress(
                    on_progress,
                    f"Rimossi {removed} skip da errori precedenti"
                    + (f" ({day})" if day else "")
                    + " — ritento.",
                )

        # Lista IMAP sul thread corrente (già background). Timeout via socket
        # IMAP + executor dedicato: non annidare sul thread UI.
        def _list() -> list:
            return imap.list_messages(
                unread_only=unread_only,
                only_acquisition=True,
                limit=limit,
                on_date=day,
                on_progress=on_progress,
            )

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(_list)
                messages = fut.result(timeout=float(IMAP_OP_TIMEOUT_SEC))
        except FuturesTimeout as exc:
            raise ImapMailError(
                f"Timeout lettura cartella IMAP «{folder}» "
                f"({IMAP_OP_TIMEOUT_SEC}s).\n"
                "Verificare rete/firewall verso SecureMail, oppure "
                "ridurre i messaggi (filtro non lette / cartella MdA_Eni)."
            ) from exc

        if skip_processed:
            before = len(messages)
            messages = [
                m
                for m in messages
                if m.entry_id and not self.db.is_imap_processed(m.entry_id)
            ]
            skipped = before - len(messages)
            if skipped:
                self._progress(
                    on_progress,
                    f"Saltati {skipped} messaggi già gestiti con successo.",
                )

        total = len(messages)
        day_lbl = f" del {day}" if day else ""
        self._progress(
            on_progress,
            f"Messaggi da elaborare: {total}{day_lbl} (cartella {folder})",
        )
        run = BatchRunResult()
        if total == 0:
            self.db.log_operation(
                "batch_imap",
                OperationResult.INFO,
                "Nessuna mail nuova da elaborare"
                + (f" ({day})" if day else ""),
            )
            return run

        for idx, msg in enumerate(messages, start=1):
            label = f"[{idx}/{total}] {msg.subject[:60]}"
            self._progress(on_progress, f"{label} — avvio...")
            notice = msg.notification or AcquisitionNotification(
                subject=msg.subject, sender=msg.sender, raw_body=msg.body
            )
            try:
                item = self._process_notice(
                    notice,
                    source_name=msg.subject[:80] or f"imap-{msg.uid}",
                    on_progress=on_progress,
                    enqueue=enqueue,
                    mail_day=msg.message_date or day or None,
                )
                run.results.append(item)
                self._item_done(on_item_done, item)
                status = "success" if item.success else "error"
                note = self._register_note(
                    subject=msg.subject,
                    uid=msg.uid,
                    success=item.success,
                    detail=item.message,
                    order_number=item.order_number,
                    acquisition_module=item.acquisition_module,
                )
                # Registro cronologico sempre (ok e errore)
                self.db.add_mail_register(
                    entry_id=msg.entry_id or "",
                    folder=msg.folder,
                    uid=msg.uid,
                    subject=msg.subject,
                    order_number=item.order_number,
                    acquisition_module=item.acquisition_module,
                    status=status,
                    note=note,
                )
                # Skip permanente + \\Seen solo a successo
                if item.success:
                    if msg.entry_id:
                        self.db.mark_imap_processed(
                            msg.entry_id,
                            folder=msg.folder,
                            uid=msg.uid,
                            subject=msg.subject,
                            order_number=item.order_number,
                            acquisition_module=item.acquisition_module,
                            result="success",
                            message=note,
                        )
                    if mark_read and msg.entry_id:
                        try:
                            imap.mark_as_read(msg.entry_id)
                        except Exception as mark_exc:
                            logger.warning("Mark read fallito: %s", mark_exc)
                status_lbl = "OK" if item.success else "ERRORE"
                self._progress(
                    on_progress, f"{label} — {status_lbl}: {item.message}"
                )
            except Exception as exc:
                logger.exception("Batch IMAP fallito: %s", exc)
                fail = BatchItemResult(
                    eml_path=msg.subject,
                    success=False,
                    message=str(exc),
                )
                run.results.append(fail)
                self._item_done(on_item_done, fail)
                note = self._register_note(
                    subject=msg.subject,
                    uid=msg.uid,
                    success=False,
                    detail=str(exc),
                )
                # Solo registro: niente imap_processed / niente \\Seen → ritentabile
                self.db.add_mail_register(
                    entry_id=msg.entry_id or "",
                    folder=msg.folder,
                    uid=msg.uid,
                    subject=msg.subject,
                    status="error",
                    note=note,
                )
                self._progress(on_progress, f"{label} — ERRORE: {exc}")
                if not continue_on_error:
                    break

        self.db.log_operation(
            "batch_imap",
            OperationResult.SUCCESS if run.fail_count == 0 else OperationResult.WARNING,
            f"ok={run.ok_count} errori={run.fail_count} totale={total}"
            + (f" day={day}" if day else ""),
        )
        return run

    def process_outlook_folder(
        self,
        *,
        folder_path: str = "Inbox/MdA_Eni",
        unread_only: bool = True,
        mark_read: bool = True,
        skip_processed: bool = True,
        on_progress: Optional[ProgressCallback] = None,
        on_item_done: Optional[ItemDoneCallback] = None,
        enqueue: bool = True,
        continue_on_error: bool = True,
        limit: int = 50,
    ) -> BatchRunResult:
        """Legacy Outlook COM — preferire process_imap_folder."""
        from services.outlook_mail_service import OutlookMailService

        outlook = OutlookMailService(folder_path=folder_path)
        self._progress(on_progress, f"Connessione Outlook: {folder_path}...")
        messages = outlook.list_messages(
            unread_only=unread_only,
            only_acquisition=True,
            limit=limit,
        )
        if skip_processed:
            messages = [
                m
                for m in messages
                if m.entry_id and not self.db.is_outlook_processed(m.entry_id)
            ]

        total = len(messages)
        self._progress(
            on_progress,
            f"Messaggi da elaborare: {total} (cartella {folder_path})",
        )
        run = BatchRunResult()
        if total == 0:
            self.db.log_operation(
                "batch_outlook",
                OperationResult.INFO,
                "Nessuna mail nuova da elaborare",
            )
            return run

        for idx, msg in enumerate(messages, start=1):
            label = f"[{idx}/{total}] {msg.subject[:60]}"
            self._progress(on_progress, f"{label} — avvio...")
            try:
                item = self._process_notice(
                    msg.notification,
                    source_name=msg.subject[:80] or f"outlook-{idx}",
                    on_progress=on_progress,
                    enqueue=enqueue,
                )
                run.results.append(item)
                self._item_done(on_item_done, item)
                if item.success:
                    if msg.entry_id:
                        self.db.mark_outlook_processed(
                            msg.entry_id,
                            subject=msg.subject,
                            order_number=item.order_number,
                            acquisition_module=item.acquisition_module,
                            result="success",
                            message=item.message,
                        )
                    if mark_read and msg.entry_id:
                        outlook.mark_as_read(msg.entry_id)
                status = "OK" if item.success else "ERRORE"
                self._progress(
                    on_progress, f"{label} — {status}: {item.message}"
                )
            except Exception as exc:
                logger.exception("Batch Outlook fallito: %s", exc)
                fail = BatchItemResult(
                    eml_path=msg.subject,
                    success=False,
                    message=str(exc),
                )
                run.results.append(fail)
                self._item_done(on_item_done, fail)
                # Nessun mark_outlook_processed / mark_as_read → ritentabile
                self._progress(on_progress, f"{label} — ERRORE: {exc}")
                if not continue_on_error:
                    break

        self.db.log_operation(
            "batch_outlook",
            OperationResult.SUCCESS if run.fail_count == 0 else OperationResult.WARNING,
            f"ok={run.ok_count} errori={run.fail_count} totale={total}",
        )
        return run

    def _process_one(
        self,
        path: Path,
        *,
        on_progress: Optional[ProgressCallback],
        enqueue: bool,
    ) -> BatchItemResult:
        if not path.is_file():
            return BatchItemResult(
                eml_path=str(path),
                success=False,
                message=f"File non trovato: {path}",
            )
        notice = parse_eml_file(path)
        return self._process_notice(
            notice,
            source_name=path.name,
            on_progress=on_progress,
            enqueue=enqueue,
        )

    def _process_notice(
        self,
        notice: AcquisitionNotification,
        *,
        source_name: str,
        on_progress: Optional[ProgressCallback],
        enqueue: bool,
        mail_day: Optional[str] = None,
    ) -> BatchItemResult:
        from datetime import date as date_cls

        order = (notice.order_number or notice.search_key or "").strip()
        module = (notice.acquisition_module or "").strip()
        framework = (notice.contract_number or "").strip() or None
        day = (mail_day or "").strip() or date_cls.today().isoformat()

        if not order:
            return BatchItemResult(
                eml_path=source_name,
                success=False,
                message="Ordine non trovato nella mail",
            )
        if not module:
            return BatchItemResult(
                eml_path=source_name,
                order_number=order,
                success=False,
                message="Modulo di Acquisizione non trovato nella mail",
            )

        self._progress(
            on_progress,
            f"Ricerca ordine {order} / MdA {module} su eniSpace "
            "(Chrome / login se necessario)...",
        )

        self.db.upsert_contract(
            order,
            order_number=order,
            framework_contract=framework,
            acquisition_module=module,
        )

        # Prima di ogni notice: se già su Marketplace, chiudi dettaglio ODA
        try:
            if self.enispace.browser.is_open:
                cur = ""
                try:
                    cur = self.enispace.browser.current_url() or ""
                except Exception:
                    cur = ""
                if "ZMP_DSH-DISPLAY" in cur.upper():
                    self.enispace.return_to_dashboard_filters()
        except Exception as exc:
            logger.debug("Pre-ricerca return_to_dashboard_filters: %s", exc)

        try:
            result = self.enispace.search_contract(
                order,
                order_number=order,
                framework_contract=framework,
                acquisition_module=module,
            )

            if not result.found:
                return BatchItemResult(
                    eml_path=source_name,
                    order_number=order,
                    acquisition_module=module,
                    success=False,
                    message=result.message or "Ricerca ordine fallita",
                )

            attachments = list(result.attachments or [])
            preferred = [
                a
                for a in attachments
                if (a.remote_id or "") == module or module in (a.filename or "")
            ]
            target: Optional[AttachmentInfo] = preferred[0] if preferred else None
            if target is None:
                # Dettaglio aperto: prova PDF per numero MdA anche se lo scrape è vuoto
                target = AttachmentInfo(
                    remote_id=module,
                    filename=f"{module}_MDA.pdf",
                    doc_type="PDF",
                    download_hint="PDF MdA/EM",
                )

            filename = target.filename or f"{module}_MDA.pdf"
            existing = self.download_service.find_identical(
                order,
                filename=filename,
                acquisition_module=module,
                day=day,
            )
            pdf_path: Path
            skipped = False
            if existing and existing.is_file():
                pdf_path = Path(existing)
                skipped = True
                self._progress(on_progress, f"PDF già presente: {pdf_path.name}")
            else:
                prep = self.download_service.prepare_destination(
                    order,
                    filename,
                    expected_sha256=None,
                    expected_size=None,
                    acquisition_module=module,
                    day=day,
                )
                assert prep.path is not None
                if prep.skipped and prep.path.is_file():
                    pdf_path = Path(prep.path)
                    skipped = True
                    self._progress(on_progress, f"PDF già presente: {pdf_path.name}")
                else:
                    self._progress(
                        on_progress,
                        f"Download MdA {module} → cartella {pdf_path_parent_label(prep.path)}...",
                    )
                    saved = self.enispace.download_attachment(target, str(prep.path))
                    pdf_path = Path(saved)
                    if not pdf_path.is_file():
                        return BatchItemResult(
                            eml_path=source_name,
                            order_number=order,
                            acquisition_module=module,
                            success=False,
                            message="Download completato ma file assente",
                        )

            contract = self.db.get_contract(order)
            if contract and contract.id:
                doc = Document(
                    contract_id=contract.id,
                    remote_id=module,
                    filename=pdf_path.name,
                    doc_type="PDF",
                    local_path=str(pdf_path),
                    size=pdf_path.stat().st_size,
                    downloaded_at=now_iso(),
                    status=DocumentStatus.DOWNLOADED,
                )
                try:
                    doc.sha256 = self.download_service.sha256_file(pdf_path)
                except OSError:
                    pass
                self.db.upsert_document(doc)

            queued = False
            if enqueue:
                self.print_queue.add(
                    pdf_path,
                    order_number=order,
                    acquisition_module=module,
                    eml_name=source_name,
                )
                queued = True

            return BatchItemResult(
                eml_path=source_name,
                order_number=order,
                acquisition_module=module,
                pdf_path=str(pdf_path),
                success=True,
                skipped=skipped,
                queued=queued,
                message=(
                    f"Scaricato e in coda: {pdf_path.name}"
                    if queued and not skipped
                    else (
                        f"Già presente, in coda: {pdf_path.name}"
                        if queued
                        else f"OK: {pdf_path.name}"
                    )
                ),
            )
        finally:
            # Dopo ogni mail (ok o errore): torna ai filtri per la successiva
            try:
                if self.enispace.browser.is_open:
                    self.enispace.return_to_dashboard_filters()
            except Exception as exc:
                logger.warning(
                    "Impossibile tornare alla dashboard filtri dopo notice: %s",
                    exc,
                )

    @staticmethod
    def _register_note(
        *,
        subject: str,
        uid: str = "",
        success: bool,
        detail: str = "",
        order_number: str = "",
        acquisition_module: str = "",
    ) -> str:
        label = (subject or "").strip() or (f"UID {uid}" if uid else "mail")
        if len(label) > 80:
            label = label[:77] + "..."
        if success:
            extra = ""
            if acquisition_module or order_number:
                parts = []
                if acquisition_module:
                    parts.append(f"MdA {acquisition_module}")
                if order_number:
                    parts.append(f"ordine {order_number}")
                extra = f" ({', '.join(parts)})"
            return f"Mail «{label}» letta e gestita{extra}."
        detail_s = (detail or "errore").strip()
        if len(detail_s) > 120:
            detail_s = detail_s[:117] + "..."
        return f"Mail «{label}» non gestita: {detail_s}"

    @staticmethod
    def _progress(cb: Optional[ProgressCallback], msg: str) -> None:
        logger.info("%s", msg)
        if cb:
            try:
                cb(msg)
            except Exception:
                pass

    @staticmethod
    def _item_done(cb: Optional[ItemDoneCallback], item: BatchItemResult) -> None:
        if not cb:
            return
        try:
            cb(item)
        except Exception:
            pass


def pdf_path_parent_label(path: Path | str) -> str:
    try:
        return Path(path).parent.name
    except Exception:
        return ""