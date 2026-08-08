"""PEC builder — prepara ma NON invia automaticamente."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PecDraft:
    subject: str = ""
    body: str = ""
    attachments: list[str] | None = None
    status: str = "PEC PRONTA PER APPROVAZIONE"
    auto_send: bool = False


class PecBuilder:
    def prepare(self, *, subject: str = "", body: str = "", attachments: list[str] | None = None) -> PecDraft:
        return PecDraft(
            subject=subject,
            body=body,
            attachments=list(attachments or []),
            status="PEC PRONTA PER APPROVAZIONE",
            auto_send=False,
        )

    def send(self, draft: PecDraft) -> None:
        raise RuntimeError(
            "Invio PEC disabilitato in questa fase. Richiede APPROVA E INVIA esplicito."
        )
