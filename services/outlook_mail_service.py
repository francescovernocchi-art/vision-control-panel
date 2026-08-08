"""Lettura automatica cartella Outlook (es. Inbox\\MdA_Eni).

Usa Outlook desktop già autenticato via COM (pywin32) — nessuna password
in chiaro. La cartella di default è «MdA_Eni» sotto Posta in arrivo.

Le chiamate COM possono bloccarsi se Outlook non risponde: usano un
timeout ragionevole e falliscono con messaggio chiaro.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from services.email_parser import AcquisitionNotification, parse_notification_text
from utils.logger import get_logger

logger = get_logger("outlook")

# olFolderInbox
OL_FOLDER_INBOX = 6
# olMail
OL_MAIL_ITEM = 43

# Timeout COM (Outlook può restare appeso se chiuso / in avvio)
DEFAULT_COM_TIMEOUT_SEC = 45

T = TypeVar("T")

@dataclass
class OutlookMessage:
    """Messaggio Outlook mappato su notifica Marketplace."""

    entry_id: str
    subject: str
    sender: str
    received: str
    unread: bool
    notification: AcquisitionNotification
    folder_path: str = ""

def _run_com(fn: Callable[[], T], *, timeout_sec: float = DEFAULT_COM_TIMEOUT_SEC) -> T:
    """Esegue lavoro COM in thread dedicato con timeout (evita hang infinito)."""

    def worker() -> T:
        pythoncom = None
        try:
            import pythoncom  # type: ignore

            pythoncom.CoInitialize()
        except Exception:
            pythoncom = None
        try:
            return fn()
        finally:
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    # wait=False allo shutdown: se COM è appeso, non bloccare forever
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(worker)
        try:
            return future.result(timeout=timeout_sec)
        except FuturesTimeout as exc:
            raise RuntimeError(
                "Outlook non risponde entro "
                f"{int(timeout_sec)} secondi.\n"
                "Aprire Outlook desktop (firmato), attendere il caricamento "
                "completo e riprovare."
            ) from exc
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

class OutlookMailService:
    """Accesso in sola lettura alla cartella Outlook configurata."""

    def __init__(
        self,
        folder_path: str = "Inbox/MdA_Eni",
        *,
        timeout_sec: float = DEFAULT_COM_TIMEOUT_SEC,
    ) -> None:
        # Formati accettati: "Inbox/MdA_Eni", "MdA_Eni", "Inbox.MdA_Eni"
        self.folder_path = (folder_path or "Inbox/MdA_Eni").strip()
        self.timeout_sec = float(timeout_sec)

    def _outlook(self) -> Any:
        try:
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Modulo pywin32 non installato.\n"
                "Eseguire: pip install pywin32"
            ) from exc
        try:
            return win32com.client.Dispatch("Outlook.Application")
        except Exception as exc:
            raise RuntimeError(
                "Impossibile avviare Outlook via COM.\n"
                "Aprire Outlook desktop e riprovare."
            ) from exc

    def test_connection(self) -> tuple[bool, str]:
        try:
            def work() -> tuple[bool, str]:
                folder = self._resolve_folder_unlocked()
                count = int(folder.Items.Count)
                path = self._folder_display_path(folder)
                return True, f"OK — {path} ({count} messaggi)"

            return _run_com(work, timeout_sec=self.timeout_sec)
        except Exception as exc:
            return False, self._friendly_com_error(exc)

    @staticmethod
    def _friendly_com_error(exc: BaseException) -> str:
        raw = str(exc)
        low = raw.lower()
        if "non è connesso" in low or "non e connesso" in low or "not connected" in low:
            return (
                "Outlook non è connesso al profilo di posta.\n"
                "Apri Outlook desktop, completa l'accesso / MFA e attendi "
                "che la posta sia online, poi riprova.\n\n"
                f"Dettaglio: {raw}"
            )
        if "outlook non risponde" in low:
            return raw
        if "pywin32" in low or "impossibile avviare outlook" in low:
            return raw
        return raw

    def list_messages(
        self,
        *,
        unread_only: bool = True,
        only_acquisition: bool = True,
        limit: int = 100,
    ) -> list[OutlookMessage]:
        def work() -> list[OutlookMessage]:
            folder = self._resolve_folder_unlocked()
            items = folder.Items
            try:
                items.Sort("[ReceivedTime]", True)
            except Exception:
                pass

            results: list[OutlookMessage] = []
            try:
                if unread_only:
                    filtered = items.Restrict("[UnRead] = true")
                else:
                    filtered = items
            except Exception:
                filtered = items

            total = int(filtered.Count)
            logger.info(
                "Outlook cartella %s: %s messaggi (unread_only=%s)",
                self._folder_display_path(folder),
                total,
                unread_only,
            )

            for i in range(1, total + 1):
                if len(results) >= limit:
                    break
                try:
                    item = filtered.Item(i)
                except Exception:
                    continue
                try:
                    if int(getattr(item, "Class", 0)) != OL_MAIL_ITEM:
                        continue
                except Exception:
                    pass

                try:
                    subject = str(getattr(item, "Subject", "") or "")
                    body = str(getattr(item, "Body", "") or "")
                    sender = str(
                        getattr(item, "SenderEmailAddress", None)
                        or getattr(item, "SenderName", "")
                        or ""
                    )
                    entry_id = str(getattr(item, "EntryID", "") or "")
                    unread = bool(getattr(item, "UnRead", False))
                    received = ""
                    try:
                        rt = getattr(item, "ReceivedTime", None)
                        received = str(rt) if rt is not None else ""
                    except Exception:
                        pass
                except Exception as exc:
                    logger.debug("Lettura messaggio Outlook fallita: %s", exc)
                    continue

                notice = parse_notification_text(
                    subject=subject, body=body, sender=sender
                )
                if only_acquisition and not notice.is_complete:
                    if "modulo di acquisizione" not in subject.lower():
                        continue
                    if not notice.order_number and not notice.acquisition_module:
                        continue

                results.append(
                    OutlookMessage(
                        entry_id=entry_id,
                        subject=subject,
                        sender=sender,
                        received=received,
                        unread=unread,
                        notification=notice,
                        folder_path=self._folder_display_path(folder),
                    )
                )

            return results

        return _run_com(work, timeout_sec=self.timeout_sec)

    def mark_as_read(self, entry_id: str) -> None:
        if not entry_id:
            return

        def work() -> None:
            app = self._outlook()
            ns = app.GetNamespace("MAPI")
            item = ns.GetItemFromID(entry_id)
            item.UnRead = False
            item.Save()

        try:
            _run_com(work, timeout_sec=min(20.0, self.timeout_sec))
        except Exception as exc:
            logger.warning("Impossibile segnare come letta %s: %s", entry_id[:20], exc)

    def _resolve_folder(self) -> Any:
        """Risolve la cartella con timeout (uso esterno / test)."""
        return _run_com(self._resolve_folder_unlocked, timeout_sec=self.timeout_sec)

    def _resolve_folder_unlocked(self) -> Any:
        """Risolve la cartella; chiamare solo da thread già protetto da timeout."""
        app = self._outlook()
        ns = app.GetNamespace("MAPI")
        inbox = ns.GetDefaultFolder(OL_FOLDER_INBOX)

        raw = self.folder_path.replace("\\", "/").strip("/")
        # Alias "Inbox.MdA_Eni" → Inbox/MdA_Eni
        if raw.lower().startswith("inbox.") and "/" not in raw:
            raw = "Inbox/" + raw.split(".", 1)[1]

        parts = [p for p in raw.split("/") if p]
        if parts and parts[0].lower() in (
            "inbox",
            "posta in arrivo",
            "boîte de réception",
        ):
            parts = parts[1:]
            current = inbox
        elif len(parts) == 1:
            found = self._find_subfolder_by_name(inbox, parts[0])
            if found is not None:
                return found
            found = self._find_folder_recursive(ns, parts[0])
            if found is not None:
                return found
            raise RuntimeError(
                f"Cartella Outlook «{parts[0]}» non trovata sotto Posta in arrivo.\n"
                "Verificare il nome in Impostazioni (es. Inbox/MdA_Eni)."
            )
        else:
            current = inbox

        for name in parts:
            nxt = self._find_subfolder_by_name(current, name)
            if nxt is None:
                raise RuntimeError(
                    f"Sottocartella Outlook «{name}» non trovata in "
                    f"«{self._folder_display_path(current)}».\n"
                    f"Percorso configurato: {self.folder_path}"
                )
            current = nxt
        return current

    @staticmethod
    def _find_subfolder_by_name(parent: Any, name: str) -> Any:
        target = name.strip().lower()
        try:
            folders = parent.Folders
            for i in range(1, int(folders.Count) + 1):
                f = folders.Item(i)
                if str(f.Name).strip().lower() == target:
                    return f
        except Exception:
            pass
        return None

    def _find_folder_recursive(self, namespace: Any, name: str) -> Any:
        target = name.strip().lower()

        def walk(folder: Any, depth: int = 0) -> Any:
            if depth > 8:
                return None
            try:
                if str(folder.Name).strip().lower() == target:
                    return folder
                folders = folder.Folders
                for i in range(1, int(folders.Count) + 1):
                    found = walk(folders.Item(i), depth + 1)
                    if found is not None:
                        return found
            except Exception:
                return None
            return None

        try:
            for i in range(1, int(namespace.Folders.Count) + 1):
                found = walk(namespace.Folders.Item(i))
                if found is not None:
                    return found
        except Exception:
            pass
        return None

    @staticmethod
    def _folder_display_path(folder: Any) -> str:
        try:
            return str(folder.FolderPath)
        except Exception:
            try:
                return str(folder.Name)
            except Exception:
                return "(cartella Outlook)"
