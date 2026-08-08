"""Test JARVIS supervisore (mock, senza IMAP/eniSpace live)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from database.db import Database
from services.batch_service import BatchItemResult, BatchService
from services.jarvis.logger import JarvisLogger
from services.jarvis.mail_watcher import MailWatcher
from services.jarvis.models import JarvisJob, MailCandidate
from services.jarvis.notifications import NotificationService
from services.jarvis.processor import JobProcessor, NeedsAttentionError, TransientError
from services.jarvis.queue import JobQueue
from services.jarvis.repository import JobRepository
from services.jarvis.states import JobOutcome, JobStatus, JarvisState
from services.print_queue_service import PrintQueueService


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "test_jarvis.db")


@pytest.fixture
def repo(db: Database) -> JobRepository:
    return JobRepository(db)


@pytest.fixture
def queue(repo: JobRepository) -> JobQueue:
    return JobQueue(repo, logger=JarvisLogger(), notifications=NotificationService())


def _candidate(mail_id: str = "INBOX.MdA_Eni:100", **kwargs) -> MailCandidate:
    base = dict(
        mail_id=mail_id,
        uid="100",
        folder="INBOX.MdA_Eni",
        subject="Notifica Modulo di Acquisizione 2013627410 - 4310758365",
        sender="marketplace@eni.com",
        order_number="4310758365",
        contract_number="2500036209",
        acquisition_module="2013627410",
    )
    base.update(kwargs)
    return MailCandidate(**base)


def test_new_valid_mail_enqueued(queue: JobQueue, repo: JobRepository) -> None:
    job = queue.enqueue(_candidate(), simulation=True)
    assert job is not None
    assert job.status == JobStatus.PENDING
    assert repo.get_by_mail_id("INBOX.MdA_Eni:100") is not None


def test_already_processed_skipped(queue: JobQueue, repo: JobRepository, db: Database) -> None:
    queue.enqueue(_candidate())
    again = queue.enqueue(_candidate())
    assert again is None

    # Anche se già in imap_processed
    db.mark_imap_processed("INBOX.MdA_Eni:200", result="success")
    skipped = queue.enqueue(_candidate(mail_id="INBOX.MdA_Eni:200", uid="200"))
    assert skipped is None


def test_two_mails_queued(queue: JobQueue) -> None:
    j1 = queue.enqueue(_candidate("INBOX.MdA_Eni:1", uid="1"))
    j2 = queue.enqueue(_candidate("INBOX.MdA_Eni:2", uid="2", order_number="999"))
    assert j1 and j2
    assert queue.count_pending() == 2
    first = queue.next_pending()
    assert first is not None
    assert first.mail_id == j1.mail_id


def test_unrecognized_contract_needs_attention(repo: JobRepository) -> None:
    batch = MagicMock(spec=BatchService)
    printer = MagicMock(spec=PrintQueueService)
    proc = JobProcessor(
        repo=repo,
        batch=batch,
        print_queue=printer,
        jarvis_logger=JarvisLogger(),
        notifications=NotificationService(),
    )
    job = repo.create(
        JarvisJob(
            mail_id="INBOX.MdA_Eni:x",
            subject="mail senza ordine",
            status=JobStatus.PENDING,
            simulation=True,
            max_attempts=1,
        )
    )
    result = proc.process(job)
    assert result.status == JobStatus.NEEDS_ATTENTION
    assert "non" in (result.error_message or "").lower() or "intervento" in (
        result.outcome or ""
    ).lower()
    batch._process_notice.assert_not_called()


def test_simulation_no_print(repo: JobRepository) -> None:
    batch = MagicMock(spec=BatchService)
    printer = MagicMock(spec=PrintQueueService)
    proc = JobProcessor(
        repo=repo,
        batch=batch,
        print_queue=printer,
        jarvis_logger=JarvisLogger(),
        notifications=NotificationService(),
    )
    job = repo.create(
        JarvisJob(
            mail_id="INBOX.MdA_Eni:sim",
            order_number="4310758365",
            acquisition_module="2013627410",
            contract_number="2500036209",
            status=JobStatus.PENDING,
            simulation=True,
            max_attempts=1,
        )
    )
    result = proc.process(job)
    assert result.status == JobStatus.COMPLETED
    assert result.outcome == JobOutcome.SIMULATA
    assert result.docs_printed == 0
    printer.print_file.assert_not_called()
    batch._process_notice.assert_not_called()


def test_login_fail_retry_then_attention(repo: JobRepository) -> None:
    from services.exceptions import LoginFailedError

    batch = MagicMock(spec=BatchService)
    batch._process_notice.side_effect = LoginFailedError("login ko")
    printer = MagicMock(spec=PrintQueueService)
    proc = JobProcessor(
        repo=repo,
        batch=batch,
        print_queue=printer,
        jarvis_logger=JarvisLogger(),
        notifications=NotificationService(),
    )
    job = repo.create(
        JarvisJob(
            mail_id="INBOX.MdA_Eni:login",
            order_number="1",
            acquisition_module="2",
            status=JobStatus.PENDING,
            simulation=False,
            max_attempts=2,
        )
    )
    with patch("services.jarvis.processor.time.sleep"):
        result = proc.process(job)
    assert result.status == JobStatus.NEEDS_ATTENTION
    assert job.attempts == 2
    assert batch._process_notice.call_count == 2


def test_download_fail_transient(repo: JobRepository) -> None:
    from services.exceptions import DownloadFailedError

    batch = MagicMock(spec=BatchService)
    batch._process_notice.side_effect = DownloadFailedError("dl fail")
    printer = MagicMock(spec=PrintQueueService)
    proc = JobProcessor(
        repo=repo,
        batch=batch,
        print_queue=printer,
        jarvis_logger=JarvisLogger(),
        notifications=NotificationService(),
    )
    job = repo.create(
        JarvisJob(
            mail_id="INBOX.MdA_Eni:dl",
            order_number="1",
            acquisition_module="2",
            status=JobStatus.PENDING,
            max_attempts=1,
        )
    )
    result = proc.process(job)
    assert result.status == JobStatus.NEEDS_ATTENTION


def test_print_fail_needs_attention(repo: JobRepository, tmp_path: Path) -> None:
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    batch = MagicMock(spec=BatchService)
    batch._process_notice.return_value = BatchItemResult(
        eml_path="mail",
        order_number="1",
        acquisition_module="2",
        pdf_path=str(pdf),
        success=True,
        message="ok",
    )
    batch.db = repo.db
    printer = MagicMock(spec=PrintQueueService)
    printer.print_file.side_effect = OSError("stampante offline")
    printer.list.return_value = []
    proc = JobProcessor(
        repo=repo,
        batch=batch,
        print_queue=printer,
        jarvis_logger=JarvisLogger(),
        notifications=NotificationService(),
    )
    job = repo.create(
        JarvisJob(
            mail_id="INBOX.MdA_Eni:print",
            order_number="1",
            acquisition_module="2",
            status=JobStatus.PENDING,
            max_attempts=1,
        )
    )
    result = proc.process(job)
    assert result.status == JobStatus.NEEDS_ATTENTION
    assert "stampa" in (result.error_message or "").lower()


def test_processing_recovery_no_reprint(repo: JobRepository) -> None:
    job = repo.create(
        JarvisJob(
            mail_id="INBOX.MdA_Eni:crash",
            order_number="1",
            acquisition_module="2",
            status=JobStatus.PROCESSING,
            state=JarvisState.STAMPA,
        )
    )
    recovered = repo.recover_interrupted_processing()
    assert len(recovered) == 1
    refreshed = repo.get_by_id(job.id or 0)
    assert refreshed is not None
    assert refreshed.status == JobStatus.NEEDS_ATTENTION
    assert "ristampa" in (refreshed.error_message or "").lower() or "intervento" in (
        refreshed.outcome or ""
    ).lower()


def test_retry_delays_constant() -> None:
    from services.jarvis.states import RETRY_DELAYS_SEC

    assert RETRY_DELAYS_SEC == (10, 30, 60)


def test_no_connection_mail_watcher(repo: JobRepository) -> None:
    watcher = MailWatcher(repo, jarvis_logger=JarvisLogger())
    cfg = MagicMock()
    cfg.unread_only = True
    with patch(
        "services.jarvis.mail_watcher.ImapMailService"
    ) as MockImap:
        MockImap.return_value.list_messages.side_effect = ConnectionError("offline")
        with pytest.raises(ConnectionError):
            watcher.poll(cfg)


def test_unexpected_error_attention(repo: JobRepository) -> None:
    batch = MagicMock(spec=BatchService)
    batch._process_notice.side_effect = RuntimeError("boom")
    printer = MagicMock(spec=PrintQueueService)
    proc = JobProcessor(
        repo=repo,
        batch=batch,
        print_queue=printer,
        jarvis_logger=JarvisLogger(),
        notifications=NotificationService(),
    )
    job = repo.create(
        JarvisJob(
            mail_id="INBOX.MdA_Eni:boom",
            order_number="1",
            acquisition_module="2",
            status=JobStatus.PENDING,
            max_attempts=1,
        )
    )
    result = proc.process(job)
    assert result.status == JobStatus.NEEDS_ATTENTION
    assert "imprevisto" in (result.error_message or "").lower()


def test_contract_not_found_no_retry(repo: JobRepository) -> None:
    from services.exceptions import ContractNotFoundError

    batch = MagicMock(spec=BatchService)
    batch._process_notice.side_effect = ContractNotFoundError("ordine assente")
    printer = MagicMock(spec=PrintQueueService)
    proc = JobProcessor(
        repo=repo,
        batch=batch,
        print_queue=printer,
        jarvis_logger=JarvisLogger(),
        notifications=NotificationService(),
    )
    job = repo.create(
        JarvisJob(
            mail_id="INBOX.MdA_Eni:nf",
            order_number="1",
            acquisition_module="2",
            status=JobStatus.PENDING,
            max_attempts=3,
        )
    )
    result = proc.process(job)
    assert result.status == JobStatus.NEEDS_ATTENTION
    assert batch._process_notice.call_count == 1


def test_successful_real_flow_print_wording(
    repo: JobRepository, tmp_path: Path
) -> None:
    pdf = tmp_path / "mda.pdf"
    pdf.write_bytes(b"%PDF-1.4 content")
    batch = MagicMock(spec=BatchService)
    batch._process_notice.return_value = BatchItemResult(
        eml_path="mail",
        order_number="4310758365",
        acquisition_module="2013627410",
        pdf_path=str(pdf),
        success=True,
        message="ok",
    )
    batch.db = repo.db
    printer = MagicMock(spec=PrintQueueService)
    printer.list.return_value = []
    events: list = []
    jlog = JarvisLogger()
    jlog.add_listener(lambda e: events.append(e.message))
    proc = JobProcessor(
        repo=repo,
        batch=batch,
        print_queue=printer,
        jarvis_logger=jlog,
        notifications=NotificationService(),
    )
    job = repo.create(
        JarvisJob(
            mail_id="INBOX.MdA_Eni:ok",
            mail_folder="INBOX.MdA_Eni",
            mail_uid="99",
            order_number="4310758365",
            acquisition_module="2013627410",
            status=JobStatus.PENDING,
            max_attempts=1,
        )
    )
    result = proc.process(job)
    assert result.status == JobStatus.COMPLETED
    assert result.docs_printed == 1
    printer.print_file.assert_called_once()
    assert any("CODA DI STAMPA" in m for m in events)
    assert not any("STAMPATO CON SUCCESSO" in m for m in events)
    assert repo.db.is_imap_processed("INBOX.MdA_Eni:99")
