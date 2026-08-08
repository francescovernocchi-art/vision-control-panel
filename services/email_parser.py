"""Parser notifiche Marketplace eniSpace.

Esempio oggetto:
  Notifica Modulo di Acquisizione 2013627410 - 4310758365

Esempio corpo:
  Modulo di Acquisizione 2013627410, relativo all'ordine numero 4310758365
  (contratto 2500036209, ...)

Supporta parsing da testo / file .eml e messaggi scaricati via IMAP.
"""

from __future__ import annotations

import email
import re
from dataclasses import dataclass
from email import policy
from pathlib import Path
from typing import Optional


@dataclass
class AcquisitionNotification:
    """Dati estratti dalla mail «Notifica Modulo di Acquisizione»."""

    acquisition_module: str = ""  # Modulo di Acquisizione (doc da scaricare)
    order_number: str = ""  # Ordine (chiave usata su eniSpace / Marketplace)
    contract_number: str = ""  # Contratto quadro
    subject: str = ""
    sender: str = ""
    raw_body: str = ""

    @property
    def is_complete(self) -> bool:
        return bool(self.order_number and self.acquisition_module)

    @property
    def search_key(self) -> str:
        """Chiave primaria di ricerca sul portale: numero ordine."""
        return self.order_number or self.contract_number

    def summary_lines(self) -> list[str]:
        lines = []
        if self.order_number:
            lines.append(f"Ordine:              {self.order_number}")
        if self.contract_number:
            lines.append(f"Contratto:           {self.contract_number}")
        if self.acquisition_module:
            lines.append(f"Modulo acquisizione: {self.acquisition_module}")
        return lines


# Subject: Notifica Modulo di Acquisizione 2013627410 - 4310758365
_SUBJECT_RE = re.compile(
    r"Modulo\s+di\s+Acquisizione\s+(\d+)\s*[-–—]\s*(\d+)",
    re.IGNORECASE,
)

# Body: Modulo di Acquisizione 2013627410
_MODULE_RE = re.compile(
    r"Modulo\s+di\s+Acquisizione\s+(\d+)",
    re.IGNORECASE,
)

# Body: ordine numero 4310758365
_ORDER_RE = re.compile(
    r"ordine\s+numero\s+(\d+)",
    re.IGNORECASE,
)

# Body: (contratto 2500036209, ...)
_CONTRACT_RE = re.compile(
    r"contratto\s+(\d+)",
    re.IGNORECASE,
)


def parse_notification_text(
    *,
    subject: str = "",
    body: str = "",
    sender: str = "",
) -> AcquisitionNotification:
    """Estrae modulo / ordine / contratto da oggetto + corpo testo."""
    result = AcquisitionNotification(subject=subject.strip(), sender=sender.strip())
    text = f"{subject}\n{body}"

    subj_match = _SUBJECT_RE.search(subject)
    if subj_match:
        result.acquisition_module = subj_match.group(1)
        result.order_number = subj_match.group(2)

    mod = _MODULE_RE.search(text)
    if mod:
        result.acquisition_module = result.acquisition_module or mod.group(1)

    order = _ORDER_RE.search(body) or _ORDER_RE.search(text)
    if order:
        result.order_number = result.order_number or order.group(1)

    contract = _CONTRACT_RE.search(body) or _CONTRACT_RE.search(text)
    if contract:
        result.contract_number = contract.group(1)

    result.raw_body = body.strip()
    return result


def _decode_part_payload(part: email.message.Message) -> str:
    try:
        payload = part.get_payload(decode=True)
        if payload is None:
            raw = part.get_payload()
            return raw if isinstance(raw, str) else ""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    except Exception:
        return ""


def parse_eml_file(path: Path | str) -> AcquisitionNotification:
    """Legge un file .eml e restituisce i dati della notifica Marketplace."""
    path = Path(path)
    raw = path.read_bytes()
    msg = email.message_from_bytes(raw, policy=policy.default)

    subject = str(msg.get("Subject", "") or "")
    sender = str(msg.get("From", "") or "")

    body_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                body_parts.append(_decode_part_payload(part))
            elif ctype == "text/html" and not body_parts:
                html = _decode_part_payload(part)
                # Strip grezzo tag HTML
                body_parts.append(re.sub(r"<[^>]+>", " ", html))
    else:
        body_parts.append(_decode_part_payload(msg))

    body = "\n".join(body_parts)
    # Decodifica quoted-printable residua tipica dei forward
    try:
        import quopri

        if "=C3=" in body or "=\n" in body or "=\r\n" in body:
            body = quopri.decodestring(body.encode("latin-1", errors="replace")).decode(
                "utf-8", errors="replace"
            )
    except Exception:
        pass

    result = parse_notification_text(subject=subject, body=body, sender=sender)
    if not result.is_complete:
        # Fallback: prova sul nome file
        # Fwd Notifica Modulo di Acquisizione 2013627410 - 4310758365.eml
        name_match = _SUBJECT_RE.search(path.stem)
        if name_match:
            result.acquisition_module = result.acquisition_module or name_match.group(1)
            result.order_number = result.order_number or name_match.group(2)
    return result


def try_parse_any(text_or_path: str) -> Optional[AcquisitionNotification]:
    """Se il testo è un path .eml esistente lo legge, altrimenti parse testo libero."""
    candidate = Path(text_or_path.strip().strip('"'))
    if candidate.is_file() and candidate.suffix.lower() == ".eml":
        return parse_eml_file(candidate)
    parsed = parse_notification_text(subject=text_or_path, body=text_or_path)
    return parsed if parsed.order_number or parsed.acquisition_module else None
