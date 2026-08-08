"""Lettura casella via IMAP (stesso approccio di VIS Protocollo).

Configurazione tipica SecureMail / Register / VIS:
  IMAP host: pop.securemail.pro  porta 993  SSL
  SMTP host: authsmtp.securemail.pro  porta 465  SSL (implicit TLS)
  Cartella:  INBOX.MdA_Eni  (alias accettati: Inbox.MdA_Eni, MdA_Eni, …)

Nota: alcuni provider usano imap.securemail.pro; Register/VIS usano pop.*
anche per IMAP su 993. Stessa username+password per IMAP e SMTP (keyring).

Password solo via Windows Credential Manager (keyring), mai in chiaro nel DB.
"""

from __future__ import annotations

import base64
import email
import imaplib
import re
import smtplib
import ssl
from dataclasses import dataclass
from email import policy
from email.header import decode_header, make_header
from email.message import Message
from typing import Callable, Optional

from services.email_parser import AcquisitionNotification, parse_notification_text
from utils.logger import get_logger

logger = get_logger("imap")

DEFAULT_FOLDER = "INBOX.MdA_Eni"
DEFAULT_IMAP_HOST = "pop.securemail.pro"
DEFAULT_SMTP_HOST = "authsmtp.securemail.pro"
IMAP_SOCKET_TIMEOUT_SEC = 30
# Lettura cartella (SEARCH + FETCH): limite globale per non bloccare SYNC all'infinito
IMAP_OP_TIMEOUT_SEC = 180

ProgressCallback = Callable[[str], None]


@dataclass
class ImapMessage:
    """Messaggio IMAP mappato su notifica Marketplace."""

    uid: str
    folder: str
    subject: str = ""
    sender: str = ""
    body: str = ""
    notification: Optional[AcquisitionNotification] = None
    unseen: bool = False
    # Data messaggio (YYYY-MM-DD) da header Date, se disponibile
    message_date: str = ""
    # Message-ID RFC (se presente) — utile per anti-dup JARVIS
    message_id: str = ""

    @property
    def entry_id(self) -> str:
        """Chiave stabile per deduplica: cartella + UID IMAP."""
        return f"{self.folder}:{self.uid}"


@dataclass
class ImapConfig:
    host: str = DEFAULT_IMAP_HOST
    port: int = 993
    security: str = "SSL"  # SSL | STARTTLS | NONE
    username: str = ""
    password: str = ""
    folder: str = DEFAULT_FOLDER
    unread_only: bool = True
    # SMTP (opzionale — per test / uso futuro)
    smtp_host: str = DEFAULT_SMTP_HOST
    smtp_port: int = 465
    smtp_security: str = "SSL"  # SSL | STARTTLS | NONE


class ImapMailError(RuntimeError):
    """Errore IMAP/SMTP con messaggio utente in italiano."""


def _ssl_context() -> ssl.SSLContext:
    """Contesto TLS di sistema (verifica certificato + hostname)."""
    return ssl.create_default_context()


def format_mail_error(exc: BaseException, *, kind: str = "IMAP") -> str:
    """Messaggio utente in italiano per errori tipici SecureMail/Register."""
    text = str(exc).strip() or type(exc).__name__
    low = text.lower()
    if "password casella errata" in low:
        return text
    auth_hints = (
        "authenticationfailed",
        "authentication rejected",
        "auth failed",
        "invalid credentials",
        "login failed",
        "535",
    )
    if any(h in low for h in auth_hints):
        return (
            f"Password casella errata o non salvata correttamente ({kind}).\n"
            "Stessa password per IMAP e SMTP: reinseriscila e premi "
            "«SALVA CRED. CASELLA», poi riprova TEST IMAP / TEST SMTP.\n"
            f"Dettaglio: {text}"
        )
    if (
        "connection unexpectedly closed" in low
        or "server disconnected" in low
        or "please run connect()" in low
    ):
        return (
            f"Connessione {kind} chiusa dal server durante l'accesso "
            "(di solito password errata/non salvata — stessa per IMAP e SMTP).\n"
            "Reinserire la password e «SALVA CRED. CASELLA».\n"
            f"Dettaglio: {text}"
        )
    if "certificate" in low or ("ssl" in low and "error" in low) or "tls" in low:
        return (
            f"Errore TLS/{kind} verso il server.\n"
            "Verificare host (pop.securemail.pro / authsmtp.securemail.pro), "
            "porta e sicurezza SSL.\n"
            f"Dettaglio: {text}"
        )
    if "timed out" in low or "timeout" in low:
        return (
            f"Timeout connessione {kind}.\n"
            "Verificare rete/firewall verso SecureMail.\n"
            f"Dettaglio: {text}"
        )
    return text


def decode_imap_folder_name(name: str) -> str:
    """Decodifica nome cartella IMAP (modified UTF-7 → testo leggibile)."""
    raw = (name or "").strip()
    if not raw or "&" not in raw:
        return raw

    def _repl(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "":
            return "&"
        try:
            b64 = token.replace(",", "/")
            pad = "=" * ((4 - len(b64) % 4) % 4)
            return base64.b64decode(b64 + pad).decode("utf-16-be")
        except Exception:
            return match.group(0)

    try:
        return re.sub(r"&([^-]*)-", _repl, raw)
    except Exception:
        return raw


def sort_imap_folders(names: list[str]) -> list[str]:
    """Ordina cartelle: INBOX, sottocartelle MdA, resto alfabetico."""

    def key(name: str) -> tuple:
        low = name.lower()
        if low == "inbox":
            return (0, name)
        if "mda_eni" in low or "mda" in low:
            return (1, name)
        if low.startswith("inbox"):
            return (2, name)
        return (3, name)

    seen: set[str] = set()
    ordered: list[str] = []
    for n in sorted(names, key=key):
        if n and n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def _decode_header_value(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


def _ymd_to_imap_date(ymd: str) -> str:
    """Converte YYYY-MM-DD → formato IMAP SEARCH (es. 07-Aug-2026)."""
    from datetime import date as date_cls

    raw = (ymd or "").strip()[:10]
    try:
        y, m, d = (int(x) for x in raw.split("-", 2))
        return date_cls(y, m, d).strftime("%d-%b-%Y")
    except Exception as exc:
        raise ValueError(f"Data non valida per IMAP: {ymd!r}") from exc


def _message_date_ymd(msg: Message) -> str:
    """Estrae YYYY-MM-DD dall'header Date del messaggio (fallback: oggi)."""
    from datetime import date as date_cls
    from email.utils import parsedate_to_datetime

    raw = msg.get("Date")
    if raw:
        try:
            dt = parsedate_to_datetime(str(raw))
            if dt is not None:
                return dt.date().isoformat()
        except Exception:
            pass
    return date_cls.today().isoformat()


def _body_from_message(msg: Message) -> str:
    parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                parts.append(_decode_part(part))
            elif ctype == "text/html" and not parts:
                html = _decode_part(part)
                parts.append(re.sub(r"<[^>]+>", " ", html))
    else:
        parts.append(_decode_part(msg))
    return "\n".join(p for p in parts if p).strip()


def _decode_part(part: Message) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            raw = part.get_payload()
            return raw if isinstance(raw, str) else ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:
        return ""


def normalize_folder_candidates(folder: str) -> list[str]:
    """Genera candidati cartella IMAP (dot / slash / solo nome)."""
    raw = (folder or DEFAULT_FOLDER).strip()
    if not raw:
        raw = DEFAULT_FOLDER
    # Inbox.MdA_Eni → INBOX.MdA_Eni
    raw = re.sub(r"(?i)^inbox([./])", r"INBOX\1", raw)
    variants: list[str] = []

    def add(name: str) -> None:
        name = name.strip().strip("/")
        if name and name not in variants:
            variants.append(name)

    add(raw)
    add(raw.replace("/", "."))
    add(raw.replace(".", "/"))
    # Solo nome cartella
    leaf = re.split(r"[./]", raw)[-1]
    if leaf:
        add(leaf)
        add(f"INBOX.{leaf}")
        add(f"INBOX/{leaf}")
        add(f"Inbox.{leaf}")
    return variants


class ImapMailService:
    """Accesso IMAP in sola lettura (+ mark read) alla cartella configurata."""

    def __init__(self, config: ImapConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------ connect
    @staticmethod
    def _apply_socket_timeout(client: imaplib.IMAP4, seconds: float = IMAP_SOCKET_TIMEOUT_SEC) -> None:
        """Garantisce timeout su socket anche dopo login (evita hang infinitio)."""
        try:
            sock = getattr(client, "socket", None)
            if callable(sock):
                s = sock()
            else:
                s = getattr(client, "sock", None)
            if s is not None:
                s.settimeout(float(seconds))
        except Exception as exc:
            logger.debug("Impostazione timeout socket IMAP: %s", exc)

    @staticmethod
    def _safe_logout(client: Optional[imaplib.IMAP4]) -> None:
        if client is None:
            return
        try:
            ImapMailService._apply_socket_timeout(client, min(10.0, IMAP_SOCKET_TIMEOUT_SEC))
            client.logout()
        except Exception:
            try:
                client.shutdown()
            except Exception:
                pass

    def _connect(self) -> imaplib.IMAP4:
        cfg = self.config
        if not cfg.host or not cfg.username or not cfg.password:
            raise ImapMailError(
                "Configurazione IMAP incompleta.\n"
                "Impostazioni → Casella IMAP: host, utente e password."
            )
        security = (cfg.security or "SSL").upper()
        ctx = _ssl_context()
        try:
            if security == "SSL":
                client: imaplib.IMAP4 = imaplib.IMAP4_SSL(
                    cfg.host,
                    int(cfg.port or 993),
                    ssl_context=ctx,
                    timeout=IMAP_SOCKET_TIMEOUT_SEC,
                )
            else:
                client = imaplib.IMAP4(
                    cfg.host, int(cfg.port or 143), timeout=IMAP_SOCKET_TIMEOUT_SEC
                )
                if security == "STARTTLS":
                    client.starttls(ssl_context=ctx)
            self._apply_socket_timeout(client)
            client.login(cfg.username, cfg.password)
            self._apply_socket_timeout(client)
            return client
        except ImapMailError:
            raise
        except Exception as exc:
            # Messaggio grezzo: format_mail_error lo traduce in test_connection
            raise ImapMailError(
                f"Connessione IMAP fallita ({cfg.host}:{cfg.port}).\n{exc}"
            ) from exc

    def test_connection(self) -> tuple[bool, str, list[str]]:
        """Verifica login + cartella; restituisce anche l'elenco mailbox."""
        try:
            client = self._connect()
            try:
                folders = self._list_folder_names(client)
                folder = self._select_folder(client, self.config.folder)
                typ, data = client.status(folder, "(MESSAGES UNSEEN)")
                info = ""
                if typ == "OK" and data and data[0]:
                    info = data[0].decode(errors="replace")
                sample = ", ".join(folders[:8])
                extra = f" … +{len(folders) - 8}" if len(folders) > 8 else ""
                msg = (
                    f"IMAP OK — cartella «{folder}»"
                    + (f" [{info}]" if info else "")
                    + (f". Cartelle: {sample}{extra}" if folders else "")
                )
                return True, msg, folders
            finally:
                self._safe_logout(client)
        except Exception as exc:
            return False, format_mail_error(exc, kind="IMAP"), []

    def test_smtp(self) -> tuple[bool, str]:
        """Test SMTP con stessa username/password IMAP (SSL implicito su 465)."""
        cfg = self.config
        host = (cfg.smtp_host or "").strip()
        if not host:
            return False, "SMTP host non configurato."
        if not cfg.username or not cfg.password:
            return False, "Credenziali casella mancanti (stesse di IMAP)."
        security = (cfg.smtp_security or "SSL").upper()
        port = int(cfg.smtp_port or 465)
        # Porta 465 = sempre SSL implicito (SMTP_SSL), non STARTTLS
        use_ssl = security == "SSL" or port == 465
        ctx = _ssl_context()
        smtp: Optional[smtplib.SMTP] = None
        try:
            if use_ssl:
                smtp = smtplib.SMTP_SSL(
                    host, port, timeout=25, context=ctx
                )
            else:
                smtp = smtplib.SMTP(host, port, timeout=25)
                if security == "STARTTLS":
                    smtp.ehlo()
                    smtp.starttls(context=ctx)
            smtp.ehlo()
            # AUTH LOGIN esplicito: SecureMail su AUTH fallita chiude la socket
            # e spesso riporta solo "Connection unexpectedly closed".
            smtp.user = cfg.username
            smtp.password = cfg.password
            try:
                smtp.auth("LOGIN", smtp.auth_login)
            except AttributeError:
                smtp.login(cfg.username, cfg.password)
            except smtplib.SMTPAuthenticationError:
                raise
            except smtplib.SMTPException:
                # LOGIN non gestito → fallback login() (PLAIN/LOGIN automatico)
                smtp.login(cfg.username, cfg.password)
            return True, f"SMTP OK — {host}:{port} ({'SSL' if use_ssl else security})"
        except smtplib.SMTPAuthenticationError as exc:
            return False, format_mail_error(exc, kind="SMTP")
        except smtplib.SMTPServerDisconnected as exc:
            detail = self._smtp_auth_login_probe(
                host, port, "SSL" if use_ssl else security, ctx
            )
            if detail:
                return False, format_mail_error(RuntimeError(detail), kind="SMTP")
            return False, format_mail_error(exc, kind="SMTP")
        except Exception as exc:
            return False, format_mail_error(exc, kind="SMTP")
        finally:
            if smtp is not None:
                try:
                    smtp.quit()
                except Exception:
                    try:
                        smtp.close()
                    except Exception:
                        pass

    def _smtp_auth_login_probe(
        self,
        host: str,
        port: int,
        security: str,
        ctx: ssl.SSLContext,
    ) -> str:
        """Rilegge la risposta AUTH LOGIN (es. 535) se smtplib ha solo il disconnect."""
        import socket

        cfg = self.config
        sock: Optional[socket.socket] = None
        ssock: Optional[ssl.SSLSocket] = None
        try:
            raw = socket.create_connection((host, port), timeout=15)
            sock = raw
            if security == "SSL" or port == 465:
                ssock = ctx.wrap_socket(raw, server_hostname=host)
                stream: socket.socket = ssock
            else:
                stream = sock

            def _recv() -> str:
                data = b""
                stream.settimeout(8)
                while True:
                    chunk = stream.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if data.endswith(b"\r\n"):
                        break
                return data.decode(errors="replace").strip()

            _recv()  # banner
            stream.sendall(b"EHLO vis-enispace\r\n")
            _recv()
            if security == "STARTTLS" and port != 465:
                stream.sendall(b"STARTTLS\r\n")
                _recv()
                ssock = ctx.wrap_socket(sock, server_hostname=host)
                stream = ssock
                stream.sendall(b"EHLO vis-enispace\r\n")
                _recv()
            stream.sendall(b"AUTH LOGIN\r\n")
            _recv()
            stream.sendall(
                base64.b64encode(cfg.username.encode("utf-8")) + b"\r\n"
            )
            _recv()
            stream.sendall(
                base64.b64encode(cfg.password.encode("utf-8")) + b"\r\n"
            )
            return _recv()
        except Exception as exc:
            logger.debug("SMTP AUTH probe fallita: %s", exc)
            return ""
        finally:
            for s in (ssock, sock):
                if s is not None:
                    try:
                        s.close()
                    except Exception:
                        pass

    def list_folders(self) -> list[str]:
        """Elenco mailbox IMAP (nomi decodificati, ordinati)."""
        client = self._connect()
        try:
            return self._list_folder_names(client)
        finally:
            self._safe_logout(client)

    def _progress(self, cb: Optional[ProgressCallback], msg: str) -> None:
        logger.info("%s", msg)
        if cb:
            try:
                cb(msg)
            except Exception:
                pass

    # ------------------------------------------------------------------ fetch
    def list_messages(
        self,
        *,
        unread_only: Optional[bool] = None,
        only_acquisition: bool = True,
        limit: int = 50,
        on_date: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> list[ImapMessage]:
        """Elenca messaggi. on_date = YYYY-MM-DD filtra per giorno (IMAP ON + header)."""
        unread = (
            self.config.unread_only if unread_only is None else bool(unread_only)
        )
        day = (on_date or "").strip()[:10] or None
        self._progress(on_progress, "IMAP: connessione in corso...")
        client = self._connect()
        try:
            self._progress(
                on_progress,
                f"IMAP: selezione cartella «{self.config.folder or DEFAULT_FOLDER}»...",
            )
            folder = self._select_folder(client, self.config.folder)
            self._progress(on_progress, f"IMAP: cartella «{folder}» selezionata.")
            parts: list[str] = []
            if unread:
                parts.append("UNSEEN")
            if day:
                parts.append(f"ON {_ymd_to_imap_date(day)}")
            criteria = " ".join(parts) if parts else "ALL"
            label = []
            if unread:
                label.append("non letti")
            if day:
                label.append(f"data {day}")
            if not label:
                label.append("tutti")
            self._progress(
                on_progress,
                f"IMAP: ricerca messaggi ({', '.join(label)})...",
            )
            typ, data = client.uid("SEARCH", None, criteria)
            if typ != "OK" or not data or not data[0]:
                self._progress(on_progress, "IMAP: nessun messaggio nella cartella.")
                return []
            uids = data[0].split()
            # Più recenti per ultimi
            uids = list(reversed(uids))
            total_uids = len(uids)
            self._progress(
                on_progress,
                f"IMAP: {total_uids} UID trovati — lettura fino a {max(1, limit)} MdA...",
            )
            results: list[ImapMessage] = []
            scanned = 0
            for uid_b in uids:
                if len(results) >= max(1, limit):
                    break
                uid = uid_b.decode() if isinstance(uid_b, bytes) else str(uid_b)
                scanned += 1
                if scanned == 1 or scanned % 5 == 0 or scanned == total_uids:
                    self._progress(
                        on_progress,
                        f"IMAP: lettura mail {scanned}/{total_uids} "
                        f"(MdA trovati: {len(results)})...",
                    )
                msg = self._fetch_uid(client, folder, uid)
                if msg is None:
                    continue
                # Filtro lato client su header Date (ON usa INTERNALDATE)
                if day and msg.message_date and msg.message_date != day:
                    continue
                if only_acquisition:
                    notice = msg.notification
                    if not notice or not (
                        notice.acquisition_module or notice.order_number
                    ):
                        subj_ok = "modulo di acquisizione" in (msg.subject or "").lower()
                        if not subj_ok:
                            continue
                results.append(msg)
            logger.info(
                "IMAP cartella %s: %s messaggi (unread_only=%s, on_date=%s, scanned=%s)",
                folder,
                len(results),
                unread,
                day or "-",
                scanned,
            )
            self._progress(
                on_progress,
                f"IMAP: letti {len(results)} messaggi MdA (scansionati {scanned}).",
            )
            return results
        finally:
            self._safe_logout(client)

    def mark_as_read(self, entry_id: str) -> None:
        if not entry_id or ":" not in entry_id:
            return
        folder, uid = entry_id.rsplit(":", 1)
        client = self._connect()
        try:
            self._select_folder(client, folder)
            client.uid("STORE", uid, "+FLAGS", "(\\Seen)")
        except Exception as exc:
            logger.warning("Mark read fallito per %s: %s", entry_id, exc)
        finally:
            self._safe_logout(client)

    # ------------------------------------------------------------------ internals
    def _fetch_uid(
        self, client: imaplib.IMAP4, folder: str, uid: str
    ) -> Optional[ImapMessage]:
        try:
            typ, data = client.uid("FETCH", uid, "(FLAGS BODY.PEEK[])")
            if typ != "OK" or not data:
                return None
            raw: Optional[bytes] = None
            flags = ""
            for item in data:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                meta = item[0]
                if isinstance(meta, bytes):
                    flags = meta.decode(errors="replace")
                payload = item[1]
                if isinstance(payload, bytes) and len(payload) > 50:
                    raw = payload
            if not raw:
                return None
            msg = email.message_from_bytes(raw, policy=policy.default)
            subject = _decode_header_value(msg.get("Subject"))
            sender = _decode_header_value(msg.get("From"))
            body = _body_from_message(msg)
            notice = parse_notification_text(
                subject=subject, body=body, sender=sender
            )
            unseen = "\\Seen" not in flags
            message_date = _message_date_ymd(msg)
            mid_raw = msg.get("Message-ID") or msg.get("Message-Id") or ""
            message_id = _decode_header_value(str(mid_raw)).strip()
            return ImapMessage(
                uid=uid,
                folder=folder,
                subject=subject,
                sender=sender,
                body=body,
                notification=notice,
                unseen=unseen,
                message_date=message_date,
                message_id=message_id,
            )
        except Exception as exc:
            logger.debug("Lettura UID %s fallita: %s", uid, exc)
            return None

    def _select_folder(self, client: imaplib.IMAP4, folder: str) -> str:
        names = self._list_folder_names(client)
        for candidate in normalize_folder_candidates(folder):
            # Match esatto case-insensitive
            for name in names:
                if name.lower() == candidate.lower():
                    typ, _ = client.select(f'"{name}"', readonly=False)
                    if typ == "OK":
                        return name
            # Prova diretta
            typ, _ = client.select(f'"{candidate}"', readonly=False)
            if typ == "OK":
                return candidate
        # Match per leaf name
        leaf = re.split(r"[./]", (folder or "").strip())[-1].lower()
        if leaf:
            for name in names:
                if name.lower().endswith(leaf) or name.lower().endswith("." + leaf):
                    typ, _ = client.select(f'"{name}"', readonly=False)
                    if typ == "OK":
                        return name
        raise ImapMailError(
            f"Cartella IMAP «{folder}» non trovata.\n"
            "Verificare Impostazioni (es. INBOX.MdA_Eni, Inbox.MdA_Eni, MdA_Eni).\n"
            f"Cartelle disponibili: {', '.join(names[:20])}"
            + ("…" if len(names) > 20 else "")
        )

    @staticmethod
    def _list_folder_names(client: imaplib.IMAP4) -> list[str]:
        """LIST IMAP → nomi cartella leggibili (UTF-7 decodificato)."""
        typ, data = client.list()
        if typ != "OK" or not data:
            return []
        names: list[str] = []
        for line in data:
            if not line:
                continue
            text = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
            # Formato tipico: (\HasNoChildren) "." "INBOX.MdA_Eni"
            # oppure: (\HasNoChildren) "/" INBOX
            m = re.search(r'"((?:\\.|[^"\\])*)"\s*$', text)
            if m:
                raw_name = m.group(1).replace('\\"', '"').replace("\\\\", "\\")
            else:
                parts = text.rsplit(" ", 1)
                if len(parts) != 2 or not parts[1]:
                    continue
                raw_name = parts[1].strip().strip('"')
            if not raw_name or raw_name.upper() == "NIL":
                continue
            decoded = decode_imap_folder_name(raw_name)
            names.append(decoded or raw_name)
        return sort_imap_folders(names)
