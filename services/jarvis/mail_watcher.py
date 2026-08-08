"""MailWatcher — riusa IMAP + parser; solo candidati ENI/MdA."""

from __future__ import annotations

from typing import Callable, Optional

from services.email_parser import AcquisitionNotification
from services.imap_mail_service import ImapConfig, ImapMailService, ImapMessage
from services.jarvis.logger import JarvisLogger
from services.jarvis.models import MailCandidate
from services.jarvis.repository import JobRepository
from services.jarvis.states import JarvisState, LogLevel
from utils.logger import get_logger

logger = get_logger("jarvis.mail")

ProgressCallback = Callable[[str], None]


class MailWatcher:
    """Controlla la casella e restituisce mail MdA non ancora gestite."""

    def __init__(
        self,
        repo: JobRepository,
        *,
        jarvis_logger: Optional[JarvisLogger] = None,
    ) -> None:
        self.repo = repo
        self.jlog = jarvis_logger

    def poll(
        self,
        config: ImapConfig,
        *,
        limit: int = 30,
        on_progress: Optional[ProgressCallback] = None,
    ) -> list[MailCandidate]:
        """Elenca candidati nuovi (non già in jarvis_jobs / imap_processed)."""
        self._log("Controllo casella mail", JarvisState.CONTROLLO_MAIL)
        if on_progress:
            on_progress("JARVIS: controllo casella...")

        imap = ImapMailService(config)
        try:
            messages = imap.list_messages(
                unread_only=config.unread_only,
                only_acquisition=True,
                limit=limit,
                on_progress=on_progress,
            )
        except Exception as exc:
            logger.exception("MailWatcher poll fallito: %s", exc)
            self._log(
                f"Errore controllo mail: {exc}",
                JarvisState.ERRORE,
                level=LogLevel.ERROR,
            )
            raise

        candidates: list[MailCandidate] = []
        for msg in messages:
            cand = self._to_candidate(msg)
            if not cand:
                continue
            if self.repo.mail_already_handled(cand.mail_id):
                continue
            # Serve almeno modulo o ordine (filtro già in IMAP, doppio check)
            if not (cand.order_number or cand.acquisition_module):
                continue
            candidates.append(cand)

        if candidates:
            self._log(
                f"Trovate {len(candidates)} mail candidate",
                JarvisState.NUOVA_MAIL,
                level=LogLevel.SUCCESS,
            )
        else:
            self._log("Nessuna nuova mail MdA", JarvisState.IN_ATTESA)

        return candidates

    def _to_candidate(self, msg: ImapMessage) -> Optional[MailCandidate]:
        notice = msg.notification or AcquisitionNotification(
            subject=msg.subject, sender=msg.sender, raw_body=msg.body
        )
        # Chiave stabile allineata a imap_processed: folder:uid
        # Message-ID salvato a parte per tracciabilità
        mail_id = (msg.entry_id or "").strip()
        if not mail_id:
            return None
        message_id = (getattr(msg, "message_id", None) or "").strip()
        return MailCandidate(
            mail_id=mail_id,
            uid=msg.uid,
            folder=msg.folder,
            message_id=message_id,
            subject=msg.subject or "",
            sender=msg.sender or "",
            body=msg.body or "",
            received_at=msg.message_date or "",
            order_number=(notice.order_number or "").strip(),
            contract_number=(notice.contract_number or "").strip(),
            acquisition_module=(notice.acquisition_module or "").strip(),
            raw_notification=notice,
        )

    def _log(
        self,
        message: str,
        state: str,
        *,
        level: str = LogLevel.INFO,
    ) -> None:
        if self.jlog:
            self.jlog.log(message, level=level, state=state)
