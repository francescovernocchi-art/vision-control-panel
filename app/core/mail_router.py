"""MailRouter — instrada mail verso moduli con regole configurabili."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from utils.logger import get_logger
from utils.paths import config_dir

logger = get_logger("vision.mail_router")


@dataclass
class MailHints:
    sender: str = ""
    recipients: str = ""
    subject: str = ""
    body_preview: str = ""
    attachment_names: list[str] = field(default_factory=list)
    folder: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class MailRouteDecision:
    module_id: Optional[str]
    action: str  # ROUTE | IGNORE | NEEDS_CLASSIFICATION
    rule_id: str = ""
    reason: str = ""


DEFAULT_RULES = {
    "rules": [
        {
            "id": "enispace_mda",
            "module_id": "enispace",
            "priority": 10,
            "match": {
                "subject_any": [
                    "Modulo di Acquisizione",
                    "MdA",
                    "ordine di acquisto",
                    "Documento di Acquisizione",
                ],
                "sender_any": ["@eni.com", "enispace", "noreply"],
                "folder_any": ["MdA_Eni", "MDA"],
            },
        },
        {
            "id": "coin_transport_sala_conta",
            "module_id": "coin_transport",
            "priority": 20,
            "match": {
                "subject_any": [
                    "Sala Conta",
                    "Trasporto Monete",
                    "trasporto monete",
                    "mezzi monetari",
                ],
                "sender_any": ["sala conta", "salaconta"],
                "attachment_any": [".pdf", ".xlsx", ".xls"],
            },
        },
    ],
    "default_action": "NEEDS_CLASSIFICATION",
}


class MailRouter:
    def __init__(self, rules_path: Optional[Path] = None) -> None:
        self.rules_path = rules_path or (config_dir() / "mail" / "router_rules.json")
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.rules_path.exists():
            self.rules_path.write_text(
                json.dumps(DEFAULT_RULES, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return dict(DEFAULT_RULES)
        try:
            data = json.loads(self.rules_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "rules" not in data:
                return dict(DEFAULT_RULES)
            return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("Regole MailRouter non leggibili (%s) — uso default", exc)
            return dict(DEFAULT_RULES)

    def reload(self) -> None:
        self._config = self._load()

    def route(self, mail: MailHints) -> MailRouteDecision:
        rules = sorted(
            self._config.get("rules") or [],
            key=lambda r: int(r.get("priority", 100)),
        )
        for rule in rules:
            if self._matches(mail, rule.get("match") or {}):
                module_id = rule.get("module_id")
                return MailRouteDecision(
                    module_id=module_id,
                    action="ROUTE" if module_id else "IGNORE",
                    rule_id=str(rule.get("id") or ""),
                    reason=f"Matched rule {rule.get('id')}",
                )
        default = str(self._config.get("default_action") or "NEEDS_CLASSIFICATION")
        if default.upper() == "IGNORE":
            return MailRouteDecision(
                module_id=None, action="IGNORE", reason="Default IGNORE"
            )
        return MailRouteDecision(
            module_id=None,
            action="NEEDS_CLASSIFICATION",
            reason="Nessuna regola corrisponde",
        )

    @staticmethod
    def _haystack(mail: MailHints) -> dict[str, str]:
        atts = " ".join(mail.attachment_names or [])
        return {
            "sender": (mail.sender or "").lower(),
            "recipients": (mail.recipients or "").lower(),
            "subject": (mail.subject or "").lower(),
            "body": (mail.body_preview or "").lower(),
            "folder": (mail.folder or "").lower(),
            "attachments": atts.lower(),
        }

    def _matches(self, mail: MailHints, match: dict[str, Any]) -> bool:
        if not match:
            return False
        h = self._haystack(mail)
        checks: list[bool] = []
        mapping = {
            "subject_any": "subject",
            "sender_any": "sender",
            "recipient_any": "recipients",
            "folder_any": "folder",
            "body_any": "body",
            "attachment_any": "attachments",
        }
        for key, field in mapping.items():
            patterns = match.get(key) or []
            if not patterns:
                continue
            text = h[field]
            checks.append(
                any(str(p).lower() in text for p in patterns if str(p).strip())
            )
        subject_re = match.get("subject_regex")
        if subject_re:
            try:
                checks.append(bool(re.search(subject_re, mail.subject or "", re.I)))
            except re.error:
                checks.append(False)
        if not checks:
            return False
        # OR tra categorie presenti: almeno una categoria deve matchare
        return any(checks)
